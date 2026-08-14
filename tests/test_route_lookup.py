"""Tests for utilities/route_lookup.py - multi-provider lookups and FR24 fallback."""

import time
from unittest.mock import MagicMock, patch

import pytest

from utilities.flight import AircraftInfo, RouteInfo

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_route_cache(monkeypatch):
    """Prevent route_cache from hitting disk during tests."""
    import utilities.routes_cache as rc

    monkeypatch.setattr(rc, "_cache", {})
    monkeypatch.setattr(rc, "_loaded", True)
    return rc


@pytest.fixture(autouse=True)
def reset_airport_caches(monkeypatch):
    """Reset module-level airport caches so tests start clean."""
    import utilities.route_providers as rp

    monkeypatch.setattr(rp, "_icao_to_iata", {})
    monkeypatch.setattr(rp, "_icao_to_iata_loaded", False)
    # Reset provider quarantine state.
    monkeypatch.setattr(rp, "_failed_at", {})
    # Reset FR24 miss tracking so tests aren't blocked by a prior call.
    import utilities.route_lookup as rl

    monkeypatch.setattr(rl, "_fr24_miss", {})


# ---------------------------------------------------------------------------
# _parse_route
# ---------------------------------------------------------------------------


class TestParseRoute:
    def test_standard_route(self):

        # _parse_route is now internal to HexdbProvider; test it via the provider
        from utilities.route_providers import HexdbProvider

        p = HexdbProvider()
        assert p._parse_route("EGPF-LEMG") == ("EGPF", "LEMG")

    def test_lowercased(self):
        from utilities.route_providers import HexdbProvider

        p = HexdbProvider()
        assert p._parse_route("egpf-lemg") == ("EGPF", "LEMG")

    def test_no_separator(self):
        from utilities.route_providers import HexdbProvider

        p = HexdbProvider()
        assert p._parse_route("EGPF") == ("", "")

    def test_empty_string(self):
        from utilities.route_providers import HexdbProvider

        p = HexdbProvider()
        assert p._parse_route("") == ("", "")


# ---------------------------------------------------------------------------
# _parse_aircraft_type
# ---------------------------------------------------------------------------


class TestParseAircraftType:
    def test_manufacturer_and_type(self):
        from utilities.route_providers import HexdbProvider

        p = HexdbProvider()
        data = {"Manufacturer": "Airbus", "ICAOTypeCode": "A320"}
        assert p._parse_aircraft_type(data) == "Airbus A320"

    def test_type_only(self):
        from utilities.route_providers import HexdbProvider

        p = HexdbProvider()
        data = {"Manufacturer": "", "ICAOTypeCode": "B738"}
        assert p._parse_aircraft_type(data) == "B738"

    def test_manufacturer_only(self):
        from utilities.route_providers import HexdbProvider

        p = HexdbProvider()
        data = {"Manufacturer": "Boeing", "ICAOTypeCode": ""}
        assert p._parse_aircraft_type(data) == "Boeing"

    def test_missing_fields(self):
        from utilities.route_providers import HexdbProvider

        p = HexdbProvider()
        assert p._parse_aircraft_type({}) == ""


# ---------------------------------------------------------------------------
# _lookup_route - provider chain success (no FR24 fallback needed)
# ---------------------------------------------------------------------------


class TestLookupRouteHexdbSuccess:
    @patch("utilities.route_providers._bundled_airport_info")
    @patch("utilities.route_providers._icao_to_iata_code")
    @patch("utilities.route_providers._session")
    def test_hexdb_returns_route(
        self, mock_session, mock_icao_to_iata, mock_airport_details
    ):
        from utilities.route_lookup import _lookup_route

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"route": "EGPF-LEMG"}
        mock_session.get.return_value = mock_resp

        mock_icao_to_iata.side_effect = lambda icao: {"EGPF": "GLA", "LEMG": "AGP"}.get(
            icao, ""
        )
        mock_airport_details.side_effect = lambda iata: {
            "GLA": {"name": "Glasgow", "municipality": "Glasgow", "country_name": "UK"},
            "AGP": {"name": "Malaga", "municipality": "Malaga", "country_name": "ES"},
        }.get(iata, {})

        result = _lookup_route("BAW123")

        assert result.origin == "GLA"
        assert result.destination == "AGP"
        assert result.origin_name == "Glasgow"
        assert result.destination_name == "Malaga"


# ---------------------------------------------------------------------------
# _lookup_route - provider chain only (FR24 fallback is handled by get_route)
# ---------------------------------------------------------------------------


class TestLookupRouteHexdbOnly:
    """_lookup_route delegates to the provider chain; FR24 fallback lives in get_route."""

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_providers._session")
    def test_hexdb_404_returns_empty_no_fr24(self, mock_session, mock_fr24):
        from utilities.route_lookup import _lookup_route

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_session.get.return_value = mock_resp

        result = _lookup_route("BAW123")

        assert result.origin == ""
        assert result.destination == ""
        mock_fr24.assert_not_called()

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_providers._session")
    def test_hexdb_empty_route_returns_empty_no_fr24(self, mock_session, mock_fr24):
        from utilities.route_lookup import _lookup_route

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"route": ""}
        mock_session.get.return_value = mock_resp

        result = _lookup_route("BAW123")

        assert result.origin == ""
        assert result.destination == ""
        mock_fr24.assert_not_called()

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_providers._icao_to_iata_code")
    @patch("utilities.route_providers._session")
    def test_iata_conversion_failure_returns_empty_no_fr24(
        self, mock_session, mock_icao_to_iata, mock_fr24
    ):
        from utilities.route_lookup import _lookup_route

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"route": "EGPF-LEMG"}
        mock_session.get.return_value = mock_resp

        mock_icao_to_iata.return_value = ""

        result = _lookup_route("BAW123")

        assert result.origin == ""
        assert result.destination == ""
        mock_fr24.assert_not_called()

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_providers._icao_to_iata_code")
    @patch("utilities.route_providers._session")
    def test_hexdb_success_returns_route_no_fr24(
        self, mock_session, mock_icao_to_iata, mock_fr24
    ):
        from utilities.route_lookup import _lookup_route

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"route": "EGPF-LEMG"}
        mock_session.get.return_value = mock_resp

        mock_icao_to_iata.side_effect = lambda icao: {"EGPF": "GLA", "LEMG": "AGP"}.get(
            icao, ""
        )

        result = _lookup_route("BAW123")

        assert result.origin == "GLA"
        assert result.destination == "AGP"
        mock_fr24.assert_not_called()


# ---------------------------------------------------------------------------
# _lookup_route - stale cache fallback (expired entry reused when providers fail)
# ---------------------------------------------------------------------------


class TestLookupRouteStaleFallback:
    """When providers return nothing, fall back to a recently-expired cache entry."""

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_providers._session")
    def test_stale_entry_reused_when_providers_fail(self, mock_session, mock_fr24):
        import utilities.routes_cache as rc
        from utilities.route_lookup import _lookup_route

        # Seed an expired cache entry (25h old, within 7-day stale threshold)
        rc.put("BAW123", {"origin": "LHR", "destination": "GLA"})
        rc._cache["BAW123"]["_ts"] = time.time() - rc.CACHE_TTL - 1

        # Providers return 404
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_session.get.return_value = mock_resp

        result = _lookup_route("BAW123")

        assert result.origin == "LHR"
        assert result.destination == "GLA"
        # FR24 not called - stale data fills the gap
        mock_fr24.assert_not_called()

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_providers._session")
    def test_stale_entry_recached_with_advanced_ts(self, mock_session, mock_fr24):
        import utilities.routes_cache as rc
        from utilities.route_lookup import _lookup_route

        # Seed an expired cache entry
        rc.put("BAW123", {"origin": "LHR", "destination": "GLA"})
        original_ts = time.time() - rc.CACHE_TTL - 1
        rc._cache["BAW123"]["_ts"] = original_ts

        # Providers return 404
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_session.get.return_value = mock_resp

        _lookup_route("BAW123")

        # Entry should be re-cached with ts advanced by 4h, not reset to now
        new_ts = rc._cache["BAW123"]["_ts"]
        expected_ts = original_ts + rc.STALE_RECACHE_ADVANCE
        assert new_ts == expected_ts

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_providers._session")
    def test_no_stale_entry_caches_miss(self, mock_session, mock_fr24):
        import utilities.routes_cache as rc
        from utilities.route_lookup import _lookup_route

        # No cache entry at all
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_session.get.return_value = mock_resp

        result = _lookup_route("BAW123")

        assert result.origin == ""
        assert result.destination == ""
        # Should have cached a miss entry
        assert rc._cache["BAW123"].get("miss") is True

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_providers._session")
    def test_stale_entry_past_7_days_not_reused(self, mock_session, mock_fr24):
        import utilities.routes_cache as rc
        from utilities.route_lookup import _lookup_route

        # Seed a cache entry older than 7 days
        rc.put("BAW123", {"origin": "LHR", "destination": "GLA"})
        rc._cache["BAW123"]["_ts"] = time.time() - rc.CACHE_TTL_STALE - 1

        # Providers return 404
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_session.get.return_value = mock_resp

        result = _lookup_route("BAW123")

        assert result.origin == ""
        assert result.destination == ""
        # Should have cached a miss, not reused the too-old entry
        assert rc._cache["BAW123"].get("miss") is True

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_providers._session")
    def test_stale_miss_entry_not_reused(self, mock_session, mock_fr24):
        import utilities.routes_cache as rc
        from utilities.route_lookup import _lookup_route

        # Seed an expired miss entry
        rc.put("BAW123", {"miss": True}, ttl=rc.CACHE_TTL_MISS)
        rc._cache["BAW123"]["_ts"] = time.time() - rc.CACHE_TTL - 1

        # Providers return 404
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_session.get.return_value = mock_resp

        result = _lookup_route("BAW123")

        # Miss entries are not eligible for stale fallback
        assert result.origin == ""
        assert result.destination == ""


# ---------------------------------------------------------------------------
# _fr24_fallback (unified route + aircraft fallback, bounds + callsign keyed)
# ---------------------------------------------------------------------------


# Position/speed used across the _fr24_fallback direct tests.
_LAT = 51.5
_LNG = -0.45
_SPEED_MPS = 250.0  # ~486 kt -> radius = min(20000, max(1000, 7500)) = 7500


class TestFr24Fallback:
    """Direct tests of the unified _fr24_fallback(callsign, lat, lng, speed, want_plane)."""

    def test_blank_callsign_returns_empty(self):
        from utilities.route_lookup import _fr24_fallback

        result = _fr24_fallback("", _LAT, _LNG, _SPEED_MPS)
        assert result.origin == ""
        assert result.destination == ""
        assert result.plane == ""

    def test_missing_position_returns_empty(self):
        from utilities.route_lookup import _fr24_fallback

        # No lat/lng -> can't build a bubble
        result = _fr24_fallback("BAW123", None, None, _SPEED_MPS)
        assert result.origin == ""
        assert result.destination == ""
        assert result.plane == ""

    @patch("utilities.route_lookup._enrich_route_names_helper")
    @patch("FlightRadar24.api.FlightRadar24API")
    def test_matching_flight_found_route_only(self, mock_api_cls, mock_airport_details):
        from utilities.route_lookup import _fr24_fallback

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        mock_tracker = MagicMock()
        mock_api.get_flight_tracker_config.return_value = mock_tracker

        mock_flight = MagicMock()
        mock_flight.callsign = "BAW123"
        mock_flight.origin_airport_iata = "LHR"
        mock_flight.destination_airport_iata = "GLA"
        mock_flight.aircraft_code = "B738"
        mock_api.get_flights.return_value = [mock_flight]

        mock_airport_details.side_effect = lambda iata: {
            "LHR": {
                "name": "London Heathrow",
                "municipality": "London",
                "country_name": "UK",
            },
            "GLA": {"name": "Glasgow", "municipality": "Glasgow", "country_name": "UK"},
        }.get(iata, {})

        # want_plane=False (default) - route only, no details call
        result = _fr24_fallback("BAW123", _LAT, _LNG, _SPEED_MPS)

        assert result.origin == "LHR"
        assert result.destination == "GLA"
        assert result.origin_name == "London Heathrow"
        assert result.destination_name == "Glasgow"
        assert result.plane == ""
        mock_api.get_flight_details.assert_not_called()

        # Verify a bounds query was used (not registration/airline)
        mock_api.get_flights.assert_called_once()
        assert mock_api.get_flights.call_args.kwargs.get("bounds") is not None
        # Verify the bounds bubble was built from the position
        mock_api.get_bounds_by_point.assert_called_once()
        call_args = mock_api.get_bounds_by_point.call_args
        assert call_args.args[0] == _LAT
        assert call_args.args[1] == _LNG
        # radius scaled by speed: min(20000, max(1000, 250*30)) = 7500
        assert call_args.args[2] == 7500

    @patch("FlightRadar24.api.FlightRadar24API")
    def test_no_matching_callsign_in_bubble(self, mock_api_cls):
        from utilities.route_lookup import _fr24_fallback

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        mock_flight = MagicMock()
        mock_flight.callsign = "BAW999"  # different callsign
        mock_flight.origin_airport_iata = "LHR"
        mock_flight.destination_airport_iata = "JFK"
        mock_api.get_flights.return_value = [mock_flight]

        result = _fr24_fallback("BAW123", _LAT, _LNG, _SPEED_MPS)

        assert result.origin == ""
        assert result.destination == ""
        assert result.plane == ""

    @patch("FlightRadar24.api.FlightRadar24API")
    def test_matching_flight_no_route_no_plane(self, mock_api_cls):
        from utilities.route_lookup import _fr24_fallback

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        mock_flight = MagicMock()
        mock_flight.callsign = "BAW123"
        mock_flight.origin_airport_iata = ""
        mock_flight.destination_airport_iata = ""
        mock_flight.aircraft_code = ""
        mock_api.get_flights.return_value = [mock_flight]

        # want_plane=False, no route data -> nothing to return
        result = _fr24_fallback("BAW123", _LAT, _LNG, _SPEED_MPS)

        assert result.origin == ""
        assert result.destination == ""
        assert result.plane == ""

    @patch("FlightRadar24.api.FlightRadar24API")
    def test_api_exception_returns_empty(self, mock_api_cls):
        from utilities.route_lookup import _fr24_fallback

        mock_api_cls.side_effect = Exception("FR24 unavailable")

        result = _fr24_fallback("BAW123", _LAT, _LNG, _SPEED_MPS)

        assert result.origin == ""
        assert result.destination == ""
        assert result.plane == ""

    @patch("FlightRadar24.api.FlightRadar24API")
    def test_get_flights_exception_returns_empty(self, mock_api_cls):
        from utilities.route_lookup import _fr24_fallback

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.get_flights.side_effect = Exception("Network error")

        result = _fr24_fallback("BAW123", _LAT, _LNG, _SPEED_MPS)

        assert result.origin == ""
        assert result.destination == ""
        assert result.plane == ""

    @patch("FlightRadar24.api.FlightRadar24API")
    def test_ground_traffic_excluded(self, mock_api_cls):
        from utilities.route_lookup import _fr24_fallback

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        mock_tracker = MagicMock()
        mock_tracker.gnd = "1"  # default
        mock_api.get_flight_tracker_config.return_value = mock_tracker

        mock_flight = MagicMock()
        mock_flight.callsign = "BAW123"
        mock_flight.origin_airport_iata = "LHR"
        mock_flight.destination_airport_iata = "GLA"
        mock_flight.aircraft_code = ""
        mock_api.get_flights.return_value = [mock_flight]

        _fr24_fallback("BAW123", _LAT, _LNG, _SPEED_MPS)

        # Verify gnd was set to 0
        assert mock_tracker.gnd == 0
        mock_api.set_flight_tracker_config.assert_called_once_with(mock_tracker)

    @patch("FlightRadar24.api.FlightRadar24API")
    def test_slow_aircraft_uses_baseline_radius(self, mock_api_cls):
        from utilities.route_lookup import _fr24_fallback

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.get_flights.return_value = []

        # 0 m/s -> radius = max(1000, 0) = 1000 (baseline)
        _fr24_fallback("BAW123", _LAT, _LNG, 0.0)

        call_args = mock_api.get_bounds_by_point.call_args
        assert call_args.args[2] == 1000

    # -- want_plane=True cases (aircraft details via get_flight_details) --------

    @patch("FlightRadar24.api.FlightRadar24API")
    def test_want_plane_full_model_name(self, mock_api_cls):
        from utilities.route_lookup import _fr24_fallback

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        mock_flight = MagicMock()
        mock_flight.callsign = "BAW123"
        mock_flight.origin_airport_iata = "LHR"
        mock_flight.destination_airport_iata = "GLA"
        mock_flight.aircraft_code = "B738"
        mock_api.get_flights.return_value = [mock_flight]
        mock_api.get_flight_details.return_value = {
            "aircraft": {"model": {"text": "Boeing 737-800"}}
        }

        result = _fr24_fallback("BAW123", _LAT, _LNG, _SPEED_MPS, want_plane=True)

        assert result.plane == "Boeing 737-800"
        assert result.origin == "LHR"
        assert result.destination == "GLA"
        mock_api.get_flight_details.assert_called_once_with(mock_flight)

    @patch("utilities.route_lookup.FR24_DETAIL_DELAY", 0)
    @patch("FlightRadar24.api.FlightRadar24API")
    def test_want_plane_details_fail_falls_back_to_aircraft_code(self, mock_api_cls):
        from utilities.route_lookup import _fr24_fallback

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        mock_flight = MagicMock()
        mock_flight.callsign = "BAW123"
        mock_flight.origin_airport_iata = ""
        mock_flight.destination_airport_iata = ""
        mock_flight.aircraft_code = "B737"
        mock_api.get_flights.return_value = [mock_flight]
        # All get_flight_details attempts raise
        mock_api.get_flight_details.side_effect = KeyError("no details")

        result = _fr24_fallback("BAW123", _LAT, _LNG, _SPEED_MPS, want_plane=True)

        # Details call failed -> fall back to the free aircraft_code
        assert result.plane == "B737"
        assert result.origin == ""
        assert result.destination == ""
        # Retried up to FR24_DETAIL_RETRIES times
        assert mock_api.get_flight_details.call_count == 3

    @patch("utilities.route_lookup.FR24_DETAIL_DELAY", 0)
    @patch("FlightRadar24.api.FlightRadar24API")
    def test_want_plane_details_fail_and_no_aircraft_code(self, mock_api_cls):
        from utilities.route_lookup import _fr24_fallback

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        mock_flight = MagicMock()
        mock_flight.callsign = "BAW123"
        mock_flight.origin_airport_iata = ""
        mock_flight.destination_airport_iata = ""
        mock_flight.aircraft_code = ""
        mock_api.get_flights.return_value = [mock_flight]
        mock_api.get_flight_details.side_effect = Exception("timeout")

        result = _fr24_fallback("BAW123", _LAT, _LNG, _SPEED_MPS, want_plane=True)

        # Both details and aircraft_code empty -> plane stays blank
        assert result.plane == ""
        assert result.origin == ""
        assert result.destination == ""

    @patch("FlightRadar24.api.FlightRadar24API")
    def test_want_plane_details_no_model_text_falls_back_to_aircraft_code(
        self, mock_api_cls
    ):
        from utilities.route_lookup import _fr24_fallback

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        mock_flight = MagicMock()
        mock_flight.callsign = "BAW123"
        mock_flight.origin_airport_iata = ""
        mock_flight.destination_airport_iata = ""
        mock_flight.aircraft_code = "A320"
        mock_api.get_flights.return_value = [mock_flight]
        # Details returned but no model text
        mock_api.get_flight_details.return_value = {"aircraft": {}}

        result = _fr24_fallback("BAW123", _LAT, _LNG, _SPEED_MPS, want_plane=True)

        assert result.plane == "A320"

    @patch("FlightRadar24.api.FlightRadar24API")
    def test_want_plane_false_skips_details_call(self, mock_api_cls):
        from utilities.route_lookup import _fr24_fallback

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        mock_flight = MagicMock()
        mock_flight.callsign = "BAW123"
        mock_flight.origin_airport_iata = "LHR"
        mock_flight.destination_airport_iata = "GLA"
        mock_flight.aircraft_code = "B738"
        mock_api.get_flights.return_value = [mock_flight]

        result = _fr24_fallback("BAW123", _LAT, _LNG, _SPEED_MPS, want_plane=False)

        assert result.plane == ""
        mock_api.get_flight_details.assert_not_called()


# ---------------------------------------------------------------------------
# get_route - integration of route + aircraft lookups + unified FR24 fallback
# ---------------------------------------------------------------------------


# Position/speed used across the TestGetRoute trigger tests.
_RT_LAT = 51.5
_RT_LNG = -0.45
_RT_SPEED = 250.0


class TestGetRoute:
    """get_route runs hexdb lookups then a single unified FR24 fallback.

    The FR24 fallback is bounds+callsign keyed: it fires when route OR plane is
    missing AND a callsign + lat/lng are available.  ``_lookup_aircraft``
    returns an ``AircraftInfo`` (plane, registration, operator_icao) and runs
    whenever the plane **or** the airline is still unknown.

    The FR24 fallback is patched to a no-op (empty RouteInfo) by default so the
    existing hexdb-merge tests are unaffected; dedicated tests below verify the
    trigger conditions and merging.
    """

    @patch("utilities.route_lookup._fr24_fallback", return_value=RouteInfo())
    @patch("utilities.route_lookup._lookup_aircraft")
    @patch("utilities.route_lookup._lookup_route")
    def test_combines_route_and_aircraft(
        self, mock_lookup_route, mock_lookup_aircraft, mock_fr24
    ):
        from utilities.route_lookup import get_route

        mock_lookup_route.return_value = RouteInfo(origin="LHR", destination="GLA")
        mock_lookup_aircraft.return_value = AircraftInfo("Airbus A320", "G-ABCD")

        result = get_route(
            "BAW123",
            mode_s="a1b2c3",
            lat=_RT_LAT,
            lng=_RT_LNG,
            ground_speed_mps=_RT_SPEED,
        )

        assert result.origin == "LHR"
        assert result.destination == "GLA"
        assert result.plane == "Airbus A320"
        assert result.registration == "G-ABCD"
        # Both route and plane resolved by hexdb -> FR24 not called
        mock_fr24.assert_not_called()

    @patch("utilities.route_lookup._fr24_fallback", return_value=RouteInfo())
    @patch("utilities.route_lookup._lookup_aircraft")
    @patch("utilities.route_lookup._lookup_route")
    def test_route_plane_not_overwritten_by_aircraft_lookup(
        self, mock_lookup_route, mock_lookup_aircraft, mock_fr24
    ):
        """A plane from the route lookup survives the mode_s lookup.

        The mode_s lookup still runs - it is the only source of
        ``operator_icao`` - but must not clobber a plane the route lookup
        already resolved.
        """
        from utilities.route_lookup import get_route

        mock_lookup_route.return_value = RouteInfo(
            origin="LHR", destination="GLA", plane="B738"
        )
        mock_lookup_aircraft.return_value = AircraftInfo("Airbus A320", "G-ABCD", "EIN")

        result = get_route(
            "BAW123",
            mode_s="a1b2c3",
            lat=_RT_LAT,
            lng=_RT_LNG,
            ground_speed_mps=_RT_SPEED,
        )

        assert result.plane == "B738"
        assert result.operator_icao == "EIN"
        mock_fr24.assert_not_called()

    @patch("utilities.route_lookup._fr24_fallback", return_value=RouteInfo())
    @patch("utilities.route_lookup._lookup_aircraft")
    @patch("utilities.route_lookup._lookup_route")
    def test_no_aircraft_lookup_when_plane_and_airline_known(
        self, mock_lookup_route, mock_lookup_aircraft, mock_fr24
    ):
        """Nothing left to resolve -> the mode_s lookup is skipped entirely."""
        from utilities.route_lookup import get_route

        mock_lookup_route.return_value = RouteInfo(
            origin="LHR", destination="GLA", plane="B738", airline_icao="BAW"
        )

        result = get_route(
            "BAW123",
            mode_s="a1b2c3",
            lat=_RT_LAT,
            lng=_RT_LNG,
            ground_speed_mps=_RT_SPEED,
        )

        assert result.plane == "B738"
        mock_lookup_aircraft.assert_not_called()
        mock_fr24.assert_not_called()

    @patch("utilities.route_lookup._fr24_fallback", return_value=RouteInfo())
    @patch("utilities.route_lookup._lookup_aircraft")
    @patch("utilities.route_lookup._lookup_route")
    def test_no_callsign_skips_route_and_fr24(
        self, mock_lookup_route, mock_lookup_aircraft, mock_fr24
    ):
        from utilities.route_lookup import get_route

        mock_lookup_aircraft.return_value = AircraftInfo("A320", "G-ABCD")

        result = get_route(
            "", mode_s="a1b2c3", lat=_RT_LAT, lng=_RT_LNG, ground_speed_mps=_RT_SPEED
        )

        assert result.plane == "A320"
        mock_lookup_route.assert_not_called()
        # No callsign -> can't disambiguate in the bubble -> FR24 not called
        mock_fr24.assert_not_called()

    @patch("utilities.route_lookup._fr24_fallback", return_value=RouteInfo())
    @patch("utilities.route_lookup._lookup_route")
    def test_no_mode_s_skips_aircraft(self, mock_lookup_route, mock_fr24):
        from utilities.route_lookup import get_route

        mock_lookup_route.return_value = RouteInfo(origin="LHR", destination="GLA")

        result = get_route(
            "BAW123", lat=_RT_LAT, lng=_RT_LNG, ground_speed_mps=_RT_SPEED
        )

        assert result.origin == "LHR"
        assert result.destination == "GLA"

    # -- unified FR24 fallback trigger conditions ------------------------------

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_lookup._lookup_aircraft")
    @patch("utilities.route_lookup._lookup_route")
    def test_route_and_plane_miss_triggers_fr24_want_plane_true(
        self, mock_lookup_route, mock_lookup_aircraft, mock_fr24
    ):
        from utilities.route_lookup import get_route

        mock_lookup_route.return_value = RouteInfo()  # hexdb route miss
        mock_lookup_aircraft.return_value = AircraftInfo("", "G-ABCD")  # plane miss
        mock_fr24.return_value = RouteInfo(
            origin="LHR", destination="GLA", plane="Boeing 737-800"
        )

        result = get_route(
            "BAW123",
            mode_s="a1b2c3",
            lat=_RT_LAT,
            lng=_RT_LNG,
            ground_speed_mps=_RT_SPEED,
        )

        assert result.origin == "LHR"
        assert result.destination == "GLA"
        assert result.plane == "Boeing 737-800"
        mock_fr24.assert_called_once_with(
            "BAW123", _RT_LAT, _RT_LNG, _RT_SPEED, want_plane=True
        )

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_lookup._lookup_aircraft")
    @patch("utilities.route_lookup._lookup_route")
    def test_route_miss_plane_hit_triggers_fr24_want_plane_false(
        self, mock_lookup_route, mock_lookup_aircraft, mock_fr24
    ):
        from utilities.route_lookup import get_route

        # hexdb route miss, but hexdb aircraft hit -> plane already known
        mock_lookup_route.return_value = RouteInfo()
        mock_lookup_aircraft.return_value = AircraftInfo("Airbus A320", "G-ABCD")
        mock_fr24.return_value = RouteInfo(origin="LHR", destination="GLA")

        result = get_route(
            "BAW123",
            mode_s="a1b2c3",
            lat=_RT_LAT,
            lng=_RT_LNG,
            ground_speed_mps=_RT_SPEED,
        )

        assert result.origin == "LHR"
        assert result.destination == "GLA"
        assert result.plane == "Airbus A320"  # from hexdb, not overwritten
        # want_plane=False because hexdb already gave a plane
        mock_fr24.assert_called_once_with(
            "BAW123", _RT_LAT, _RT_LNG, _RT_SPEED, want_plane=False
        )

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_lookup._lookup_aircraft")
    @patch("utilities.route_lookup._lookup_route")
    def test_route_hit_plane_miss_triggers_fr24_want_plane_true(
        self, mock_lookup_route, mock_lookup_aircraft, mock_fr24
    ):
        from utilities.route_lookup import get_route

        # hexdb route hit, hexdb aircraft miss (plane blank)
        mock_lookup_route.return_value = RouteInfo(origin="LHR", destination="GLA")
        mock_lookup_aircraft.return_value = AircraftInfo("", "G-ABCD")
        mock_fr24.return_value = RouteInfo(plane="Boeing 737-800")

        result = get_route(
            "BAW123",
            mode_s="a1b2c3",
            lat=_RT_LAT,
            lng=_RT_LNG,
            ground_speed_mps=_RT_SPEED,
        )

        assert result.origin == "LHR"  # from hexdb, not overwritten
        assert result.destination == "GLA"
        assert result.plane == "Boeing 737-800"  # from FR24
        mock_fr24.assert_called_once_with(
            "BAW123", _RT_LAT, _RT_LNG, _RT_SPEED, want_plane=True
        )

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_lookup._lookup_aircraft")
    @patch("utilities.route_lookup._lookup_route")
    def test_both_hit_skips_fr24(
        self, mock_lookup_route, mock_lookup_aircraft, mock_fr24
    ):
        from utilities.route_lookup import get_route

        mock_lookup_route.return_value = RouteInfo(origin="LHR", destination="GLA")
        mock_lookup_aircraft.return_value = AircraftInfo("Airbus A320", "G-ABCD")

        result = get_route(
            "BAW123",
            mode_s="a1b2c3",
            lat=_RT_LAT,
            lng=_RT_LNG,
            ground_speed_mps=_RT_SPEED,
        )

        assert result.origin == "LHR"
        assert result.destination == "GLA"
        assert result.plane == "Airbus A320"
        mock_fr24.assert_not_called()

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_lookup._lookup_aircraft")
    @patch("utilities.route_lookup._lookup_route")
    def test_no_position_skips_fr24(
        self, mock_lookup_route, mock_lookup_aircraft, mock_fr24
    ):
        from utilities.route_lookup import get_route

        # hexdb route+plane miss, but no lat/lng -> can't build a bubble
        mock_lookup_route.return_value = RouteInfo()
        mock_lookup_aircraft.return_value = AircraftInfo("", "")

        result = get_route("BAW123", mode_s="a1b2c3")  # no lat/lng/speed

        assert result.origin == ""
        assert result.destination == ""
        assert result.plane == ""
        mock_fr24.assert_not_called()

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_lookup._lookup_aircraft")
    @patch("utilities.route_lookup._lookup_route")
    def test_blank_callsign_skips_fr24(
        self, mock_lookup_route, mock_lookup_aircraft, mock_fr24
    ):
        from utilities.route_lookup import get_route

        # No callsign -> can't disambiguate in the bubble
        mock_lookup_route.return_value = RouteInfo()
        mock_lookup_aircraft.return_value = AircraftInfo("", "")

        result = get_route(
            "", mode_s="a1b2c3", lat=_RT_LAT, lng=_RT_LNG, ground_speed_mps=_RT_SPEED
        )

        assert result.origin == ""
        assert result.plane == ""
        mock_fr24.assert_not_called()

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_lookup._lookup_aircraft")
    @patch("utilities.route_lookup._lookup_route")
    def test_fr24_plane_cached_under_mode_s_key(
        self, mock_lookup_route, mock_lookup_aircraft, mock_fr24
    ):
        import utilities.routes_cache as rc
        from utilities.route_lookup import get_route

        mock_lookup_route.return_value = RouteInfo()  # route miss
        mock_lookup_aircraft.return_value = AircraftInfo(
            "", "G-ABCD"
        )  # plane miss, reg present
        mock_fr24.return_value = RouteInfo(plane="Boeing 737-800")  # plane only

        result = get_route(
            "BAW123",
            mode_s="a1b2c3",
            lat=_RT_LAT,
            lng=_RT_LNG,
            ground_speed_mps=_RT_SPEED,
        )

        assert result.plane == "Boeing 737-800"
        # Plane + registration cached under the mode_s key so subsequent polls
        # skip FR24 entirely
        assert rc.get("a1b2c3") == {
            "plane": "Boeing 737-800",
            "registration": "G-ABCD",
            "operator_icao": "",
            "owner": "",
        }


# ---------------------------------------------------------------------------
# _lookup_aircraft - stale cache fallback
# ---------------------------------------------------------------------------


class TestLookupAircraftStaleFallback:
    """When providers return nothing, fall back to a recently-expired cache entry."""

    @patch("utilities.route_providers._session")
    def test_stale_entry_reused_when_providers_fail(self, mock_session):
        import utilities.routes_cache as rc
        from utilities.route_lookup import _lookup_aircraft

        # Seed an expired cache entry (25h old, within 7-day stale threshold)
        rc.put("a1b2c3", {"plane": "Airbus A320", "registration": "G-ABCD"})
        rc._cache["a1b2c3"]["_ts"] = time.time() - rc.CACHE_TTL - 1

        # Providers return 404
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_session.get.return_value = mock_resp

        info = _lookup_aircraft("a1b2c3")

        assert info.plane == "Airbus A320"
        assert info.registration == "G-ABCD"

    @patch("utilities.route_providers._session")
    def test_stale_entry_recached_with_advanced_ts(self, mock_session):
        import utilities.routes_cache as rc
        from utilities.route_lookup import _lookup_aircraft

        rc.put("a1b2c3", {"plane": "Airbus A320", "registration": "G-ABCD"})
        original_ts = time.time() - rc.CACHE_TTL - 1
        rc._cache["a1b2c3"]["_ts"] = original_ts

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_session.get.return_value = mock_resp

        _lookup_aircraft("a1b2c3")

        new_ts = rc._cache["a1b2c3"]["_ts"]
        expected_ts = original_ts + rc.STALE_RECACHE_ADVANCE
        assert new_ts == expected_ts

    @patch("utilities.route_providers._session")
    def test_no_stale_entry_caches_empty(self, mock_session):
        import utilities.routes_cache as rc
        from utilities.route_lookup import _lookup_aircraft

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_session.get.return_value = mock_resp

        info = _lookup_aircraft("a1b2c3")

        assert info.plane == ""
        assert info.registration == ""
        # Should have cached an empty entry
        assert rc._cache["a1b2c3"]["plane"] == ""

    @patch("utilities.route_providers._session")
    def test_stale_entry_past_7_days_not_reused(self, mock_session):
        import utilities.routes_cache as rc
        from utilities.route_lookup import _lookup_aircraft

        rc.put("a1b2c3", {"plane": "Airbus A320", "registration": "G-ABCD"})
        rc._cache["a1b2c3"]["_ts"] = time.time() - rc.CACHE_TTL_STALE - 1

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_session.get.return_value = mock_resp

        info = _lookup_aircraft("a1b2c3")

        assert info.plane == ""
        assert info.registration == ""


# ---------------------------------------------------------------------------
# Operator ICAO code (Mode S hex -> registered operator)
# ---------------------------------------------------------------------------


class TestCleanOperatorCode:
    """Provider operator-flag fields are free-form; only 3-letter codes count."""

    def test_valid_code(self):
        from utilities.route_providers import clean_operator_code

        assert clean_operator_code("ein") == "EIN"

    def test_strips_whitespace(self):
        from utilities.route_providers import clean_operator_code

        assert clean_operator_code("  BAW  ") == "BAW"

    def test_rejects_wrong_length(self):
        from utilities.route_providers import clean_operator_code

        assert clean_operator_code("EI") == ""
        assert clean_operator_code("EINX") == ""

    def test_rejects_non_alpha(self):
        from utilities.route_providers import clean_operator_code

        assert clean_operator_code("E1N") == ""

    def test_rejects_blank_and_none(self):
        from utilities.route_providers import clean_operator_code

        assert clean_operator_code("") == ""
        assert clean_operator_code(None) == ""


class TestHexdbParseOperatorIcao:
    def test_operator_flag_code(self):
        from utilities.route_providers import HexdbProvider

        p = HexdbProvider()
        assert p._parse_operator_icao({"OperatorFlagCode": "EIN"}) == "EIN"

    def test_missing_field(self):
        from utilities.route_providers import HexdbProvider

        p = HexdbProvider()
        assert p._parse_operator_icao({}) == ""

    def test_malformed_field_rejected(self):
        from utilities.route_providers import HexdbProvider

        p = HexdbProvider()
        assert p._parse_operator_icao({"OperatorFlagCode": "G-ABCD"}) == ""


class TestLookupAircraftChain:
    """route_providers.lookup_aircraft merges operator codes across providers."""

    def test_operator_only_provider_does_not_stop_chain(self):
        import utilities.route_providers as rp
        from utilities.flight import AircraftInfo

        first = MagicMock()
        first.lookup_aircraft.return_value = AircraftInfo(operator_icao="EIN")
        second = MagicMock()
        second.lookup_aircraft.return_value = AircraftInfo("Airbus A320", "G-ABCD")

        with patch.object(rp, "available_providers", return_value=[first, second]):
            info = rp.lookup_aircraft("a1b2c3")

        assert info.plane == "Airbus A320"
        assert info.registration == "G-ABCD"
        # Operator from the first provider is carried through
        assert info.operator_icao == "EIN"

    def test_first_hit_wins_for_operator_too(self):
        import utilities.route_providers as rp
        from utilities.flight import AircraftInfo

        first = MagicMock()
        first.lookup_aircraft.return_value = AircraftInfo("A320", "G-ABCD", "EIN")
        second = MagicMock()

        with patch.object(rp, "available_providers", return_value=[first, second]):
            info = rp.lookup_aircraft("a1b2c3")

        assert info.operator_icao == "EIN"
        second.lookup_aircraft.assert_not_called()

    def test_all_empty(self):
        import utilities.route_providers as rp
        from utilities.flight import AircraftInfo

        provider = MagicMock()
        provider.lookup_aircraft.return_value = AircraftInfo()

        with patch.object(rp, "available_providers", return_value=[provider]):
            info = rp.lookup_aircraft("a1b2c3")

        assert not info


class TestOperatorIcaoCaching:
    """operator_icao belongs to the airframe, not the flight."""

    @patch("utilities.route_lookup._fr24_fallback", return_value=RouteInfo())
    @patch("utilities.route_lookup._lookup_aircraft")
    @patch("utilities.route_lookup._lookup_route")
    def test_operator_icao_not_stored_under_callsign_key(
        self, mock_lookup_route, mock_lookup_aircraft, mock_fr24
    ):
        import utilities.routes_cache as rc
        from utilities.route_lookup import get_route

        mock_lookup_route.return_value = RouteInfo(origin="LHR", destination="GLA")
        mock_lookup_aircraft.return_value = AircraftInfo("A320", "G-ABCD", "EIN")

        result = get_route("EAG56R", mode_s="a1b2c3")

        assert result.operator_icao == "EIN"
        # ...but the callsign cache entry must not carry it, or tomorrow's
        # airframe on the same flight number would inherit today's operator.
        assert "operator_icao" not in rc.get("EAG56R")

    @patch("utilities.route_providers.lookup_aircraft")
    def test_operator_icao_round_trips_through_mode_s_cache(self, mock_lookup):
        from utilities.route_lookup import _lookup_aircraft

        mock_lookup.return_value = AircraftInfo("A320", "G-ABCD", "EIN")

        first = _lookup_aircraft("a1b2c3")
        second = _lookup_aircraft("a1b2c3")  # served from cache

        assert first.operator_icao == "EIN"
        assert second.operator_icao == "EIN"
        mock_lookup.assert_called_once()

    @patch("utilities.route_providers.lookup_aircraft")
    def test_legacy_cache_entry_without_operator_icao(self, mock_lookup):
        """Entries written before operator_icao existed must not blow up."""
        import utilities.routes_cache as rc
        from utilities.route_lookup import _lookup_aircraft

        rc.put("a1b2c3", {"plane": "Airbus A320", "registration": "G-ABCD"})

        info = _lookup_aircraft("a1b2c3")

        assert info.plane == "Airbus A320"
        assert info.operator_icao == ""
        mock_lookup.assert_not_called()


class TestOwnerLookup:
    """Registered owner name - the only identity a GA aircraft has."""

    def test_hexdb_parses_registered_owners(self):
        from utilities.route_providers import HexdbProvider

        p = HexdbProvider()
        assert (
            p._parse_owner({"RegisteredOwners": "Leading Edge Flight Training"})
            == "Leading Edge Flight Training"
        )

    def test_hexdb_owner_missing(self):
        from utilities.route_providers import HexdbProvider

        p = HexdbProvider()
        assert p._parse_owner({}) == ""

    def test_owner_carried_from_earlier_provider(self):
        import utilities.route_providers as rp

        first = MagicMock()
        first.lookup_aircraft.return_value = AircraftInfo(owner="Flying Club")
        second = MagicMock()
        second.lookup_aircraft.return_value = AircraftInfo("C172", "G-BSFE")

        with patch.object(rp, "available_providers", return_value=[first, second]):
            info = rp.lookup_aircraft("400f5a")

        assert info.registration == "G-BSFE"
        assert info.owner == "Flying Club"

    @patch("utilities.route_providers.lookup_aircraft")
    def test_owner_round_trips_through_mode_s_cache(self, mock_lookup):
        from utilities.route_lookup import _lookup_aircraft

        mock_lookup.return_value = AircraftInfo(
            "Cessna C172", "G-BSFE", "", "Leading Edge Flight Training"
        )

        _lookup_aircraft("400f5a")
        cached = _lookup_aircraft("400f5a")

        assert cached.owner == "Leading Edge Flight Training"
        mock_lookup.assert_called_once()

    @patch("utilities.route_lookup._fr24_fallback", return_value=RouteInfo())
    @patch("utilities.route_lookup._lookup_aircraft")
    @patch("utilities.route_lookup._lookup_route")
    def test_owner_not_stored_under_callsign_key(
        self, mock_lookup_route, mock_lookup_aircraft, mock_fr24
    ):
        import utilities.routes_cache as rc
        from utilities.route_lookup import get_route

        mock_lookup_route.return_value = RouteInfo(origin="LHR", destination="GLA")
        mock_lookup_aircraft.return_value = AircraftInfo(
            "C172", "G-BSFE", "", "Leading Edge Flight Training"
        )

        result = get_route("BAW123", mode_s="400f5a")

        assert result.owner == "Leading Edge Flight Training"
        assert "owner" not in rc.get("BAW123")

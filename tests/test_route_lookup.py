"""Tests for utilities/route_lookup.py - hexdb lookups and FR24 fallback."""

from unittest.mock import MagicMock, patch

import pytest

from utilities.flight import RouteInfo

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
    import utilities.route_lookup as rl

    monkeypatch.setattr(rl, "_airport_cache", {})
    monkeypatch.setattr(rl, "_airports_cache", {})
    monkeypatch.setattr(rl, "_airports_loaded", False)
    monkeypatch.setattr(rl, "_icao_to_iata", {})
    monkeypatch.setattr(rl, "_icao_to_iata_loaded", False)
    # Reset the FR24 fallback throttle so tests aren't blocked by a prior call.
    monkeypatch.setattr(rl, "_fr24_last_call", 0.0)


# ---------------------------------------------------------------------------
# _parse_route
# ---------------------------------------------------------------------------


class TestParseRoute:
    def test_standard_route(self):
        from utilities.route_lookup import _parse_route

        assert _parse_route("EGPF-LEMG") == ("EGPF", "LEMG")

    def test_lowercased(self):
        from utilities.route_lookup import _parse_route

        assert _parse_route("egpf-lemg") == ("EGPF", "LEMG")

    def test_no_separator(self):
        from utilities.route_lookup import _parse_route

        assert _parse_route("EGPF") == ("", "")

    def test_empty_string(self):
        from utilities.route_lookup import _parse_route

        assert _parse_route("") == ("", "")


# ---------------------------------------------------------------------------
# _parse_aircraft_type
# ---------------------------------------------------------------------------


class TestParseAircraftType:
    def test_manufacturer_and_type(self):
        from utilities.route_lookup import _parse_aircraft_type

        data = {"Manufacturer": "Airbus", "ICAOTypeCode": "A320"}
        assert _parse_aircraft_type(data) == "Airbus A320"

    def test_type_only(self):
        from utilities.route_lookup import _parse_aircraft_type

        data = {"Manufacturer": "", "ICAOTypeCode": "B738"}
        assert _parse_aircraft_type(data) == "B738"

    def test_manufacturer_only(self):
        from utilities.route_lookup import _parse_aircraft_type

        data = {"Manufacturer": "Boeing", "ICAOTypeCode": ""}
        assert _parse_aircraft_type(data) == "Boeing"

    def test_missing_fields(self):
        from utilities.route_lookup import _parse_aircraft_type

        assert _parse_aircraft_type({}) == ""


# ---------------------------------------------------------------------------
# _lookup_route - hexdb success (no FR24 fallback needed)
# ---------------------------------------------------------------------------


class TestLookupRouteHexdbSuccess:
    @patch("utilities.route_lookup._airport_details")
    @patch("utilities.route_lookup._icao_to_iata_code")
    @patch("utilities.route_lookup._session")
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
# _lookup_route - hexdb only (FR24 fallback is handled by get_route)
# ---------------------------------------------------------------------------


class TestLookupRouteHexdbOnly:
    """_lookup_route is now hexdb-only; the FR24 fallback lives in get_route."""

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_lookup._session")
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
    @patch("utilities.route_lookup._session")
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
    @patch("utilities.route_lookup._icao_to_iata_code")
    @patch("utilities.route_lookup._session")
    def test_iata_conversion_failure_returns_empty_no_fr24(
        self, mock_session, mock_icao_to_iata, mock_fr24
    ):
        from utilities.route_lookup import _lookup_route

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"route": "EGPF-LEMG"}
        mock_session.get.return_value = mock_resp

        # hexdb parsed the route but IATA conversion failed - both empty.
        # _lookup_route no longer falls back to FR24; it just returns empty.
        mock_icao_to_iata.return_value = ""

        result = _lookup_route("BAW123")

        assert result.origin == ""
        assert result.destination == ""
        mock_fr24.assert_not_called()

    @patch("utilities.route_lookup._fr24_fallback")
    @patch("utilities.route_lookup._icao_to_iata_code")
    @patch("utilities.route_lookup._session")
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

    @patch("utilities.route_lookup._airport_details")
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
    returns a ``(plane, registration)`` tuple.

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
        mock_lookup_aircraft.return_value = ("Airbus A320", "G-ABCD")

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
    def test_no_aircraft_when_route_has_plane(
        self, mock_lookup_route, mock_lookup_aircraft, mock_fr24
    ):
        from utilities.route_lookup import get_route

        mock_lookup_route.return_value = RouteInfo(
            origin="LHR", destination="GLA", plane="B738"
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

        mock_lookup_aircraft.return_value = ("A320", "G-ABCD")

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
        mock_lookup_aircraft.return_value = ("", "G-ABCD")  # plane miss
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
        mock_lookup_aircraft.return_value = ("Airbus A320", "G-ABCD")
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
        mock_lookup_aircraft.return_value = ("", "G-ABCD")
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
        mock_lookup_aircraft.return_value = ("Airbus A320", "G-ABCD")

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
        mock_lookup_aircraft.return_value = ("", "")

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
        mock_lookup_aircraft.return_value = ("", "")

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
        mock_lookup_aircraft.return_value = ("", "G-ABCD")  # plane miss, reg present
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
        assert rc.get("a1b2c3") == {"plane": "Boeing 737-800", "registration": "G-ABCD"}

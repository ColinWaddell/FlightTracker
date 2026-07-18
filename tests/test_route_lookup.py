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
# _lookup_route — hexdb success (no FR24 fallback needed)
# ---------------------------------------------------------------------------


class TestLookupRouteHexdbSuccess:
    @patch("utilities.route_lookup._airport_details")
    @patch("utilities.route_lookup._icao_to_iata_code")
    @patch("utilities.route_lookup._session")
    def test_hexdb_returns_route(self, mock_session, mock_icao_to_iata, mock_airport_details):
        from utilities.route_lookup import _lookup_route

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"route": "EGPF-LEMG"}
        mock_session.get.return_value = mock_resp

        mock_icao_to_iata.side_effect = lambda icao: {"EGPF": "GLA", "LEMG": "AGP"}.get(icao, "")
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
# _lookup_route — hexdb miss triggers FR24 fallback
# ---------------------------------------------------------------------------


class TestLookupRouteFr24Fallback:
    @patch("utilities.route_lookup._fr24_route_fallback")
    @patch("utilities.route_lookup._session")
    def test_hexdb_404_triggers_fr24_fallback(self, mock_session, mock_fr24):
        from utilities.route_lookup import _lookup_route

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_session.get.return_value = mock_resp

        mock_fr24.return_value = RouteInfo(
            origin="LHR",
            destination="GLA",
            origin_name="London Heathrow",
            destination_name="Glasgow",
        )

        result = _lookup_route("BAW123")

        assert result.origin == "LHR"
        assert result.destination == "GLA"
        mock_fr24.assert_called_once_with("BAW123")

    @patch("utilities.route_lookup._fr24_route_fallback")
    @patch("utilities.route_lookup._session")
    def test_hexdb_empty_route_triggers_fr24_fallback(self, mock_session, mock_fr24):
        from utilities.route_lookup import _lookup_route

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"route": ""}
        mock_session.get.return_value = mock_resp

        mock_fr24.return_value = RouteInfo(origin="LHR", destination="GLA")

        result = _lookup_route("BAW123")

        assert result.origin == "LHR"
        assert result.destination == "GLA"
        mock_fr24.assert_called_once_with("BAW123")

    @patch("utilities.route_lookup._fr24_route_fallback")
    @patch("utilities.route_lookup._session")
    def test_both_hexdb_and_fr24_miss_returns_empty(self, mock_session, mock_fr24):
        from utilities.route_lookup import _lookup_route

        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_session.get.return_value = mock_resp

        mock_fr24.return_value = RouteInfo()

        result = _lookup_route("BAW123")

        assert result.origin == ""
        assert result.destination == ""
        mock_fr24.assert_called_once_with("BAW123")

    @patch("utilities.route_lookup._fr24_route_fallback")
    @patch("utilities.route_lookup._session")
    def test_fr24_fallback_fires_when_iata_conversion_fails(self, mock_session, mock_fr24):
        from utilities.route_lookup import _lookup_route

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"route": "EGPF-LEMG"}
        mock_session.get.return_value = mock_resp

        # hexdb parsed the route but IATA conversion failed — both empty,
        # so FR24 fallback should fire
        fr24_result = RouteInfo(origin="GLA", destination="AGP")
        mock_fr24.return_value = fr24_result

        with patch("utilities.route_lookup._icao_to_iata_code", return_value=""):
            result = _lookup_route("BAW123")

        assert result.origin == "GLA"
        assert result.destination == "AGP"
        mock_fr24.assert_called_once_with("BAW123")

    @patch("utilities.route_lookup._fr24_route_fallback")
    @patch("utilities.route_lookup._icao_to_iata_code")
    @patch("utilities.route_lookup._session")
    def test_fr24_fallback_not_called_when_hexdb_succeeds(self, mock_session, mock_icao_to_iata, mock_fr24):
        from utilities.route_lookup import _lookup_route

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json.return_value = {"route": "EGPF-LEMG"}
        mock_session.get.return_value = mock_resp

        mock_icao_to_iata.side_effect = lambda icao: {"EGPF": "GLA", "LEMG": "AGP"}.get(icao, "")

        result = _lookup_route("BAW123")

        assert result.origin == "GLA"
        assert result.destination == "AGP"
        mock_fr24.assert_not_called()


# ---------------------------------------------------------------------------
# _fr24_route_fallback
# ---------------------------------------------------------------------------


class TestFr24RouteFallback:
    def test_short_callsign_returns_empty(self):
        from utilities.route_lookup import _fr24_route_fallback

        result = _fr24_route_fallback("AB")
        assert result.origin == ""
        assert result.destination == ""

    def test_empty_callsign_returns_empty(self):
        from utilities.route_lookup import _fr24_route_fallback

        result = _fr24_route_fallback("")
        assert result.origin == ""
        assert result.destination == ""

    @patch("utilities.route_lookup._airport_details")
    @patch("FlightRadar24.api.FlightRadar24API")
    def test_matching_flight_found(self, mock_api_cls, mock_airport_details):
        from utilities.route_lookup import _fr24_route_fallback

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        mock_tracker = MagicMock()
        mock_api.get_flight_tracker_config.return_value = mock_tracker

        mock_flight = MagicMock()
        mock_flight.callsign = "BAW123"
        mock_flight.origin_airport_iata = "LHR"
        mock_flight.destination_airport_iata = "GLA"
        mock_api.get_flights.return_value = [mock_flight]

        mock_airport_details.side_effect = lambda iata: {
            "LHR": {"name": "London Heathrow", "municipality": "London", "country_name": "UK"},
            "GLA": {"name": "Glasgow", "municipality": "Glasgow", "country_name": "UK"},
        }.get(iata, {})

        result = _fr24_route_fallback("BAW123")

        assert result.origin == "LHR"
        assert result.destination == "GLA"
        assert result.origin_name == "London Heathrow"
        assert result.destination_name == "Glasgow"

        # Verify airline filter was applied
        mock_api.get_flights.assert_called_once_with(airline="BAW")

    @patch("FlightRadar24.api.FlightRadar24API")
    def test_no_matching_flight(self, mock_api_cls):
        from utilities.route_lookup import _fr24_route_fallback

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        mock_flight = MagicMock()
        mock_flight.callsign = "BAW999"
        mock_flight.origin_airport_iata = "LHR"
        mock_flight.destination_airport_iata = "JFK"
        mock_api.get_flights.return_value = [mock_flight]

        result = _fr24_route_fallback("BAW123")

        assert result.origin == ""
        assert result.destination == ""

    @patch("FlightRadar24.api.FlightRadar24API")
    def test_matching_flight_no_route_data(self, mock_api_cls):
        from utilities.route_lookup import _fr24_route_fallback

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        mock_flight = MagicMock()
        mock_flight.callsign = "BAW123"
        mock_flight.origin_airport_iata = ""
        mock_flight.destination_airport_iata = ""
        mock_api.get_flights.return_value = [mock_flight]

        result = _fr24_route_fallback("BAW123")

        assert result.origin == ""
        assert result.destination == ""

    @patch("FlightRadar24.api.FlightRadar24API")
    def test_api_exception_returns_empty(self, mock_api_cls):
        from utilities.route_lookup import _fr24_route_fallback

        mock_api_cls.side_effect = Exception("FR24 unavailable")

        result = _fr24_route_fallback("BAW123")

        assert result.origin == ""
        assert result.destination == ""

    @patch("FlightRadar24.api.FlightRadar24API")
    def test_get_flights_exception_returns_empty(self, mock_api_cls):
        from utilities.route_lookup import _fr24_route_fallback

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api
        mock_api.get_flights.side_effect = Exception("Network error")

        result = _fr24_route_fallback("BAW123")

        assert result.origin == ""
        assert result.destination == ""

    @patch("FlightRadar24.api.FlightRadar24API")
    def test_ground_traffic_excluded(self, mock_api_cls):
        from utilities.route_lookup import _fr24_route_fallback

        mock_api = MagicMock()
        mock_api_cls.return_value = mock_api

        mock_tracker = MagicMock()
        mock_tracker.gnd = "1"  # default
        mock_api.get_flight_tracker_config.return_value = mock_tracker

        mock_flight = MagicMock()
        mock_flight.callsign = "BAW123"
        mock_flight.origin_airport_iata = "LHR"
        mock_flight.destination_airport_iata = "GLA"
        mock_api.get_flights.return_value = [mock_flight]

        _fr24_route_fallback("BAW123")

        # Verify gnd was set to 0
        assert mock_tracker.gnd == 0
        mock_api.set_flight_tracker_config.assert_called_once_with(mock_tracker)


# ---------------------------------------------------------------------------
# get_route — integration of route + aircraft lookups
# ---------------------------------------------------------------------------


class TestGetRoute:
    @patch("utilities.route_lookup._lookup_aircraft")
    @patch("utilities.route_lookup._lookup_route")
    def test_combines_route_and_aircraft(self, mock_lookup_route, mock_lookup_aircraft):
        from utilities.route_lookup import get_route

        mock_lookup_route.return_value = RouteInfo(origin="LHR", destination="GLA")
        mock_lookup_aircraft.return_value = "Airbus A320"

        result = get_route("BAW123", mode_s="a1b2c3")

        assert result.origin == "LHR"
        assert result.destination == "GLA"
        assert result.plane == "Airbus A320"

    @patch("utilities.route_lookup._lookup_aircraft")
    @patch("utilities.route_lookup._lookup_route")
    def test_no_aircraft_when_route_has_plane(self, mock_lookup_route, mock_lookup_aircraft):
        from utilities.route_lookup import get_route

        mock_lookup_route.return_value = RouteInfo(origin="LHR", destination="GLA", plane="B738")

        result = get_route("BAW123", mode_s="a1b2c3")

        assert result.plane == "B738"
        mock_lookup_aircraft.assert_not_called()

    @patch("utilities.route_lookup._lookup_aircraft")
    @patch("utilities.route_lookup._lookup_route")
    def test_no_callsign_skips_route(self, mock_lookup_route, mock_lookup_aircraft):
        from utilities.route_lookup import get_route

        mock_lookup_aircraft.return_value = "A320"

        result = get_route("", mode_s="a1b2c3")

        assert result.origin == ""
        assert result.plane == "A320"
        mock_lookup_route.assert_not_called()

    @patch("utilities.route_lookup._lookup_route")
    def test_no_mode_s_skips_aircraft(self, mock_lookup_route):
        from utilities.route_lookup import get_route

        mock_lookup_route.return_value = RouteInfo(origin="LHR", destination="GLA")

        result = get_route("BAW123")

        assert result.origin == "LHR"
        assert result.plane == ""

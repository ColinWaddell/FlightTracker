"""Tests for utilities/overhead_tar1090.py and overhead_fr24.py - data handling."""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared helpers (now in overhead_utilities)
# ---------------------------------------------------------------------------
from utilities.flight import RouteInfo

# ---------------------------------------------------------------------------
# FR24-specific adapter
# ---------------------------------------------------------------------------
from utilities.overhead_fr24 import distance_from_flight_to_home
from utilities.overhead_utilities import (
    airport_info,
    airport_name,
    clean_field,
    distance_from_home,
    in_zone,
)


class TestInZone:
    def test_inside(self):
        zone = {"tl_y": 56.0, "tl_x": -5.0, "br_y": 55.0, "br_x": -3.0}
        assert in_zone(55.5, -4.0, zone) is True

    def test_outside_lat(self):
        zone = {"tl_y": 56.0, "tl_x": -5.0, "br_y": 55.0, "br_x": -3.0}
        assert in_zone(57.0, -4.0, zone) is False

    def test_outside_lon(self):
        zone = {"tl_y": 56.0, "tl_x": -5.0, "br_y": 55.0, "br_x": -3.0}
        assert in_zone(55.5, -6.0, zone) is False

    def test_on_boundary(self):
        zone = {"tl_y": 56.0, "tl_x": -5.0, "br_y": 55.0, "br_x": -3.0}
        # On the boundary should be included (<=, >=)
        assert in_zone(56.0, -5.0, zone) is True
        assert in_zone(55.0, -3.0, zone) is True


class TestDistanceFromHome:
    def test_directly_overhead(self):
        # Same lat/lon, different altitude
        home = [55.0, -4.0, 6371.0]  # on the surface
        dist = distance_from_home(55.0, -4.0, 10000, home)
        # Should be approximately the altitude converted to km
        assert 1.0 < dist < 5.0  # rough range for 10000ft

    def test_same_point_zero_altitude(self):
        home = [55.0, -4.0, 6371.0]
        dist = distance_from_home(55.0, -4.0, 0, home)
        assert dist == pytest.approx(0.0, abs=0.1)

    def test_far_apart(self):
        home = [55.0, -4.0, 6371.0]
        dist = distance_from_home(60.0, 10.0, 30000, home)
        assert dist > 500.0  # many hundreds of km


class TestAirportInfo:
    def test_known_airport(self):
        # GLA should be in the bundled airports.json
        info = airport_info("GLA")
        assert isinstance(info, dict)
        # It may or may not have "name" but it should be a dict
        if info:
            assert "name" in info or "municipality" in info

    def test_unknown_airport(self):
        info = airport_info("ZZZ")
        assert info == {}

    def test_lowercase_normalised(self):
        # Should uppercase the input
        info_g = airport_info("gla")
        info_G = airport_info("GLA")
        assert info_g == info_G

    def test_empty_string(self):
        assert airport_info("") == {}


class TestAirportName:
    def test_returns_string(self):
        name = airport_name("GLA")
        assert isinstance(name, str)

    def test_unknown_returns_empty(self):
        assert airport_name("ZZZ") == ""


# ---------------------------------------------------------------------------
# tar1090 Overhead - data unavailability
# ---------------------------------------------------------------------------


class TestTar1090DataUnavailability:
    @pytest.fixture
    def overhead_instance(self):
        """Create an Overhead instance with mocked Config."""
        with patch("setup.configuration.Config") as MockConfig:
            cfg = MockConfig.instance.return_value
            cfg.tar1090_url = "http://localhost/tar1090/data/aircraft.json"
            cfg.zone_home = {"tl_y": 56.0, "tl_x": -5.0, "br_y": 55.0, "br_x": -3.0}
            cfg.flight_min_altitude = 300.0  # metres
            cfg.flight_max_altitude = 15000.0  # metres
            cfg.location_home = [55.5, -4.0, 6371.0]
            cfg.max_flight_lookup = 10

            from utilities.overhead_tar1090 import Overhead

            return Overhead()

    def test_initial_state(self, overhead_instance):
        assert overhead_instance.data_is_empty is True
        assert overhead_instance.processing is False
        assert overhead_instance.new_data is False
        assert overhead_instance.error is None

    def test_empty_aircraft_list(self, overhead_instance):
        """API returns no aircraft - should be empty data, no error."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"aircraft": []}
        mock_response.raise_for_status = MagicMock()

        overhead_instance._session.get = MagicMock(return_value=mock_response)
        overhead_instance.refresh()

        assert overhead_instance.data_is_empty is True
        assert overhead_instance.error is None
        assert overhead_instance.data == []

    def test_connection_error(self, overhead_instance):
        """API unreachable - should show URL-error placeholder, no error set."""
        from requests.exceptions import ConnectionError as ReqConnError

        overhead_instance._session.get = MagicMock(
            side_effect=ReqConnError("Connection refused")
        )
        overhead_instance.refresh()

        # tar1090 Overhead surfaces a placeholder flight on connection errors
        # rather than setting error_store (unlike the FR24 backend).
        assert overhead_instance.error is None
        assert overhead_instance.data_is_empty is False
        assert overhead_instance.data[0].callsign == "URL ERROR"

    def test_invalid_json(self, overhead_instance):
        """API returns invalid JSON - should show URL-error placeholder."""
        mock_response = MagicMock()
        mock_response.json.side_effect = ValueError("Invalid JSON")
        mock_response.raise_for_status = MagicMock()

        overhead_instance._session.get = MagicMock(return_value=mock_response)
        overhead_instance.refresh()

        # ValueError is caught - placeholder flight is shown, error stays None
        assert overhead_instance.error is None
        assert overhead_instance.data_is_empty is False
        assert overhead_instance.data[0].callsign == "URL ERROR"

    def test_successful_data(self, overhead_instance):
        """API returns valid aircraft - should populate data."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "aircraft": [
                {
                    "lat": 55.5,
                    "lon": -4.0,
                    "alt_baro": 35000,
                    "flight": "BAW123",
                    "desc": "A320",
                    "gs": 450,
                    "track": 90,
                    "baro_rate": 0,
                }
            ]
        }
        mock_response.raise_for_status = MagicMock()

        mock_route = RouteInfo(
            origin="LHR",
            destination="GLA",
            plane="",
            origin_name="London Heathrow",
            origin_municipality="London",
            origin_country="United Kingdom",
            destination_name="Glasgow Airport",
            destination_municipality="Glasgow",
            destination_country="United Kingdom",
        )

        overhead_instance._session.get = MagicMock(return_value=mock_response)

        with patch(
            "utilities.overhead_tar1090.route_lookup.get_route", return_value=mock_route
        ):
            overhead_instance.refresh()

        assert overhead_instance.error is None
        assert overhead_instance.data_is_empty is False
        assert len(overhead_instance.data) == 1
        assert overhead_instance.data[0].callsign == "BAW123"
        assert overhead_instance.data[0].altitude == 35000


# ---------------------------------------------------------------------------
# FR24 helpers
# ---------------------------------------------------------------------------


class TestCleanField:
    def test_strips_whitespace(self):
        assert clean_field("  BAW123  ") == "BAW123"

    def test_none_input(self):
        assert clean_field(None) == ""

    def test_empty_string(self):
        assert clean_field("") == ""

    def test_integer_input(self):
        # clean_field should handle non-string types
        assert clean_field(123) == "123" or clean_field(123) == ""


class TestDistanceFromFlightToHome:
    def test_overhead_flight(self):
        """Flight directly above home location."""
        flight = MagicMock()
        flight.latitude = 55.0
        flight.longitude = -4.0
        flight.altitude = 35000  # feet
        home = [55.0, -4.0, 6371.0]
        dist = distance_from_flight_to_home(flight, home)
        # Should be roughly the altitude in km (35000ft ≈ 10.7km)
        assert 8.0 < dist < 15.0

    def test_distant_flight(self):
        flight = MagicMock()
        flight.latitude = 60.0
        flight.longitude = 10.0
        flight.altitude = 35000
        home = [55.0, -4.0, 6371.0]
        dist = distance_from_flight_to_home(flight, home)
        assert dist > 500.0

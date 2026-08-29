"""Tests for the shared overhead helpers and the tar1090 flight adapter."""

from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Shared helpers (in overhead_utilities)
# ---------------------------------------------------------------------------
from lookups.providers.tar1090.flights import FlightProvider as Tar1090FlightProvider
from lookups.providers.tar1090.flights import _to_observation
from utilities.flight import RouteInfo
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


# ---------------------------------------------------------------------------
# tar1090 flight adapter - observation parsing
# ---------------------------------------------------------------------------


class TestTar1090ObservationParsing:
    def test_readsb_field_names(self):
        """tar1090/readsb-style alt_baro/gs/baro_rate parse correctly."""
        obs = _to_observation(
            {
                "hex": "400f5a",
                "flight": "BAW506 ",
                "lat": 55.5,
                "lon": -4.0,
                "alt_baro": 35000,
                "gs": 450,
                "track": 90,
                "baro_rate": 0,
                "desc": "A320",
                "r": "G-EUUA",
            }
        )
        assert obs.icao == "400f5a"
        assert obs.callsign == "BAW506"
        assert obs.altitude_ft == 35000
        assert obs.ground_speed_kt == 450
        assert obs.heading_deg == 90
        assert obs.vertical_speed_fpm == 0
        assert obs.plane == "A320"
        assert obs.registration == "G-EUUA"

    def test_dump1090_field_names(self):
        """dump1090-style altitude/speed/vert_rate parse correctly (issue #90)."""
        obs = _to_observation(
            {
                "hex": "485779",
                "flight": "KLM1127 ",
                "lat": 55.5,
                "lon": -4.0,
                "altitude": 34000,  # dump1090 name (no alt_baro)
                "speed": 415,  # dump1090 name (no gs)
                "vert_rate": 64,  # dump1090 name (no baro_rate)
                "track": 277,
            }
        )
        assert obs.icao == "485779"
        assert obs.callsign == "KLM1127"
        assert obs.altitude_ft == 34000
        assert obs.ground_speed_kt == 415
        assert obs.heading_deg == 277
        assert obs.vertical_speed_fpm == 64

    def test_mixed_field_names_prefer_readsb(self):
        """When both forks' fields are present the readsb value wins."""
        obs = _to_observation(
            {"hex": "a", "alt_baro": 10000, "latitude_dummy": 0, "altitude": 9999}
        )
        assert obs.altitude_ft == 10000

    def test_none_alt_baro_string(self):
        """tar1090 reports 'ground' as alt_baro - not a usable altitude."""
        obs = _to_observation({"hex": "b", "alt_baro": "ground", "altitude": None})
        assert obs.altitude_ft == 0


class TestTar1090Fetch:
    @pytest.fixture
    def provider(self):
        return Tar1090FlightProvider(
            {"url": "http://localhost/tar1090/data/aircraft.json"}
        )

    @pytest.fixture
    def query(self):
        from lookups.results import FlightQuery

        return FlightQuery(
            zone={"tl_y": 56.0, "tl_x": -5.0, "br_y": 55.0, "br_x": -3.0},
            home=[55.5, -4.0, 6371.0],
            min_altitude_m=100.0,
            max_altitude_m=15000.0,
            max_results=5,
        )

    def _mock_response(self, aircraft):
        response = MagicMock()
        response.json.return_value = {"aircraft": aircraft}
        response.raise_for_status = MagicMock()
        return response

    def test_empty_sky_is_found_with_empty_list(self, provider, query):
        provider._session.get = MagicMock(return_value=self._mock_response([]))
        result = provider.fetch(query)
        assert result.is_found
        assert result.value == []

    def test_connection_error_is_unavailable(self, provider, query):
        from requests.exceptions import ConnectionError as ReqConnError

        provider._session.get = MagicMock(
            side_effect=ReqConnError("Connection refused")
        )
        result = provider.fetch(query)
        assert result.is_unavailable

    def test_altitude_and_zone_filtering(self, provider, query):
        aircraft = [
            {  # inside zone, inside altitudes
                "hex": "400f5a",
                "lat": 55.5,
                "lon": -4.0,
                "alt_baro": 35000,
                "gs": 450,
            },
            {  # below min altitude
                "hex": "111111",
                "lat": 55.5,
                "lon": -4.0,
                "alt_baro": 100,  # ~30m - below 100m min
                "gs": 100,
            },
            {  # outside zone (north)
                "hex": "222222",
                "lat": 57.0,
                "lon": -4.0,
                "alt_baro": 20000,
                "gs": 300,
            },
            {  # no position
                "hex": "333333",
                "alt_baro": 20000,
            },
        ]
        provider._session.get = MagicMock(return_value=self._mock_response(aircraft))
        result = provider.fetch(query)
        assert result.is_found
        assert len(result.value) == 1
        assert result.value[0].icao == "400f5a"

    def test_sorted_by_distance_from_home(self, provider, query):
        aircraft = [
            {"hex": "near", "lat": 55.6, "lon": -4.1, "alt_baro": 20000, "gs": 300},
            {"hex": "far", "lat": 55.1, "lon": -3.1, "alt_baro": 20000, "gs": 300},
        ]
        provider._session.get = MagicMock(return_value=self._mock_response(aircraft))
        result = provider.fetch(query)
        assert result.value[0].icao == "near"

    def test_unconfigured_url_is_unavailable(self, query):
        provider = Tar1090FlightProvider({})
        result = provider.fetch(query)
        assert result.is_unavailable

    def test_max_results_respected(self, provider, query):
        query.max_results = 2
        aircraft = [
            {
                "hex": str(i % 10) * 6,
                "lat": 55.5 + i * 0.01,
                "lon": -4.0,
                "alt_baro": 20000,
                "gs": 400,
            }
            for i in range(5)
        ]
        provider._session.get = MagicMock(return_value=self._mock_response(aircraft))
        result = provider.fetch(query)
        assert len(result.value) == 2
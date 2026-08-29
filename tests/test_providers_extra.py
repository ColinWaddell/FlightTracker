"""Tests for the extra flight-position aggregators.

adsb.fi / ADSB.lol / airplanes.live share the readsb-format adapter in
providers.common.aggregator; the envelope key differs per host.
"""

from __future__ import annotations

import unittest.mock as mock

import pytest

from lookups.results import FlightQuery, LookupContext


def _record(**fields):
    record = {
        "hex": "406df5",
        "flight": "GSGTS  ",
        "r": "G-SGTS",
        "desc": "De Havilland DHC-6 Twin Otter",
        "alt_baro": 6000,
        "gs": 161.1,
        "track": 151.0,
        "baro_rate": -512,
        "lat": 55.5,
        "lon": -4.0,
    }
    record.update(fields)
    return record


def _response(payload, status=200):
    response = mock.Mock()
    response.status_code = status
    response.json.return_value = payload
    return response


def _provider(module_name, response):
    """Aggregator provider with a stubbed HTTP session."""
    import importlib

    flights = importlib.import_module(f"lookups.providers.{module_name}.flights")
    provider = flights.FlightProvider({})
    provider._session = mock.Mock()
    provider._session.get.return_value = response
    return provider


def _query():
    return FlightQuery(
        zone={"tl_y": 56.0, "tl_x": -5.0, "br_y": 55.0, "br_x": -3.0},
        home=[55.5, -4.0, 6371.0],
        min_altitude_m=100.0,
        max_altitude_m=15000.0,
        max_results=5,
    )


@pytest.mark.parametrize(
    "module_name, envelope",
    [
        ("adsbfi", "aircraft"),
        ("adsblol", "ac"),
        ("airplaneslive", "ac"),
    ],
)
class TestFlightAggregators:
    def test_fetch_maps_fields(self, module_name, envelope):
        provider = _provider(module_name, _response({envelope: [_record()]}))

        result = provider.fetch(_query())

        assert result.is_found
        assert len(result.value) == 1
        obs = result.value[0]
        assert obs.icao == "406df5"
        assert obs.callsign == "GSGTS"
        assert obs.altitude_ft == 6000
        assert obs.plane == "De Havilland DHC-6 Twin Otter"
        assert obs.registration == "G-SGTS"

    def test_filters_outliers_and_orders_by_distance(self, module_name, envelope):
        payload = {
            envelope: [
                _record(hex="111111", lat=57.0, lon=-4.0),  # out of zone
                _record(hex="333333", alt_baro=60000),  # above the band
                _record(hex="406df5"),  # overhead
                _record(hex="444444", lat=55.05, lon=-3.1),  # far corner
            ]
        }
        provider = _provider(module_name, _response(payload))

        result = provider.fetch(_query())

        # Overhead first, the far corner second; the out-of-zone and
        # out-of-band records never reach the display.
        assert [o.icao for o in result.value] == ["406df5", "444444"]

    def test_empty_sky_is_found_empty(self, module_name, envelope):
        provider = _provider(module_name, _response({}))

        result = provider.fetch(_query())

        assert result.is_found and result.value == []

    def test_unreachable_is_unavailable(self, module_name, envelope):
        import importlib

        import requests

        flights = importlib.import_module(f"lookups.providers.{module_name}.flights")
        provider = flights.FlightProvider({})
        provider._session = mock.Mock()
        provider._session.get.side_effect = requests.ConnectionError("boom")

        result = provider.fetch(_query())

        assert result.is_unavailable

# ---------------------------------------------------------------------------
# ADSB.im routeset route provider
# ---------------------------------------------------------------------------


class TestAdsbImRoutes:
    def test_route_found(self, monkeypatch):
        import lookups.providers.adsbim.routes as adsbim

        entry = {
            "callsign": "BAW123",
            "airport_codes": "EGLL-OTHH",
            "_airport_codes_iata": "LHR-DOH",
            "airline_code": "BAW",
            "plausible": True,
        }
        monkeypatch.setattr(
            adsbim.requests, "post", lambda *a, **k: _response([entry])
        )

        result = adsbim.RouteProvider({}).lookup_route(_context("BAW123"))

        assert result.is_found
        assert result.value.origin == "LHR"
        assert result.value.destination == "DOH"
        assert result.value.airline_icao == "BAW"

    def test_implausible_is_not_found(self, monkeypatch):
        import lookups.providers.adsbim.routes as adsbim

        entry = {"callsign": "X", "airport_codes": "EGLL-OTHH", "plausible": False}
        monkeypatch.setattr(adsbim.requests, "post", lambda *a, **k: _response([entry]))

        result = adsbim.RouteProvider({}).lookup_route(_context("BAW123"))
        assert result.is_not_found

    def test_unknown_callsign_is_not_found(self, monkeypatch):
        import lookups.providers.adsbim.routes as adsbim

        entry = {"callsign": "BAW123", "airport_codes": "unknown", "plausible": False}
        monkeypatch.setattr(adsbim.requests, "post", lambda *a, **k: _response([entry]))

        result = adsbim.RouteProvider({}).lookup_route(_context("BAW123"))
        assert result.is_not_found

    def test_missing_position_is_not_found(self):
        import lookups.providers.adsbim.routes as adsbim

        ctx = LookupContext(callsign="BAW123")  # no lat/lng
        result = adsbim.RouteProvider({}).lookup_route(ctx)
        assert result.is_not_found

    def test_connection_error_is_unavailable(self, monkeypatch):
        import requests

        import lookups.providers.adsbim.routes as adsbim

        def boom(*args, **kwargs):
            raise requests.ConnectionError("down")

        monkeypatch.setattr(adsbim.requests, "post", boom)
        result = adsbim.RouteProvider({}).lookup_route(_context("BAW123", 55.0, -4.0))
        assert result.is_unavailable


def _context(callsign="BAW123", lat=55.5, lng=-4.0):
    return LookupContext(callsign=callsign, lat=lat, lng=lng)


# ---------------------------------------------------------------------------
# AirLabs + FlightAware (keyed route providers)
# ---------------------------------------------------------------------------


class TestAirLabs:
    def test_route_found(self):
        import lookups.providers.airlabs.routes as airlabs

        provider = airlabs.RouteProvider({"api_key": "k"})
        response = _response(
            {"response": [{"airline_icao": "BAW", "dep_iata": "LHR", "arr_iata": "JFK"}]}
        )
        with mock.patch.object(airlabs.requests, "get", return_value=response):
            result = provider.lookup_route(_context("BAW123"))

        assert result.is_found
        assert result.value.origin == "LHR"
        assert result.value.destination == "JFK"
        assert result.value.airline_icao == "BAW"

    def test_missing_key_is_unavailable(self):
        from lookups.providers.airlabs.routes import RouteProvider

        result = RouteProvider({}).lookup_route(_context("BAW123"))
        assert result.is_unavailable

    def test_empty_response_is_not_found(self):
        import lookups.providers.airlabs.routes as airlabs

        provider = airlabs.RouteProvider({"api_key": "k"})
        with mock.patch.object(airlabs.requests, "get", return_value=_response({})):
            result = provider.lookup_route(_context("BAW123"))
        assert result.is_not_found

    def test_route_found_with_icao_to_iata(self):
        import lookups.providers.flightaware.routes as flightaware

        provider = flightaware.RouteProvider({"api_key": "k"})
        response = _response({
            "flights": [{"origin": {"code": "EGLL"}, "destination": {"code": "KJFK"}}]
        })
        with mock.patch.object(flightaware.requests, "get", return_value=response):
            result = provider.lookup_route(_context("BAW123"))

        assert result.is_found
        # AeroAPI answers in ICAO codes; the bundled table restores IATA.
        assert result.value.origin == "LHR"
        assert result.value.destination == "JFK"

    def test_404_is_not_found(self):
        import lookups.providers.flightaware.routes as flightaware

        provider = flightaware.RouteProvider({"api_key": "k"})
        response = _response({}, status=404)
        with mock.patch.object(flightaware.requests, "get", return_value=response):
            result = provider.lookup_route(_context("BAW123"))
        assert result.is_not_found

    def test_auth_error_is_unavailable(self):
        import lookups.providers.flightaware.routes as flightaware

        provider = flightaware.RouteProvider({"api_key": "k"})
        with mock.patch.object(flightaware.requests, "get", return_value=_response({}, status=401)):
            result = provider.lookup_route(_context("BAW123"))
        assert result.is_unavailable


# ---------------------------------------------------------------------------
# FlightRadar24 API (official, commercial)
# ---------------------------------------------------------------------------


def _fr24_record(**fields):
    record = {
        "fr24_id": "abc123",
        "hex": "406DF5",
        "callsign": "BAW1AB",
        "flight": "BA1AB",
        "lat": 55.5,
        "lon": -4.0,
        "alt": 12000,
        "gspeed": 400,
        "track": 90,
        "vspeed": -64,
        "orig_iata": "LHR",
        "orig_icao": "EGLL",
        "dest_iata": "DOH",
        "dest_icao": "OTHH",
        "painted_as": "BAW",
        "type": "A35K",
        "reg": "G-XWBA",
    }
    record.update(fields)
    return record


def _fr24_response(data, status=200):
    response = mock.Mock()
    response.status_code = status
    response.json.return_value = {"data": data}
    return response


class TestFr24ApiFlights:
    def _fetch(self, monkeypatch, data=None, status=200):
        import lookups.providers.fr24api.flights as fr24api
        from lookups.results import FlightQuery

        captured = {}

        def fake_get(path, token, params=None):
            captured["path"] = path
            captured["token"] = token
            captured["params"] = params
            return _fr24_response(data or [], status)

        monkeypatch.setattr(fr24api, "_get_explicit", fake_get, raising=False)
        # The provider imports get() inside fetch(); patch the client module.
        import lookups.providers.fr24api.client as client

        monkeypatch.setattr(client, "get", fake_get)

        query = FlightQuery(
            zone={"tl_y": 56.0, "tl_x": -5.0, "br_y": 55.0, "br_x": -3.0},
            home=[55.5, -4.0, 100],
        )
        result = fr24api.FlightProvider({"api_key": "TOK"}).fetch(query)
        return result, captured

    def test_found_and_mapped(self, monkeypatch):
        result, captured = self._fetch(
            monkeypatch,
            data=[_fr24_record(), _fr24_record(hex="222222", lat=54.0)],
        )
        assert result.is_found
        assert [o.icao for o in result.value] == ["406df5"]
        obs = result.value[0]
        assert obs.callsign == "BAW1AB"
        assert obs.flight_number == "BA1AB"
        assert obs.altitude_ft == 12000
        assert obs.ground_speed_kt == 400
        assert obs.heading_deg == 90
        assert obs.vertical_speed_fpm == -64
        assert obs.origin == "LHR"
        assert obs.destination == "DOH"
        assert obs.airline_icao == "BAW"
        # Bounds use the zone corners, north-south-west-east order.
        assert captured["path"] == "/api/live/flight-positions/full"
        assert captured["params"]["bounds"] == "56.0,55.0,-5.0,-3.0"
        assert captured["token"] == "TOK"

    def test_no_token_is_unavailable(self):
        import lookups.providers.fr24api.flights as fr24api

        result = fr24api.FlightProvider({}).fetch(_query())
        assert result.is_unavailable

    def test_auth_and_credit_errors_are_unavailable(self, monkeypatch):
        import lookups.providers.fr24api.client as client
        import lookups.providers.fr24api.flights as fr24api

        monkeypatch.setattr(
            client, "get", lambda *a, **k: _fr24_response([], status=402)
        )
        from lookups.results import FlightQuery

        result = fr24api.FlightProvider({"api_key": "TOK"}).fetch(
            FlightQuery(
                zone={"tl_y": 56.0, "tl_x": -5.0, "br_y": 55.0, "br_x": -3.0},
                home=[55.5, -4.0, 100],
            )
        )
        assert result.is_unavailable
        assert "credit" in result.reason

    def test_transport_error_is_unavailable(self, monkeypatch):
        import requests

        import lookups.providers.fr24api.client as client
        import lookups.providers.fr24api.flights as fr24api

        def boom(*args, **kwargs):
            raise requests.ConnectionError("down")

        monkeypatch.setattr(client, "get", boom)
        from lookups.results import FlightQuery

        result = fr24api.FlightProvider({"api_key": "TOK"}).fetch(
            FlightQuery(
                zone={"tl_y": 56.0, "tl_x": -5.0, "br_y": 55.0, "br_x": -3.0},
                home=[55.5, -4.0, 100],
            )
        )
        assert result.is_unavailable


class TestFr24ApiRoutes:
    def _lookup(self, monkeypatch, data=None, status=200, callsign="BAW1AB"):
        import lookups.providers.fr24api.client as client
        import lookups.providers.fr24api.routes as fr24api

        monkeypatch.setattr(
            client, "get", lambda *a, **k: _fr24_response(data or [], status)
        )
        return fr24api.RouteProvider({"api_key": "TOK"}).lookup_route(
            _context(callsign)
        )

    def test_found(self, monkeypatch):
        result = self._lookup(monkeypatch, data=[_fr24_record()])
        assert result.is_found
        assert result.value.origin == "LHR"
        assert result.value.destination == "DOH"
        assert result.value.airline_icao == "BAW"

    def test_icao_only_codes_converted(self, monkeypatch):
        record = {
            "orig_iata": "",
            "orig_icao": "EGLL",
            "dest_iata": "",
            "dest_icao": "KJFK",
        }
        result = self._lookup(monkeypatch, data=[record])
        assert result.is_found
        assert result.value.origin == "LHR"
        assert result.value.destination == "JFK"

    def test_unroutable_flight_is_not_found(self, monkeypatch):
        record = {"orig_iata": "", "dest_iata": "", "orig_icao": "", "dest_icao": ""}
        result = self._lookup(monkeypatch, data=[record])
        assert result.is_not_found

    def test_unknown_callsign_is_not_found(self, monkeypatch):
        result = self._lookup(monkeypatch, data=[])
        assert result.is_not_found

    def test_no_callsign_is_not_found(self):
        from lookups.providers.fr24api.routes import RouteProvider

        assert RouteProvider({"api_key": "TOK"}).lookup_route(_context("")).is_not_found

    def test_missing_token_is_unavailable(self):
        from lookups.providers.fr24api.routes import RouteProvider

        result = RouteProvider({}).lookup_route(_context("BAW1AB"))
        assert result.is_unavailable

    def test_credit_error_is_unavailable(self, monkeypatch):
        result = self._lookup(monkeypatch, data=[], status=402)
        assert result.is_unavailable
        assert "credit" in result.reason


class TestFr24ApiAircraft:
    def test_found(self, monkeypatch):
        import lookups.providers.fr24api.aircraft as fr24api
        import lookups.providers.fr24api.client as client

        monkeypatch.setattr(
            client, "get", lambda *a, **k: _fr24_response([_fr24_record()])
        )
        result = fr24api.AircraftProvider({"api_key": "TOK"}).lookup_aircraft(
            _context("BAW1AB")
        )
        assert result.is_found
        assert result.value.registration == "G-XWBA"
        assert result.value.plane == "A35K"
        assert result.value.operator_icao == "BAW"

    def test_unknown_callsign_is_not_found(self, monkeypatch):
        import lookups.providers.fr24api.aircraft as fr24api
        import lookups.providers.fr24api.client as client

        monkeypatch.setattr(client, "get", lambda *a, **k: _fr24_response([]))
        result = fr24api.AircraftProvider({"api_key": "TOK"}).lookup_aircraft(
            _context("BAW1AB")
        )
        assert result.is_not_found

    def test_no_callsign_is_not_found(self):
        import lookups.providers.fr24api.aircraft as fr24api

        result = fr24api.AircraftProvider({"api_key": "TOK"}).lookup_aircraft(
            _context("")
        )
        assert result.is_not_found

    def test_missing_token_is_unavailable(self):
        import lookups.providers.fr24api.aircraft as fr24api

        result = fr24api.AircraftProvider({}).lookup_aircraft(_context("BAW1AB"))
        assert result.is_unavailable


class TestFr24ApiCatalogue:
    def test_registered(self):
        from lookups.registry import PROVIDERS

        spec = PROVIDERS["fr24api"]
        assert spec.implements("flights")
        assert spec.implements("routes")
        assert spec.implements("aircraft")

    def test_config_defaults(self):
        from setup.configuration import DEFAULTS

        assert DEFAULTS["providers"]["fr24api"] == {"api_key": ""}
        assert any(
            e["provider"] == "fr24api" for e in DEFAULTS["flight_providers"]
        )
        assert any(
            e["provider"] == "fr24api" for e in DEFAULTS["route_providers"]
        )

    def test_completeness_pass_appends_fr24api_disabled(self):
        from setup.configuration import _complete_provider_lists

        data = {
            "flight_providers": [{"provider": "fr24", "enabled": True}],
            "route_providers": [{"provider": "hexdb", "enabled": True}],
            "providers": {},
        }
        _complete_provider_lists(data)
        flight = {e["provider"]: e["enabled"] for e in data["flight_providers"]}
        route = {e["provider"] for e in data["route_providers"]}
        assert flight["fr24api"] is False
        assert "fr24api" in route

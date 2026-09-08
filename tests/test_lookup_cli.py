"""Tests for the CLI lookup commands (utilities/lookup_cli.py).

The commands are exercised through dispatch_cli_command so the wiring in
utilities/cli.py is covered too.  Heavy lookups (flights/routes/aircraft)
are stubbed at the service boundary - the pipelines themselves have their
own test coverage; these tests pin the CLI glue: argument parsing,
forcing, --fresh, JSON shapes and exit codes.
"""

import json

import pytest

from utilities.cli import dispatch_cli_command


def run(capsys, *argv):
    """Dispatch a lookup command; return (exit_code, json_or_None, stderr)."""
    code = dispatch_cli_command(["flight-tracker.py", *argv])
    captured = capsys.readouterr()
    payload = None
    if captured.out.strip():
        payload = json.loads(captured.out)
    return code, payload, captured.err


@pytest.fixture(autouse=True)
def _clean_registry():
    """Keep forced-provider overrides out of neighbouring tests."""
    from utilities.lookups import registry

    registry.clear_forced_providers()
    yield
    registry.clear_forced_providers()


# ---------------------------------------------------------------------------
# Registry forcing hook
# ---------------------------------------------------------------------------


class TestForcedProvider:
    @pytest.fixture
    def stub_adapters(self, monkeypatch):
        from utilities.lookups import registry

        sentinel = object()
        monkeypatch.setattr(registry, "get_adapter", lambda *a, **k: sentinel)
        monkeypatch.setattr(
            registry,
            "load_config",
            lambda: type(
                "C", (), {"provider_settings": staticmethod(lambda pid: {})}
            )(),
        )
        return sentinel

    def test_forced_chain_is_single_provider(self, stub_adapters):
        from utilities.lookups import registry

        registry.set_forced_provider("routes", "adsbdb")
        chain = registry.resolve_chain(None, "routes")
        assert [pid for pid, _ in chain] == ["adsbdb"]
        assert chain[0][1] is stub_adapters

    def test_clear_restores_config_chain(self, stub_adapters):
        from utilities.lookups import registry

        registry.set_forced_provider("routes", "adsbdb")
        registry.clear_forced_providers()
        cfg = type("C", (), {"route_providers": []})()
        assert registry.resolve_chain(cfg, "routes") == []

    def test_unknown_provider_rejected(self):
        from utilities.lookups import registry

        with pytest.raises(ValueError) as exc:
            registry.set_forced_provider("routes", "opensky")
        assert "valid:" in str(exc.value)

    def test_nonexistent_provider_rejected(self):
        from utilities.lookups import registry

        with pytest.raises(ValueError):
            registry.set_forced_provider("routes", "not-a-provider")

    def test_capabilities_force_independently(self):
        from utilities.lookups import registry

        registry.set_forced_provider("routes", "fr24")
        assert registry.forced_provider("routes") == "fr24"
        assert registry.forced_provider("aircraft") is None
        assert registry.forced_provider("flights") is None


# ---------------------------------------------------------------------------
# lookup callsign / lookup airport (local, no network)
# ---------------------------------------------------------------------------


class TestCallsignCommand:
    def test_known_callsign(self, capsys):
        code, payload, _ = run(capsys, "lookup", "callsign", "BAW117")
        assert code == 0
        assert payload["callsign"] == "BAW117"
        assert payload["iata_flight"] == "BA117"
        assert payload["airline"]["name"] == "British Airways"
        assert payload["airline"]["iata"] == "BA"

    def test_unknown_callsign(self, capsys):
        code, payload, _ = run(capsys, "lookup", "callsign", "ZZZ1")
        assert code == 1
        assert payload["iata_flight"] == ""


class TestAirportCommand:
    def test_iata_code(self, capsys):
        code, payload, _ = run(capsys, "lookup", "airport", "GLA")
        assert code == 0
        entry = payload["airports"][0]
        assert entry["found"] is True
        assert "Glasgow" in entry["name"]
        assert payload["table"] == "airports.json"

    def test_mixed_codes_exit_code(self, capsys):
        code, payload, _ = run(capsys, "lookup", "airport", "GLA", "ZZZZ")
        assert code == 0  # one hit is enough
        assert [a["code"] for a in payload["airports"]] == ["GLA", "ZZZZ"]

    def test_all_misses_exit_code_and_hint(self, capsys):
        code, payload, _ = run(capsys, "lookup", "airport", "KRGA")
        assert code == 1
        assert payload["airports"][0]["found"] is False
        assert "airport_lookup_full" in payload["hint"]

    def test_full_table_resolves_icao_code(self, capsys, monkeypatch):
        from utilities import overhead_utilities as oh

        monkeypatch.setattr(
            oh, "_selected_airports_filename", lambda: "airports-full.json"
        )
        oh.reset_airports_cache()
        try:
            code, payload, _ = run(capsys, "lookup", "airport", "KRGA")
        finally:
            oh.reset_airports_cache()
        assert code == 0
        assert payload["airports"][0]["name"] == "Central Kentucky Regional Airport"


# ---------------------------------------------------------------------------
# lookup route
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_enrich(monkeypatch):
    from utilities.lookups import enrichment
    from utilities.lookups.results import RouteInfo

    calls = {}

    def fake(observation):
        calls["observation"] = observation
        return RouteInfo(
            plane="B738",
            registration="G-RYRA",
            airline_icao="RYR",
            origin="STN",
            destination="DUB",
            origin_name="London Stansted Airport",
        )

    monkeypatch.setattr(enrichment, "enrich", fake)
    return calls


class TestRouteCommand:
    def test_found(self, capsys, fake_enrich):
        code, payload, _ = run(capsys, "lookup", "route", "ryr215k")
        assert code == 0
        assert payload["callsign"] == "RYR215K"  # normalised to upper
        assert payload["route"]["destination"] == "DUB"
        assert "iata_flight" in payload
        assert fake_enrich["observation"].callsign == "RYR215K"

    def test_hex_reaches_the_observation(self, capsys, fake_enrich):
        run(capsys, "lookup", "route", "RYR215K", "--hex", "406F3A")
        assert fake_enrich["observation"].icao == "406f3a"

    def test_no_hex_means_blank_mode_s(self, capsys, fake_enrich):
        run(capsys, "lookup", "route", "RYR215K")
        assert fake_enrich["observation"].icao == ""

    def test_blank_result_is_not_found(self, capsys, monkeypatch):
        from utilities.lookups import enrichment
        from utilities.lookups.results import RouteInfo

        monkeypatch.setattr(enrichment, "enrich", lambda obs: RouteInfo())
        code, _, _ = run(capsys, "lookup", "route", "ZZZZZZ")
        assert code == 1

    def test_fresh_drops_route_cache(self, capsys, fake_enrich, monkeypatch):
        from utilities.lookups import cache

        deleted = []
        monkeypatch.setattr(
            cache, "delete", lambda keys, kind: deleted.append((list(keys), kind))
        )
        run(capsys, "lookup", "route", "RYR215K", "--fresh")
        assert (["RYR215K"], "route") in deleted

    def test_fresh_with_hex_drops_aircraft_cache(
        self, capsys, fake_enrich, monkeypatch
    ):
        from utilities.lookups import cache

        deleted = []
        monkeypatch.setattr(
            cache, "delete", lambda keys, kind: deleted.append((list(keys), kind))
        )
        run(capsys, "lookup", "route", "RYR215K", "--hex", "406F3A", "--fresh")
        assert (["406f3a"], "aircraft") in deleted  # lower-cased

    def test_forcing_invalid_provider_is_usage_error(self, capsys):
        code, _, err = run(
            capsys, "lookup", "route", "RYR215K", "--provider-route", "opensky"
        )
        assert code == 2
        assert "does not support" in err

    def test_forcing_pins_the_chain(self, capsys, fake_enrich, monkeypatch):
        from utilities.lookups import registry

        forced = []
        monkeypatch.setattr(
            registry, "set_forced_provider", lambda cap, pid: forced.append((cap, pid))
        )
        run(capsys, "lookup", "route", "RYR215K", "--provider-route", "fr24")
        assert ("routes", "fr24") in forced


# ---------------------------------------------------------------------------
# lookup aircraft
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_aircraft(monkeypatch):
    from utilities.lookups import aircraft as aircraft_service
    from utilities.lookups.results import AircraftInfo

    seen = {}

    def fake(ctx):
        seen["mode_s"] = ctx.mode_s
        seen["want_plane"] = ctx.want_plane
        return AircraftInfo(plane="A320", registration="G-EUUU")

    monkeypatch.setattr(aircraft_service, "lookup_aircraft", fake)
    return seen


class TestAircraftCommand:
    def test_found(self, capsys, fake_aircraft):
        code, payload, _ = run(capsys, "lookup", "aircraft", "406F3A")
        assert code == 0
        assert payload["hex"] == "406f3a"  # lower-cased
        assert payload["aircraft"]["plane"] == "A320"
        assert fake_aircraft["want_plane"] is True

    def test_blank_result_is_not_found(self, capsys, monkeypatch):
        from utilities.lookups import aircraft as aircraft_service
        from utilities.lookups.results import AircraftInfo

        monkeypatch.setattr(
            aircraft_service, "lookup_aircraft", lambda ctx: AircraftInfo()
        )
        code, _, _ = run(capsys, "lookup", "aircraft", "000000")
        assert code == 1

    def test_fresh_drops_aircraft_cache(self, capsys, fake_aircraft, monkeypatch):
        from utilities.lookups import cache

        deleted = []
        monkeypatch.setattr(
            cache, "delete", lambda keys, kind: deleted.append((list(keys), kind))
        )
        run(capsys, "lookup", "aircraft", "406F3A", "--fresh")
        assert (["406f3a"], "aircraft") in deleted


# ---------------------------------------------------------------------------
# lookup location
# ---------------------------------------------------------------------------


class _FakeConfig:
    """Stand-in Config: simple-mode zone computed from in-memory overrides."""

    # Empty provider lists - resolve_chain walks nothing in these tests.
    flight_providers: list = []
    route_providers: list = []

    def __init__(self):
        self.data: dict = {}

    def set(self, key, value):
        self.data[key] = value

    @property
    def flight_lat(self):
        return self.data.get("flight_lat", 51.5)

    @property
    def flight_lng(self):
        return self.data.get("flight_lng", -1.0)

    @property
    def flight_radius(self):
        return self.data.get("flight_radius", 10.0)

    @property
    def flight_min_altitude(self):
        return self.data.get("flight_min_altitude", 100.0)

    @property
    def flight_max_altitude(self):
        return self.data.get("flight_max_altitude", 12000.0)

    @property
    def max_flight_lookup(self):
        return self.data.get("max_flight_lookup", 8)

    @property
    def zone_home(self):
        lat, lng, r = self.flight_lat, self.flight_lng, self.flight_radius
        lat_deg = r / 111.0
        lng_deg = r / 111.0
        return {
            "tl_y": lat + lat_deg,
            "tl_x": lng - lng_deg,
            "br_y": lat - lat_deg,
            "br_x": lng + lng_deg,
        }

    @property
    def location_home(self):
        return [self.flight_lat, self.flight_lng, 6371.0]


@pytest.fixture
def fake_location(monkeypatch):
    from setup.configuration import Config
    from utilities.flight import Flight
    from utilities.lookups import cache
    from utilities.lookups import flights as flights_module
    from utilities.lookups.flights import FlightFetchOutcome
    from utilities.lookups.results import FlightObservation
    from utilities.overhead import Overhead

    state = {"fresh_keys": [], "cfg": _FakeConfig()}

    def fake_fetch(query):
        state["query"] = query
        return FlightFetchOutcome(
            ok=True,
            observations=[FlightObservation(icao="406f3a", callsign="RYR215K")],
            provider_id="tar1090",
            source_name="tar1090",
        )

    def fake_to_flight(self, observation, enrichment):
        return Flight(callsign="RYR215K", origin="STN", destination="DUB")

    def fake_delete(keys, kind):
        state["fresh_keys"].append((list(keys), kind))
        return len(keys)

    monkeypatch.setattr(
        Config, "reload", classmethod(lambda cls: state["cfg"])
    )
    monkeypatch.setattr(flights_module, "fetch_flights", fake_fetch)
    monkeypatch.setattr(Overhead, "_to_flight", fake_to_flight)
    monkeypatch.setattr(cache, "delete", fake_delete)
    return state


class TestLocationCommand:
    def test_found(self, capsys, fake_location):
        code, payload, _ = run(capsys, "lookup", "location", "55.9", "-4.8", "40")
        assert code == 0
        assert payload["provider"]["id"] == "tar1090"
        assert payload["query"] == {"lat": 55.9, "lng": -4.8, "radius_km": 40.0}
        assert payload["count"] == 1
        assert payload["flights"][0]["callsign"] == "RYR215K"
        # The query honoured the CLI position, not the config default.
        assert fake_location["query"].zone["tl_y"] > 55.9

    def test_overrides_are_applied_in_memory(self, capsys, fake_location):
        run(
            capsys,
            "lookup",
            "location",
            "55.9",
            "-4.8",
            "40",
            "--max-flights",
            "3",
        )
        cfg = fake_location["cfg"].data
        assert cfg["flight_lat"] == 55.9
        assert cfg["flight_lng"] == -4.8
        assert cfg["flight_radius"] == 40.0
        assert cfg["max_flight_lookup"] == 3
        assert fake_location["query"].max_results == 3

    def test_fresh_drops_route_and_aircraft_entries(self, capsys, fake_location):
        run(capsys, "lookup", "location", "55.9", "-4.8", "40", "--fresh")
        assert (["RYR215K"], "route") in fake_location["fresh_keys"]
        assert (["406f3a"], "aircraft") in fake_location["fresh_keys"]

    def test_unavailable_exit_code(self, capsys, monkeypatch):
        from setup.configuration import Config
        from utilities.lookups import flights as flights_module
        from utilities.lookups.flights import FlightFetchOutcome

        monkeypatch.setattr(
            Config, "reload", classmethod(lambda cls: _FakeConfig())
        )

        original = flights_module.fetch_flights
        flights_module.fetch_flights = lambda q: FlightFetchOutcome(
            ok=False, errors=["tar1090: timeout"]
        )
        try:
            code, payload, _ = run(capsys, "lookup", "location", "55.9", "-4.8", "40")
        finally:
            flights_module.fetch_flights = original
        assert code == 1
        assert "unavailable" in payload["error"]
        assert payload["provider"]["errors"] == ["tar1090: timeout"]


# ---------------------------------------------------------------------------
# lookup providers
# ---------------------------------------------------------------------------


class TestProvidersCommand:
    def test_lists_chains_and_state(self, capsys):
        code, payload, _ = run(capsys, "lookup", "providers")
        assert code == 0
        assert set(payload["chains"]) == {"flights", "routes", "aircraft"}
        assert "fr24" in {p["provider"] for p in payload["providers"]}
        capabilities = {p["capability"] for p in payload["providers"]}
        assert capabilities == {"flights", "routes", "aircraft"}

    def test_usage_included_when_requested(self, capsys):
        code, payload, _ = run(capsys, "lookup", "providers", "--usage")
        assert code == 0
        assert "usage" in payload


# ---------------------------------------------------------------------------
# Dispatch wiring
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_no_subcommand_shows_lookup_help(self, capsys):
        code = dispatch_cli_command(["flight-tracker.py", "lookup"])
        assert code == 2
        assert "location" in capsys.readouterr().out  # lookup-specific help

    def test_unknown_subcommand_is_usage_error(self):
        with pytest.raises(SystemExit) as exc:
            dispatch_cli_command(["flight-tracker.py", "lookup", "wibble"])
        assert exc.value.code == 2

    def test_usage_text_mentions_lookup(self, capsys):
        code = dispatch_cli_command(["flight-tracker.py", "help"])
        assert code == 0
        assert "lookup" in capsys.readouterr().out

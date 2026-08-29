"""Tests for the lookups services - pipeline, caching rules, FR24 providers.

Replaces the legacy test_route_lookup.py suite, targeting the new
architecture: lookups.routes / lookups.aircraft services, the provider
adapters, and the FR24 bubble client.
"""

import sys
import time
import types
from unittest.mock import MagicMock

import pytest

from lookups.results import (
    AircraftInfo,
    FlightObservation,
    FlightQuery,
    LookupContext,
    LookupResult,
    RouteInfo,
)

# ---------------------------------------------------------------------------
# Stub the FlightRadar24 package so client.py's lazy import resolves.
# ---------------------------------------------------------------------------

if "FlightRadar24" not in sys.modules:
    _fr24_pkg = types.ModuleType("FlightRadar24")
    _fr24_api = types.ModuleType("FlightRadar24.api")
    _fr24_api.FlightRadar24API = MagicMock()
    _fr24_pkg.api = _fr24_api
    sys.modules["FlightRadar24"] = _fr24_pkg
    sys.modules["FlightRadar24.api"] = _fr24_api


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def isolated_caches(monkeypatch, tmp_path):
    """Isolate the persistent cache and reset quarantine state per test."""
    import lookups.cache as rc

    monkeypatch.setattr(rc, "CACHE_PATH", tmp_path / "routes_cache.json")
    monkeypatch.setattr(rc, "_cache", {})
    monkeypatch.setattr(rc, "_loaded", True)
    monkeypatch.setattr(rc, "_dirty", False)
    return rc


@pytest.fixture(autouse=True)
def reset_quarantine():
    from lookups.quarantine import QUARANTINE

    QUARANTINE.reset()
    yield
    QUARANTINE.reset()


class StubConfig:
    """Minimal Config stand-in for service resolution."""

    def __init__(self, route_providers=None, settings=None):
        self.route_providers = route_providers or []
        self._settings = settings or {}

    def provider_settings(self, pid):
        return dict(self._settings.get(pid, {}))


# ---------------------------------------------------------------------------
# hexdb parsing helpers
# ---------------------------------------------------------------------------


class TestParseRoute:
    def test_standard_route(self):
        from lookups.providers.hexdb.routes import parse_route

        assert parse_route("EGPF-LEMG") == ("EGPF", "LEMG")

    def test_lowercased(self):
        from lookups.providers.hexdb.routes import parse_route

        assert parse_route("egpf-lemg") == ("EGPF", "LEMG")

    def test_no_separator(self):
        from lookups.providers.hexdb.routes import parse_route

        assert parse_route("EGPF") == ("", "")

    def test_empty_string(self):
        from lookups.providers.hexdb.routes import parse_route

        assert parse_route("") == ("", "")


class TestParseAircraftType:
    def test_manufacturer_and_type(self):
        from lookups.providers.hexdb.aircraft import parse_aircraft_type

        data = {"Manufacturer": "Airbus", "ICAOTypeCode": "A320"}
        assert parse_aircraft_type(data) == "Airbus A320"

    def test_type_only(self):
        from lookups.providers.hexdb.aircraft import parse_aircraft_type

        assert (
            parse_aircraft_type({"Manufacturer": "", "ICAOTypeCode": "B738"}) == "B738"
        )

    def test_manufacturer_only(self):
        from lookups.providers.hexdb.aircraft import parse_aircraft_type

        assert (
            parse_aircraft_type({"Manufacturer": "Boeing", "ICAOTypeCode": ""})
            == "Boeing"
        )

    def test_missing_fields(self):
        from lookups.providers.hexdb.aircraft import parse_aircraft_type

        assert parse_aircraft_type({}) == ""


class TestHexdbParseOperatorIcao:
    def test_operator_flag_code(self):
        from lookups.providers.hexdb.aircraft import parse_operator_icao

        assert parse_operator_icao({"OperatorFlagCode": "RYR"}) == "RYR"

    def test_missing_field(self):
        from lookups.providers.hexdb.aircraft import parse_operator_icao

        assert parse_operator_icao({}) == ""

    def test_malformed_field_rejected(self):
        from lookups.providers.hexdb.aircraft import parse_operator_icao

        assert parse_operator_icao({"OperatorFlagCode": "G-ABCD"}) == ""


class TestOwnerLookup:
    """Registered owner name - the only identity a GA aircraft has."""

    def test_hexdb_parses_registered_owners(self):
        from lookups.providers.hexdb.aircraft import parse_owner

        assert (
            parse_owner({"RegisteredOwners": "Leading Edge Flight Training"})
            == "Leading Edge Flight Training"
        )

    def test_hexdb_owner_missing(self):
        from lookups.providers.hexdb.aircraft import parse_owner

        assert parse_owner({}) == ""


class TestCleanOperatorCode:
    def test_valid_code(self):
        from lookups.providers.common.operators import clean_operator_code

        assert clean_operator_code("BAW") == "BAW"

    def test_strips_whitespace(self):
        from lookups.providers.common.operators import clean_operator_code

        assert clean_operator_code(" RYR ") == "RYR"

    def test_rejects_wrong_length(self):
        from lookups.providers.common.operators import clean_operator_code

        assert clean_operator_code("AB") == ""
        assert clean_operator_code("ABCD") == ""

    def test_rejects_non_alpha(self):
        from lookups.providers.common.operators import clean_operator_code

        assert clean_operator_code("A1C") == ""

    def test_rejects_blank_and_none(self):
        from lookups.providers.common.operators import clean_operator_code

        assert clean_operator_code("") == ""
        assert clean_operator_code(None) == ""


# ---------------------------------------------------------------------------
# Route pipeline (run_route_pipeline with stub adapters)
# ---------------------------------------------------------------------------


class TestRoutePipeline:
    def _ctx(self, callsign="BAW123"):
        return LookupContext(callsign=callsign)

    def test_first_found_wins_higher_priority(self):
        import lookups.routes as rs

        first = MagicMock()
        first.lookup_route.return_value = LookupResult.found(
            RouteInfo(origin="LHR", destination="GLA")
        )
        second = MagicMock()
        second.lookup_route.return_value = LookupResult.found(
            RouteInfo(origin="EDI", destination="MAN", airline_icao="EZ Y")
        )

        result, answered, hit = rs.run_route_pipeline(
            self._ctx(), [("a", first), ("b", second)]
        )

        # Lower-priority providers do not overwrite; blanks fill only.
        assert result.origin == "LHR"
        assert result.destination == "GLA"
        assert hit == "a"
        # The route-only answer isn't "complete" (no plane/registration),
        # so the pipeline kept walking for the remaining fields.
        assert second.lookup_route.call_count == 1

    def test_merge_fills_blanks_from_lower_priority(self):
        import lookups.routes as rs

        first = MagicMock()
        first.lookup_route.return_value = LookupResult.found(
            RouteInfo(origin="LHR", destination="GLA", airline_icao="BAW")
        )
        second = MagicMock()
        second.lookup_route.return_value = LookupResult.found(
            RouteInfo(plane="Airbus A320", registration="G-XLEA")
        )

        result, _answered, _hit = rs.run_route_pipeline(
            self._ctx(), [("a", first), ("b", second)]
        )

        assert result.origin == "LHR"
        assert result.plane == "Airbus A320"
        assert result.registration == "G-XLEA"

    def test_not_found_continues_to_next_provider(self):
        import lookups.routes as rs

        first = MagicMock()
        first.lookup_route.return_value = LookupResult.not_found("nope")
        second = MagicMock()
        second.lookup_route.return_value = LookupResult.found(
            RouteInfo(origin="GLA", destination="AMS")
        )

        result, answered, hit = rs.run_route_pipeline(
            self._ctx(), [("a", first), ("b", second)]
        )

        assert result.origin == "GLA"
        assert answered is True
        assert hit == "b"

    def test_unavailable_quarantines_and_falls_through(self):
        import lookups.quarantine as q
        import lookups.routes as rs

        dead = MagicMock()
        dead.lookup_route.return_value = LookupResult.unavailable("429")
        healthy = MagicMock()
        healthy.lookup_route.return_value = LookupResult.found(
            RouteInfo(origin="GLA", destination="CDG")
        )

        result, answered, _hit = rs.run_route_pipeline(
            self._ctx(), [("dead", dead), ("healthy", healthy)]
        )

        assert result.origin == "GLA"
        assert answered is False  # silence is not ground truth
        assert q.QUARANTINE.is_quarantined("dead")

    def test_provider_crash_treated_as_unavailable(self):
        import lookups.quarantine as q
        import lookups.routes as rs

        bad = MagicMock()
        bad.lookup_route.side_effect = RuntimeError("boom")

        result, answered, _hit = rs.run_route_pipeline(self._ctx(), [("bad", bad)])

        assert result.origin == ""
        assert answered is False
        assert q.QUARANTINE.is_quarantined("bad")


# ---------------------------------------------------------------------------
# lookup_route service (cache interplay)
# ---------------------------------------------------------------------------


class TestLookupRouteService:
    def _providers(self, *adapters):
        return [(f"p{i}", a) for i, a in enumerate(adapters)]

    def test_positive_result_cached_under_callsign(self):
        import lookups.cache as rc
        import lookups.routes as rs

        adapter = MagicMock()
        adapter.lookup_route.return_value = LookupResult.found(
            RouteInfo(origin="LHR", destination="GLA", operator_icao="BAW", owner="BA")
        )

        ctx = LookupContext(callsign="BAW123")
        result = rs._run_pipeline_with_cache(ctx, "BAW123", [("a", adapter)])

        assert result.origin == "LHR"
        entry = rc.get("BAW123")
        assert entry is not None
        assert entry["origin"] == "LHR"
        # operator/owner belong to the airframe, never the callsign key
        assert "operator_icao" not in entry
        assert "owner" not in entry

    def test_all_not_found_caches_miss(self):
        import lookups.cache as rc
        import lookups.routes as rs

        adapter = MagicMock()
        adapter.lookup_route.return_value = LookupResult.not_found("no route")

        ctx = LookupContext(callsign="ZZZ999")
        result = rs._run_pipeline_with_cache(ctx, "ZZZ999", [("a", adapter)])

        assert result.origin == ""
        entry = rc.get("ZZZ999")
        assert entry is not None and entry.get("miss") is True

    def test_unavailable_not_miss_cached(self):
        import lookups.cache as rc
        import lookups.routes as rs

        adapter = MagicMock()
        adapter.lookup_route.return_value = LookupResult.unavailable("down")

        ctx = LookupContext(callsign="WWW111")
        rs._run_pipeline_with_cache(ctx, "WWW111", [("a", adapter)])

        assert rc.get("WWW111") is None

    def test_miss_entry_skips_providers(self):
        import lookups.cache as rc
        import lookups.routes as rs

        rc.put("ZZZ999", {"miss": True}, ttl=rc.CACHE_TTL_MISS)
        adapter = MagicMock()

        result = rs.lookup_route(
            LookupContext(callsign="ZZZ999"),
            cfg=StubConfig(route_providers=[{"provider": "a", "enabled": True}]),
        )

        adapter.lookup_route.assert_not_called()
        assert result.origin == ""

    def test_cached_route_returned_without_providers(self):
        import lookups.cache as rc
        import lookups.routes as rs

        rc.put(
            "BAW123",
            {
                "origin": "LHR",
                "destination": "GLA",
                "origin_name": "",
                "airline_icao": "BAW",
                "plane": "A319",
                "registration": "G-EUPD",
            },
        )
        adapter = MagicMock()

        result = rs.lookup_route(
            LookupContext(callsign="BAW123"),
            cfg=StubConfig(route_providers=[{"provider": "a", "enabled": True}]),
        )

        adapter.lookup_route.assert_not_called()
        assert result.origin == "LHR"
        assert result.plane == "A319"

    def test_stale_entry_reused_when_providers_fail(self, monkeypatch):
        import lookups.cache as rc
        import lookups.routes as rs

        # Seed a stale (expired-but-within-7-days) entry directly.
        stale_ts = time.time() - 2 * rs.cache.CACHE_TTL
        rc._cache["BAW123"] = {
            "origin": "LHR",
            "destination": "GLA",
            "_ts": stale_ts,
        }
        monkeypatch.setattr(rc, "_dirty", True)

        adapter = MagicMock()
        adapter.lookup_route.return_value = LookupResult.not_found("nope")

        ctx = LookupContext(callsign="BAW123")
        result = rs._run_pipeline_with_cache(ctx, "BAW123", [("a", adapter)])

        assert result.origin == "LHR"
        # Re-cached with the timestamp advanced 4h.  (The entry stays past
        # its normal TTL by design - it re-expires quickly so providers are
        # retried again soon - so assert on the raw entry, not get().)
        refreshed_ts = rc._cache["BAW123"]["_ts"]
        assert refreshed_ts == pytest.approx(stale_ts + rc.STALE_RECACHE_ADVANCE)

    def test_stale_entry_past_7_days_not_reused(self, monkeypatch):
        import lookups.cache as rc
        import lookups.routes as rs

        ancient_ts = time.time() - (rc.CACHE_TTL_STALE + 86400)
        rc._cache["BAW123"] = {
            "origin": "LHR",
            "destination": "GLA",
            "_ts": ancient_ts,
        }

        adapter = MagicMock()
        adapter.lookup_route.return_value = LookupResult.not_found("nope")

        ctx = LookupContext(callsign="BAW123")
        result = rs._run_pipeline_with_cache(ctx, "BAW123", [("a", adapter)])

        assert result.origin == ""
        # A miss was cached instead.
        assert rc.get(
            "BAW123",
        ) and rc.get(
            "BAW123"
        ).get("miss")

    def test_no_providers_dont_cache_miss(self):
        import lookups.cache as rc
        import lookups.routes as rs

        ctx = LookupContext(callsign="EMPTYY")
        rs._run_pipeline_with_cache(ctx, "EMPTYY", [])

        assert rc.get("EMPTYY") is None


# ---------------------------------------------------------------------------
# Aircraft pipeline
# ---------------------------------------------------------------------------


class TestAircraftPipeline:
    @pytest.fixture
    def install_providers(self, monkeypatch):
        """Return a helper that patches the aircraft provider resolver."""
        import lookups.aircraft as ac

        def _install(adapters):
            monkeypatch.setattr(
                ac, "resolve_aircraft_providers", lambda cfg=None: adapters
            )

        return _install

    def test_first_hit_wins(self):
        import lookups.aircraft as ac

        first = MagicMock()
        first.lookup_aircraft.return_value = LookupResult.found(
            AircraftInfo(plane="C172", registration="G-BSFE")
        )
        second = MagicMock()

        ctx = LookupContext(callsign="", mode_s="400f5a")
        info, answered, hit = ac.run_aircraft_pipeline(
            ctx, [("a", first), ("b", second)]
        )

        assert info.plane == "C172"
        # A C172/G-BSFE answer lacks operator_icao, so the pipeline kept
        # walking to fill the remaining identity fields.
        assert second.lookup_aircraft.call_count == 1
        assert hit == "a"

    def test_identity_only_does_not_stop_chain(self):
        """A provider returning only operator/owner is retained but the
        chain keeps walking for the type (legacy chain behaviour)."""
        import lookups.aircraft as ac

        identity_only = MagicMock()
        identity_only.lookup_aircraft.return_value = LookupResult.found(
            AircraftInfo(operator_icao="FLY", owner="Flying Club")
        )
        full = MagicMock()
        full.lookup_aircraft.return_value = LookupResult.found(
            AircraftInfo(plane="C172", registration="G-BSFE")
        )

        ctx = LookupContext(callsign="", mode_s="400f5a")
        info, _answered, _hit = ac.run_aircraft_pipeline(
            ctx, [("a", identity_only), ("b", full)]
        )

        # merge_missing keeps the identity fields and fills type/registration
        assert info.plane == "C172"
        assert info.operator_icao == "FLY"
        assert info.owner == "Flying Club"

    def test_blank_result_cached_24h_when_all_answered(self, install_providers):
        import lookups.aircraft as ac
        import lookups.cache as rc

        adapter = MagicMock()
        adapter.lookup_aircraft.return_value = LookupResult.not_found("404")
        install_providers([("hexdb", adapter)])

        ctx = LookupContext(callsign="", mode_s="000000")
        info = ac.lookup_aircraft(ctx)

        assert not info.plane
        entry = rc.get("000000")
        assert entry is not None
        assert entry["plane"] == ""

    def test_unavailable_not_cached(self, install_providers):
        import lookups.aircraft as ac
        import lookups.cache as rc

        adapter = MagicMock()
        adapter.lookup_aircraft.return_value = LookupResult.unavailable("dead")
        install_providers([("hexdb", adapter)])

        ctx = LookupContext(callsign="", mode_s="111111")
        ac.lookup_aircraft(ctx)

        assert rc.get("111111") is None

    def test_cached_positive_short_circuits(self, install_providers):
        import lookups.aircraft as ac
        import lookups.cache as rc

        rc.put("400f5a", {"plane": "A320", "registration": "G-EUXM"})
        adapter = MagicMock()
        install_providers([("hexdb", adapter)])

        ctx = LookupContext(callsign="", mode_s="400f5a")
        info = ac.lookup_aircraft(ctx)

        adapter.lookup_aircraft.assert_not_called()
        assert info.plane == "A320"

    def test_stale_reused_with_fresh_identity(self, install_providers, monkeypatch):
        import lookups.aircraft as ac
        import lookups.cache as rc

        stale_ts = time.time() - 2 * ac.cache.CACHE_TTL
        rc._cache["400f5a"] = {
            "plane": "A320",
            "registration": "G-EUXM",
            "operator_icao": "",
            "owner": "",
            "_ts": stale_ts,
        }

        adapter = MagicMock()
        # Fresh answer: nothing useful, but resolves the operator.
        adapter.lookup_aircraft.return_value = LookupResult.found(
            AircraftInfo(operator_icao="BAW")
        )
        install_providers([("hexdb", adapter)])

        ctx = LookupContext(callsign="", mode_s="400f5a")
        info = ac.lookup_aircraft(ctx)

        assert info.plane == "A320"  # stale
        assert info.operator_icao == "BAW"  # fresh beats blank
        # Re-cached with the advanced timestamp.
        assert rc._cache["400f5a"]["_ts"] == pytest.approx(
            stale_ts + rc.STALE_RECACHE_ADVANCE
        )


# ---------------------------------------------------------------------------
# FR24 route provider (client mocked)
# ---------------------------------------------------------------------------


def _feed_flight(callsign="BAW123", origin="LHR", dest="GLA", registration="G-EUPX"):
    flight = MagicMock()
    flight.callsign = callsign
    flight.origin_airport_iata = origin
    flight.destination_airport_iata = dest
    flight.registration = registration
    flight.airline_icao = "BAW"
    flight.aircraft_code = "A319"
    return flight


class TestFr24RouteProvider:
    @pytest.fixture
    def client(self):
        client = MagicMock()
        client.recently_missed.return_value = False
        client.match_in_bubble.return_value = None
        return client

    @pytest.fixture
    def provider(self, client, monkeypatch):
        import lookups.providers.fr24.routes as fr

        monkeypatch.setattr(fr, "get_client", lambda: client)
        from lookups.providers.fr24.routes import RouteProvider

        return RouteProvider({})

    def test_no_callsign_is_not_found(self, provider):
        result = provider.lookup_route(LookupContext(callsign="", lat=55, lng=-4))
        assert result.is_not_found

    def test_no_position_is_not_found(self, provider):
        result = provider.lookup_route(LookupContext(callsign="BAW123"))
        assert result.is_not_found

    def test_recent_miss_short_circuits(self, provider, client):
        client.recently_missed.return_value = True

        result = provider.lookup_route(LookupContext(callsign="BAW123", lat=55, lng=-4))

        assert result.is_not_found
        client.match_in_bubble.assert_not_called()

    def test_no_bubble_match_records_feed_miss(self, provider, client):
        client.match_in_bubble.return_value = None

        ctx = LookupContext(callsign="ZZZ999", lat=55.0, lng=-4.0, ground_speed_mps=100)
        result = provider.lookup_route(ctx)

        assert result.is_not_found
        client.record_feed_miss.assert_called_once_with("ZZZ999")

    def test_match_found_route(self, provider, client):
        client.match_in_bubble.return_value = _feed_flight()

        ctx = LookupContext(callsign="BAW123", lat=55.0, lng=-4.0)
        result = provider.lookup_route(ctx)

        assert result.is_found
        assert result.value.origin == "LHR"
        assert result.value.destination == "GLA"
        assert result.value.airline_icao == "BAW"
        client.clear_feed_miss.assert_called_once_with("BAW123")

    def test_match_without_route_data_is_not_found(self, provider, client):
        """A matched flight with no route fields doesn't claim FOUND and
        leaves the feed miss cleared (the aircraft provider may still
        resolve the type from the same bubble)."""
        client.match_in_bubble.return_value = _feed_flight(origin="", dest="")

        ctx = LookupContext(callsign="BAW123", lat=55.0, lng=-4.0)
        result = provider.lookup_route(ctx)

        assert result.is_not_found
        client.record_feed_miss.assert_not_called()
        client.clear_feed_miss.assert_not_called()


# ---------------------------------------------------------------------------
# FR24 aircraft provider (client mocked)
# ---------------------------------------------------------------------------


class TestFr24AircraftProvider:
    @pytest.fixture
    def client(self):
        client = MagicMock()
        client.recently_missed.return_value = False
        client.match_in_bubble.return_value = None
        client.aircraft_model_text.return_value = "Airbus A319"
        return client

    @pytest.fixture
    def provider(self, client, monkeypatch):
        import lookups.providers.fr24.aircraft as fr

        monkeypatch.setattr(fr, "get_client", lambda: client)
        from lookups.providers.fr24.aircraft import AircraftProvider

        return AircraftProvider({})

    def _ctx(self, want_plane=True):
        return LookupContext(
            callsign="BAW123", lat=55.0, lng=-4.0, want_plane=want_plane
        )

    def test_plane_not_requested_is_not_found(self, provider, client):
        result = provider.lookup_aircraft(self._ctx(want_plane=False))
        assert result.is_not_found
        client.match_in_bubble.assert_not_called()

    def test_no_match_records_miss(self, provider, client):
        client.match_in_bubble.return_value = None
        result = provider.lookup_aircraft(self._ctx())
        assert result.is_not_found
        client.record_feed_miss.assert_called_once()

    def test_model_text_found(self, provider, client):
        client.match_in_bubble.return_value = _feed_flight()
        result = provider.lookup_aircraft(self._ctx())
        assert result.is_found
        assert result.value.plane == "Airbus A319"
        assert result.value.registration == "G-EUPX"

    def test_no_model_text_is_not_found(self, provider, client):
        client.match_in_bubble.return_value = _feed_flight()
        client.aircraft_model_text.return_value = ""
        result = provider.lookup_aircraft(self._ctx())
        assert result.is_not_found


# ---------------------------------------------------------------------------
# FR24 client singleton behaviour
# ---------------------------------------------------------------------------


class TestFr24Client:
    def test_bubble_radius_bounds(self):
        from lookups.providers.fr24.client import bubble_radius_for

        assert bubble_radius_for(0) == 1000  # baseline
        assert bubble_radius_for(10) == 1000  # 10*30=300 -> baseline
        assert bubble_radius_for(100) == 3000  # 100*30
        assert bubble_radius_for(1000) == 20000  # capped

    def test_bubble_memo_shares_one_feed_call(self):
        from lookups.providers.fr24 import client as fc

        c = fc.FR24Client()
        api = MagicMock()
        api.get_bounds_by_point.return_value = {"b": 1}
        api.get_flights.return_value = [_feed_flight()]
        c._api = api

        first = c.bubble_flights("BAW123", 55.0, -4.0, 100)
        second = c.bubble_flights("BAW123", 55.0, -4.0, 100)

        assert api.get_flights.call_count == 1
        assert first == second

    def test_miss_ttl_expiry(self, monkeypatch):
        from lookups.providers.fr24 import client as fc

        c = fc.FR24Client()
        fake_time = [1000.0]
        monkeypatch.setattr(fc.time, "monotonic", lambda: fake_time[0])

        c.record_feed_miss("BAW123")
        assert c.recently_missed("BAW123") is True

        fake_time[0] += fc.MISS_TTL_S + 1
        assert c.recently_missed("BAW123") is False

    def test_get_client_singleton(self):
        from lookups.providers.fr24 import client as fc

        fc.reset_client()
        assert fc.get_client() is fc.get_client()
        fc.reset_client()
        assert fc._client is None


# ---------------------------------------------------------------------------
# Flights service
# ---------------------------------------------------------------------------


class TestFlightsService:
    def _query(self):
        return FlightQuery(
            zone={"tl_y": 56.0, "tl_x": -5.0, "br_y": 55.0, "br_x": -3.0},
            home=[55.5, -4.0, 6371.0],
        )

    def _patch_resolution(self, monkeypatch, providers):
        """Patch provider resolution so [(pid, adapter)] stubs are used."""
        import lookups.flights as fs

        monkeypatch.setattr(fs, "_chain", lambda: providers)

    def test_first_provider_answers(self, monkeypatch):
        import lookups.flights as fs

        obs = [FlightObservation(callsign="BAW123")]
        adapter = MagicMock()
        adapter.fetch.return_value = LookupResult.found(obs)
        self._patch_resolution(monkeypatch, [("fr24", adapter)])

        outcome = fs.fetch_flights(self._query())
        assert outcome.ok is True
        assert outcome.provider_id == "fr24"
        assert outcome.observations == obs

    def test_unavailable_falls_through(self, monkeypatch):
        import lookups.flights as fs

        dead = MagicMock()
        dead.fetch.return_value = LookupResult.unavailable("429")
        good = MagicMock()
        good.fetch.return_value = LookupResult.found(
            [FlightObservation(callsign="KLM1")]
        )
        self._patch_resolution(monkeypatch, [("dead", dead), ("good", good)])

        outcome = fs.fetch_flights(self._query())
        assert outcome.ok is True
        assert outcome.provider_id == "good"

    def test_all_unavailable_is_error(self, monkeypatch):
        import lookups.flights as fs

        dead = MagicMock()
        dead.fetch.return_value = LookupResult.unavailable("down")
        self._patch_resolution(monkeypatch, [("dead", dead)])

        outcome = fs.fetch_flights(self._query())
        assert outcome.ok is False
        assert outcome.errors

    def test_empty_list_is_ok_empty_sky(self, monkeypatch):
        import lookups.flights as fs

        adapter = MagicMock()
        adapter.fetch.return_value = LookupResult.found([])
        self._patch_resolution(monkeypatch, [("empty", adapter)])

        outcome = fs.fetch_flights(self._query())
        assert outcome.ok is True
        assert outcome.observations == []

    def test_quarantined_provider_skipped(self, monkeypatch):
        import lookups.flights as fs
        from lookups.quarantine import QUARANTINE

        QUARANTINE.record_failure("skipped")
        skipped = MagicMock()
        healthy = MagicMock()
        healthy.fetch.return_value = LookupResult.found(
            [FlightObservation(callsign="X")]
        )
        self._patch_resolution(
            monkeypatch, [("skipped", skipped), ("healthy", healthy)]
        )

        outcome = fs.fetch_flights(self._query())
        skipped.fetch.assert_not_called()
        assert outcome.provider_id == "healthy"

    def test_adapter_crash_quarantines(self, monkeypatch):
        import lookups.flights as fs
        from lookups.quarantine import QUARANTINE

        crashy = MagicMock()
        crashy.fetch.side_effect = RuntimeError("boom")
        self._patch_resolution(monkeypatch, [("crashy", crashy)])

        outcome = fs.fetch_flights(self._query())
        assert outcome.ok is False
        assert QUARANTINE.is_quarantined("crashy")


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_normalise_drops_unknown_provider(self):
        from lookups.registry import normalise_provider_list

        clean, warnings = normalise_provider_list(
            [{"provider": "nosuch", "enabled": True}], "flights"
        )
        assert clean == []
        assert warnings

    def test_normalise_drops_capability_mismatch(self):
        from lookups.registry import normalise_provider_list

        # hexdb cannot serve flights
        clean, _warnings = normalise_provider_list(
            [{"provider": "hexdb", "enabled": True}], "flights"
        )
        assert clean == []

    def test_normalise_coerces_enabled_to_bool(self):
        from lookups.registry import normalise_provider_list

        clean, _warnings = normalise_provider_list(
            [{"provider": "fr24", "enabled": "yes"}], "flights"
        )
        assert clean == [{"provider": "fr24", "enabled": True}]

    def test_normalise_dedupes(self):
        from lookups.registry import normalise_provider_list

        clean, warnings = normalise_provider_list(
            [
                {"provider": "fr24", "enabled": True},
                {"provider": "fr24", "enabled": False},
            ],
            "flights",
        )
        assert len(clean) == 1
        assert clean[0]["enabled"] is True

    def test_catalogue_capabilities(self):
        from lookups.registry import PROVIDERS

        assert "flights" in PROVIDERS["fr24"].capabilities
        assert "routes" in PROVIDERS["fr24"].capabilities
        assert "aircraft" in PROVIDERS["fr24"].capabilities
        assert "flights" in PROVIDERS["tar1090"].capabilities
        assert "routes" not in PROVIDERS["tar1090"].capabilities
        assert "routes" in PROVIDERS["hexdb"].capabilities
        assert "aircraft" in PROVIDERS["hexdb"].capabilities
        assert "flights" not in PROVIDERS["adsbdb"].capabilities


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------


class TestEnrichment:
    def test_prefill_priority_over_providers(self, monkeypatch):
        import lookups.routes as rs
        from lookups.enrichment import enrich

        adapter = MagicMock()
        adapter.lookup_route.return_value = LookupResult.found(
            RouteInfo(origin="EDI", destination="MAN")  # must NOT win
        )

        def fake_resolver(cfg=None):
            return [("hexdb", adapter)]

        monkeypatch.setattr(rs, "resolve_route_providers", fake_resolver)

        obs = FlightObservation(
            callsign="BAW123",
            icao="400f5a",
            latitude=55.9,
            longitude=-4.3,
            origin="LHR",
            destination="GLA",
        )
        route = enrich(obs)
        assert route.origin == "LHR"
        assert route.destination == "GLA"

    def test_operator_icao_replaced_by_aircraft_pipeline(self, monkeypatch):
        import lookups.aircraft as ac
        import lookups.routes as rs
        from lookups.enrichment import enrich

        # The route pipeline is unavailable for the callsign; a distinct
        # (non-quarantined) provider supplies the airframe answer.
        route_adapter = MagicMock()
        route_adapter.lookup_route.return_value = LookupResult.unavailable("none")

        monkeypatch.setattr(
            rs,
            "resolve_route_providers",
            lambda cfg=None: [("routeprov", route_adapter)],
        )

        aircraft_adapter = MagicMock()
        aircraft_adapter.lookup_aircraft.return_value = LookupResult.found(
            AircraftInfo(plane="A320", registration="G-XLEH", operator_icao="BAW")
        )
        monkeypatch.setattr(
            ac,
            "resolve_aircraft_providers",
            lambda cfg=None: [("aircraftprov", aircraft_adapter)],
        )

        obs = FlightObservation(callsign="BAW123", icao="400f5a")
        route = enrich(obs)
        assert route.plane == "A320"
        assert route.operator_icao == "BAW"

    def test_no_callsign_still_enriches_airframe(self, monkeypatch):
        """GA aircraft without a callsign still get their type resolved."""
        import lookups.aircraft as ac
        from lookups.enrichment import enrich

        aircraft_adapter = MagicMock()
        aircraft_adapter.lookup_aircraft.return_value = LookupResult.found(
            AircraftInfo(plane="C172", registration="G-BSFE")
        )
        monkeypatch.setattr(
            ac,
            "resolve_aircraft_providers",
            lambda cfg=None: [("hexdb", aircraft_adapter)],
        )

        obs = FlightObservation(callsign="", icao="400f5a")
        route = enrich(obs)
        assert route.plane == "C172"


# ---------------------------------------------------------------------------
# ICAO->IATA conversion + hexdb airport enrichment (real bundled table)
# ---------------------------------------------------------------------------


class TestIcaoToIata:
    def test_known_code(self):
        from lookups.providers.common.airports import icao_to_iata_code

        assert icao_to_iata_code("EGPF") == "GLA"

    def test_unknown_code_returns_empty(self):
        from lookups.providers.common.airports import icao_to_iata_code

        assert icao_to_iata_code("ZZZZ") == ""

    def test_blank_and_none(self):
        from lookups.providers.common.airports import icao_to_iata_code

        assert icao_to_iata_code("") == ""
        assert icao_to_iata_code(None) == ""

    def test_lowercase_normalised(self):
        from lookups.providers.common.airports import icao_to_iata_code

        assert icao_to_iata_code("egpf") == "GLA"


class TestHexdbRouteLookup:
    """End-to-end route adapter test with a stubbed HTTP layer."""

    @pytest.fixture
    def adapter(self):
        from lookups.providers.hexdb.routes import RouteProvider

        return RouteProvider({})

    def test_route_found_and_enriched(self, adapter, monkeypatch):
        from lookups.providers.hexdb import routes as hex_routes

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"route": "EGPF-EGAA"}
        monkeypatch.setattr(hex_routes, "_get", lambda url, timeout=10: response)

        result = adapter.lookup_route(LookupContext(callsign="BAW123"))

        assert result.is_found
        # ICAO codes converted via the bundled table (EGPF->GLA, EGAA->BFS)
        assert result.value.origin == "GLA"
        assert result.value.destination == "BFS"
        # Airport names enriched from the bundled airports.json
        assert result.value.origin_name != ""
        assert result.value.destination_name != ""

    def test_404_is_not_found(self, adapter, monkeypatch):
        from lookups.providers.hexdb import routes as hex_routes

        response = MagicMock()
        response.status_code = 404
        monkeypatch.setattr(hex_routes, "_get", lambda url, timeout=10: response)

        result = adapter.lookup_route(LookupContext(callsign="ZZZ999"))
        assert result.is_not_found

    def test_unconvertible_codes_are_not_found(self, adapter, monkeypatch):
        from lookups.providers.hexdb import routes as hex_routes

        response = MagicMock()
        response.status_code = 200
        response.json.return_value = {"route": "ZZZZ-QQQQ"}
        monkeypatch.setattr(hex_routes, "_get", lambda url, timeout=10: response)

        result = adapter.lookup_route(LookupContext(callsign="BAW123"))
        assert result.is_not_found

    def test_connection_error_is_unavailable(self, adapter, monkeypatch):
        from requests.exceptions import ConnectionError as ReqConnError

        from lookups.providers.hexdb import routes as hex_routes

        def boom(url, timeout=10):
            raise ReqConnError("nope")

        monkeypatch.setattr(hex_routes, "_get", boom)

        result = adapter.lookup_route(LookupContext(callsign="BAW123"))
        assert result.is_unavailable

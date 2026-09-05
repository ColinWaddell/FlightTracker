"""Tests for lookups/usage.py - tallying, debounced flushing, summary ranges."""

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_usage(tmp_path, monkeypatch):
    """Redirect the usage db to a temp file and reset the in-memory state."""
    import utilities.lookups.usage as ru

    monkeypatch.setattr(ru, "DB_PATH", tmp_path / "usage.sqlite3")
    monkeypatch.setattr(ru, "_conn", None)
    monkeypatch.setattr(ru, "_providers_dirty", {})
    monkeypatch.setattr(ru, "_cache_dirty", {})
    monkeypatch.setattr(ru, "_last_flush", 0.0)
    yield ru
    if ru._conn is not None:
        ru._conn.close()
        ru._conn = None


@pytest.fixture()
def isolated_cache(tmp_path, monkeypatch):
    """Redirect the lookup cache db to a temp file (independence tests)."""
    import utilities.lookups.cache as rc

    monkeypatch.setattr(rc, "DB_PATH", tmp_path / "cache.sqlite3")
    monkeypatch.setattr(rc, "LEGACY_JSON_PATH", tmp_path / "routes_cache.json")
    monkeypatch.setattr(rc, "_conn", None)
    yield rc
    if rc._conn is not None:
        rc._conn.close()
        rc._conn = None


class TestRecording:
    def test_record_accumulates_events(self, isolated_usage):
        ru = isolated_usage
        ru.record("routes", "hexdb", "attempt")
        ru.record("routes", "hexdb", "attempt")
        assert ru._providers_dirty == {(ru._today(), "routes", "hexdb", "attempt"): 2}

    def test_record_n_accumulates_quantities(self, isolated_usage):
        ru = isolated_usage
        # aircraft returned is a SUM: 15 + 12 aircraft across two answers
        ru.record("flights", "tar1090", "aircraft", n=15)
        ru.record("flights", "tar1090", "aircraft", n=12)
        assert (
            ru._providers_dirty[(ru._today(), "flights", "tar1090", "aircraft")] == 27
        )

    def test_record_ignores_zero_and_negative(self, isolated_usage):
        ru = isolated_usage
        ru.record("routes", "hexdb", "attempt", 0)
        ru.record("routes", "hexdb", "attempt", -1)
        assert ru._providers_dirty == {}

    def test_record_cache(self, isolated_usage):
        ru = isolated_usage
        ru.record_cache("routes", "hit")
        ru.record_cache("routes", "hit")
        ru.record_cache("routes", "miss")
        assert ru._cache_dirty == {
            (ru._today(), "routes", "hit"): 2,
            (ru._today(), "routes", "miss"): 1,
        }


class TestFlushing:
    def test_flush_writes_and_clears(self, isolated_usage):
        ru = isolated_usage
        ru.record("routes", "hexdb", "attempt")
        ru.record("routes", "hexdb", "no_result", 3)
        ru.record_cache("routes", "miss")
        ru.flush()

        assert ru._providers_dirty == {}
        assert ru._cache_dirty == {}
        # straight from the database
        rows = ru._conn.execute(
            "SELECT kind, provider, outcome, n FROM provider_hits"
        ).fetchall()
        assert set(rows) == {
            ("routes", "hexdb", "attempt", 1),
            ("routes", "hexdb", "no_result", 3),
        }
        # the no_result row accumulated n=3
        n = ru._conn.execute(
            "SELECT n FROM provider_hits WHERE outcome = 'no_result'"
        ).fetchone()[0]
        assert n == 3

    def test_flush_debounces(self, isolated_usage, monkeypatch):
        ru = isolated_usage
        ru.record("routes", "hexdb", "attempt")
        ru._last_flush = ru._now()  # flushed a moment ago
        ru.flush_if_due()
        assert ru._providers_dirty, "within the debounce window nothing is written"
        ru.flush()  # forced writes regardless
        assert ru._providers_dirty == {}

    def test_flush_if_due_after_interval(self, isolated_usage, monkeypatch):
        ru = isolated_usage
        clock = {"t": 100.0}
        monkeypatch.setattr(ru, "_now", lambda: clock["t"])
        ru.record("routes", "hexdb", "attempt")
        clock["t"] += ru.FLUSH_EVERY_S + 1
        ru.flush_if_due()
        assert ru._providers_dirty == {}

    def test_flush_noop_on_empty(self, isolated_usage):
        ru = isolated_usage
        ru.flush()  # must not create/require anything, or raise
        assert ru._conn is None  # nothing was ever written

    def test_failed_flush_keeps_counters(self, isolated_usage, monkeypatch):
        ru = isolated_usage
        broken = "INSERT INTO nope VALUES (1)"
        original = ru.PROVIDER_UPSERT
        ru.record("routes", "hexdb", "attempt")
        # Break the upsert: the counters must survive a failed flush.
        monkeypatch.setattr(ru, "PROVIDER_UPSERT", broken)
        ru.flush()
        assert ru._providers_dirty, "counters stay queued on write failure"
        # Restore within the still-isolated test and retry.
        monkeypatch.setattr(ru, "PROVIDER_UPSERT", original)
        ru.flush()
        assert ru._providers_dirty == {}
        assert ru._conn.execute("SELECT COUNT(*) FROM provider_hits").fetchone()[0] == 1


class TestPersistence:
    def test_tallies_survive_connection_reset(self, isolated_usage):
        ru = isolated_usage
        ru.record("aircraft", "adsbdb", "attempt")
        ru.record_cache("aircraft", "hit")
        ru.flush()
        ru._conn = None  # simulate a restart
        result = ru.summary()
        assert result["providers"]["aircraft"]["adsbdb"] == {
            "attempts": 1,
            "no_results": 0,
        }
        assert result["cache"]["aircraft"] == {"hits": 1, "misses": 0}

    def test_corrupt_db_moved_aside_and_rebuilt(self, isolated_usage):
        ru = isolated_usage
        ru.record("routes", "hexdb", "attempt")
        ru.flush()
        ru._conn = None
        for suffix in ("", "-wal", "-shm"):
            sidecar = Path(f"{ru.DB_PATH}{suffix}")
            if sidecar.exists():
                sidecar.write_bytes(b"this is not a database" * 200)

        # fresh, working tallies after recovery
        assert ru.summary()["providers"]["routes"] == {}
        leftovers = [
            p.name for p in ru.DB_PATH.parent.iterdir() if ".corrupt-" in p.name
        ]
        assert leftovers, "corrupt usage db should be moved aside"

    def test_usable_when_unwritable(self, isolated_usage, tmp_path, monkeypatch):
        ru = isolated_usage
        blocker = tmp_path / "blocker"
        blocker.write_text("a file, not a directory")
        monkeypatch.setattr(ru, "DB_PATH", tmp_path / "blocker" / "usage.sqlite3")

        ru.record("routes", "hexdb", "attempt")
        ru.flush()  # falls back to memory; must not raise
        assert ru.summary()["providers"]["routes"]["hexdb"]["attempts"] == 1
        assert not (tmp_path / "blocker" / "usage.sqlite3").exists()


class TestDayBucketing:
    def test_days_roll_separately(self, isolated_usage, monkeypatch):
        ru = isolated_usage
        monkeypatch.setattr(ru, "_today", lambda: "2026-08-30")
        ru.record("routes", "hexdb", "attempt")
        monkeypatch.setattr(ru, "_today", lambda: "2026-08-31")
        ru.record("routes", "hexdb", "attempt")
        ru.flush()

        full = ru.summary()
        assert full["providers"]["routes"]["hexdb"]["attempts"] == 2

        day1 = ru.summary(start="2026-08-30", end="2026-08-30")
        assert day1["providers"]["routes"]["hexdb"]["attempts"] == 1
        assert day1["range"] == {"start": "2026-08-30", "end": "2026-08-30"}

    def test_range_is_inclusive_and_filtered(self, isolated_usage, monkeypatch):
        ru = isolated_usage
        monkeypatch.setattr(ru, "_today", lambda: "2026-08-30")
        ru.record("routes", "hexdb", "attempt")
        monkeypatch.setattr(ru, "_today", lambda: "2026-08-31")
        ru.record("routes", "hexdb", "no_result")

        within = ru.summary(start="2026-08-30", end="2026-08-30")
        assert within["providers"]["routes"]["hexdb"] == {
            "attempts": 1,
            "no_results": 0,
        }
        assert within["range"] == {"start": "2026-08-30", "end": "2026-08-30"}

        open_ended = ru.summary(end="2026-08-30")
        assert open_ended["providers"]["routes"]["hexdb"] == {
            "attempts": 1,
            "no_results": 0,
        }
        assert open_ended["range"] == {"start": None, "end": "2026-08-30"}
        # and the unbounded side picks up only the later day
        assert ru.summary(start="2026-08-31")["providers"]["routes"]["hexdb"] == {
            "attempts": 0,
            "no_results": 1,
        }
        assert open_ended["range"] == {"start": None, "end": "2026-08-30"}

    def test_start_after_end_is_swapped(self, isolated_usage, monkeypatch):
        ru = isolated_usage
        monkeypatch.setattr(ru, "_today", lambda: "2026-08-30")
        ru.record("routes", "hexdb", "attempt")
        late = ru.summary(start="2026-08-29", end="2026-08-30")
        assert late["providers"]["routes"]["hexdb"]["attempts"] == 1


class TestSummaryShape:
    def test_empty_database_has_stable_shape(self, isolated_usage):
        ru = isolated_usage
        result = ru.summary()
        assert result["range"] == {"start": None, "end": None}
        assert result["cache"] == {
            "routes": {"hits": 0, "misses": 0},
            "aircraft": {"hits": 0, "misses": 0},
        }
        assert result["providers"] == {"flights": {}, "routes": {}, "aircraft": {}}

    def test_flights_outcomes_map_to_api_shape(self, isolated_usage):
        ru = isolated_usage
        ru.record("flights", "tar1090", "api_call", 3)
        ru.record("flights", "tar1090", "aircraft", 42)
        result = ru.summary()
        assert result["providers"]["flights"]["tar1090"] == {
            "api_calls": 3,
            "aircraft": 42,
        }

    def test_summary_includes_unflushed_counters(self, isolated_usage):
        ru = isolated_usage
        ru.record("routes", "hexdb", "attempt")
        # no flush() - summary must flush first (read-your-writes)
        assert ru.summary()["providers"]["routes"]["hexdb"]["attempts"] == 1


class TestCacheClearIndependence:
    def test_cache_clear_does_not_touch_usage(self, isolated_cache, isolated_usage):
        rc, ru = isolated_cache, isolated_usage
        rc.put("BAW123", {"plane": "A320"}, kind=rc.KIND_ROUTE)
        ru.record("routes", "hexdb", "attempt")
        ru.flush()
        rc.clear()
        assert ru.summary()["providers"]["routes"]["hexdb"]["attempts"] == 1


class TestCollectionToggle:
    def test_disabled_collection_records_nothing(self, isolated_usage, monkeypatch):
        ru = isolated_usage
        monkeypatch.setattr(ru, "_collection_enabled", lambda: False)
        ru.record("routes", "hexdb", "attempt")
        ru.record("flights", "tar1090", "aircraft", n=7)
        ru.record_cache("routes", "miss")
        ru.flush()
        assert ru.summary()["providers"] == {
            "flights": {},
            "routes": {},
            "aircraft": {},
        }
        assert ru.summary()["cache"]["routes"] == {"hits": 0, "misses": 0}

    def test_gate_defaults_on_without_config(self, isolated_usage, monkeypatch):
        """A config hiccup must never stop tallying (fail-open)."""
        ru = isolated_usage
        monkeypatch.setattr(ru, "_collection_enabled", lambda: True)
        ru.record("routes", "hexdb", "attempt")
        assert next(iter(ru._providers_dirty.values())) == 1


class TestClear:
    def test_clear_wipes_pending_and_history(self, isolated_usage):
        ru = isolated_usage
        ru.record("routes", "hexdb", "attempt", 4)
        ru.record_cache("aircraft", "hit")
        ru.flush()
        assert ru.summary()["providers"]["routes"]["hexdb"]["attempts"] == 4
        ru.record("routes", "hexdb", "attempt")  # unflushed, should go too
        ru.clear()
        result = ru.summary()
        assert result["providers"]["routes"] == {}
        assert result["cache"]["aircraft"] == {"hits": 0, "misses": 0}
        assert ru._conn.execute("SELECT COUNT(*) FROM provider_hits").fetchone()[0] == 0
        assert ru._conn.execute("SELECT COUNT(*) FROM cache_events").fetchone()[0] == 0

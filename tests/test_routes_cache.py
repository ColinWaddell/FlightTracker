"""Tests for lookups/cache.py - SQLite backend, TTL, kinds, legacy import."""

import json
import threading
import time
import types
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Redirect the cache to a temp database (and legacy JSON source)."""
    import scenes.flight.lookups.cache as rc

    monkeypatch.setattr(rc, "DB_PATH", tmp_path / "cache.sqlite3")
    monkeypatch.setattr(rc, "LEGACY_JSON_PATH", tmp_path / "routes_cache.json")
    monkeypatch.setattr(rc, "_conn", None)
    yield rc
    if rc._conn is not None:
        rc._conn.close()
        rc._conn = None


def _put_stale(rc, key, info, kind, extra_seconds):
    """Store an entry aged past its default TTL by *extra_seconds*."""
    rc.put(key, info, ts=time.time() - rc.CACHE_TTL - extra_seconds, kind=kind)


class TestRoutesCacheGet:
    def test_miss_on_empty_cache(self, isolated_cache):
        rc = isolated_cache
        assert rc.get("BAW123", rc.KIND_ROUTE) is None

    def test_hit_after_put(self, isolated_cache):
        rc = isolated_cache
        rc.put(
            "BAW123",
            {"plane": "A320", "origin": "LHR", "destination": "GLA"},
            kind=rc.KIND_ROUTE,
        )
        result = rc.get("BAW123", rc.KIND_ROUTE)
        assert result is not None
        assert result["plane"] == "A320"
        assert result["origin"] == "LHR"
        assert result["destination"] == "GLA"

    def test_strips_internal_keys(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "_junk": "x"}, kind=rc.KIND_ROUTE)
        result = rc.get("BAW123", rc.KIND_ROUTE)
        assert "_ts" not in result
        assert "_junk" not in result

    def test_expired_entry_returns_none(self, isolated_cache):
        rc = isolated_cache
        _put_stale(rc, "BAW123", {"plane": "A320"}, rc.KIND_ROUTE, 1)
        assert rc.get("BAW123", rc.KIND_ROUTE) is None

    def test_expired_entry_preserved_for_stale_fallback(self, isolated_cache):
        rc = isolated_cache
        _put_stale(rc, "BAW123", {"plane": "A320"}, rc.KIND_ROUTE, 1)
        assert rc.get("BAW123", rc.KIND_ROUTE) is None
        # get() no longer deletes expired entries so get_stale() finds them
        assert rc.get_stale("BAW123", rc.KIND_ROUTE) is not None

    def test_wrong_kind_returns_none(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320"}, kind=rc.KIND_ROUTE)
        assert rc.get("BAW123", rc.KIND_AIRCRAFT) is None

    def test_none_callsign(self, isolated_cache):
        rc = isolated_cache
        assert rc.get(None, rc.KIND_ROUTE) is None


class TestRoutesCacheGetStale:
    """get_stale() returns raw entries (with _ts) within the 7-day threshold."""

    def test_returns_expired_entry_within_threshold(self, isolated_cache):
        rc = isolated_cache
        _put_stale(rc, "BAW123", {"plane": "A320", "origin": "LHR"}, rc.KIND_ROUTE, 1)
        result = rc.get_stale("BAW123", rc.KIND_ROUTE)
        assert result is not None
        assert result["plane"] == "A320"
        assert result["origin"] == "LHR"

    def test_returns_raw_entry_with_ts(self, isolated_cache):
        rc = isolated_cache
        _put_stale(rc, "BAW123", {"plane": "A320"}, rc.KIND_ROUTE, 1)
        result = rc.get_stale("BAW123", rc.KIND_ROUTE)
        assert "_ts" in result

    def test_returns_none_past_stale_threshold(self, isolated_cache):
        rc = isolated_cache
        rc.put(
            "BAW123",
            {"plane": "A320"},
            ts=time.time() - rc.CACHE_TTL_STALE - 1,
            kind=rc.KIND_ROUTE,
        )
        assert rc.get_stale("BAW123", rc.KIND_ROUTE) is None

    def test_excludes_miss_entries(self, isolated_cache):
        rc = isolated_cache
        rc.put(
            "BAW123",
            {"miss": True},
            ttl=rc.CACHE_TTL_MISS,
            ts=time.time() - rc.CACHE_TTL - 1,
            kind=rc.KIND_ROUTE,
        )
        assert rc.get_stale("BAW123", rc.KIND_ROUTE) is None

    def test_returns_none_for_missing_key(self, isolated_cache):
        rc = isolated_cache
        assert rc.get_stale("NONEXIST", rc.KIND_ROUTE) is None

    def test_returns_none_for_none_key(self, isolated_cache):
        rc = isolated_cache
        assert rc.get_stale(None, rc.KIND_ROUTE) is None

    def test_returns_fresh_entry_too(self, isolated_cache):
        """get_stale also returns entries that haven't expired yet."""
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR"}, kind=rc.KIND_ROUTE)
        result = rc.get_stale("BAW123", rc.KIND_ROUTE)
        assert result is not None
        assert result["plane"] == "A320"


class TestRoutesCachePut:
    def test_put_overwrites_existing(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR"}, kind=rc.KIND_ROUTE)
        rc.put("BAW123", {"plane": "B737", "origin": "LGW"}, kind=rc.KIND_ROUTE)
        result = rc.get("BAW123", rc.KIND_ROUTE)
        assert result["plane"] == "B737"
        assert result["origin"] == "LGW"

    def test_put_persists_immediately(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320"}, kind=rc.KIND_ROUTE)
        # Simulate a fresh session: drop the pooled connection, the entry
        # must still be visible from a newly-opened database.
        rc._conn = None
        assert rc.get("BAW123", rc.KIND_ROUTE) == {"plane": "A320"}

    def test_put_with_custom_ts(self, isolated_cache):
        rc = isolated_cache
        custom_ts = time.time() - 7200  # 2 hours ago
        rc.put("BAW123", {"plane": "A320"}, ts=custom_ts, kind=rc.KIND_ROUTE)
        assert rc.get_stale("BAW123", rc.KIND_ROUTE)["_ts"] == custom_ts

    def test_put_with_custom_ts_expires_correctly(self, isolated_cache):
        rc = isolated_cache
        # 25 hours ago - expired with the default 24h TTL
        custom_ts = time.time() - rc.CACHE_TTL - 3600
        rc.put("BAW123", {"plane": "A320"}, ts=custom_ts, kind=rc.KIND_ROUTE)
        assert rc.get("BAW123", rc.KIND_ROUTE) is None
        # But get_stale should still find it (within 7 days)
        assert rc.get_stale("BAW123", rc.KIND_ROUTE) is not None

    def test_put_none_key_is_noop(self, isolated_cache):
        rc = isolated_cache
        rc.put(None, {"plane": "A320"}, kind=rc.KIND_ROUTE)
        assert rc.debug_entries() == []

    def test_put_empty_entry_reads_back_as_empty_dict(self, isolated_cache):
        """Blank aircraft entries are cached as empty payloads - a hit must
        read back as {} (not None) to short-circuit the providers."""
        rc = isolated_cache
        rc.put("400f5a", {}, kind=rc.KIND_AIRCRAFT)
        assert rc.get("400f5a", rc.KIND_AIRCRAFT) == {}

    def test_miss_entry_roundtrip(self, isolated_cache):
        """Miss rows read back as {"miss": True} and are never stale-able."""
        rc = isolated_cache
        rc.put("ZZZ999", {"miss": True}, ttl=rc.CACHE_TTL_MISS, kind=rc.KIND_ROUTE)
        assert rc.get("ZZZ999", rc.KIND_ROUTE) == {"miss": True}
        _put_stale(rc, "OLD", {"miss": True}, rc.KIND_ROUTE, 1)
        # miss TTL (1h) expired -> gone; and never eligible for stale
        assert rc.get("OLD", rc.KIND_ROUTE) is None
        assert rc.get_stale("OLD", rc.KIND_ROUTE) is None
        assert rc.get_stale("ZZZ999", rc.KIND_ROUTE) is None


class TestRoutesCacheClear:
    def test_clear_empties_cache(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320"}, kind=rc.KIND_ROUTE)
        rc.clear()
        assert rc.get("BAW123", rc.KIND_ROUTE) is None

    def test_clear_clears_all_kinds(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320"}, kind=rc.KIND_ROUTE)
        rc.put("400f5a", {"plane": "B738"}, kind=rc.KIND_AIRCRAFT)
        rc.clear()
        assert rc.get("BAW123", rc.KIND_ROUTE) is None
        assert rc.get("400f5a", rc.KIND_AIRCRAFT) is None

    def test_clear_on_empty_cache(self, isolated_cache):
        rc = isolated_cache
        rc.clear()
        assert rc.get("anything", rc.KIND_ROUTE) is None


class TestRoutesCachePurgeStale:
    """flush() purges entries older than the 7-day stale threshold."""

    def test_purge_removes_entries_older_than_stale_threshold(self, isolated_cache):
        rc = isolated_cache
        rc.put(
            "BAW123",
            {"plane": "A320"},
            ts=time.time() - rc.CACHE_TTL_STALE - 1,
            kind=rc.KIND_ROUTE,
        )
        rc.flush()
        assert rc.get_stale("BAW123", rc.KIND_ROUTE) is None

    def test_purge_preserves_entries_within_stale_threshold(self, isolated_cache):
        rc = isolated_cache
        _put_stale(rc, "BAW123", {"plane": "A320"}, rc.KIND_ROUTE, 1)
        rc.flush()
        assert rc.get_stale("BAW123", rc.KIND_ROUTE) is not None

    def test_purge_preserves_fresh_entries(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320"}, kind=rc.KIND_ROUTE)
        rc.flush()
        assert rc.get("BAW123", rc.KIND_ROUTE) is not None

    def test_purge_removes_only_old_entries(self, isolated_cache):
        rc = isolated_cache
        now = time.time()
        rc.put("FRESH", {"plane": "A320"}, ts=now, kind=rc.KIND_ROUTE)
        rc.put(
            "STALE", {"plane": "B737"}, ts=now - rc.CACHE_TTL - 1, kind=rc.KIND_ROUTE
        )
        rc.put(
            "TOO_OLD",
            {"plane": "C172"},
            ts=now - rc.CACHE_TTL_STALE - 1,
            kind=rc.KIND_ROUTE,
        )
        rc.flush()
        assert rc.get("FRESH", rc.KIND_ROUTE) is not None
        assert rc.get_stale("STALE", rc.KIND_ROUTE) is not None
        assert rc.get_stale("TOO_OLD", rc.KIND_ROUTE) is None

    def test_flush_safe_when_db_not_yet_created(self, isolated_cache):
        rc = isolated_cache
        rc.flush()  # must not raise on a first-run, write-less cache
        assert rc.debug_entries() == []


class TestRoutesCacheDelete:
    def test_delete_returns_count_of_removed(self, isolated_cache):
        rc = isolated_cache
        rc.put("A1", {"plane": "X"}, kind=rc.KIND_ROUTE)
        rc.put("A2", {"plane": "Y"}, kind=rc.KIND_ROUTE)
        assert rc.delete(["A1", "A2", "MISSING"], rc.KIND_ROUTE) == 2

    def test_delete_accepts_single_string(self, isolated_cache):
        rc = isolated_cache
        rc.put("A1", {"plane": "X"}, kind=rc.KIND_ROUTE)
        assert rc.delete("A1", rc.KIND_ROUTE) == 1
        assert rc.get("A1", rc.KIND_ROUTE) is None

    def test_delete_empty_list_returns_zero(self, isolated_cache):
        rc = isolated_cache
        rc.put("A1", {"plane": "X"}, kind=rc.KIND_ROUTE)
        assert rc.delete([], rc.KIND_ROUTE) == 0

    def test_delete_is_kind_scoped(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"origin": "LHR"}, kind=rc.KIND_ROUTE)
        rc.put("BAW123", {"plane": "A320"}, kind=rc.KIND_AIRCRAFT)
        assert rc.delete(["BAW123"], rc.KIND_ROUTE) == 1
        assert rc.get("BAW123", rc.KIND_ROUTE) is None
        assert rc.get("BAW123", rc.KIND_AIRCRAFT) is not None

    def test_delete_persists(self, isolated_cache):
        rc = isolated_cache
        rc.put("A1", {"plane": "X"}, kind=rc.KIND_ROUTE)
        rc.delete("A1", rc.KIND_ROUTE)
        rc._conn = None
        assert rc.get("A1", rc.KIND_ROUTE) is None


class TestRoutesCacheKinds:
    def test_same_key_coexists_across_kinds(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"origin": "LHR", "destination": "GLA"}, kind=rc.KIND_ROUTE)
        rc.put(
            "BAW123", {"plane": "A320", "registration": "G-EUXM"}, kind=rc.KIND_AIRCRAFT
        )
        route = rc.get("BAW123", rc.KIND_ROUTE)
        aircraft = rc.get("BAW123", rc.KIND_AIRCRAFT)
        assert route["origin"] == "LHR"
        assert aircraft["plane"] == "A320"

        rc.delete(["BAW123"], rc.KIND_ROUTE)
        assert rc.get("BAW123", rc.KIND_AIRCRAFT) is not None

    def test_kind_constants_distinct(self, isolated_cache):
        rc = isolated_cache
        assert rc.KIND_ROUTE != rc.KIND_AIRCRAFT


class TestRoutesCacheConcurrency:
    def test_parallel_writes_are_serialised(self, isolated_cache):
        rc = isolated_cache
        errors = []

        def worker(n):
            try:
                for i in range(25):
                    rc.put(f"K{n}-{i}", {"plane": "A320", "i": i}, kind=rc.KIND_ROUTE)
                    assert rc.get(f"K{n}-{i}", rc.KIND_ROUTE) is not None
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        assert len(rc.debug_entries(rc.KIND_ROUTE)) == 100


# ---------------------------------------------------------------------------
# Legacy JSON -> database migration
# ---------------------------------------------------------------------------


class TestRoutesCacheLegacyImport:
    def test_import_classifies_callsign_and_hex_keys(self, isolated_cache):
        rc = isolated_cache
        rc.LEGACY_JSON_PATH.write_text(
            json.dumps(
                {
                    "BAW123": {
                        "origin": "LHR",
                        "destination": "GLA",
                        "_ts": time.time(),
                    },
                    "400f5a": {
                        "plane": "B738",
                        "registration": "G-XLMC",
                        "_ts": time.time(),
                    },
                }
            )
        )
        assert rc.get("BAW123", rc.KIND_ROUTE) == {
            "origin": "LHR",
            "destination": "GLA",
        }
        assert rc.get("400f5a", rc.KIND_AIRCRAFT)["plane"] == "B738"
        # cross-kind misses: namespaces do not bleed into each other
        assert rc.get("BAW123", rc.KIND_AIRCRAFT) is None
        assert rc.get("400f5a", rc.KIND_ROUTE) is None

    def test_import_preserves_timestamps(self, isolated_cache):
        rc = isolated_cache
        stale_ts = time.time() - rc.CACHE_TTL - 10
        rc.LEGACY_JSON_PATH.write_text(
            json.dumps(
                {
                    "BAW123": {"origin": "LHR", "destination": "GLA", "_ts": stale_ts},
                    "FRESH1": {
                        "origin": "MAN",
                        "destination": "EDI",
                        "_ts": time.time() - 60,
                    },
                }
            )
        )
        assert rc.get("BAW123", rc.KIND_ROUTE) is None
        stale = rc.get_stale("BAW123", rc.KIND_ROUTE)
        assert stale["origin"] == "LHR"
        assert stale["_ts"] == pytest.approx(stale_ts)
        assert rc.get("FRESH1", rc.KIND_ROUTE)["origin"] == "MAN"

    def test_import_preserves_ttl_and_miss(self, isolated_cache):
        rc = isolated_cache
        rc.LEGACY_JSON_PATH.write_text(
            json.dumps(
                {
                    "ZZZ999": {"miss": True, "_ts": time.time() - 30, "_ttl": 3600},
                }
            )
        )
        assert rc.get("ZZZ999", rc.KIND_ROUTE) == {"miss": True}
        assert rc.get_stale("ZZZ999", rc.KIND_ROUTE) is None

    def test_import_renames_json_to_imported(self, isolated_cache):
        rc = isolated_cache
        rc.LEGACY_JSON_PATH.write_text(
            json.dumps({"BAW123": {"origin": "LHR", "_ts": time.time()}})
        )
        rc.get("BAW123", rc.KIND_ROUTE)
        assert not rc.LEGACY_JSON_PATH.exists()
        imported = rc.LEGACY_JSON_PATH.with_name(rc.LEGACY_JSON_PATH.name + ".imported")
        assert imported.exists()
        assert json.loads(imported.read_text())["BAW123"]["origin"] == "LHR"

    def test_import_stamps_missing_ts(self, isolated_cache):
        rc = isolated_cache
        rc.LEGACY_JSON_PATH.write_text(
            json.dumps({"BAW123": {"origin": "LHR"}})  # no _ts - stamped with now
        )
        assert rc.get("BAW123", rc.KIND_ROUTE) == {"origin": "LHR"}

    def test_import_skips_non_dict_entries(self, isolated_cache):
        rc = isolated_cache
        rc.LEGACY_JSON_PATH.write_text(
            json.dumps(
                {"BAW123": {"origin": "LHR", "_ts": time.time()}, "junk": [1, 2]}
            )
        )
        assert rc.get("BAW123", rc.KIND_ROUTE) is not None
        assert len(rc.debug_entries()) == 1

    def test_corrupt_json_left_in_place_cache_start_fresh(self, isolated_cache):
        rc = isolated_cache
        rc.LEGACY_JSON_PATH.write_text("{definitely not json")
        assert rc.get("BAW123", rc.KIND_ROUTE) is None
        assert rc.debug_entries() == []
        # corrupt source is preserved, not renamed or deleted
        assert rc.LEGACY_JSON_PATH.exists()
        assert rc.LEGACY_JSON_PATH.read_text() == "{definitely not json"
        # and the cache itself still works
        rc.put("BAW123", {"origin": "LHR"}, kind=rc.KIND_ROUTE)
        assert rc.get("BAW123", rc.KIND_ROUTE)["origin"] == "LHR"

    def test_non_object_json_ignored(self, isolated_cache):
        rc = isolated_cache
        rc.LEGACY_JSON_PATH.write_text(json.dumps(["not", "a", "dict"]))
        assert rc.debug_entries() == []

    def test_empty_json_imported_nothing_and_renamed(self, isolated_cache):
        rc = isolated_cache
        rc.LEGACY_JSON_PATH.write_text("{}")
        assert rc.debug_entries() == []
        assert not rc.LEGACY_JSON_PATH.exists()

    def test_import_skipped_when_db_already_versioned(self, isolated_cache):
        rc = isolated_cache
        # Database gets populated first (user_version stamped), then a
        # leftover legacy JSON appears - it must be ignored, not imported.
        rc.put("BAW123", {"origin": "LGW"}, kind=rc.KIND_ROUTE)
        rc.LEGACY_JSON_PATH.write_text(
            json.dumps({"BAW123": {"origin": "LHR", "_ts": time.time()}})
        )
        rc._conn = None  # simulate a restart
        assert rc.get("BAW123", rc.KIND_ROUTE)["origin"] == "LGW"
        assert rc.LEGACY_JSON_PATH.exists()  # untouched


class TestRoutesCacheSchemaAndRecovery:
    def test_future_user_version_recreates_cache(self, isolated_cache):
        rc = isolated_cache
        rc.put("OLD1", {"plane": "X"}, kind=rc.KIND_ROUTE)
        rc._conn.execute("PRAGMA user_version = 99")
        rc._conn = None  # reopen with an unknown future schema
        rc.put("NEW1", {"plane": "Y"}, kind=rc.KIND_ROUTE)
        assert rc.get("OLD1", rc.KIND_ROUTE) is None
        assert rc.get("NEW1", rc.KIND_ROUTE)["plane"] == "Y"
        assert rc._conn.execute("PRAGMA user_version").fetchone()[0] == 1

    def test_corrupt_db_moved_aside_and_rebuilt(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320"}, kind=rc.KIND_ROUTE)
        rc._conn = None
        # Corrupt the main database *and* the WAL sidecars - SQLite can
        # otherwise legitimately recover the db from a warm -wal file.
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(rc.DB_PATH) + suffix)
            if path.exists():
                path.write_bytes(b"this is not a database" * 200)

        assert rc.get("BAW123", rc.KIND_ROUTE) is None  # fresh empty cache

        leftovers = [
            p.name for p in rc.DB_PATH.parent.iterdir() if ".corrupt-" in p.name
        ]
        assert leftovers, "corrupt database should be moved aside"
        # ... and the rebuilt database works
        rc.put("BAW123", {"plane": "A320"}, kind=rc.KIND_ROUTE)
        assert rc.get("BAW123", rc.KIND_ROUTE)["plane"] == "A320"

    def test_unwritable_path_falls_back_to_memory(
        self, isolated_cache, tmp_path, monkeypatch
    ):
        rc = isolated_cache
        blocker = tmp_path / "blocker"
        blocker.write_text("a file, not a directory")
        monkeypatch.setattr(rc, "DB_PATH", tmp_path / "blocker" / "cache.sqlite3")

        # The path can never be created - the cache still works in-session.
        rc.put("BAW123", {"plane": "A320"}, kind=rc.KIND_ROUTE)
        assert rc.get("BAW123", rc.KIND_ROUTE)["plane"] == "A320"
        assert not (tmp_path / "blocker" / "cache.sqlite3").exists()


class TestRoutesCacheDebugEntries:
    def test_rows_expose_raw_fields_and_public_entry(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR"}, kind=rc.KIND_ROUTE)
        rc.put("ZZZ999", {"miss": True}, ttl=rc.CACHE_TTL_MISS, kind=rc.KIND_ROUTE)

        rows = rc.debug_entries()
        assert len(rows) == 2
        entries = {row["key"]: row for row in rows}
        route = entries["BAW123"]
        assert route["kind"] == rc.KIND_ROUTE
        assert isinstance(route["ts"], float)
        assert route["ttl"] == rc.CACHE_TTL
        assert route["entry"]["plane"] == "A320"
        miss = entries["ZZZ999"]
        assert miss["ttl"] == rc.CACHE_TTL_MISS
        assert miss["miss"] is True
        assert miss["entry"] == {"miss": True}

    def test_kind_filter(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320"}, kind=rc.KIND_ROUTE)
        rc.put("400f5a", {"plane": "B738"}, kind=rc.KIND_AIRCRAFT)
        assert [r["key"] for r in rc.debug_entries(rc.KIND_AIRCRAFT)] == ["400f5a"]
        # unfiltered listing is ordered by kind, then key: aircraft < route
        keys = [r["key"] for r in rc.debug_entries()]
        assert keys == ["400f5a", "BAW123"]


# ---------------------------------------------------------------------------
# Configurable cache durations (#102)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------


class TestConfiguredTtl:
    """put()/get_stale()/flush() honour the user's configured durations."""

    @staticmethod
    def _patch_days(monkeypatch, route_days, aircraft_days):
        import setup.configuration as configuration

        stub = types.SimpleNamespace(
            cache_route_days=route_days, cache_aircraft_days=aircraft_days
        )
        monkeypatch.setattr(
            configuration,
            "Config",
            type("StubConfig", (), {"instance": staticmethod(lambda s=stub: s)}),
        )

    def test_put_uses_configured_route_days(self, isolated_cache, monkeypatch):
        rc = isolated_cache
        self._patch_days(monkeypatch, route_days=3, aircraft_days=1)
        rc.put("BAW123", {"plane": "A320"}, kind=rc.KIND_ROUTE)

        rows = rc.debug_entries(rc.KIND_ROUTE)
        assert rows[0]["ttl"] == 3 * 86400

    def test_put_uses_configured_aircraft_days(self, isolated_cache, monkeypatch):
        rc = isolated_cache
        self._patch_days(monkeypatch, route_days=1, aircraft_days=2)
        rc.put("400f5a", {"plane": "B738"}, kind=rc.KIND_AIRCRAFT)

        rows = rc.debug_entries(rc.KIND_AIRCRAFT)
        assert rows[0]["ttl"] == 2 * 86400

    def test_miss_entries_keep_miss_ttl(self, isolated_cache, monkeypatch):
        rc = isolated_cache
        self._patch_days(monkeypatch, route_days=3, aircraft_days=3)
        rc.put("ZZZ999", {"miss": True}, kind=rc.KIND_ROUTE)

        rows = rc.debug_entries(rc.KIND_ROUTE)
        assert rows[0]["ttl"] == rc.CACHE_TTL_MISS

    def test_long_ttl_row_is_fresh_and_survives_flush(
        self, isolated_cache, monkeypatch
    ):
        """A 10-day route entry is still fresh one week after it was written
        (the purge horizon grows with the configured duration)."""
        rc = isolated_cache
        self._patch_days(monkeypatch, route_days=10, aircraft_days=10)
        rc.put(
            "BAW123", {"plane": "A320"}, ts=time.time() - 7 * 86400, kind=rc.KIND_ROUTE
        )

        assert rc.get("BAW123", rc.KIND_ROUTE) is not None
        rc.flush()
        assert rc.get("BAW123", rc.KIND_ROUTE) is not None

    def test_rows_purge_after_configured_ttl(self, isolated_cache, monkeypatch):
        rc = isolated_cache
        self._patch_days(monkeypatch, route_days=1, aircraft_days=1)
        rc.put("OLD", {"plane": "A320"}, ts=time.time() - 8 * 86400, kind=rc.KIND_ROUTE)
        rc.flush()
        assert rc.get("OLD", rc.KIND_ROUTE) is None

    def test_default_config_matches_legacy_behaviour(self, isolated_cache, monkeypatch):
        """With the default 1-day settings, put/get behave exactly like the
        pre-configurable cache: 1-day freshness, 7-day stale window."""
        rc = isolated_cache
        self._patch_days(monkeypatch, route_days=1, aircraft_days=1)

        rc.put(
            "BAW123",
            {"plane": "A320"},
            ts=time.time() - 5 * 86400,
            kind=rc.KIND_ROUTE,
        )
        assert rc.get("BAW123", rc.KIND_ROUTE) is None  # past 1-day freshness
        stale = rc.get_stale("BAW123", rc.KIND_ROUTE)
        assert stale is not None  # ... but inside the 7-day stale window
        rc.flush()
        assert rc.get_stale("BAW123", rc.KIND_ROUTE) is not None  # 5d: not purged yet

        rc.put("OLD", {"plane": "A320"}, ts=time.time() - 8 * 86400, kind=rc.KIND_ROUTE)
        rc.flush()
        assert rc.get_stale("OLD", rc.KIND_ROUTE) is None  # purged at 7 days


class TestTtlForSource:
    def test_ttl_for_reads_config_days_and_clamps(self, monkeypatch):
        import scenes.flight.lookups.cache as rc
        import setup.configuration as configuration

        for days, expected in ((0, 1), (5, 5), (55, 30)):
            stub = types.SimpleNamespace(
                cache_route_days=days, cache_aircraft_days=days
            )
            monkeypatch.setattr(
                configuration,
                "Config",
                type("StubConfig", (), {"instance": staticmethod(lambda s=stub: s)}),
            )
            assert rc.ttl_for(rc.KIND_ROUTE) == expected * 86400

    def test_unreadable_config_falls_back_to_legacy_day(
        self, isolated_cache, monkeypatch
    ):
        """When the config is unreadable the cache falls back to the
        historical 1-day TTL instead of raising."""
        rc = isolated_cache
        import setup.configuration as configuration

        class _Broken:
            def instance(self):
                raise RuntimeError("no config")

        monkeypatch.setattr(configuration, "Config", _Broken)
        rc.put("BAW123", {"plane": "A320"}, kind=rc.KIND_ROUTE)
        rows = rc.debug_entries(rc.KIND_ROUTE)
        assert rows[0]["ttl"] == rc.CACHE_TTL
        assert rc.get("BAW123", rc.KIND_ROUTE)["plane"] == "A320"

"""Tests for lookups/cache.py - TTL, get/put/clear, thread safety."""

import json
import time

import pytest


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Redirect routes_cache to use a temp file and reset internal state."""
    cache_file = tmp_path / "routes_cache.json"

    import lookups.cache as rc

    monkeypatch.setattr(rc, "CACHE_PATH", cache_file)
    monkeypatch.setattr(rc, "_cache", {})
    monkeypatch.setattr(rc, "_loaded", False)
    monkeypatch.setattr(rc, "_dirty", False)
    return rc


class TestRoutesCacheGet:
    def test_miss_on_empty_cache(self, isolated_cache):
        rc = isolated_cache
        assert rc.get("BAW123") is None

    def test_hit_after_put(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        result = rc.get("BAW123")
        assert result is not None
        assert result["plane"] == "A320"
        assert result["origin"] == "LHR"
        assert result["destination"] == "GLA"

    def test_strips_internal_keys(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        result = rc.get("BAW123")
        assert "_ts" not in result

    def test_expired_entry_returns_none(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        # Manually age the timestamp
        rc._cache["BAW123"]["_ts"] = time.time() - rc.CACHE_TTL - 1
        result = rc.get("BAW123")
        assert result is None

    def test_expired_entry_preserved_for_stale_fallback(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        rc._cache["BAW123"]["_ts"] = time.time() - rc.CACHE_TTL - 1
        rc.get("BAW123")
        # get() no longer deletes expired entries so get_stale() can find them
        assert "BAW123" in rc._cache

    def test_none_callsign(self, isolated_cache):
        rc = isolated_cache
        assert rc.get(None) is None


class TestRoutesCacheGetStale:
    """Tests for get_stale() - returns raw expired entries within 7-day threshold."""

    def test_returns_expired_entry_within_threshold(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        # Age past normal TTL but within stale threshold
        rc._cache["BAW123"]["_ts"] = time.time() - rc.CACHE_TTL - 1
        result = rc.get_stale("BAW123")
        assert result is not None
        assert result["plane"] == "A320"
        assert result["origin"] == "LHR"

    def test_returns_raw_entry_with_ts(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        rc._cache["BAW123"]["_ts"] = time.time() - rc.CACHE_TTL - 1
        result = rc.get_stale("BAW123")
        # get_stale returns raw entry including _ts so callers can advance it
        assert "_ts" in result

    def test_returns_none_past_stale_threshold(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        # Age past the 7-day stale threshold
        rc._cache["BAW123"]["_ts"] = time.time() - rc.CACHE_TTL_STALE - 1
        result = rc.get_stale("BAW123")
        assert result is None

    def test_excludes_miss_entries(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"miss": True}, ttl=rc.CACHE_TTL_MISS)
        rc._cache["BAW123"]["_ts"] = time.time() - rc.CACHE_TTL - 1
        result = rc.get_stale("BAW123")
        assert result is None

    def test_returns_none_for_missing_key(self, isolated_cache):
        rc = isolated_cache
        assert rc.get_stale("NONEXIST") is None

    def test_returns_none_for_none_key(self, isolated_cache):
        rc = isolated_cache
        assert rc.get_stale(None) is None

    def test_returns_fresh_entry_too(self, isolated_cache):
        """get_stale also returns entries that haven't expired yet."""
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        result = rc.get_stale("BAW123")
        assert result is not None
        assert result["plane"] == "A320"


class TestRoutesCachePut:
    def test_put_creates_entry_with_timestamp(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        assert "BAW123" in rc._cache
        assert "_ts" in rc._cache["BAW123"]

    def test_put_overwrites_existing(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        rc.put("BAW123", {"plane": "B737", "origin": "LGW", "destination": "EDI"})
        result = rc.get("BAW123")
        assert result["plane"] == "B737"
        assert result["origin"] == "LGW"

    def test_put_persists_to_disk_after_flush(self, isolated_cache, tmp_path):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        # put() no longer writes immediately - must call flush() first
        assert (
            not rc.CACHE_PATH.exists()
        ), "put() should not write to disk before flush()"
        rc.flush()
        assert rc.CACHE_PATH.exists()
        data = json.loads(rc.CACHE_PATH.read_text())
        assert "BAW123" in data

    def test_flush_clears_dirty_flag(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        assert rc._dirty is True
        rc.flush()
        assert rc._dirty is False

    def test_put_with_custom_ts(self, isolated_cache):
        rc = isolated_cache
        custom_ts = time.time() - 7200  # 2 hours ago
        rc.put("BAW123", {"plane": "A320"}, ts=custom_ts)
        assert rc._cache["BAW123"]["_ts"] == custom_ts

    def test_put_with_custom_ts_expires_correctly(self, isolated_cache):
        rc = isolated_cache
        # Set ts to 25 hours ago - should be expired with default 24h TTL
        custom_ts = time.time() - rc.CACHE_TTL - 3600
        rc.put("BAW123", {"plane": "A320"}, ts=custom_ts)
        assert rc.get("BAW123") is None
        # But get_stale should still find it (within 7 days)
        assert rc.get_stale("BAW123") is not None

    def test_flush_noop_when_not_dirty(self, isolated_cache, tmp_path):
        rc = isolated_cache
        rc.flush()  # nothing to flush - should not create file
        assert not rc.CACHE_PATH.exists()


class TestRoutesCacheClear:
    def test_clear_empties_in_memory_cache(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        rc.clear()
        assert "BAW123" not in rc._cache

    def test_clear_empties_disk(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        rc.clear()
        data = json.loads(rc.CACHE_PATH.read_text())
        assert data == {}

    def test_clear_on_empty_cache(self, isolated_cache):
        rc = isolated_cache
        rc.clear()
        assert rc.get("anything") is None


class TestRoutesCachePurgeStale:
    """Tests for _purge_stale() - removes entries older than 7 days during flush."""

    def test_purge_removes_entries_older_than_stale_threshold(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        rc._cache["BAW123"]["_ts"] = time.time() - rc.CACHE_TTL_STALE - 1
        rc.flush()
        assert "BAW123" not in rc._cache

    def test_purge_preserves_entries_within_stale_threshold(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        # Expired past normal TTL but within stale threshold
        rc._cache["BAW123"]["_ts"] = time.time() - rc.CACHE_TTL - 1
        rc.flush()
        assert "BAW123" in rc._cache

    def test_purge_preserves_fresh_entries(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        rc.flush()
        assert "BAW123" in rc._cache

    def test_purge_removes_only_old_entries(self, isolated_cache):
        rc = isolated_cache
        # Fresh entry
        rc.put("FRESH", {"plane": "A320"})
        # Expired but within stale threshold
        rc.put("STALE", {"plane": "B737"})
        rc._cache["STALE"]["_ts"] = time.time() - rc.CACHE_TTL - 1
        # Too old - past stale threshold
        rc.put("TOO_OLD", {"plane": "C172"})
        rc._cache["TOO_OLD"]["_ts"] = time.time() - rc.CACHE_TTL_STALE - 1
        rc.flush()
        assert "FRESH" in rc._cache
        assert "STALE" in rc._cache
        assert "TOO_OLD" not in rc._cache


class TestRoutesCachePersistence:
    def test_load_from_disk(self, isolated_cache, tmp_path):
        rc = isolated_cache
        # Write a cache file manually
        rc.CACHE_PATH.write_text(
            json.dumps(
                {
                    "BAW123": {
                        "plane": "A320",
                        "origin": "LHR",
                        "destination": "GLA",
                        "_ts": time.time(),
                    }
                }
            )
        )
        # Reset in-memory state
        rc._cache = {}
        rc._loaded = False
        result = rc.get("BAW123")
        assert result is not None
        assert result["plane"] == "A320"

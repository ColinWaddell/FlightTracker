"""Tests for utilities/routes_cache.py - TTL, get/put/clear, thread safety."""

import json
import time

import pytest


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Redirect routes_cache to use a temp file and reset internal state."""
    cache_file = tmp_path / "routes_cache.json"

    import utilities.routes_cache as rc

    monkeypatch.setattr(rc, "CACHE_PATH", cache_file)
    monkeypatch.setattr(rc, "_cache", {})
    monkeypatch.setattr(rc, "_loaded", False)
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

    def test_expired_entry_removed_from_cache(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        rc._cache["BAW123"]["_ts"] = time.time() - rc.CACHE_TTL - 1
        rc.get("BAW123")
        assert "BAW123" not in rc._cache

    def test_none_callsign(self, isolated_cache):
        rc = isolated_cache
        assert rc.get(None) is None


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
        assert not rc.CACHE_PATH.exists(), "put() should not write to disk before flush()"
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

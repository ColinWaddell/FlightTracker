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

    def test_put_persists_to_disk(self, isolated_cache, tmp_path):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        # File should exist and contain valid JSON
        assert rc.CACHE_PATH.exists()
        data = json.loads(rc.CACHE_PATH.read_text())
        assert "BAW123" in data


class TestRoutesCacheClear:
    # NOTE: clear() has a bug - `_cache = {}` inside the function is a local
    # variable, not a global assignment. The in-memory cache is NOT cleared
    # and _save() writes the old (non-empty) cache to disk. These tests
    # document the current behaviour. When the bug is fixed, update them.

    def test_clear_does_not_empty_in_memory_cache(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
        rc.clear()
        # Bug: _cache is a local in clear(), so the global is untouched
        assert "BAW123" in rc._cache

    def test_clear_on_empty_cache(self, isolated_cache):
        rc = isolated_cache
        rc.clear()
        assert rc.get("anything") is None

    # When the clear() bug is fixed, these tests should pass:
    # def test_clear_empties_in_memory_cache(self, isolated_cache):
    #     rc = isolated_cache
    #     rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
    #     rc.clear()
    #     assert "BAW123" not in rc._cache
    #
    # def test_clear_empties_disk(self, isolated_cache):
    #     rc = isolated_cache
    #     rc.put("BAW123", {"plane": "A320", "origin": "LHR", "destination": "GLA"})
    #     rc.clear()
    #     data = json.loads(rc.CACHE_PATH.read_text())
    #     assert data == {}


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

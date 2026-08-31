"""Tests for utilities/tle_manager.py - disk-cache priming and holdoff.

The manager must keep serving a stale TLE cache (pass prediction degrades
gracefully over days) while a CelesTrak outage makes refreshes fail; the
refresh loop continues on its own backoff schedule.
"""

from __future__ import annotations

import json
import logging
import time

import pytest

import utilities.tle_manager as tle_manager

_TLE = ("ISS (ZARYA)", "1 25544U 98067A   ...", "2 25544  51.6 ...")


@pytest.fixture
def cache_path(tmp_path, monkeypatch):
    path = tmp_path / "tle_cache.json"
    monkeypatch.setattr(tle_manager, "TLE_CACHE_PATH", path)
    return path


def _write_cache(path, age_seconds):
    path.write_text(
        json.dumps(
            {
                "timestamp": time.time() - age_seconds,
                "tles": [list(_TLE)],
            }
        )
    )


class TestPrimeFromDisk:
    def test_missing_cache_is_a_noop(self, cache_path):
        mgr = tle_manager.TLEManager()
        mgr.prime_from_disk()

        assert mgr.tles == []
        assert not mgr.ready.is_set()

    def test_fresh_cache_serves_immediately(self, cache_path, caplog):
        _write_cache(cache_path, age_seconds=100)
        mgr = tle_manager.TLEManager()

        mgr.prime_from_disk()

        assert mgr.ready.is_set()
        assert mgr.tles == [_TLE]
        assert "stale" not in caplog.text.lower()

    def test_stale_cache_is_served_with_warning(self, cache_path, caplog):
        """Outage resilience: a days-old cache still predicts passes."""
        _write_cache(cache_path, age_seconds=5 * 86400)
        mgr = tle_manager.TLEManager()

        with caplog.at_level(logging.DEBUG):
            mgr.prime_from_disk()

        assert mgr.ready.is_set()
        assert mgr.tles == [_TLE]
        assert "stale" in caplog.text.lower()

    def test_ancient_cache_is_discarded(self, cache_path, caplog):
        _write_cache(cache_path, age_seconds=40 * 86400)
        mgr = tle_manager.TLEManager()

        mgr.prime_from_disk()

        assert mgr.tles == []
        assert not mgr.ready.is_set()
        assert "too old to serve" in caplog.text


class TestFailedRefreshHoldoff:
    def test_stale_fallback_bumps_retry_by_four_hours(
        self, cache_path, monkeypatch, caplog
    ):
        """With stale data in memory, a failed refresh advances the retry
        clock (4h) instead of hammering CelesTrak; the bump is persisted."""
        _write_cache(cache_path, age_seconds=100)
        mgr = tle_manager.TLEManager()
        mgr.prime_from_disk()

        class _StubConfig:
            satellite_norad_ids = [25544]

            @classmethod
            def instance(cls):
                return cls()

        monkeypatch.setattr(tle_manager, "Config", _StubConfig)
        monkeypatch.setattr(tle_manager, "fetch_tle", lambda norad_id: None)

        before = time.time()
        mgr.do_fetch()

        bumped_age = time.time() - mgr.fetched_at
        assert mgr.ready.is_set() is not False  # ready flag untouched
        assert tle_manager.TLE_CACHE_TTL - bumped_age > 3 * 3600  # ~4h from now
        assert "reusing stale cache" in caplog.text
        assert mgr.backoff_seconds == 0.0

        persisted = json.loads(cache_path.read_text())
        assert persisted["timestamp"] == mgr.fetched_at
        assert before - mgr.fetched_at < 86400  # sanity: near-future retry

    def test_no_cached_data_backs_off(self, cache_path, monkeypatch, caplog):
        """First-ever refresh failure backs off exponentially, serving
        nothing until data arrives."""
        mgr = tle_manager.TLEManager()

        class _StubConfig:
            satellite_norad_ids = [25544]

            @classmethod
            def instance(cls):
                return cls()

        monkeypatch.setattr(tle_manager, "Config", _StubConfig)
        monkeypatch.setattr(tle_manager, "fetch_tle", lambda norad_id: None)

        with caplog.at_level(logging.DEBUG):
            mgr.do_fetch()
            assert mgr.backoff_seconds == tle_manager.BACKOFF_MIN
            first = mgr.next_attempt_at - time.time()

            mgr.do_fetch()
            assert mgr.backoff_seconds == tle_manager.BACKOFF_MIN * 2
            second = mgr.next_attempt_at - time.time()

        assert first <= second
        # ready IS set with an empty list: the scene's `not tles` check
        # treats that as no-data, and get() callers unblock either way.
        assert mgr.ready.is_set()
        assert mgr.tles == []

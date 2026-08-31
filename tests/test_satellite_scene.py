"""Tests for scenes/satellite/satellite_scene.py - pass recompute holdoff.

A CelesTrak outage used to re-run - and re-log - the skipped pass
computation on every poll tick.  These tests pin the holdoff behaviour:
recompute is gated by a cooldown and the skip warning is rate-limited.
"""

from __future__ import annotations

import logging
import types

import scenes.satellite.satellite_scene as satellite_scene
from scenes.satellite.satellite_scene import SatelliteScene

_LOGGER = "scenes.satellite.satellite_scene"


class _FakeTLEManager:
    def __init__(self, tles):
        self._tles = tles
        self.try_get_calls = 0

    def try_get(self):
        self.try_get_calls += 1
        return self._tles


class _StubConfig:
    satellite_max_count = 3
    observer_lat = 55.9
    observer_lng = -4.3
    satellite_min_elevation = 10

    @classmethod
    def instance(cls):
        return cls()


def _cfg():
    return types.SimpleNamespace(
        observer_lat=55.9,
        observer_lng=-4.3,
        satellite_min_elevation=10,
        satellite_max_count=3,
    )


def _scene(tles=None):
    manager = _FakeTLEManager(tles)
    return SatelliteScene(canvas=None, panel=None, tle_manager=manager), manager


class TestNoTleHoldoff:
    """recompute_passes with no TLE data: warn once, retry on cooldown."""

    def test_warns_once_then_goes_quiet(self, caplog):
        scene, manager = _scene(tles=None)

        with caplog.at_level(logging.DEBUG, logger=_LOGGER):
            scene.recompute_passes(_cfg())  # first skip warns
            scene.recompute_passes(_cfg())  # identical repeat stays silent

        assert manager.try_get_calls == 2
        assert caplog.text.count("no TLE data available") == 1

    def test_poll_gates_recompute_behind_cooldown(self, monkeypatch, caplog):
        monkeypatch.setattr(satellite_scene, "Config", _StubConfig)
        scene, manager = _scene(tles=None)

        with caplog.at_level(logging.DEBUG, logger=_LOGGER):
            scene.poll()  # first tick: warns + arms the cooldown
            scene.poll()  # within cooldown: no recompute attempt at all
            assert manager.try_get_calls == 1
            assert caplog.text.count("no TLE data available") == 1

            scene.next_recompute_at = 0.0
            scene.poll()  # cooldown expired: retries, but the log stays quiet
            assert manager.try_get_calls == 2
            assert caplog.text.count("no TLE data available") == 1

            scene.last_no_tle_logged_at = 0.0
            scene.next_recompute_at = 0.0
            scene.poll()  # log interval expired: warns once more
            assert manager.try_get_calls == 3
            assert caplog.text.count("no TLE data available") == 2

    def test_poll_skips_recompute_while_cooled_down(self, monkeypatch):
        monkeypatch.setattr(satellite_scene, "Config", _StubConfig)
        scene, manager = _scene(tles=None)

        scene.next_recompute_at = float("inf")  # far future
        scene.poll()

        assert manager.try_get_calls == 0  # cooldown blocks the attempt


class TestRecoveryFromOutage:
    def test_success_resets_suppression_and_computes(self, monkeypatch):
        tle = ("ISS (ZARYA)", "1 25544U 98067A   ...", "2 25544  51.6 ...")
        scene, manager = _scene(tles=[tle])
        scene.last_no_tle_logged_at = 12345.0  # as if an outage had been warned
        monkeypatch.setattr(
            satellite_scene.passes_mod, "compute_passes", lambda *args, **kw: []
        )

        scene.recompute_passes(_cfg())

        assert manager.try_get_calls == 1
        assert scene.last_no_tle_logged_at == 0.0
        assert scene.next_recompute_at > scene.windows_computed_at


class TestHealthyPathCooldown:
    def test_success_arms_cooldown_again(self, monkeypatch):
        """Success also arms the cooldown: empty SGP4 results used to
        recompute every tick, hammering the Pi's CPU for no benefit."""
        monkeypatch.setattr(satellite_scene, "Config", _StubConfig)
        tle = ("ISS (ZARYA)", "1 25544U ...", "2 25544 ...")
        scene, manager = _scene(tles=[tle])
        monkeypatch.setattr(
            satellite_scene.passes_mod, "compute_passes", lambda *a, **k: []
        )

        scene.poll()

        assert scene.pass_windows == []
        assert scene.windows_computed_at > 0
        assert scene.next_recompute_at >= scene.windows_computed_at

        scene.poll()  # next tick: gated, try_get not called again
        assert manager.try_get_calls == 1

"""Tests for scenes/satellite/passes.py - coordinate math and pass filtering."""

import datetime
import math

import pytest

from scenes.satellite.passes import (
    PassWindow,
    current_passes,
    fake_pass_window,
    gmst_rad,
    jday_from_dt,
    visible_passes,
)


def _make_pass(name, aos_delta_min, los_delta_min, max_el=45.0):
    """Helper to create a PassWindow relative to now (UTC)."""
    now = datetime.datetime.utcnow()
    return PassWindow(
        name=name,
        tle_index=0,
        aos=now + datetime.timedelta(minutes=aos_delta_min),
        los=now + datetime.timedelta(minutes=los_delta_min),
        max_el=max_el,
        trajectory=[],
    )


# ---------------------------------------------------------------------------
# jday_from_dt
# ---------------------------------------------------------------------------


class TestJdayFromDt:
    def test_j2000_epoch(self):
        # J2000 epoch: 2000-01-01 12:00 UTC → JD 2451545.0
        dt = datetime.datetime(2000, 1, 1, 12, 0, 0)
        jd, fr = jday_from_dt(dt)
        total = jd + fr
        assert total == pytest.approx(2451545.0, abs=0.01)

    def test_jan_2026(self):
        # 2026-01-01 00:00 UTC → JD ≈ 2461041.5
        dt = datetime.datetime(2026, 1, 1, 0, 0, 0)
        jd, fr = jday_from_dt(dt)
        total = jd + fr
        assert total == pytest.approx(2461041.5, abs=0.5)

    def test_returns_tuple_of_two(self):
        dt = datetime.datetime(2026, 7, 11, 15, 0, 0)
        result = jday_from_dt(dt)
        assert len(result) == 2
        assert isinstance(result[0], float)
        assert isinstance(result[1], float)


# ---------------------------------------------------------------------------
# gmst_rad
# ---------------------------------------------------------------------------


class TestGmstRad:
    def test_j2000_gmst(self):
        gmst = gmst_rad(2451545.0, 0.0)
        assert isinstance(gmst, float)
        assert 0 <= gmst < 2 * math.pi

    def test_returns_float(self):
        gmst = gmst_rad(2461043.5, 0.0)
        assert isinstance(gmst, float)
        assert 0 <= gmst < 2 * math.pi


# ---------------------------------------------------------------------------
# fake_pass_window
# ---------------------------------------------------------------------------


class TestFakePassWindow:
    def test_returns_pass_window(self):
        pw = fake_pass_window()
        assert isinstance(pw, PassWindow)

    def test_has_required_fields(self):
        pw = fake_pass_window()
        assert hasattr(pw, "aos")
        assert hasattr(pw, "los")
        assert hasattr(pw, "max_el")
        assert hasattr(pw, "trajectory")
        assert hasattr(pw, "name")

    def test_trajectory_is_list(self):
        pw = fake_pass_window()
        assert isinstance(pw.trajectory, list)
        assert len(pw.trajectory) > 0

    def test_aos_before_los(self):
        pw = fake_pass_window()
        assert pw.aos < pw.los


# ---------------------------------------------------------------------------
# current_passes
# ---------------------------------------------------------------------------


class TestCurrentPasses:
    def test_active_pass(self):
        pw = _make_pass("ACTIVE", -2, 5)
        result = current_passes([pw])
        assert len(result) == 1

    def test_past_pass(self):
        pw = _make_pass("PAST", -20, -10)
        result = current_passes([pw])
        assert len(result) == 0

    def test_future_pass(self):
        pw = _make_pass("FUTURE", 10, 20)
        result = current_passes([pw])
        assert len(result) == 0

    def test_mixed(self):
        active = _make_pass("ACTIVE", -2, 5)
        past = _make_pass("PAST", -20, -10)
        result = current_passes([active, past])
        assert len(result) == 1
        assert result[0].name == "ACTIVE"


# ---------------------------------------------------------------------------
# visible_passes (with timeout)
# ---------------------------------------------------------------------------


class TestVisiblePasses:
    def test_no_timeout_returns_all_active(self):
        pw = _make_pass("ACTIVE", -2, 10)
        result = visible_passes([pw], timeout_enabled=False, timeout_seconds=0)
        assert len(result) == 1

    def test_timeout_active_within_window(self):
        # Pass started 30 seconds ago, timeout is 60s → still visible
        pw = _make_pass("ACTIVE", -0.5, 10)
        result = visible_passes([pw], timeout_enabled=True, timeout_seconds=60)
        assert len(result) == 1

    def test_timeout_expired(self):
        # Pass started 5 minutes ago, timeout is 60s → not visible
        pw = _make_pass("ACTIVE", -5, 10)
        result = visible_passes([pw], timeout_enabled=True, timeout_seconds=60)
        assert len(result) == 0

    def test_timeout_zero_returns_all_active(self):
        pw = _make_pass("ACTIVE", -2, 10)
        result = visible_passes([pw], timeout_enabled=True, timeout_seconds=0)
        assert len(result) == 1

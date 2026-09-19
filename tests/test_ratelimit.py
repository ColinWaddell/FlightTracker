"""Tests for lookups/ratelimit.py - per-provider API call limiting."""

import sqlite3
import time as _time

import pytest


class FakeConfig:
    """Config stand-in: global mode + per-provider settings subtree."""

    def __init__(self, mode="none", settings=None):
        self.api_limit_mode = mode
        self._settings = settings or {}

    def provider_settings(self, pid):
        return dict(self._settings.get(pid, {}))


@pytest.fixture()
def isolated_ratelimit(tmp_path, monkeypatch):
    """Redirect the rate-limit db to a temp file and reset in-memory state."""
    import utilities.lookups.ratelimit as rr

    monkeypatch.setattr(rr, "DB_PATH", tmp_path / "ratelimit.sqlite3")
    monkeypatch.setattr(rr, "_conn", None)
    monkeypatch.setattr(rr, "_warned", set())
    yield rr
    if rr._conn is not None:
        rr._conn.close()
        rr._conn = None


def limit(rr, monkeypatch, mode="daily", settings=None):
    """Pin the limiter's config source to a FakeConfig."""
    monkeypatch.setattr(rr, "_config", lambda: FakeConfig(mode, settings or {}))


def settings_of(rr, pid, enabled=True, limit=500):
    """Descriptor-shaped per-provider settings."""
    return {pid: {"api_limiting_enabled": enabled, "api_limit": limit}}


# ---------------------------------------------------------------------------
# Descriptor wiring
# ---------------------------------------------------------------------------


class TestDescriptorFields:
    def test_every_provider_declares_rate_limit_fields(self):
        from utilities.lookups.registry import PROVIDERS

        assert len(PROVIDERS) == 13
        for pid, spec in PROVIDERS.items():
            enabled = spec.config.field("api_limiting_enabled")
            limit = spec.config.field("api_limit")
            assert enabled is not None, pid
            assert enabled.type == "bool" and enabled.default is False, pid
            assert limit is not None, pid
            assert limit.type == "int" and limit.default == 500, pid

    def test_defaults_fill_on_validation_without_migration(self):
        from utilities.lookups.config import validate_provider_settings
        from utilities.lookups.registry import PROVIDERS

        for pid, spec in PROVIDERS.items():
            clean, warnings = validate_provider_settings(spec.config, {})
            assert clean["api_limiting_enabled"] is False, pid
            assert clean["api_limit"] == 500, pid
            assert not warnings, pid


# ---------------------------------------------------------------------------
# Gate behaviour
# ---------------------------------------------------------------------------


class TestGate:
    def test_mode_none_passes_without_touching_the_store(
        self, isolated_ratelimit, monkeypatch
    ):
        rr = isolated_ratelimit
        limit(rr, monkeypatch, mode="none", settings=settings_of(rr, "adsbdb"))
        assert rr.gate("adsbdb") is True
        # Nothing was ever counted - the store was not even opened.
        assert rr._conn is None

    def test_disabled_provider_passes_without_counting(
        self, isolated_ratelimit, monkeypatch
    ):
        rr = isolated_ratelimit
        limit(
            rr,
            monkeypatch,
            mode="daily",
            settings={"adsbdb": {"api_limiting_enabled": False, "api_limit": 1}},
        )
        assert rr.gate("adsbdb") is True
        assert rr._conn is None

    def test_counts_and_blocks_at_limit(self, isolated_ratelimit, monkeypatch):
        rr = isolated_ratelimit
        limit(rr, monkeypatch, settings=settings_of(rr, "adsbdb", limit=3))
        assert [rr.gate("adsbdb") for _ in range(3)] == [True, True, True]
        assert rr.gate("adsbdb") is False
        assert rr.gate("adsbdb") is False

    def test_write_through_visible_without_flush(self, isolated_ratelimit, monkeypatch):
        rr = isolated_ratelimit
        limit(rr, monkeypatch, settings=settings_of(rr, "adsbdb", limit=100))
        rr.gate("adsbdb")
        rr.gate("adsbdb")
        with rr._lock:
            row = (
                rr._connect()
                .execute("SELECT n FROM calls WHERE provider = 'adsbdb'")
                .fetchone()
            )
        assert row[0] == 2

    def test_zero_limit_is_unlimited_but_counted(self, isolated_ratelimit, monkeypatch):
        rr = isolated_ratelimit
        limit(rr, monkeypatch, settings=settings_of(rr, "adsbdb", limit=0))
        assert all(rr.gate("adsbdb") for _ in range(5))
        assert rr._used("adsbdb", rr._period(rr.MODE_DAILY)) == 5

    def test_negative_limit_is_unlimited(self, isolated_ratelimit, monkeypatch):
        rr = isolated_ratelimit
        limit(rr, monkeypatch, settings=settings_of(rr, "adsbdb", limit=-7))
        assert all(rr.gate("adsbdb") for _ in range(10))

    def test_providers_are_isolated(self, isolated_ratelimit, monkeypatch):
        rr = isolated_ratelimit
        limit(
            rr,
            monkeypatch,
            settings={
                **settings_of(rr, "adsbdb", limit=1),
                **settings_of(rr, "hexdb", limit=1),
            },
        )
        assert rr.gate("adsbdb") is True
        assert rr.gate("adsbdb") is False
        # The other provider's budget is untouched.
        assert rr.gate("hexdb") is True

    def test_monthly_mode_uses_monthly_bucket(self, isolated_ratelimit, monkeypatch):
        rr = isolated_ratelimit
        limit(rr, monkeypatch, mode="monthly", settings=settings_of(rr, "adsbdb"))
        rr.gate("adsbdb")
        period = rr._period(rr.MODE_MONTHLY)
        assert len(period) == 7  # "YYYY-MM"
        assert rr._used("adsbdb", period) == 1
        assert rr._used("adsbdb", rr._period(rr.MODE_DAILY)) == 0

    def test_gate_uses_current_daily_bucket(self, isolated_ratelimit, monkeypatch):
        rr = isolated_ratelimit
        limit(rr, monkeypatch, mode="daily", settings=settings_of(rr, "adsbdb"))
        rr.gate("adsbdb")
        assert rr._used("adsbdb", rr._period(rr.MODE_DAILY)) == 1

    def test_fail_open_when_store_unusable(self, isolated_ratelimit, monkeypatch):
        rr = isolated_ratelimit

        def boom(provider, period):
            raise sqlite3.OperationalError("disk I/O error")

        limit(rr, monkeypatch, settings=settings_of(rr, "adsbdb", limit=1))
        monkeypatch.setattr(rr, "_bump", boom)
        assert rr.gate("adsbdb") is True

    def test_corrupt_db_moved_aside_and_recovered(
        self, isolated_ratelimit, tmp_path, monkeypatch
    ):
        rr = isolated_ratelimit
        rr.DB_PATH.write_bytes(b"this is not a database")
        limit(rr, monkeypatch, settings=settings_of(rr, "adsbdb", limit=10))
        assert rr.gate("adsbdb") is True
        assert rr._used("adsbdb", rr._period(rr.MODE_DAILY)) == 1
        asides = list(tmp_path.glob("ratelimit.sqlite3.corrupt-*"))
        assert asides, "corrupt file should be moved aside, not destroyed"

    def test_unlimited_mode_ignores_provider_settings_shape(
        self, isolated_ratelimit, monkeypatch
    ):
        rr = isolated_ratelimit
        # Settings that never went through descriptor validation: the
        # limiter must cope with junk instead of crashing.
        limit(
            rr, monkeypatch, mode="daily", settings={"adsbdb": {"api_limit": "bogus"}}
        )
        assert rr.gate("adsbdb") is True


class TestWarning:
    def test_warned_once_per_period(self, isolated_ratelimit, monkeypatch, caplog):
        rr = isolated_ratelimit
        limit(rr, monkeypatch, settings=settings_of(rr, "adsbdb", limit=1))
        with caplog.at_level("WARNING", logger="utilities.lookups.ratelimit"):
            rr.gate("adsbdb")  # the one allowed call
            rr.gate("adsbdb")  # blocked -> warn
            rr.gate("adsbdb")  # still blocked -> no second warning
        warnings = [r for r in caplog.records if "adsbdb" in r.message]
        assert len(warnings) == 1

    def test_warning_resets_for_next_period(
        self, isolated_ratelimit, monkeypatch, caplog
    ):
        rr = isolated_ratelimit
        limit(rr, monkeypatch, settings=settings_of(rr, "adsbdb", limit=1))
        with caplog.at_level("WARNING", logger="utilities.lookups.ratelimit"):
            rr.gate("adsbdb")
            rr.gate("adsbdb")  # warn for today
            monkeypatch.setattr(
                rr,
                "_period",
                lambda mode, now=None: "2026-12-25",
            )
            rr.gate("adsbdb")  # new period -> one fresh call, no warning
        warnings = [r for r in caplog.records if "adsbdb" in r.message]
        assert len(warnings) == 1


class TestPeriods:
    def test_daily_and_monthly_formats(self, isolated_ratelimit):
        rr = isolated_ratelimit
        ts = _time.mktime(_time.strptime("2026-09-19 12:00:00", "%Y-%m-%d %H:%M:%S"))
        assert rr._period(rr.MODE_DAILY, ts) == "2026-09-19"
        assert rr._period(rr.MODE_MONTHLY, ts) == "2026-09"
        assert rr._period(rr.MODE_NONE, ts) == "2026-09"  # monthly fallback

    def test_prune_keeps_current_and_two_previous_buckets(self, isolated_ratelimit):
        rr = isolated_ratelimit
        conn = rr._connect()
        today = rr._period(rr.MODE_DAILY)
        month = rr._period(rr.MODE_MONTHLY)
        stale_rows = [("old", "2020-01-01", 5), ("old", "2020-01", 5)]
        current = [("fresh", today, 1), ("fresh", month, 5)]
        for provider, period, n in stale_rows + current:
            conn.execute(
                "INSERT INTO calls (provider, period, n) VALUES (?, ?, ?)",
                (provider, period, n),
            )
        rr._prune(conn)
        remaining = set(conn.execute("SELECT provider, period FROM calls").fetchall())
        assert ("old", "2020-01-01") not in remaining
        assert ("old", "2020-01") not in remaining
        assert ("fresh", today) in remaining
        assert ("fresh", month) in remaining


# ---------------------------------------------------------------------------
# Status snapshot
# ---------------------------------------------------------------------------


class TestStatus:
    def test_mode_none_reports_no_usage(self, isolated_ratelimit, monkeypatch):
        rr = isolated_ratelimit
        limit(rr, monkeypatch, mode="none", settings=settings_of(rr, "adsbdb"))
        status = rr.status()
        assert status["mode"] == "none"
        assert status["period"] == ""
        assert status["providers"]["adsbdb"]["used"] == 0

    def test_enabled_provider_reports_used_and_limit(
        self, isolated_ratelimit, monkeypatch
    ):
        rr = isolated_ratelimit
        limit(
            rr,
            monkeypatch,
            mode="daily",
            settings=settings_of(rr, "adsbdb", limit=50),
        )
        rr.gate("adsbdb")
        rr.gate("adsbdb")
        status = rr.status()
        assert status["mode"] == "daily"
        assert status["providers"]["adsbdb"] == {
            "enabled": True,
            "limit": 50,
            "used": 2,
        }

    def test_all_registry_providers_present(self, isolated_ratelimit, monkeypatch):
        rr = isolated_ratelimit
        limit(rr, monkeypatch, mode="daily")
        from utilities.lookups.registry import PROVIDERS

        status = rr.status()
        assert set(status["providers"]) == set(PROVIDERS)


# ---------------------------------------------------------------------------
# clear()
# ---------------------------------------------------------------------------


class TestClear:
    def test_clear_empties_counts(self, isolated_ratelimit, monkeypatch):
        rr = isolated_ratelimit
        limit(rr, monkeypatch, settings=settings_of(rr, "adsbdb"))
        rr.gate("adsbdb")
        rr.clear()
        assert rr._used("adsbdb", rr._period(rr.MODE_DAILY)) == 0

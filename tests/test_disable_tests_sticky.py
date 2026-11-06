"""Tests for the sticky ``--disable-tests`` boot flag.

Passing ``--disable-tests`` must be persisted into config.json so the
start-up connectivity tests stay skipped across machine reboots (where
systemd's ExecStart runs without the flag) and across web-driven
"Save & Restart" cycles.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[1] / "flight-tracker.py"
SPEC = importlib.util.spec_from_file_location(
    "flight_tracker_sticky_tests", MODULE_PATH
)
ft_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(ft_module)


class FakeConfig:
    """Minimal Config double: startup_tests_disabled + save recording."""

    def __init__(self, start_disabled=False):
        self.data_store = {"startup_tests_disabled": start_disabled}
        self.save_calls = 0

    @property
    def startup_tests_disabled(self):
        return bool(self.data_store.get("startup_tests_disabled", False))

    def set(self, key, value):
        self.data_store[key] = value

    def save(self):
        self.save_calls += 1


class TestApplyStickyDisableTests:
    def test_flag_persisted_when_not_already_set(self):
        cfg = FakeConfig(start_disabled=False)

        result = ft_module._apply_sticky_disable_tests(cfg, True)

        assert result is True
        assert cfg.startup_tests_disabled is True
        assert cfg.save_calls == 1

    def test_flag_not_re_saved_when_already_persisted(self):
        """Already-sticky state must not rewrite the config on every boot."""
        cfg = FakeConfig(start_disabled=True)

        result = ft_module._apply_sticky_disable_tests(cfg, True)

        assert result is True
        assert cfg.save_calls == 0

    def test_without_flag_already_sticky_state_skips_tests(self):
        """A plain reboot (no flag) honours the sticky state."""
        cfg = FakeConfig(start_disabled=True)

        result = ft_module._apply_sticky_disable_tests(cfg, False)

        assert result is True
        assert cfg.save_calls == 0

    def test_without_flag_no_state_runs_tests_and_saves_nothing(self):
        cfg = FakeConfig(start_disabled=False)

        result = ft_module._apply_sticky_disable_tests(cfg, False)

        assert result is False
        assert cfg.save_calls == 0
        assert cfg.startup_tests_disabled is False

    def test_persisted_state_survives_a_reboot_round_trip(self, tmp_path):
        """End-to-end: flag boot writes config.json; next boot (no flag)
        reads it and still skips the tests."""
        config_path = tmp_path / "config.json"

        # Boot 1: --disable-tests passed.
        boot1 = FakeConfig(start_disabled=False)
        assert ft_module._apply_sticky_disable_tests(boot1, True) is True
        config_path.write_text(json.dumps(boot1.data_store))

        # Boot 2: systemd start, no flag.
        stored = json.loads(config_path.read_text())
        boot2 = FakeConfig(start_disabled=stored["startup_tests_disabled"])
        assert ft_module._apply_sticky_disable_tests(boot2, False) is True

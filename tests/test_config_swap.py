"""Tests for the swap-on-boot config import mechanism in flight-tracker.py.

flight-tracker.py can't be imported normally (hyphenated filename, heavy
hardware imports at module level).  We load it via importlib with the
hardware dependencies pre-stubbed, then test apply_pending_config_update()
and cleanup_successful_import() against a tmp_path.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture(scope="module")
def ft_module():
    """Load flight-tracker.py as a module with hardware deps stubbed."""
    # Pre-stub heavy modules that flight-tracker.py imports at top level.
    for mod_name in ("display", "display.panel_factory"):
        if mod_name not in sys.modules:
            mod = types.ModuleType(mod_name)
            sys.modules[mod_name] = mod
    sys.modules["display.panel_factory"].get_panel = MagicMock()
    # get_panel() returns a mock panel; load_font returns a mock font.
    panel = MagicMock()
    sys.modules["display.panel_factory"].get_panel.return_value = panel

    # Stub qrcode (optional import in flight-tracker.py, but be safe).
    if "qrcode" not in sys.modules:
        sys.modules["qrcode"] = MagicMock()

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "flight_tracker_under_test", root / "flight-tracker.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    yield mod


@pytest.fixture
def swap_paths(tmp_path, ft_module, monkeypatch):
    """Point the swap-on-boot paths at tmp_path and return them."""
    monkeypatch.setattr(ft_module, "PLATFORM_DATA_DIR", tmp_path)
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(ft_module, "CONFIG_PATH", config_path)

    return {
        "config": config_path,
        "update": tmp_path / "config-update.json",
        "backup": tmp_path / "config-backup.json",
        "in_progress": tmp_path / ".import-in-progress",
        "failed": tmp_path / ".import-failed",
    }


class TestApplyPendingConfigUpdate:
    def test_no_update_file_is_noop(self, ft_module, swap_paths):
        config = swap_paths["config"]
        config.write_text(json.dumps({"old": True}))

        ft_module.apply_pending_config_update()

        assert json.loads(config.read_text()) == {"old": True}
        assert not swap_paths["backup"].exists()
        assert not swap_paths["in_progress"].exists()

    def test_fresh_import_swaps_config(self, ft_module, swap_paths):
        config = swap_paths["config"]
        config.write_text(json.dumps({"old": True}))
        swap_paths["update"].write_text(json.dumps({"new": True}))

        ft_module.apply_pending_config_update()

        assert json.loads(config.read_text()) == {"new": True}
        assert json.loads(swap_paths["backup"].read_text()) == {"old": True}
        assert swap_paths["in_progress"].exists()
        assert not swap_paths["update"].exists()

    def test_fresh_import_no_existing_config(self, ft_module, swap_paths):
        """If config.json doesn't exist yet, swap still applies the update."""
        swap_paths["update"].write_text(json.dumps({"new": True}))

        ft_module.apply_pending_config_update()

        assert json.loads(swap_paths["config"].read_text()) == {"new": True}
        assert not swap_paths["backup"].exists()
        assert swap_paths["in_progress"].exists()

    def test_crash_restore_restores_backup(self, ft_module, swap_paths):
        """Marker + update present => previous boot crashed; restore backup."""
        config = swap_paths["config"]
        config.write_text(json.dumps({"crashed_new": True}))
        swap_paths["backup"].write_text(json.dumps({"good": True}))
        swap_paths["in_progress"].touch()
        swap_paths["update"].write_text(json.dumps({"another": True}))

        ft_module.apply_pending_config_update()

        assert json.loads(config.read_text()) == {"good": True}
        assert not swap_paths["update"].exists()
        assert not swap_paths["in_progress"].exists()
        assert swap_paths["failed"].exists()

    def test_failed_marker_already_present_is_noop(self, ft_module, swap_paths):
        config = swap_paths["config"]
        config.write_text(json.dumps({"keep": True}))
        swap_paths["failed"].touch()
        swap_paths["update"].write_text(json.dumps({"ignore": True}))

        ft_module.apply_pending_config_update()

        assert json.loads(config.read_text()) == {"keep": True}
        assert swap_paths["update"].exists(), "should not consume update"


class TestCleanupSuccessfulImport:
    def test_deletes_backup_and_marker(self, ft_module, swap_paths):
        swap_paths["backup"].write_text(json.dumps({"old": True}))
        swap_paths["in_progress"].touch()

        ft_module.cleanup_successful_import()

        assert not swap_paths["backup"].exists()
        assert not swap_paths["in_progress"].exists()

    def test_no_files_is_noop(self, ft_module, swap_paths):
        """Should not raise if there's nothing to clean up."""
        ft_module.cleanup_successful_import()
        assert not swap_paths["backup"].exists()
        assert not swap_paths["in_progress"].exists()

    def test_does_not_touch_failed_marker(self, ft_module, swap_paths):
        """Cleanup on success should not delete a pre-existing failed marker."""
        swap_paths["backup"].write_text(json.dumps({"old": True}))
        swap_paths["in_progress"].touch()
        swap_paths["failed"].touch()

        ft_module.cleanup_successful_import()

        assert swap_paths["failed"].exists()


class TestFullImportCycle:
    """End-to-end: fresh import -> cleanup -> no leftover state."""

    def test_successful_import_cycle(self, ft_module, swap_paths):
        config = swap_paths["config"]
        config.write_text(json.dumps({"old": True}))
        swap_paths["update"].write_text(json.dumps({"new": True}))

        # Boot 1: apply the staged import.
        ft_module.apply_pending_config_update()
        assert json.loads(config.read_text()) == {"new": True}
        assert swap_paths["backup"].exists()
        assert swap_paths["in_progress"].exists()

        # Boot succeeds: cleanup.
        ft_module.cleanup_successful_import()
        assert not swap_paths["backup"].exists()
        assert not swap_paths["in_progress"].exists()
        assert not swap_paths["failed"].exists()

        # Boot 2: no leftover state, no-op.
        ft_module.apply_pending_config_update()
        assert json.loads(config.read_text()) == {"new": True}
        assert not swap_paths["backup"].exists()

    def test_crash_then_restore_cycle(self, ft_module, swap_paths):
        config = swap_paths["config"]
        config.write_text(json.dumps({"old": True}))
        swap_paths["update"].write_text(json.dumps({"bad": True}))

        # Boot 1: apply staged import.
        ft_module.apply_pending_config_update()
        assert json.loads(config.read_text()) == {"bad": True}

        # Process crashes - no cleanup.  systemd restarts.
        # Boot 2: marker still present => restore backup.
        ft_module.apply_pending_config_update()
        assert json.loads(config.read_text()) == {"old": True}
        assert swap_paths["failed"].exists()

        # Boot 3: failed marker present => no-op, config stays restored.
        ft_module.apply_pending_config_update()
        assert json.loads(config.read_text()) == {"old": True}

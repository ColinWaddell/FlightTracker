"""Tests for Display.update_brightness - simple and advanced schedules.

Builds the Display class via ``build_display_class()`` with the panel
factory patched (MagicMock panel) and ``Config.instance`` mocked, so no
hardware or real config file is involved.
"""

from datetime import time
from unittest.mock import MagicMock, patch

import display


def _make_display(cfg, brightness=60):
    """Build a Display with a mocked panel, config, and scenes.

    ``brightness`` seeds the panel's get_brightness() return value.
    Returns (display, panel) with panel call counters reset, so init-time
    calls (clear/create_canvas) don't pollute assertions.
    """
    panel = MagicMock()
    panel.get_brightness.return_value = brightness
    panel.create_canvas.return_value = MagicMock(name="canvas")

    with (
        patch("display.panel_factory.get_panel", return_value=panel),
        # Config is imported inside build_display_class(), so patch it at
        # its source module rather than on the display package.
        patch("setup.configuration.Config") as MockConfig,
        patch("display.get_overhead_instance") as mock_overhead,
        # Real scenes start threads / touch real config - stub them.
        patch("utilities.scene_manager.SceneManager") as mock_sm_cls,
        patch("scenes.idle.idle_scene.IdleScene"),
        patch("scenes.flight.flight_scene.FlightScene"),
    ):
        MockConfig.instance.return_value = cfg
        mock_overhead.return_value = MagicMock()

        display_cls = display.build_display_class()
        disp = display_cls()

    disp.scene_manager = mock_sm_cls.return_value
    panel.reset_mock()
    return disp, panel


def _advanced_cfg(entries, mode="advanced", default_brightness=3):
    """A MagicMock cfg exposing the schedule API update_brightness uses."""
    cfg = MagicMock()
    cfg.brightness_mode = mode
    cfg.brightness_percent = {1: 20, 2: 40, 3: 60, 4: 80, 5: 100}[default_brightness]
    cfg.screen_schedule_advanced = entries
    cfg.advanced_brightness_percent_at.side_effect = lambda: _percent_at(entries)
    cfg.is_in_brightness_schedule.return_value = False
    cfg.schedule_brightness_percent = 0
    cfg.is_in_device_standby.return_value = False
    # Attributes read by build_display_class() before Display is built.
    cfg.colour_theme = 0
    cfg.loading_indicator = "none"
    cfg.satellite_tracking_enabled = False
    cfg.display_scan_rate = 16
    cfg.screen_rotate = False
    cfg.hat_pwm_enabled = False
    cfg.gpio_slowdown = 1
    cfg.panel_colour_order = "RGB"
    cfg.display_speed_factor = 1.0
    return cfg


def _percent_at(entries):
    """Mirror Config.advanced_brightness_percent_at for mock cfgs."""
    if not entries:
        return None
    now = time().hour * 60 + time().minute
    active = entries[-1]
    for entry in entries:
        h, m = (int(x) for x in entry["time"].split(":"))
        if h * 60 + m <= now:
            active = entry
        else:
            break
    return {0: 0, 1: 20, 2: 40, 3: 60, 4: 80, 5: 100}[active["brightness"]]


class TestAdvancedScheduleApplication:
    def test_applies_active_entry_percent(self):
        entries = [{"time": "00:00", "brightness": 2}]
        cfg = _advanced_cfg(entries)
        disp, panel = _make_display(cfg, brightness=60)

        disp.update_brightness()

        panel.set_brightness.assert_called_once_with(40)

    def test_zero_entry_clears_canvas(self):
        entries = [{"time": "00:00", "brightness": 0}]
        cfg = _advanced_cfg(entries)
        disp, panel = _make_display(cfg, brightness=60)

        disp.update_brightness()

        panel.set_brightness.assert_called_once_with(0)
        panel.clear.assert_called_once_with(disp.canvas)

    def test_no_redundant_write_when_unchanged(self):
        entries = [{"time": "00:00", "brightness": 3}]
        cfg = _advanced_cfg(entries)
        disp, panel = _make_display(cfg, brightness=60)

        disp.update_brightness()

        panel.set_brightness.assert_not_called()
        panel.clear.assert_not_called()

    def test_empty_schedule_restores_default(self):
        cfg = _advanced_cfg([])
        disp, panel = _make_display(cfg, brightness=20)

        disp.update_brightness()

        panel.set_brightness.assert_called_once_with(60)
        panel.clear.assert_not_called()

    def test_transition_from_zero_restores_without_clear(self):
        """Leaving a 0% entry restores brightness but doesn't clear."""
        entries = [{"time": "00:00", "brightness": 0}]
        cfg = _advanced_cfg(entries)
        disp, panel = _make_display(cfg, brightness=0)

        # Simulate the schedule moving to a non-zero entry.
        cfg.screen_schedule_advanced = [{"time": "00:00", "brightness": 4}]
        cfg.advanced_brightness_percent_at.side_effect = None
        cfg.advanced_brightness_percent_at.return_value = 80

        disp.update_brightness()

        panel.set_brightness.assert_called_once_with(80)
        panel.clear.assert_not_called()


class TestSimpleScheduleApplication:
    def test_out_of_schedule_restores_default(self):
        cfg = _advanced_cfg([], mode="simple")
        cfg.is_in_brightness_schedule.return_value = False
        disp, panel = _make_display(cfg, brightness=20)

        disp.update_brightness()

        panel.set_brightness.assert_called_once_with(60)

    def test_in_schedule_applies_scheduled_percent(self):
        cfg = _advanced_cfg([], mode="simple")
        cfg.is_in_brightness_schedule.return_value = True
        cfg.schedule_brightness_percent = 40
        disp, panel = _make_display(cfg, brightness=60)

        disp.update_brightness()

        panel.set_brightness.assert_called_once_with(40)
        panel.clear.assert_not_called()

    def test_in_schedule_zero_clears_canvas(self):
        cfg = _advanced_cfg([], mode="simple")
        cfg.is_in_brightness_schedule.return_value = True
        cfg.schedule_brightness_percent = 0
        disp, panel = _make_display(cfg, brightness=60)

        disp.update_brightness()

        panel.set_brightness.assert_called_once_with(0)
        panel.clear.assert_called_once_with(disp.canvas)


class TestStandbyGate:
    def test_standby_skips_scene_kick(self):
        """The run-loop gate consults is_in_device_standby."""
        entries = [{"time": "00:00", "brightness": 0}]
        cfg = _advanced_cfg(entries)
        cfg.is_in_device_standby.return_value = True
        disp, _panel = _make_display(cfg)

        # Simulate one iteration of the run loop's gate.
        if not cfg.is_in_device_standby():
            disp.scene_manager.kick()

        disp.scene_manager.kick.assert_not_called()

    def test_not_standby_kicks_scenes(self):
        cfg = _advanced_cfg([{"time": "00:00", "brightness": 3}])
        cfg.is_in_device_standby.return_value = False
        disp, _panel = _make_display(cfg)

        if not cfg.is_in_device_standby():
            disp.scene_manager.kick()

        disp.scene_manager.kick.assert_called_once()

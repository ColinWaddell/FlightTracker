"""Tests for utilities/cli.py - CLI command dispatch."""

import json
from unittest.mock import patch

import pytest

from utilities.cli import dispatch_cli_command


@pytest.fixture
def mock_config(tmp_path):
    """Patch CONFIG_PATH and Config for CLI tests."""
    config_path = tmp_path / "config.json"

    with (
        patch("utilities.cli.CONFIG_PATH", config_path),
        patch("utilities.cli.Config") as MockConfig,
    ):
        cfg = MockConfig.instance.return_value
        cfg.as_dict.return_value = {
            "flight_lat": 55.0,
            "flight_lng": -4.0,
            "temperature_unit": "c",
        }

        def _set(key, value):
            cfg.as_dict.return_value[key] = value

        cfg.set.side_effect = _set

        def _save():
            config_path.write_text(json.dumps(cfg.as_dict.return_value))

        cfg.save.side_effect = _save

        yield config_path, MockConfig


class TestNoCommand:
    def test_no_args_returns_zero(self, mock_config):
        assert dispatch_cli_command(["flight-tracker.py"]) == 0


class TestVersion:
    def test_version_flag(self, mock_config, capsys):
        result = dispatch_cli_command(["flight-tracker.py", "--version"])
        assert result == 0
        captured = capsys.readouterr()
        # Should print something like "2.0.6"
        assert "." in captured.out.strip()


class TestHelp:
    def test_help_command(self, mock_config, capsys):
        result = dispatch_cli_command(["flight-tracker.py", "help"])
        assert result == 0
        captured = capsys.readouterr()
        assert "Usage" in captured.out
        assert "config" in captured.out.lower()

    def test_help_flag(self, mock_config, capsys):
        result = dispatch_cli_command(["flight-tracker.py", "--help"])
        assert result == 0

    def test_h_flag(self, mock_config, capsys):
        result = dispatch_cli_command(["flight-tracker.py", "-h"])
        assert result == 0


class TestConfigCommand:
    def test_config_dumps_json(self, mock_config, capsys):
        config_path, _ = mock_config
        config_path.write_text('{"existing": true}')
        result = dispatch_cli_command(["flight-tracker.py", "config"])
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "flight_lat" in data

    def test_config_no_file(self, mock_config, capsys):
        config_path, _ = mock_config
        # Don't create the config file
        assert not config_path.exists()
        result = dispatch_cli_command(["flight-tracker.py", "config"])
        assert result == 1
        captured = capsys.readouterr()
        assert "No config" in captured.err


class TestDataCommand:
    def test_data_prints_path(self, mock_config, capsys):
        config_path, _ = mock_config
        result = dispatch_cli_command(["flight-tracker.py", "data"])
        assert result == 0
        captured = capsys.readouterr()
        assert str(config_path.parent) in captured.out


class TestResetPassword:
    def test_reset_password(self, mock_config, capsys):
        config_path, _ = mock_config
        config_path.write_text('{"existing": true}')
        result = dispatch_cli_command(["flight-tracker.py", "reset", "password"])
        assert result == 0
        captured = capsys.readouterr()
        assert "web_password_hash" in captured.out

    def test_reset_password_no_config(self, mock_config, capsys):
        config_path, _ = mock_config
        assert not config_path.exists()
        result = dispatch_cli_command(["flight-tracker.py", "reset", "password"])
        assert result == 1


class TestResetSettings:
    def test_reset_settings(self, mock_config, capsys):
        config_path, _ = mock_config
        config_path.write_text('{"existing": true}')
        result = dispatch_cli_command(["flight-tracker.py", "reset", "settings"])
        assert result == 0
        captured = capsys.readouterr()
        assert str(config_path) in captured.out
        assert not config_path.exists()

    def test_reset_settings_no_config(self, mock_config, capsys):
        config_path, _ = mock_config
        assert not config_path.exists()
        result = dispatch_cli_command(["flight-tracker.py", "reset", "settings"])
        assert result == 1


class TestInterfaceCommand:
    def test_interface_enable(self, mock_config, capsys):
        config_path, _ = mock_config
        config_path.write_text('{"existing": true}')
        result = dispatch_cli_command(["flight-tracker.py", "interface", "enable"])
        assert result == 0
        captured = capsys.readouterr()
        assert "web_interface_enabled=True" in captured.out

    def test_interface_disable(self, mock_config, capsys):
        config_path, _ = mock_config
        config_path.write_text('{"existing": true}')
        result = dispatch_cli_command(["flight-tracker.py", "interface", "disable"])
        assert result == 0
        captured = capsys.readouterr()
        assert "web_interface_enabled=False" in captured.out

    def test_interface_no_config(self, mock_config, capsys):
        config_path, _ = mock_config
        assert not config_path.exists()
        result = dispatch_cli_command(["flight-tracker.py", "interface", "enable"])
        assert result == 1


class TestConfigSet:
    def test_config_set_known_key(self, mock_config, capsys):
        config_path, MockConfig = mock_config
        config_path.write_text('{"existing": true}')
        result = dispatch_cli_command(
            ["flight-tracker.py", "config", "set", "flight_lat", "51.5"]
        )
        assert result == 0
        cfg = MockConfig.instance.return_value
        cfg.set.assert_called_with("flight_lat", 51.5)
        cfg.save.assert_called_once()
        captured = capsys.readouterr()
        assert "flight_lat" in captured.out

    def test_config_set_coerces_bool(self, mock_config):
        config_path, MockConfig = mock_config
        config_path.write_text('{"existing": true}')
        dispatch_cli_command(
            ["flight-tracker.py", "config", "set", "screen_rotate", "true"]
        )
        cfg = MockConfig.instance.return_value
        cfg.set.assert_called_with("screen_rotate", True)

    def test_config_set_coerces_list(self, mock_config):
        config_path, MockConfig = mock_config
        config_path.write_text('{"existing": true}')
        dispatch_cli_command(
            [
                "flight-tracker.py",
                "config",
                "set",
                "satellite_norad_ids",
                "[25544,40069]",
            ]
        )
        cfg = MockConfig.instance.return_value
        cfg.set.assert_called_with("satellite_norad_ids", [25544, 40069])

    def test_config_set_bare_string(self, mock_config):
        config_path, MockConfig = mock_config
        config_path.write_text('{"existing": true}')
        dispatch_cli_command(
            ["flight-tracker.py", "config", "set", "data_source", "tar1090"]
        )
        cfg = MockConfig.instance.return_value
        cfg.set.assert_called_with("data_source", "tar1090")

    def test_config_set_unknown_key_rejected(self, mock_config, capsys):
        config_path, _ = mock_config
        config_path.write_text('{"existing": true}')
        result = dispatch_cli_command(
            ["flight-tracker.py", "config", "set", "flight_lattitude", "51.5"]
        )
        assert result == 2
        captured = capsys.readouterr()
        assert "Unknown config key" in captured.err

    def test_config_set_no_args_usage(self, mock_config, capsys):
        config_path, _ = mock_config
        config_path.write_text('{"existing": true}')
        result = dispatch_cli_command(["flight-tracker.py", "config", "set"])
        assert result == 2
        captured = capsys.readouterr()
        assert "Usage" in captured.err


class TestScreenTest:
    def test_screen_test_runs_four_steps(self, mock_config, capsys):
        config_path, MockConfig = mock_config
        config_path.write_text('{"existing": true}')
        cfg = MockConfig.instance.return_value
        cfg.brightness_percent = 60
        cfg.screen_rotate = False
        cfg.hat_pwm_enabled = True
        cfg.gpio_slowdown = 1

        with (
            patch("display.panel_factory.get_panel") as mock_get_panel,
            patch("utilities.cli.time.sleep") as mock_sleep,
        ):
            panel = mock_get_panel.return_value

            result = dispatch_cli_command(["flight-tracker.py", "screen-test"])

        assert result == 0
        # Panel initialised with config-derived settings
        panel.init_matrix.assert_called_once()
        kwargs = panel.init_matrix.call_args.kwargs
        assert kwargs["brightness"] == 60
        assert kwargs["rotation"] == 0
        assert kwargs["hat_pwm"] is True
        assert kwargs["gpio_slowdown"] == 1

        # Seven colours x three brightness steps = 21 fills/swaps/sleeps
        assert panel.fill.call_count == 21
        assert panel.swap.call_count >= 21
        assert mock_sleep.call_count == 21
        for call in mock_sleep.call_args_list:
            assert call.args[0] == 2

        # set_brightness called once per step (21) plus once in finally to restore
        assert panel.set_brightness.call_count == 22
        brightnesses = [call.args[0] for call in panel.set_brightness.call_args_list]
        # First 21 calls cycle 100/66/33 for each of the 7 colours
        assert brightnesses[:3] == [100, 66, 33]
        # Final call restores the configured brightness
        assert brightnesses[-1] == 60

        captured = capsys.readouterr()
        assert "white" in captured.out
        assert "red" in captured.out
        assert "green" in captured.out
        assert "blue" in captured.out
        assert "yellow" in captured.out
        assert "magenta" in captured.out
        assert "cyan" in captured.out
        assert "100%" in captured.out
        assert "66%" in captured.out
        assert "33%" in captured.out
        assert "Screen test complete" in captured.out

    def test_screen_test_rotation_180_when_configured(self, mock_config):
        config_path, MockConfig = mock_config
        config_path.write_text('{"existing": true}')
        cfg = MockConfig.instance.return_value
        cfg.brightness_percent = 80
        cfg.screen_rotate = True
        cfg.hat_pwm_enabled = False
        cfg.gpio_slowdown = 2

        with (
            patch("display.panel_factory.get_panel") as mock_get_panel,
            patch("utilities.cli.time.sleep"),
        ):
            panel = mock_get_panel.return_value
            dispatch_cli_command(["flight-tracker.py", "screen-test"])

        kwargs = panel.init_matrix.call_args.kwargs
        assert kwargs["rotation"] == 180
        assert kwargs["brightness"] == 80
        assert kwargs["hat_pwm"] is False
        assert kwargs["gpio_slowdown"] == 2

    def test_screen_test_clears_on_interrupt(self, mock_config, capsys):
        config_path, MockConfig = mock_config
        config_path.write_text('{"existing": true}')
        cfg = MockConfig.instance.return_value
        cfg.brightness_percent = 60
        cfg.screen_rotate = False
        cfg.hat_pwm_enabled = True
        cfg.gpio_slowdown = 1

        with (
            patch("display.panel_factory.get_panel") as mock_get_panel,
            patch("utilities.cli.time.sleep", side_effect=KeyboardInterrupt),
        ):
            panel = mock_get_panel.return_value
            canvas = panel.create_canvas.return_value
            result = dispatch_cli_command(["flight-tracker.py", "screen-test"])

        assert result == 0
        # Canvas should still be cleared in the finally block
        panel.clear.assert_called_once_with(canvas)
        captured = capsys.readouterr()
        assert "Interrupted" in captured.err


class TestUnknownCommand:
    def test_unknown_command(self, mock_config, capsys):
        result = dispatch_cli_command(["flight-tracker.py", "badcommand"])
        assert result == 2
        captured = capsys.readouterr()
        assert "Unknown command" in captured.err

    def test_bad_interface_action(self, mock_config, capsys):
        result = dispatch_cli_command(["flight-tracker.py", "interface", "badaction"])
        assert result == 2

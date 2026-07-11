"""Tests for utilities/cli.py — CLI command dispatch."""

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
            "units": "m",
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
        result = dispatch_cli_command(["flight-tracker.py", "reset-password"])
        assert result == 0
        captured = capsys.readouterr()
        assert "web_password_hash" in captured.out

    def test_reset_password_no_config(self, mock_config, capsys):
        config_path, _ = mock_config
        assert not config_path.exists()
        result = dispatch_cli_command(["flight-tracker.py", "reset-password"])
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


class TestUnknownCommand:
    def test_unknown_command(self, mock_config, capsys):
        result = dispatch_cli_command(["flight-tracker.py", "badcommand"])
        assert result == 2
        captured = capsys.readouterr()
        assert "Unknown command" in captured.err

    def test_bad_interface_action(self, mock_config, capsys):
        result = dispatch_cli_command(["flight-tracker.py", "interface", "badaction"])
        assert result == 2

from __future__ import annotations

import json
import sys
from collections.abc import Sequence

from setup.configuration import CONFIG_PATH, Config
from utilities import routes_cache
from utilities.tle_manager import TLE_CACHE_PATH
from version import VERSION


def _config_exists() -> bool:
    return CONFIG_PATH.exists()


def _warn_no_config() -> None:
    print(f"No config found at {CONFIG_PATH}", file=sys.stderr)
    print(
        "Run the application once or create a config before using this command.",
        file=sys.stderr,
    )


def _load_existing_config() -> Config | None:
    if not _config_exists():
        _warn_no_config()
        return None
    return Config.instance()


def _save_config_change(key: str, value) -> int:
    cfg = _load_existing_config()
    if cfg is None:
        return 1
    cfg.set(key, value)
    cfg.save()
    print(f"Updated {key} in {CONFIG_PATH}")
    return 0


def _cache_clear() -> int:
    """Wipe all on-disk cache files (routes and TLE)."""
    cleared = []

    routes_cache.clear()
    cleared.append(f"routes cache ({routes_cache.CACHE_PATH})")

    if TLE_CACHE_PATH.exists():
        try:
            TLE_CACHE_PATH.unlink()
            cleared.append(f"TLE cache ({TLE_CACHE_PATH})")
        except OSError as e:
            print(f"Failed to delete TLE cache: {e}", file=sys.stderr)
            return 1

    for item in cleared:
        print(f"Cleared {item}")
    return 0


def _print_usage() -> None:
    print("Usage: python flight-tracker.py [command]")
    print("Commands:")
    print("  config                 Dump current configuration as JSON")
    print("  data                   Print the platform data directory path")
    print("  reset-password         Clear web_password_hash in the config")
    print("  cache clear            Wipe all on-disk cache files")
    print("  interface enable       Enable the web interface in the config")
    print("  interface disable      Disable the web interface in the config")
    print("  help                   Show this help message")
    print("  --version              Print the program version")


def dispatch_cli_command(argv: Sequence[str]) -> int:
    if len(argv) == 1:
        return 0

    command = argv[1].lower()
    if len(argv) == 2:
        if command == "config":
            if not _config_exists():
                _warn_no_config()
                return 1
            cfg = Config.instance()
            print(json.dumps(cfg.as_dict(), indent=2))
            return 0
        if command == "data":
            print(CONFIG_PATH.parent)
            return 0
        if command == "--version":
            print(".".join(map(str, VERSION)))
            return 0
        if command == "reset-password":
            return _save_config_change("web_password_hash", "")
        if command in {"help", "--help", "-h"}:
            _print_usage()
            return 0
        print(f"Unknown command: {command}", file=sys.stderr)
        _print_usage()
        return 2

    if len(argv) == 3:
        action = argv[2].lower()
        if command == "interface" and action in {"enable", "disable"}:
            if not _config_exists():
                _warn_no_config()
                return 1
            cfg = Config.instance()
            enabled = action == "enable"
            cfg.set("web_interface_enabled", enabled)
            cfg.save()
            print(f"Set web_interface_enabled={enabled} in {CONFIG_PATH}")
            return 0
        if command == "cache" and action == "clear":
            return _cache_clear()

    _print_usage()
    return 2

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict

from setup.configuration import CONFIG_PATH, DEFAULTS, Config
from utilities import routes_cache
from utilities.tle_manager import TLE_CACHE_PATH, fetch_tle
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


def _coerce_value(raw: str):
    """Parse a CLI string into a Python value via JSON, falling back to str.

    ``true``/``false`` -> bool, ``123`` -> int, ``55.87`` -> float,
    ``[25544, 40069]`` -> list, ``"GLA"`` -> str, bare ``fr24`` -> str.
    """
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return raw


def _set_nested(cfg: Config, key: str, value) -> None:
    """Set a possibly dot-separated nested key in the config data store.

    ``theme.forecast.duration`` walks into cfg["theme"]["forecast"]["duration"],
    creating intermediate dicts as needed.
    """
    if "." not in key:
        cfg.set(key, value)
        return

    parts = key.split(".")
    top = parts[0]
    container = cfg.get(top)
    if not isinstance(container, dict):
        container = {}
        cfg.set(top, container)
    for part in parts[1:-1]:
        if not isinstance(container.get(part), dict):
            container[part] = {}
        container = container[part]
    container[parts[-1]] = value


def _config_set(argv: Sequence[str]) -> int:
    """Handle ``config set <key> <value>``."""
    if len(argv) < 2:
        print("Usage: config set <key> <value>", file=sys.stderr)
        print(
            "Run 'python flight-tracker.py config' to see valid keys.",
            file=sys.stderr,
        )
        return 2

    key, raw_value = argv[0], argv[1]
    top = key.split(".")[0]

    if top not in DEFAULTS:
        print(f"Unknown config key: {key}", file=sys.stderr)
        print(f"Valid keys: {', '.join(sorted(DEFAULTS))}", file=sys.stderr)
        return 2

    value = _coerce_value(raw_value)

    # reload() creates config.json from DEFAULTS if it doesn't exist yet,
    # so the install script can seed values before first run.
    Config.reload()
    cfg = Config.instance()
    _set_nested(cfg, key, value)
    cfg.save()
    print(f"Set {key}={value!r} in {CONFIG_PATH}")
    return 0


def _screen_test() -> int:
    """Display each colour at 100/66/33% brightness for 2s each, then quit.

    Cycles through white, red, green, blue, yellow, magenta, cyan. For each
    colour the panel brightness is stepped through 100%, 66%, and 33% (2s per
    step), so each colour is shown for 6 seconds total. Loads screen settings
    (rotation, PWM, GPIO slowdown) from the config; brightness is driven by
    the test itself rather than the config value.
    """
    from display.panel_factory import get_panel

    # reload() creates config.json from DEFAULTS if it doesn't exist yet.
    Config.reload()
    cfg = Config.instance()

    panel = get_panel()
    panel.init_matrix(
        width=64,
        height=32,
        brightness=cfg.brightness_percent,
        rotation=180 if cfg.screen_rotate else 0,
        hat_pwm=cfg.hat_pwm_enabled,
        gpio_slowdown=cfg.gpio_slowdown,
    )
    canvas = panel.create_canvas()

    colours = [
        ("white", 255, 255, 255),
        ("red", 255, 0, 0),
        ("green", 0, 255, 0),
        ("blue", 0, 0, 255),
        ("yellow", 255, 255, 0),
        ("magenta", 255, 0, 255),
        ("cyan", 0, 255, 255),
    ]
    brightness_steps = [100, 66, 33]

    try:
        for name, r, g, b in colours:
            for percent in brightness_steps:
                print(f"Displaying {name} at {percent}% brightness for 2 seconds...")
                panel.set_brightness(percent)
                panel.fill(canvas, r, g, b)
                panel.swap(canvas)
                time.sleep(2)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
    finally:
        panel.clear(canvas)
        panel.swap(canvas)
        # Restore the configured brightness so we don't leave the panel dim.
        panel.set_brightness(cfg.brightness_percent)

    print("Screen test complete.")
    return 0


def _reset_settings() -> int:
    """Delete the config.json file from the platform data directory."""
    if not _config_exists():
        print(f"No config found at {CONFIG_PATH}", file=sys.stderr)
        return 1
    try:
        CONFIG_PATH.unlink()
        print(f"Deleted {CONFIG_PATH}")
        return 0
    except OSError as e:
        print(f"Failed to delete config: {e}", file=sys.stderr)
        return 1


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


# ---------------------------------------------------------------------------
# test overhead / test tle commands
# ---------------------------------------------------------------------------


def _parse_test_args(argv: Sequence[str], target: str) -> argparse.Namespace:
    """Parse --parameters for ``test`` sub-commands."""
    p = argparse.ArgumentParser(
        prog=f"python flight-tracker.py test {target}",
        description=f"Run a {target} lookup and print JSON output.",
    )

    if target == "overhead_fr24":
        p.add_argument(
            "--lat", type=float, help="Centre latitude (default: from config)"
        )
        p.add_argument(
            "--lng", type=float, help="Centre longitude (default: from config)"
        )
        p.add_argument(
            "--radius", type=float, help="Search radius in km (default: from config)"
        )
        p.add_argument(
            "--max_flights",
            type=int,
            help="Max flights to return (default: from config)",
        )
        p.add_argument(
            "--callsign_format",
            choices=["icao", "iata"],
            help="Callsign format (default: from config)",
        )

    elif target == "overhead_tar1090":
        p.add_argument("--url", help="tar1090 aircraft.json URL (default: from config)")
        p.add_argument(
            "--lat", type=float, help="Centre latitude (default: from config)"
        )
        p.add_argument(
            "--lng", type=float, help="Centre longitude (default: from config)"
        )
        p.add_argument(
            "--radius", type=float, help="Search radius in km (default: from config)"
        )
        p.add_argument(
            "--max_flights",
            type=int,
            help="Max flights to return (default: from config)",
        )

    elif target == "overhead_osn":
        p.add_argument(
            "--client_id", help="OpenSky Network client ID (default: from config)"
        )
        p.add_argument(
            "--client_secret",
            help="OpenSky Network client secret (default: from config)",
        )
        p.add_argument(
            "--lat", type=float, help="Centre latitude (default: from config)"
        )
        p.add_argument(
            "--lng", type=float, help="Centre longitude (default: from config)"
        )
        p.add_argument(
            "--radius", type=float, help="Search radius in km (default: from config)"
        )
        p.add_argument(
            "--max_flights",
            type=int,
            help="Max flights to return (default: from config)",
        )

    elif target == "tle":
        p.add_argument(
            "--norad_id",
            type=int,
            action="append",
            default=[],
            help="NORAD catalog ID to fetch (can be repeated, default: from config)",
        )

    p.add_argument(
        "--interval",
        type=float,
        default=None,
        help="Seconds between repeated attempts (default: single-shot)",
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of attempts when --interval is set (default: unlimited)",
    )

    return p.parse_args(argv)


def _apply_overhead_overrides(cfg: Config, args: argparse.Namespace) -> None:
    """Override config fields from CLI args before constructing an Overhead."""
    if getattr(args, "lat", None) is not None:
        cfg.set("flight_lat", args.lat)
    if getattr(args, "lng", None) is not None:
        cfg.set("flight_lng", args.lng)
    if getattr(args, "radius", None) is not None:
        cfg.set("flight_radius", args.radius)
    if getattr(args, "max_flights", None) is not None:
        cfg.set("max_flight_lookup", args.max_flights)
    if getattr(args, "callsign_format", None) is not None:
        cfg.set("callsign_format", args.callsign_format)
    if getattr(args, "url", None) is not None:
        cfg.set("tar1090_url", args.url)
    if getattr(args, "client_id", None) is not None:
        cfg.set("osn_client_id", args.client_id)
    if getattr(args, "client_secret", None) is not None:
        cfg.set("osn_client_secret", args.client_secret)


def _run_overhead_test(target: str, argv: Sequence[str]) -> int:
    """Instantiate an Overhead module, fetch data, and print JSON."""
    args = _parse_test_args(argv, target)

    # Force config to load fresh (it creates defaults if no file exists)
    Config.reload()
    cfg = Config.instance()
    _apply_overhead_overrides(cfg, args)

    module_map = {
        "overhead_fr24": "utilities.overhead_fr24",
        "overhead_tar1090": "utilities.overhead_tar1090",
        "overhead_osn": "utilities.overhead_osn",
    }

    import importlib

    mod = importlib.import_module(module_map[target])
    overhead = mod.Overhead()

    def do_one() -> None:
        overhead.refresh()
        if overhead.error is not None:
            print(json.dumps({"error": str(overhead.error)}, indent=2))
        else:
            flights = [asdict(f) for f in overhead.data]
            print(json.dumps(flights, indent=2))

    return _loop(do_one, args)


def _run_tle_test(argv: Sequence[str]) -> int:
    """Fetch TLE data and print JSON."""
    args = _parse_test_args(argv, "tle")

    norad_ids = args.norad_id
    if not norad_ids:
        Config.reload()
        norad_ids = Config.instance().satellite_norad_ids
        if not norad_ids:
            print(
                json.dumps(
                    {"error": "No NORAD IDs supplied and none in config"}, indent=2
                )
            )
            return 1

    def do_one() -> None:
        results = []
        for nid in norad_ids:
            tle = fetch_tle(nid)
            if tle:
                results.append(
                    {"norad_id": nid, "name": tle[0], "line1": tle[1], "line2": tle[2]}
                )
            else:
                results.append({"norad_id": nid, "error": "No TLE found"})
        print(json.dumps(results, indent=2))

    return _loop(do_one, args)


def _loop(fn, args: argparse.Namespace) -> int:
    """Run *fn* once, or repeatedly at --interval until --limit or Ctrl-C."""
    count = 0
    try:
        while True:
            count += 1
            if args.interval and count > 1:
                print(f"--- waiting {args.interval}s ---", file=sys.stderr)
                time.sleep(args.interval)
            fn()
            if args.interval is None:
                break
            if args.limit is not None and count >= args.limit:
                break
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
    return 0


def _print_usage() -> None:
    print("Usage: python flight-tracker.py [command]")
    print("Commands:")
    print("  config                 Dump current configuration as JSON")
    print("  config set <key> <val> Set a config key (validated against defaults)")
    print("  data                   Print the platform data directory path")
    print(
        "  screen-test            Cycle each colour through 100/66/33% brightness (2s each)"
    )
    print("  reset password         Clear web_password_hash in the config")
    print("  reset settings         Delete the config.json file")
    print("  cache clear            Wipe all on-disk cache files")
    print("  interface enable       Enable the web interface in the config")
    print("  interface disable      Disable the web interface in the config")
    print("  test overhead_fr24     Test FlightRadar24 data source")
    print("  test overhead_tar1090  Test tar1090 data source")
    print("  test overhead_osn      Test OpenSky Network data source")
    print("  test tle               Test TLE satellite lookup")
    print("  help                   Show this help message")
    print("  --version              Print the program version")
    print()
    print("Test commands accept --parameters and --interval/--limit for repeated runs.")
    print("Run 'python flight-tracker.py test <target> --help' for details.")


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
        if command == "screen-test":
            return _screen_test()
        if command == "--version":
            print(".".join(map(str, VERSION)))
            return 0
        if command in {"help", "--help", "-h"}:
            _print_usage()
            return 0
        print(f"Unknown command: {command}", file=sys.stderr)
        _print_usage()
        return 2

    if len(argv) == 3:
        action = argv[2].lower()
        if command == "reset" and action == "password":
            return _save_config_change("web_password_hash", "")
        if command == "reset" and action == "settings":
            return _reset_settings()
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

    if command == "config" and len(argv) >= 3 and argv[2].lower() == "set":
        return _config_set(argv[3:])

    if command == "test" and len(argv) >= 3:
        target = argv[2].lower()
        valid_targets = {"overhead_fr24", "overhead_tar1090", "overhead_osn", "tle"}
        if target not in valid_targets:
            print(f"Unknown test target: {target}", file=sys.stderr)
            print(f"Valid targets: {', '.join(sorted(valid_targets))}", file=sys.stderr)
            return 2
        test_argv = argv[3:]
        if target == "tle":
            return _run_tle_test(test_argv)
        return _run_overhead_test(target, test_argv)

    _print_usage()
    return 2

from __future__ import annotations

import argparse
import json
import sys
import time
from collections.abc import Sequence
from dataclasses import asdict

from setup.configuration import CONFIG_PATH, Config
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
    print("  data                   Print the platform data directory path")
    print("  reset-password         Clear web_password_hash in the config")
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

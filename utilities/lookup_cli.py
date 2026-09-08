"""CLI lookup commands - exercise the device's lookup machinery by hand.

``flight-tracker.py lookup ...`` runs the same provider pipelines the
display uses (same config, priority lists, caches, quarantine and usage
accounting) against explicit inputs, printing JSON on stdout.  Intended
for testing provider configuration without running the panel.

Design notes:

- Device-identical by default.  Every command walks the real services
  (``lookups.flights`` / ``enrichment`` / ``routes`` / ``aircraft``) with
  the real :class:`~setup.configuration.Config` - provider order, cache
  TTLs, quarantine and usage accounting behave exactly as the display.
- Overrides are in memory only.  Position, radius and provider forcing
  live for the lifetime of the command; nothing is ever written back to
  config.json.
- Verbosity lives here, at the CLI layer.  ``--verbose`` attaches a
  DEBUG handler to the lookup packages (stderr) and makes the command
  log its resolved chains and cache decisions; no library code logs
  differently.  stdout stays parseable JSON regardless.
- Provider forcing is exclusive: ``--provider-route fr24`` pins the
  route chain to exactly fr24 (see
  :func:`utilities.lookups.registry.set_forced_provider`).  Quarantine
  is cleared for a forced provider so a stale quarantine from an
  earlier failure cannot silently swallow the lookup.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys

from utilities.lookups.registry import PROVIDERS, forced_provider

logger = logging.getLogger("utilities.lookup_cli")

# Exit codes.
EXIT_OK = 0  # lookup answered
EXIT_NOT_FOUND = 1  # nothing found / every provider unavailable
EXIT_USAGE = 2  # bad arguments (argparse also uses this)

_CAPABILITY_FLAGS = (
    ("flights", "provider_flights"),
    ("routes", "provider_route"),
    ("aircraft", "provider_aircraft"),
)

# Package loggers --verbose switches on.  Kept narrow so unrelated
# utilities stay quiet even under --verbose.
_VERBOSE_LOGGERS = (
    "utilities.lookups",
    "utilities.overhead",
    "utilities.overhead_utilities",
)

_verbose = False


class _UsageError(Exception):
    """A provider-forcing flag named an unknown/incapable provider."""


# ---------------------------------------------------------------------------
# Shared plumbing
# ---------------------------------------------------------------------------


def _configure_verbose(enabled: bool) -> None:
    """Attach a stderr DEBUG handler to the lookup packages."""
    global _verbose
    _verbose = enabled
    if not enabled:
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s", "%H:%M:%S")
    )
    for name in _VERBOSE_LOGGERS:
        pkg = logging.getLogger(name)
        pkg.setLevel(logging.DEBUG)
        pkg.addHandler(handler)
        pkg.propagate = False
    logger.setLevel(logging.DEBUG)


def _log_chain(capability: str, chain: list) -> None:
    """Log the effective chain for *capability* (post-forcing)."""
    if not _verbose:
        return
    pids = " -> ".join(pid for pid, _ in chain)
    logger.debug("%s chain: %s", capability, pids or "(empty)")


def _apply_forcing(args: argparse.Namespace) -> None:
    """Pin provider chains from --provider-* flags; validate ids."""
    from utilities.lookups.quarantine import QUARANTINE
    from utilities.lookups.registry import (
        load_config,
        set_forced_provider,
        specs_for_capability,
    )

    for capability, attr in (
        ("flights", "provider_flights"),
        ("routes", "provider_route"),
        ("aircraft", "provider_aircraft"),
    ):
        pid = getattr(args, attr, None)
        if not pid:
            continue
        try:
            set_forced_provider(capability, pid)
        except ValueError as e:
            raise _UsageError(str(e)) from e
        # A stale quarantine must not swallow the forced lookup.  The
        # service loops consult QUARANTINE before calling the adapter.
        QUARANTINE.record_success(pid)
        # Surfaced, not fatal: an unconfigured forced provider answers
        # UNAVAILABLE with its own reason, which is exactly what the
        # operator asked to see.
        spec = PROVIDERS[pid]
        if not spec.config.is_configured(load_config().provider_settings(pid)):
            logger.warning(
                "%s: forced provider %r is not fully configured; "
                "expect UNAVAILABLE answers",
                capability,
                pid,
            )
        if not _verbose:
            continue
        valid = ", ".join(s.id for s in specs_for_capability(capability))
        logger.debug(
            "%s chain forced to %r (others ignored; valid: %s)",
            capability,
            pid,
            valid,
        )


def _drop_fresh(args: argparse.Namespace, keys: list[tuple[str, str]]) -> None:
    """Delete *keys* ([(key, kind), ...]) from the persistent cache.

    ``--fresh`` forces a real provider walk: the entry is removed, the
    cache read misses, and the pipeline re-caches whatever this lookup
    finds - exactly like the device relearning the flight.
    """
    if not getattr(args, "fresh", False) or not keys:
        return
    from utilities.lookups import cache

    by_kind: dict[str, list[str]] = {}
    for key, kind in keys:
        by_kind.setdefault(kind, []).append(key)
    for kind, kind_keys in by_kind.items():
        removed = cache.delete(kind_keys, kind)
        logger.debug(
            "cache: dropped %d %s entr%s",
            removed,
            kind,
            "y" if removed == 1 else "ies",
        )


def _config():
    """Fresh Config instance - same file the device reads."""
    from setup.configuration import Config

    return Config.reload()


def _apply_extended_table(cfg, args: argparse.Namespace) -> None:
    """--extended: use airports-full.json for this lookup (in memory only).

    Flips the ``airport_lookup_full`` setting for the lifetime of the
    command without saving it, and resets the airport-name cache so the
    extended table is the one actually loaded.
    """
    if not getattr(args, "extended", False):
        return
    from utilities import overhead_utilities as oh

    cfg.set("airport_lookup_full", True)
    oh.reset_airports_cache()
    logger.debug("airport table: forced to airports-full.json for this lookup")


def _print(payload: dict) -> None:
    print(json.dumps(payload, indent=2, default=str))


# ---------------------------------------------------------------------------
# lookup location - the device's full overhead path
# ---------------------------------------------------------------------------


def _run_location(args: argparse.Namespace) -> int:
    from setup.configuration import Config
    from utilities.lookups import enrichment, flights
    from utilities.lookups.results import FlightQuery

    cfg = Config.reload()
    cfg.set("flight_lat", args.lat)
    cfg.set("flight_lng", args.lng)
    cfg.set("flight_radius", args.radius)
    if args.max_flights is not None:
        cfg.set("max_flight_lookup", args.max_flights)
    if args.alt_min is not None:
        cfg.set("flight_min_altitude", args.alt_min)
    if args.alt_max is not None:
        cfg.set("flight_max_altitude", args.alt_max)
    if args.callsign_format is not None:
        cfg.set("callsign_format", args.callsign_format)
    _apply_forcing(args)
    _apply_extended_table(cfg, args)

    # Mirror Overhead.grab_data_impl: same query build, same fetch, same
    # per-aircraft conversion.  The loop is spelled out here (rather than
    # calling Overhead.refresh()) so --fresh can drop each aircraft's
    # cache entries between the fetch and its enrichment.
    from utilities.lookups.registry import FLIGHTS, resolve_chain

    _log_chain("flights", resolve_chain(cfg, FLIGHTS))
    query = FlightQuery(
        zone=cfg.zone_home,
        home=cfg.location_home,
        min_altitude_m=cfg.flight_min_altitude,
        max_altitude_m=cfg.flight_max_altitude,
        max_results=cfg.max_flight_lookup,
    )
    outcome = flights.fetch_flights(query)
    header = {
        "query": {"lat": args.lat, "lng": args.lng, "radius_km": args.radius},
        "provider": {
            "id": outcome.provider_id,
            "name": outcome.source_name,
            "errors": list(outcome.errors),
        },
    }
    if not outcome.ok:
        header["error"] = "every enabled flight provider is unavailable"
        _print(header)
        return EXIT_NOT_FOUND

    if args.fresh:
        _drop_fresh(
            args,
            [(obs.callsign.strip().upper(), "route") for obs in outcome.observations]
            + [(obs.icao, "aircraft") for obs in outcome.observations if obs.icao],
        )

    # Overhead._to_flight is the device's exact observation -> Flight
    # conversion (enrichment + callsign-format handling); borrowed here so
    # the CLI can never drift from what the panel displays.
    from utilities.overhead import Overhead

    glue = Overhead()
    out_flights: list[dict] = []
    for observation in outcome.observations:
        try:
            flight = glue._to_flight(observation, enrichment)
        except (KeyError, AttributeError, TypeError):
            continue
        out_flights.append(dataclasses.asdict(flight))

    _print({**header, "count": len(out_flights), "flights": out_flights})
    return EXIT_OK


# ---------------------------------------------------------------------------
# lookup route - one callsign through the full enrichment pipeline
# ---------------------------------------------------------------------------


def _run_route(args: argparse.Namespace) -> int:
    from setup.configuration import Config
    from utilities.lookups import enrichment
    from utilities.lookups.results import FlightObservation

    cfg = Config.reload()
    _apply_forcing(args)
    _apply_extended_table(cfg, args)

    callsign = args.callsign.strip().upper()
    mode_s = (args.hex or "").strip().lower()
    if args.fresh:
        fresh = [(callsign, "route")]
        if mode_s:
            fresh.append((mode_s, "aircraft"))
        _drop_fresh(args, fresh)

    if _verbose:
        from utilities.lookups.registry import ROUTES, load_config, resolve_chain

        _log_chain("routes", resolve_chain(load_config(), ROUTES))
        logger.debug(
            "route: cache %s for %r",
            "bypassed by --fresh" if args.fresh else "consulted",
            callsign,
        )

    observation = FlightObservation(
        icao=mode_s,
        callsign=callsign,
        latitude=args.lat,
        longitude=args.lng,
    )
    result = enrichment.enrich(observation)

    from assets.airlines.convert import icao_flight_to_iata

    payload = {
        "callsign": callsign,
        "iata_flight": icao_flight_to_iata(callsign) or "",
        "fresh": bool(args.fresh),
        "route": dataclasses.asdict(result),
    }
    _print(payload)
    found = any(
        (
            result.origin,
            result.destination,
            result.airline_icao,
            result.plane,
            result.registration,
            result.operator_icao,
            result.owner,
        )
    )
    return EXIT_OK if found else EXIT_NOT_FOUND


# ---------------------------------------------------------------------------
# lookup aircraft <mode-s hex>
# ---------------------------------------------------------------------------


def _run_aircraft(args: argparse.Namespace) -> int:
    from setup.configuration import Config
    from utilities.lookups import aircraft as aircraft_service
    from utilities.lookups.results import LookupContext

    Config.reload()
    _apply_forcing(args)

    mode_s = args.hex.strip().lower()
    if args.fresh:
        _drop_fresh(args, [(mode_s, "aircraft")])

    ctx = LookupContext(
        callsign="",
        mode_s=mode_s,
        lat=None,
        lng=None,
        ground_speed_mps=0.0,
        want_plane=True,
    )
    info = aircraft_service.lookup_aircraft(ctx)
    _print({"hex": mode_s, "fresh": bool(args.fresh), "aircraft": dataclasses.asdict(info)})
    return EXIT_OK if info else EXIT_NOT_FOUND


# ---------------------------------------------------------------------------
# lookup callsign <callsign>  (local tables only - no network)
# ---------------------------------------------------------------------------


def _run_callsign(args: argparse.Namespace) -> int:
    import re

    from assets.airlines import airline_codes
    from assets.airlines.convert import icao_flight_to_iata

    callsign = args.callsign.strip().upper()
    match = re.match(r"^([A-Z]{1,3})(\d.*)$", callsign)
    designator = match.group(1) if match else ""
    iata_airline = airline_codes.icao_to_iata.get(designator, "")
    name = airline_codes.icao_to_name.get(designator, "")

    payload = {
        "callsign": callsign,
        "iata_flight": icao_flight_to_iata(callsign) or "",
        "airline": {
            "icao": designator,
            "iata": iata_airline,
            "name": name,
        },
        "iata_airline_known": bool(iata_airline),
        "airline_name_known": bool(name),
    }
    _print(payload)
    return EXIT_OK if (payload["iata_flight"] or iata_airline or name) else EXIT_NOT_FOUND


# ---------------------------------------------------------------------------
# lookup airport <code>...  (bundled tables only - no network)
# ---------------------------------------------------------------------------


def _run_airport(args: argparse.Namespace) -> int:
    import os

    from setup.configuration import Config
    from utilities.overhead_utilities import airport_info

    cfg = Config.reload()
    _apply_extended_table(cfg, args)
    table = "airports-full.json" if cfg.airport_lookup_full else "airports.json"
    results = []
    for raw in args.codes:
        code = raw.strip().upper()
        info = airport_info(code)
        if info:
            results.append({"code": code, "found": True, **info})
        else:
            results.append({"code": code, "found": False})

    payload = {"table": os.path.basename(table), "airports": results}
    missed = [r["code"] for r in results if not r["found"]]
    if missed and not cfg.airport_lookup_full:
        payload["hint"] = (
            "airport_lookup_full is off - the extended table (FAA local "
            "+ ICAO/gps codes) was not consulted"
        )
    _print(payload)
    return EXIT_OK if any(r["found"] for r in results) else EXIT_NOT_FOUND


# ---------------------------------------------------------------------------
# lookup providers  (read-only diagnostic)
# ---------------------------------------------------------------------------

_CAPABILITY_LIST_ATTR = {
    "flights": "flight_providers",
    "routes": "route_providers",
    "aircraft": "route_providers",
}


def _run_providers(args: argparse.Namespace) -> int:
    from setup.configuration import Config
    from utilities.lookups.quarantine import QUARANTINE
    from utilities.lookups.registry import (
        FLIGHTS,
        ROUTES,
        resolve_chain,
        specs_for_capability,
    )

    cfg = Config.reload()
    chains = {}
    for capability in (FLIGHTS, ROUTES, "aircraft"):
        chain = resolve_chain(cfg, capability)
        chains[capability] = [pid for pid, _ in chain]

    providers: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for capability, attr in _CAPABILITY_LIST_ATTR.items():
        for entry in getattr(cfg, attr):
            pid = entry.get("provider", "")
            key = (pid, capability)
            if key in seen:
                continue
            seen.add(key)
            spec = PROVIDERS.get(pid)
            settings = cfg.provider_settings(pid) if spec else {}
            providers.append(
                {
                    "provider": pid,
                    "capability": capability,
                    "enabled": bool(entry.get("enabled")),
                    "implements": bool(spec and spec.implements(capability)),
                    "configured": bool(
                        spec and spec.config.is_configured(settings)
                    ),
                    "quarantined": QUARANTINE.is_quarantined(pid),
                    "in_chain": pid in chains.get(capability, []),
                    "forced": forced_provider(capability) == pid,
                }
            )
    # Providers that implement a capability but are absent from the saved
    # lists (newly shipped, never reordered) still deserve a row.
    for capability in (FLIGHTS, ROUTES, "aircraft"):
        for spec in specs_for_capability(capability):
            if (spec.id, capability) in seen:
                continue
            settings = cfg.provider_settings(spec.id)
            providers.append(
                {
                    "provider": spec.id,
                    "capability": capability,
                    "enabled": False,
                    "implements": True,
                    "configured": spec.config.is_configured(settings),
                    "quarantined": QUARANTINE.is_quarantined(spec.id),
                    "in_chain": False,
                    "forced": forced_provider(capability) == spec.id,
                }
            )

    payload = {"chains": chains, "providers": providers}
    if args.usage:
        from utilities.lookups import usage

        payload["usage"] = usage.summary()
    _print(payload)
    return EXIT_OK


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _add_provider_flags(sp: argparse.ArgumentParser, *capabilities: str) -> None:
    flag_map = {
        "flights": "--provider-flights",
        "routes": "--provider-route",
        "aircraft": "--provider-aircraft",
    }
    for capability in capabilities:
        sp.add_argument(
            flag_map[capability],
            metavar="ID",
            help=f"force the {capability} chain to one provider "
            f"(default: config priority order)",
        )


def _add_loop_flags(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--interval", type=float, default=None, help="seconds between repeated runs"
    )
    sp.add_argument("--limit", type=int, default=None, help="stop after N runs")


def _add_extended_flag(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--extended",
        action="store_true",
        help="use the extended airport table (FAA local + ICAO/gps codes) "
        "for this lookup, without saving the airport_lookup_full setting",
    )


def _add_common_flags(sp: argparse.ArgumentParser) -> None:
    sp.add_argument(
        "--fresh",
        action="store_true",
        help="drop this key's cache entries first; the pipeline re-walks "
        "the providers and re-caches what it finds",
    )
    sp.add_argument(
        "--verbose",
        action="store_true",
        help="DEBUG logging to stderr (chains, cache decisions, providers)",
    )


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python flight-tracker.py lookup",
        description="Exercise the lookup providers exactly as the device "
        "does, printing JSON on stdout.",
    )
    sub = p.add_subparsers(dest="command", required=True, metavar="<target>")

    sp = sub.add_parser(
        "location",
        help="full overhead lookup: fetch the zone and enrich every aircraft",
    )
    sp.add_argument("lat", type=float, help="centre latitude")
    sp.add_argument("lng", type=float, help="centre longitude")
    sp.add_argument("radius", type=float, help="search radius in km")
    sp.add_argument("--max-flights", type=int, help="max flights (default: config)")
    sp.add_argument("--alt-min", type=float, help="min altitude m (default: config)")
    sp.add_argument("--alt-max", type=float, help="max altitude m (default: config)")
    sp.add_argument(
        "--callsign-format", choices=["icao", "iata"], help="default: config"
    )
    _add_provider_flags(sp, "flights", "routes", "aircraft")
    _add_extended_flag(sp)
    _add_common_flags(sp)
    _add_loop_flags(sp)
    sp.set_defaults(handler=_run_location)

    sp = sub.add_parser(
        "route", help="route + airline enrichment for one callsign"
    )
    sp.add_argument("callsign", help="ICAO callsign, e.g. RYR215K")
    sp.add_argument(
        "--hex",
        help="mode-s hex - lets the aircraft pipeline participate, exactly "
        "as a live observation would",
    )
    sp.add_argument(
        "--lat", type=float, help="live-position hint for position-gated providers"
    )
    sp.add_argument("--lng", type=float, help="live-position hint")
    _add_provider_flags(sp, "routes", "aircraft")
    _add_extended_flag(sp)
    _add_common_flags(sp)
    _add_loop_flags(sp)
    sp.set_defaults(handler=_run_route)

    sp = sub.add_parser("aircraft", help="airframe metadata for a mode-s hex")
    sp.add_argument("hex", help="mode-s hex, e.g. 406f3a")
    _add_provider_flags(sp, "aircraft")
    _add_common_flags(sp)
    _add_loop_flags(sp)
    sp.set_defaults(handler=_run_aircraft)

    sp = sub.add_parser(
        "callsign",
        help="local callsign conversion: IATA flight number + airline",
    )
    sp.add_argument("callsign", help="ICAO callsign, e.g. BAW117")
    _add_common_flags(sp)
    sp.set_defaults(handler=_run_callsign)

    sp = sub.add_parser(
        "airport", help="airport names from the bundled tables (no network)"
    )
    sp.add_argument("codes", nargs="+", metavar="CODE", help="IATA/local/ICAO code")
    _add_extended_flag(sp)
    _add_common_flags(sp)
    sp.set_defaults(handler=_run_airport)

    sp = sub.add_parser(
        "providers", help="show resolved provider chains and their state"
    )
    sp.add_argument(
        "--usage", action="store_true", help="include provider usage tallies"
    )
    _add_common_flags(sp)
    sp.set_defaults(handler=_run_providers)

    return p


def print_help() -> None:
    """Print the lookup sub-command help (bare 'lookup')."""
    _build_parser().print_help()


def run(argv: list[str]) -> int:
    """Entry point from utilities.cli.dispatch_cli_command (argv after 'lookup')."""
    args = _build_parser().parse_args(argv)
    _configure_verbose(args.verbose)
    try:
        return args.handler(args)
    except _UsageError as e:
        print(f"lookup: {e}", file=sys.stderr)
        return EXIT_USAGE
    finally:
        from utilities.lookups.registry import clear_forced_providers

        clear_forced_providers()

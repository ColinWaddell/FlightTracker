"""
Route lookup service.

Resolves origin/destination (and flight-level airline identity) for a
callsign by walking the user's configured route-provider priority list,
backed by the persistent callsign cache:

1.  Persistent cache (``routes_cache.json``): miss entries (1 h) skip the
    provider chain entirely; positive entries seed the pipeline result.
2.  Provider pipeline: each *enabled, configured, non-quarantined* provider
    fills what it can.  Higher-priority results are never overwritten -
    lower-priority providers only fill blanks (``RouteInfo.merge_missing``)
    - and the pipeline stops as soon as the result is complete.  An
    ``UNAVAILABLE`` result quarantines the provider temporarily and is
    never cached as a miss.
3.  Stale fallback: a recently-expired positive entry (within 7 days) is
    re-cached with its timestamp advanced 4 h and returned, so the display
    keeps showing real route data while providers are failing.
4.  Miss caching: when every provider answers ``NOT_FOUND``, the callsign
    is miss-cached for 1 h so repeated polls skip the HTTP calls.
"""

from __future__ import annotations

import logging
import time

from lookups import cache
from lookups.quarantine import QUARANTINE
from lookups.registry import provider_spec
from lookups.results import LookupContext, RouteInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adapter construction (memoised - sessions survive across polls)
# ---------------------------------------------------------------------------

_adapter_cache: dict[tuple, object] = {}


def get_route_adapter(pid: str, settings: dict):
    """Return a (cached) route-capable adapter for *pid*."""
    key = ("routes", pid, tuple(sorted((k, str(v)) for k, v in settings.items())))
    adapter = _adapter_cache.get(key)
    if adapter is None:
        spec = provider_spec(pid)
        if spec is None or spec.route_factory is None:
            return None
        adapter = spec.route_factory(settings)
        _adapter_cache[key] = adapter
    return adapter


def reset_adapters() -> None:
    """Drop memoised adapters (tests / config reload)."""
    _adapter_cache.clear()


# ---------------------------------------------------------------------------
# Provider resolution (Config read lazily to avoid import cycles)
# ---------------------------------------------------------------------------


def _config():
    from setup.configuration import Config

    return Config.instance()


def resolve_route_providers(cfg) -> list[tuple[str, object]]:
    """``[(provider_id, adapter)]`` for enabled, configured route providers."""
    providers = []
    for entry in cfg.route_providers:
        pid = entry["provider"]
        if not entry.get("enabled"):
            continue
        spec = provider_spec(pid)
        if spec is None or "routes" not in spec.capabilities:
            continue
        settings = cfg.provider_settings(pid)
        if not spec.config.is_configured(settings):
            continue
        adapter = get_route_adapter(pid, settings)
        if adapter is not None:
            providers.append((pid, adapter))
    return providers


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def run_route_pipeline(
    ctx: LookupContext, providers: list[tuple[str, object]]
) -> tuple[RouteInfo, bool, str]:
    """Walk *providers* in priority order, merging answers into one result.

    Returns ``(result, all_answered, first_hit_pid)``.  ``all_answered`` is
    False when any provider was quarantined-skipped or answered
    UNAVAILABLE, or when a provider crashed - in those cases the pipeline's
    silence is not ground truth and must not be cached as a miss.
    """
    result = RouteInfo()
    all_answered = True
    first_hit = ""

    for pid, adapter in providers:
        if QUARANTINE.is_quarantined(pid):
            all_answered = False
            continue

        try:
            lookup = adapter.lookup_route(ctx)
        except Exception as e:  # defensive: adapters shouldn't raise
            logger.warning("Route provider %s crashed: %s", pid, e)
            QUARANTINE.record_failure(pid)
            all_answered = False
            continue

        if lookup.is_found:
            QUARANTINE.record_success(pid)
            result.merge_missing(lookup.value)
            if not first_hit and (result.origin or result.destination):
                first_hit = pid
            if result.is_complete():
                break
        elif lookup.is_unavailable:
            QUARANTINE.record_failure(pid)
            all_answered = False
        else:
            QUARANTINE.record_success(pid)
            # NOT_FOUND: keep walking - a lower-priority provider may know.

    return result, all_answered, first_hit


def enrich_route_names(route: RouteInfo) -> bool:
    """Fill blank name/municipality/country fields from the bundled airports.json.

    Modifies *route* in-place; returns True when anything changed (callers
    use that to decide whether to re-write the cache).
    """
    from utilities.overhead_utilities import airport_info as bundled

    changed = False
    for side in ("origin", "destination"):
        if not getattr(route, side) or getattr(route, f"{side}_name"):
            continue
        details = bundled(getattr(route, side)) or {}
        name = details.get("name", "")
        municipality = details.get("municipality", "")
        country = details.get("country_name", "")
        if name or municipality or country:
            setattr(route, f"{side}_name", name)
            setattr(route, f"{side}_municipality", municipality)
            setattr(route, f"{side}_country", country)
            changed = True
    return changed


def _run_pipeline_with_cache(
    ctx: LookupContext, callsign: str, providers: list[tuple[str, object]]
) -> RouteInfo:
    """Pipeline plus the full cache bookkeeping (positive/stale/miss)."""
    result, all_answered, _hit = run_route_pipeline(ctx, providers)

    if result.origin or result.destination:
        # Positive result - enrich names and cache under the callsign.
        # operator_icao/owner are stripped: they describe the airframe
        # (mode_s key), not the flight; caching them per-callsign would let
        # one day's airframe decide tomorrow's logo.
        enrich_route_names(result)
        entry = result.to_dict()
        entry.pop("operator_icao", None)
        entry.pop("owner", None)
        cache.put(callsign, entry)
        return result

    # Providers found nothing.  Stale fallback: a recently-expired positive
    # entry (within 7 days) is returned and re-cached so the screen shows
    # real data while providers keep failing.
    stale = cache.get_stale(callsign)
    if stale is not None and (stale.get("origin") or stale.get("destination")):
        stale_route = RouteInfo.from_dict(stale)
        enrich_route_names(stale_route)
        cache.put(
            callsign,
            stale_route.to_dict(),
            ts=stale["_ts"] + cache.STALE_RECACHE_ADVANCE,
        )
        logger.debug(
            "Route providers found nothing for %r - reusing stale cached "
            "route (age %.1fh)",
            callsign,
            (time.time() - stale["_ts"]) / 3600,
        )
        return stale_route

    # Cache the miss only when the pipeline answered truthfully.
    if all_answered and providers:
        cache.put(callsign, {"miss": True}, ttl=cache.CACHE_TTL_MISS)
    return result


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def lookup_route(
    ctx: LookupContext,
    prefill: RouteInfo | None = None,
    cfg=None,
) -> RouteInfo:
    """Resolve route details for *ctx* via cache + provider pipeline.

    *prefill* carries fields the live feed supplied directly (highest
    priority - providers only fill its blanks).  *cfg* allows an explicit
    configuration injection (tests); when omitted Config is read lazily.

    Never raises.  Returns a :class:`RouteInfo` (blank when unknown).
    """
    callsign = (ctx.callsign or "").strip()
    result = RouteInfo()
    if prefill is not None:
        result.merge_missing(prefill)

    if not callsign:
        return result

    # 1. Persistent cache.
    cached = cache.get(callsign)
    if cached is not None and cached.get("miss"):
        # Whole pipeline (all providers, FR24 included) answered "unknown"
        # recently - skip everything for this poll.
        return result

    if cached is not None and (cached.get("origin") or cached.get("destination")):
        cached_route = RouteInfo.from_dict(cached)
        if enrich_route_names(cached_route):
            entry = cached_route.to_dict()
            entry.pop("operator_icao", None)
            entry.pop("owner", None)
            cache.put(callsign, entry)
        result.merge_missing(cached_route)
        if result.is_complete():
            return result

    # 2. Provider pipeline - run when there is no cached route, or when the
    #    cached route is incomplete (providers may fill airline_icao etc.).
    providers = resolve_route_providers(cfg or _config())

    if cached is None or not (
        cached.get("origin") or cached.get("destination")
    ):
        pipeline_result = _run_pipeline_with_cache(ctx, callsign, providers)
    else:
        # Cached (incomplete) route: run the pipeline for gap-filling but
        # only re-cache when the merge actually improved the entry.
        before = result.to_dict()
        pipeline_result, _answered, _hit = run_route_pipeline(ctx, providers)
        result.merge_missing(pipeline_result)
        if result.to_dict() != before:
            entry = result.to_dict()
            entry.pop("operator_icao", None)
            entry.pop("owner", None)
            cache.put(callsign, entry)
        pipeline_result = None

    if pipeline_result is not None:
        result.merge_missing(pipeline_result)

    return result


# ---------------------------------------------------------------------------
# Startup support
# ---------------------------------------------------------------------------


def check_routing() -> bool:
    """True when at least one enabled route provider is reachable.

    Probes each enabled, configured, non-quarantined provider's ping()
    until one responds.  Providers without a ping probe (feed-based
    adapters) count as reachable by construction.
    """
    try:
        providers = resolve_route_providers(_config())
    except Exception:
        return False
    for pid, adapter in providers:
        if QUARANTINE.is_quarantined(pid):
            continue
        ping = getattr(adapter, "ping", None)
        if ping is None:
            return True
        try:
            if ping():
                return True
        except Exception:
            continue
    return False

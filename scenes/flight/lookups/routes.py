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
    - and the pipeline stops as soon as the *flight-level* result is
    complete (origin, destination, airline).  Airframe identity (type,
    registration, operator) is deliberately not chased here: the mode-s
    aircraft pipeline owns it and caches it per airframe, so route
    providers are never re-queried just to fill airframe fields.  An
    ``UNAVAILABLE`` result quarantines the provider temporarily and is
    never cached as a miss.
3.  Gap-fill back-off: a cached route that is still incomplete (e.g. a GA
    flight with no airline anywhere) re-asks the chain at most once an
    hour instead of on every poll, so a paid provider low in the priority
    list is called once per flight, not once per poll.
4.  Stale fallback: a recently-expired positive entry (within 7 days) is
    re-cached with its timestamp advanced 4 h and returned, so the display
    keeps showing real route data while providers are failing.
5.  Miss caching: when every provider answers ``NOT_FOUND``, the callsign
    is miss-cached for 1 h so repeated polls skip the HTTP calls.
"""

from __future__ import annotations

import logging
import threading
import time

from scenes.flight.lookups import cache, usage
from scenes.flight.lookups.providers.common.airports import fill_airport_details
from scenes.flight.lookups.quarantine import QUARANTINE
from scenes.flight.lookups.registry import ROUTES, load_config, resolve_chain
from scenes.flight.lookups.results import LookupContext, RouteInfo

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider chain
# ---------------------------------------------------------------------------


def resolve_route_providers(cfg) -> list[tuple[str, object]]:
    """``[(provider_id, adapter)]`` for enabled, configured route providers."""
    return resolve_chain(cfg, ROUTES)


def reset_adapters() -> None:
    """Drop memoised adapters (tests / config reload)."""
    from scenes.flight.lookups.registry import reset_adapters as _reset

    _reset()


# ---------------------------------------------------------------------------
# Gap-fill back-off
# ---------------------------------------------------------------------------

# How long to wait before re-walking the provider chain for a cached route
# that is still incomplete.  Without this, a callsign whose route can never
# complete (a GA flight with no airline, say) re-queried every enabled
# provider - including paid ones - on every poll (10-30 s) for as long as
# the entry is cached.
GAPFILL_RETRY_SECONDS = 3600

# callsign -> monotonic time of the last chain run for it.
_gapfill_last_attempt: dict[str, float] = {}
_gapfill_lock = threading.Lock()

# Cap the throttle table; callsigns not seen since the retry window are
# pruned once the table outgrows this many entries.
_GAPFILL_MAX_KEYS = 4096


def _gapfill_record(callsign: str, now: float | None = None) -> None:
    """Record that the provider chain just ran for *callsign*."""
    now = time.monotonic() if now is None else now
    with _gapfill_lock:
        _gapfill_last_attempt[callsign] = now
        if len(_gapfill_last_attempt) > _GAPFILL_MAX_KEYS:
            cutoff = now - GAPFILL_RETRY_SECONDS
            for key in [
                k
                for k, ts in _gapfill_last_attempt.items()
                if ts < cutoff and k != callsign
            ]:
                del _gapfill_last_attempt[key]


def _gapfill_gate(callsign: str) -> bool:
    """True when a gap-fill attempt may run for *callsign* now.

    Checks the back-off window and records the attempt atomically, so a
    passing decision and its timestamp cannot race.
    """
    now = time.monotonic()
    with _gapfill_lock:
        last = _gapfill_last_attempt.get(callsign)
        if last is not None and now - last < GAPFILL_RETRY_SECONDS:
            return False
        _gapfill_last_attempt[callsign] = now
        if len(_gapfill_last_attempt) > _GAPFILL_MAX_KEYS:
            cutoff = now - GAPFILL_RETRY_SECONDS
            for key in [
                k
                for k, ts in _gapfill_last_attempt.items()
                if ts < cutoff and k != callsign
            ]:
                del _gapfill_last_attempt[key]
        return True


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

        usage.record("routes", pid, "attempt")
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
            usage.record("routes", pid, "no_result")

    return result, all_answered, first_hit


def enrich_route_names(route: RouteInfo) -> bool:
    """Fill blank name/municipality/country fields from the bundled airports.json.

    Modifies *route* in-place; returns True when anything changed (callers
    use that to decide whether to re-write the cache).
    """
    changed = False
    for side in ("origin", "destination"):
        if fill_airport_details(route, side):
            changed = True
    return changed


def _cacheable(route: RouteInfo) -> dict:
    """Serialise *route* for the callsign cache key.

    ``operator_icao`` and ``owner`` are stripped: they describe the
    airframe (mode-s key), not the flight; caching them per-callsign would
    let one day's airframe decide tomorrow's logo.
    """
    entry = route.to_dict()
    entry.pop("operator_icao", None)
    entry.pop("owner", None)
    return entry


def _run_pipeline_with_cache(
    ctx: LookupContext, callsign: str, providers: list[tuple[str, object]]
) -> RouteInfo:
    """Pipeline plus the full cache bookkeeping (positive/stale/miss)."""
    result, all_answered, _hit = run_route_pipeline(ctx, providers)
    # The chain just ran for this callsign - arm the gap-fill back-off so
    # the first re-walk waits out the window instead of firing next poll.
    _gapfill_record(callsign)

    if result.origin or result.destination:
        # Positive result - enrich names and cache under the callsign.
        enrich_route_names(result)
        cache.put(callsign, _cacheable(result), kind=cache.KIND_ROUTE)
        return result

    # Providers found nothing.  Stale fallback: a recently-expired positive
    # entry (within 7 days) is returned and re-cached so the screen shows
    # real data while providers keep failing.
    stale = cache.get_stale(callsign, cache.KIND_ROUTE)
    if stale is not None and (stale.get("origin") or stale.get("destination")):
        stale_route = RouteInfo.from_dict(stale)
        enrich_route_names(stale_route)
        cache.put(
            callsign,
            _cacheable(stale_route),
            ts=stale["_ts"] + cache.STALE_RECACHE_ADVANCE,
            kind=cache.KIND_ROUTE,
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
        cache.put(
            callsign, {"miss": True}, ttl=cache.CACHE_TTL_MISS, kind=cache.KIND_ROUTE
        )
    return result


def _fill_cached_gaps(
    ctx: LookupContext, callsign: str, result: RouteInfo
) -> RouteInfo:
    """Run the provider pipeline against a cached-but-incomplete route.

    Back-off: the chain is re-walked at most once per
    ``GAPFILL_RETRY_SECONDS`` per callsign, so a route whose remaining gap
    can never be filled (no airline for a GA flight) costs one attempt an
    hour rather than one per poll.  The result is only re-cached when the
    merge actually improved the entry, so a poll that fills nothing costs
    no cache write.
    """
    if not _gapfill_gate(callsign):
        return result

    before = result.to_dict()
    pipeline_result, _answered, _hit = run_route_pipeline(
        ctx, resolve_chain(load_config(), ROUTES)
    )
    result.merge_missing(pipeline_result)
    if result.to_dict() != before:
        cache.put(callsign, _cacheable(result), kind=cache.KIND_ROUTE)
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
    cached = cache.get(callsign, cache.KIND_ROUTE)
    usage.record_cache("routes", "hit" if cached is not None else "miss")
    if cached is not None and cached.get("miss"):
        # Whole pipeline (all providers, FR24 included) answered "unknown"
        # recently - skip everything for this poll.
        return result

    if cached is None:
        # 2a. No cached entry - run the pipeline with full cache
        #     bookkeeping (positive write / stale fallback / miss write).
        result.merge_missing(
            _run_pipeline_with_cache(
                ctx, callsign, resolve_route_providers(cfg or load_config())
            )
        )
        return result

    # 2b. Cached entry - seed from the cache, then fill any remaining gaps
    #     from live providers (e.g. a cached route missing its airline).
    cached_route = RouteInfo.from_dict(cached)
    if enrich_route_names(cached_route):
        cache.put(callsign, _cacheable(cached_route), kind=cache.KIND_ROUTE)
    result.merge_missing(cached_route)

    if not result.is_complete():
        result = _fill_cached_gaps(ctx, callsign, result)

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
        providers = resolve_route_providers(load_config())
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

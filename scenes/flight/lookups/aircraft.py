"""
Aircraft lookup service.

Resolves airframe metadata (type, registration, registered operator, owner)
for a Mode-S hex by walking the user's configured aircraft-capable provider
priority list, backed by the same persistent cache (mode-s keys, 24 h TTL -
blank entries are also cached 24 h so repeated 404s aren't re-fetched).

Higher-priority answers are never overwritten; lower-priority providers
only fill blanks, and the pipeline stops as soon as the result is complete
(plane, registration and operator code all known).  A stale fallback and
the same all-answered miss rule as the route service apply.
"""

from __future__ import annotations

import logging
import time

from scenes.flight.lookups import cache, usage
from scenes.flight.lookups.quarantine import QUARANTINE
from scenes.flight.lookups.registry import AIRCRAFT, load_config, resolve_chain
from scenes.flight.lookups.results import AircraftInfo, LookupContext

logger = logging.getLogger(__name__)


def resolve_aircraft_providers(cfg) -> list[tuple[str, object]]:
    """``[(provider_id, adapter)]`` for enabled, configured aircraft providers."""
    return resolve_chain(cfg, AIRCRAFT)


def reset_adapters() -> None:
    """Drop memoised adapters (tests / config reload)."""
    from scenes.flight.lookups.registry import reset_adapters as _reset

    _reset()


def run_aircraft_pipeline(
    ctx: LookupContext, providers: list[tuple[str, object]]
) -> tuple[AircraftInfo, bool, str]:
    """Walk *providers* in priority order, merging answers into one result.

    Returns ``(info, all_answered, first_hit_pid)``.  A provider "hits"
    when it resolves the aircraft type or registration (identity-only
    answers - an operator code or owner name - are retained and merged but
    do not stop the chain).
    """
    info = AircraftInfo()
    all_answered = True
    first_hit = ""

    for pid, adapter in providers:
        if QUARANTINE.is_quarantined(pid):
            all_answered = False
            continue

        usage.record("aircraft", pid, "attempt")
        try:
            lookup = adapter.lookup_aircraft(ctx)
        except Exception as e:  # defensive: adapters shouldn't raise
            logger.warning("Aircraft provider %s crashed: %s", pid, e)
            QUARANTINE.record_failure(pid)
            all_answered = False
            continue

        if lookup.is_found:
            QUARANTINE.record_success(pid)
            info.merge_missing(lookup.value)
            if not first_hit and (info.plane or info.registration):
                first_hit = pid
            if info.is_complete():
                break
        elif lookup.is_unavailable:
            QUARANTINE.record_failure(pid)
            all_answered = False
        else:
            QUARANTINE.record_success(pid)
            usage.record("aircraft", pid, "no_result")

    return info, all_answered, first_hit


def lookup_aircraft(ctx: LookupContext, cfg=None) -> AircraftInfo:
    """Resolve aircraft info for *ctx.mode_s* via cache + provider pipeline.

    Never raises.  Returns an :class:`AircraftInfo` (blank when unknown).
    """
    mode_s = (ctx.mode_s or "").strip().lower()
    if not mode_s:
        return AircraftInfo()

    # 1. Persistent cache - blank entries are cached too (24 h), so any hit
    #    short-circuits the providers.
    cached = cache.get(mode_s, cache.KIND_AIRCRAFT)
    usage.record_cache("aircraft", "hit" if cached is not None else "miss")
    if cached is not None:
        return AircraftInfo(
            plane=cached.get("plane", ""),
            registration=cached.get("registration", ""),
            operator_icao=cached.get("operator_icao", ""),
            owner=cached.get("owner", ""),
        )

    providers = resolve_aircraft_providers(cfg or load_config())
    info, all_answered, _hit = run_aircraft_pipeline(ctx, providers)

    if info.plane or info.registration:
        # Resolved something usable - cache the full airframe record.
        cache.put(mode_s, _aircraft_cache_entry(info), kind=cache.KIND_AIRCRAFT)
        return info

    # Providers resolved nothing usable.  Stale fallback: a recently-
    # expired entry (within 7 days) is returned and re-cached; its stale
    # type/registration are combined with any freshly-resolved identity.
    stale = cache.get_stale(mode_s, cache.KIND_AIRCRAFT)
    if stale is not None and (stale.get("plane") or stale.get("registration")):
        stale_info = AircraftInfo(
            plane=stale.get("plane", ""),
            registration=stale.get("registration", ""),
            operator_icao=info.operator_icao or stale.get("operator_icao", ""),
            owner=info.owner or stale.get("owner", ""),
        )
        cache.put(
            mode_s,
            _aircraft_cache_entry(stale_info),
            ts=stale["_ts"] + cache.STALE_RECACHE_ADVANCE,
            kind=cache.KIND_AIRCRAFT,
        )
        logger.debug(
            "Aircraft providers found nothing for mode_s %r - reusing "
            "stale cached info (age %.1fh)",
            mode_s,
            (time.time() - stale["_ts"]) / 3600,
        )
        return stale_info

    # All-answered blanks are cached (24 h) so 404s aren't repeated - but
    # only when the pipeline actually ran and answered truthfully.
    if all_answered and providers:
        cache.put(mode_s, _aircraft_cache_entry(info), kind=cache.KIND_AIRCRAFT)
    return info


def _aircraft_cache_entry(info: AircraftInfo) -> dict:
    """Serialise an :class:`AircraftInfo` for the mode-s cache key."""
    return {
        "plane": info.plane,
        "registration": info.registration,
        "operator_icao": info.operator_icao,
        "owner": info.owner,
    }

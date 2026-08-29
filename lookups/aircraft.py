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

from lookups import cache
from lookups.quarantine import QUARANTINE
from lookups.registry import provider_spec
from lookups.results import AircraftInfo, LookupContext

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Adapter construction (memoised)
# ---------------------------------------------------------------------------

_adapter_cache: dict[tuple, object] = {}


def get_aircraft_adapter(pid: str, settings: dict):
    """Return a (cached) aircraft-capable adapter for *pid*."""
    key = ("aircraft", pid, tuple(sorted((k, str(v)) for k, v in settings.items())))
    adapter = _adapter_cache.get(key)
    if adapter is None:
        spec = provider_spec(pid)
        if spec is None or spec.aircraft_factory is None:
            return None
        adapter = spec.aircraft_factory(settings)
        _adapter_cache[key] = adapter
    return adapter


def reset_adapters() -> None:
    _adapter_cache.clear()


# ---------------------------------------------------------------------------
# Provider resolution (Config read lazily)
# ---------------------------------------------------------------------------


def _config():
    from setup.configuration import Config

    return Config.instance()


def resolve_aircraft_providers(cfg) -> list[tuple[str, object]]:
    """``[(provider_id, adapter)]`` for enabled, configured aircraft providers."""
    providers = []
    for entry in cfg.route_providers:
        pid = entry["provider"]
        if not entry.get("enabled"):
            continue
        spec = provider_spec(pid)
        if spec is None or "aircraft" not in spec.capabilities:
            continue
        settings = cfg.provider_settings(pid)
        if not spec.config.is_configured(settings):
            continue
        adapter = get_aircraft_adapter(pid, settings)
        if adapter is not None:
            providers.append((pid, adapter))
    return providers


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


def run_aircraft_pipeline(
    ctx: LookupContext, providers: list[tuple[str, object]]
) -> tuple[AircraftInfo, bool, str]:
    """Walk *providers* in priority order, merging answers into one result.

    Returns ``(info, all_answered, first_hit_pid)``.  A provider "hits"
    when it resolves the aircraft type or registration (identity-only
    answers - an operator code or owner name - are retained and merged but
    do not stop the chain, matching the legacy behaviour).
    """
    info = AircraftInfo()
    all_answered = True
    first_hit = ""

    for pid, adapter in providers:
        if QUARANTINE.is_quarantined(pid):
            all_answered = False
            continue

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

    return info, all_answered, first_hit


def lookup_aircraft(
    ctx: LookupContext,
    cfg=None,
) -> AircraftInfo:
    """Resolve aircraft info for *ctx.mode_s* via cache + provider pipeline.

    Never raises.  Returns an :class:`AircraftInfo` (blank when unknown).
    """
    mode_s = (ctx.mode_s or "").strip().lower()
    if not mode_s:
        return AircraftInfo()

    # 1. Persistent cache - blank entries are cached too (24 h), so a hit
    #    always short-circuits the providers.
    cached = cache.get(mode_s)
    if cached is not None and not cached.get("miss"):
        # A freshly-resolved identity beats a stale one is handled below in
        # the pipeline path; a cached entry here is authoritative.
        return AircraftInfo(
            plane=cached.get("plane", ""),
            registration=cached.get("registration", ""),
            operator_icao=cached.get("operator_icao", ""),
            owner=cached.get("owner", ""),
        )

    providers = resolve_aircraft_providers(cfg or _config())
    info, all_answered, _hit = run_aircraft_pipeline(ctx, providers)

    if not info.plane and not info.registration:
        # Providers resolved nothing usable.  Stale fallback: a recently-
        # expired entry (within 7 days) is returned and re-cached.
        stale = cache.get_stale(mode_s)
        if stale is not None and (
            stale.get("plane") or stale.get("registration")
        ):
            stale_info = AircraftInfo(
                plane=stale.get("plane", ""),
                registration=stale.get("registration", ""),
                # A freshly-resolved identity beats a stale one.
                operator_icao=info.operator_icao or stale.get("operator_icao", ""),
                owner=info.owner or stale.get("owner", ""),
            )
            cache.put(
                mode_s,
                _aircraft_cache_entry(stale_info),
                ts=stale["_ts"] + cache.STALE_RECACHE_ADVANCE,
            )
            logger.debug(
                "Aircraft providers found nothing for mode_s %r - reusing "
                "stale cached info (age %.1fh)",
                mode_s,
                (time.time() - stale["_ts"]) / 3600,
            )
            return stale_info

        # All-answered blanks are cached (24 h) so 404s aren't repeated -
        # but only when the pipeline answered truthfully.
        if all_answered and providers:
            _cache_put(mode_s, info)
        return info

    _cache_put(mode_s, info)
    return info


def _cache_put(mode_s: str, info: AircraftInfo) -> None:
    """Serialise *info* under the mode-s cache key (24 h TTL)."""
    cache.put(mode_s, _aircraft_cache_entry(info))


def _aircraft_cache_entry(info: AircraftInfo) -> dict:
    """Serialise an :class:`AircraftInfo` for the mode-s cache key."""
    return {
        "plane": info.plane,
        "registration": info.registration,
        "operator_icao": info.operator_icao,
        "owner": info.owner,
    }
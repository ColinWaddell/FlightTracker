"""
Live flight-observation service.

The public :func:`fetch_flights` entry point walks the user's configured
flight-provider priority list and returns the first provider that answers
with data (an empty list is a legitimate answer - an empty sky).  Only
*enabled, configured, non-quarantined* providers are consulted; a
temporary failure (``LookupStatus.UNAVAILABLE``) quarantines the provider
for the standard interval so a dead endpoint doesn't stall every poll.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from lookups.quarantine import QUARANTINE
from lookups.registry import provider_spec, specs_for_capability

logger = logging.getLogger(__name__)

# Polling interval (seconds) associated with each flight provider.  Local
# receivers refresh fastest; free public APIs are polled slowly as they
# rate-limit.
REFRESH_INTERVALS = {
    "tar1090": 10,
    "opensky": 22,
    "fr24": 30,
}

DEFAULT_REFRESH_INTERVAL = 30


@dataclass
class FlightFetchOutcome:
    """Result of a live flight-position fetch.

    ``ok`` is True when a provider answered - *including* when it answered
    with an empty list (an empty sky is real data).  ``ok`` is False only
    when every enabled provider was unavailable (dead URL, auth failure,
    rate limit), i.e. when there is genuinely no live data to show.
    """

    ok: bool
    observations: list = field(default_factory=list)
    provider_id: str = ""
    source_name: str = ""
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Adapter construction (memoised so sessions/tokens persist across polls)
# ---------------------------------------------------------------------------

_adapter_cache: dict[tuple, object] = {}


def _settings_fingerprint(settings: dict) -> tuple:
    return tuple(sorted((k, str(v)) for k, v in settings.items()))


def get_flight_adapter(pid: str, settings: dict):
    """Return a (cached) flight-capable adapter for *pid*.

    Adapters are rebuilt automatically when their settings change so
    config edits take effect without a restart.
    """
    key = ("flights", pid, _settings_fingerprint(settings))
    cached = _adapter_cache.get(key)
    if cached is None:
        spec = provider_spec(pid)
        if spec is None or spec.flight_factory is None:
            return None
        cached = spec.flight_factory(settings)
        _adapter_cache[key] = cached
    return cached


def reset_adapters() -> None:
    """Drop memoised adapters (used by tests and after config reloads)."""
    _adapter_cache.clear()


# ---------------------------------------------------------------------------
# Provider resolution
# ---------------------------------------------------------------------------


def _flight_providers() -> list[tuple[str, dict]]:
    """Resolve enabled, configured flight providers in priority order.

    Returns ``[(provider_id, settings), ...]``.  Reads Config lazily.
    """
    from setup.configuration import Config

    cfg = Config.instance()
    return _resolve_flight_providers(cfg)


def _resolve_flight_providers(cfg) -> list[tuple[str, dict]]:
    providers = []
    for entry in cfg.flight_providers:
        pid = entry["provider"]
        if not entry.get("enabled"):
            continue
        spec = provider_spec(pid)
        if spec is None or "flights" not in spec.capabilities:
            continue
        settings = cfg.provider_settings(pid)
        if not spec.config.is_configured(settings):
            continue
        providers.append((pid, settings))
    return providers


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def fetch_flights(query) -> FlightFetchOutcome:
    """Fetch live flight observations from the highest-priority provider.

    Providers are tried in configured priority order; the first to answer
    ``FOUND`` wins (an empty list is a real answer - an empty sky).
    ``UNAVAILABLE`` results quarantine the provider temporarily and fall
    through to the next candidate.  ``NOT_FOUND`` is not meaningful for a
    zone query, so it is treated as equivalent to a fall-through.

    Never raises.
    """
    outcome = FlightFetchOutcome(ok=False)
    attempted_any = False

    for pid, settings in _flight_providers():
        spec = provider_spec(pid)
        adapter = get_flight_adapter(pid, settings)
        if adapter is None:
            continue
        if QUARANTINE.is_quarantined(pid):
            # Skip providers inside their quarantine window - they stay
            # skipped until it expires without being re-probed.
            continue

        attempted_any = True

        try:
            result = adapter.fetch(query)
        except Exception as e:  # defensive: adapters shouldn't raise
            logger.warning("Flight provider %s crashed: %s", pid, e)
            QUARANTINE.record_failure(pid)
            outcome.errors.append(f"{pid}: {e}")
            continue

        if result.is_found:
            QUARANTINE.record_success(pid)
            return FlightFetchOutcome(
                ok=True,
                observations=list(result.value or []),
                provider_id=pid,
                source_name=spec.name if spec else pid,
            )

        if result.is_unavailable:
            QUARANTINE.record_failure(pid)
            outcome.errors.append(f"{pid}: {result.reason}")
            continue

        # NOT_FOUND from a flights provider is odd (it means "no aircraft",
        # not "I cannot answer") but treat it as a legitimate empty sky.
        QUARANTINE.record_success(pid)
        return FlightFetchOutcome(
            ok=True,
            observations=[],
            provider_id=pid,
            source_name=spec.name if spec else pid,
        )

    if not attempted_any:
        outcome.errors.append("no enabled flight providers are configured")
    return outcome


def top_flight_provider() -> tuple[str, str] | tuple[None, None]:
    """``(provider_id, display_name)`` of the top enabled flight provider."""
    providers = _flight_providers()
    if not providers:
        return None, None
    pid = providers[0][0]
    spec = provider_spec(pid)
    return pid, (spec.name if spec else pid)


def refresh_interval() -> int:
    """Poll interval for the top enabled flight provider (seconds)."""
    providers = _flight_providers()
    if not providers:
        return DEFAULT_REFRESH_INTERVAL
    return REFRESH_INTERVALS.get(providers[0][0], DEFAULT_REFRESH_INTERVAL)


def startup_check() -> bool:
    """Probe the top enabled flight provider's endpoint.

    Status-agnostic (a 4xx is still "reachable").  True when the endpoint
    responds, False on connection errors or when nothing is configured.
    """
    providers = _flight_providers()
    if not providers:
        return False
    pid, settings = providers[0]
    spec = provider_spec(pid)
    if spec is None or spec.startup_check is None:
        return False
    if pid == "tar1090":
        # tar1090's probe needs the configured URL passed explicitly.
        return bool(spec.startup_check(settings.get("url", "")))
    try:
        return bool(spec.startup_check())
    except Exception:
        return False


def provider_status() -> dict[str, str]:
    """``{provider_id: "ok"|"fail"|"skip"|"quarantined"}`` for flight providers.

    Used by the startup screen and web UI.  "skip" = not enabled/configured.
    """
    from setup.configuration import Config

    cfg = Config.instance()
    status: dict[str, str] = {}
    for spec in specs_for_capability("flights"):
        settings = cfg.provider_settings(spec.id)
        enabled = any(
            e["provider"] == spec.id and e.get("enabled")
            for e in cfg.flight_providers
        )
        if not enabled or not spec.config.is_configured(settings):
            status[spec.id] = "skip"
        elif QUARANTINE.is_quarantined(spec.id):
            status[spec.id] = "quarantined"
        else:
            status[spec.id] = "ok"
    return status

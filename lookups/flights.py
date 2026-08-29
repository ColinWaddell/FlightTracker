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
from lookups.registry import (
    FLIGHTS,
    load_config,
    provider_spec,
    resolve_chain,
)

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


def _chain():
    """Enabled, configured flight adapters in priority order."""
    return resolve_chain(load_config(), FLIGHTS)


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

    for pid, adapter in _chain():
        spec = provider_spec(pid)
        if QUARANTINE.is_quarantined(pid):
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


def top_flight_provider() -> tuple[str | None, str | None]:
    """``(provider_id, display_name)`` of the top enabled flight provider."""
    chain = _chain()
    if not chain:
        return None, None
    pid = chain[0][0]
    return pid, provider_spec(pid).name


def refresh_interval() -> int:
    """Poll interval for the top enabled flight provider (seconds)."""
    chain = _chain()
    if not chain:
        return DEFAULT_REFRESH_INTERVAL
    return REFRESH_INTERVALS.get(chain[0][0], DEFAULT_REFRESH_INTERVAL)


def startup_check() -> bool:
    """Probe the top enabled flight provider's endpoint.

    Status-agnostic (a 4xx is still "reachable").  True when the endpoint
    responds, False on connection errors or when nothing is configured.
    """
    chain = _chain()
    if not chain:
        return False
    pid, adapter_or_spec = chain[0][0], provider_spec(chain[0][0])
    try:
        from setup.configuration import Config

        settings = Config.instance().provider_settings(pid)
        return bool(adapter_or_spec.startup_check(settings))
    except Exception:
        return False

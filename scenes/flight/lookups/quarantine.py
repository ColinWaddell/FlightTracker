"""
Shared provider quarantine mechanism.

Tracks temporarily-unavailable providers so the lookup services can skip a
dead, rate-limited or misconfigured provider instead of hammering it for
every aircraft on every poll.  Quarantine entries expire automatically after
:data:`INTERVAL` seconds, at which point the provider is retried.

Providers do not implement quarantine themselves.  They report
``LookupStatus.UNAVAILABLE`` when they cannot currently answer; the lookup
services (:mod:`lookups.flights`, :mod:`lookups.routes`,
:mod:`lookups.aircraft`) record temporary failures here and skip
quarantined providers until the window expires.

Quarantine is keyed by provider id, so a rate-limited FR24 service is
skipped for every capability (flights, routes and aircraft) at once.
"""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

# How long a provider is quarantined after a temporary failure (seconds).
INTERVAL = 3600  # 1 hour - matches the historical PROVIDER_RETRY_INTERVAL


class Quarantine:
    """Thread-safe registry of temporarily-failed providers.

    The monotonic clock is injectable so tests can simulate expiry.
    """

    def __init__(self, interval: float = INTERVAL, clock=time.monotonic):
        self._interval = interval
        self._clock = clock
        self._failed_at: dict[str, float] = {}
        self._lock = threading.Lock()

    def record_failure(self, provider_id: str) -> None:
        """Mark *provider_id* as temporarily unavailable."""
        with self._lock:
            self._failed_at[provider_id] = self._clock()
        logger.debug("Provider %s quarantined for %ds", provider_id, self._interval)

    def record_success(self, provider_id: str) -> None:
        """Mark *provider_id* as healthy, clearing any active quarantine."""
        with self._lock:
            self._failed_at.pop(provider_id, None)

    def is_quarantined(self, provider_id: str) -> bool:
        """True while *provider_id* is inside its quarantine window.

        Expired entries are removed lazily so providers recover without
        needing a separate expiry sweep.
        """
        with self._lock:
            failed_at = self._failed_at.get(provider_id)
            if failed_at is None:
                return False
            if self._clock() - failed_at < self._interval:
                return True
            # Quarantine expired - allow the provider to be tried again.
            del self._failed_at[provider_id]
            return False

    def reset(self) -> None:
        """Clear all quarantine state (used by tests and manual overrides)."""
        with self._lock:
            self._failed_at.clear()

    def snapshot(self) -> dict[str, float]:
        """Return ``{provider_id: seconds_remaining}`` for active quarantines."""
        with self._lock:
            now = self._clock()
            return {
                pid: self._interval - (now - ts)
                for pid, ts in self._failed_at.items()
                if now - ts < self._interval
            }


# Process-wide quarantine used by the lookup services.
QUARANTINE = Quarantine()

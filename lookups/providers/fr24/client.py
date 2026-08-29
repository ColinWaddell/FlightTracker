"""
Shared FlightRadar24 API client.

Owns everything service-specific about talking to FR24 that more than one
FR24 capability needs: API construction (lazy - FlightRadarAPI drags in
curl_cffi + brotli, which costs seconds on a Pi), cookie hygiene, ground
traffic filtering, timeout/retry behaviour, a short-lived memo of bubble
lookups so a single enrichment pass never issues duplicate ``get_flights``
calls, and per-callsign live-feed miss tracking so a flight the feed does
not show isn't re-queried on every poll.

Capability modules (``flights.py``, ``routes.py``, ``aircraft.py``) all
build on this client instead of re-implementing the same API behaviour.
"""

from __future__ import annotations

import contextlib
import logging
import threading
import time

logger = logging.getLogger(__name__)

# FR24 request timeout (seconds) - the library default of 30 is too short
# for a Pi on slow networks, and the clickhandler details call is slowest.
FR24_TIMEOUT = 60

# get_flight_details retry behaviour.  Sleep only happens *between* retries
# (not before the first attempt) so a single successful call has no added
# latency.
DETAIL_RETRIES = 3
DETAIL_DELAY_S = 1  # seconds, slept between failed attempts

# Bubble (bounds-by-point) sizing for position+callsign lookups:
# radius_m = min(CAP, max(BASELINE, speed * WINDOW_S))
BOUNDS_BASELINE_M = 1000  # minimum radius (covers slow/stationary + GPS jitter)
BOUNDS_WINDOW_S = 30  # assumed FR24 feed staleness window (seconds)
BOUNDS_CAP_M = 20000  # sanity cap so a speed anomaly can't blow the box out

# Bubble lookups are memoised briefly so the route pipeline and the aircraft
# pipeline for the same aircraft during one enrichment pass share a single
# feed call.
BUBBLE_MEMO_TTL_S = 15.0

# In-memory per-callsign live-feed miss TTL (1 hour).
MISS_TTL_S = 3600.0


def _load_api():
    """Import FlightRadar24API lazily (drags in curl_cffi + brotli on a Pi)."""
    try:
        from FlightRadar24.api import FlightRadar24API
    except ImportError:
        from FlightRadarAPI import FlightRadar24API
    return FlightRadar24API


try:
    from curl_cffi.requests.exceptions import Timeout as CurlTimeout
except ImportError:  # pragma: no cover - depends on optional dep
    CurlTimeout = None


def _is_curl_timeout(e: Exception) -> bool:
    """True when *e* is curl_cffi's Timeout (doesn't inherit requests')."""
    return CurlTimeout is not None and isinstance(e, CurlTimeout)


def bubble_radius_for(speed_mps: float) -> int:
    """Bubble radius (metres) for a ground speed in m/s."""
    return min(
        BOUNDS_CAP_M, max(BOUNDS_BASELINE_M, (speed_mps or 0.0) * BOUNDS_WINDOW_S)
    )


class FR24Client:
    """Thin, shared wrapper around the FlightRadar24API library."""

    def __init__(self, timeout: int = FR24_TIMEOUT):
        self.timeout = timeout
        self._api = None
        self._api_lock = threading.Lock()
        # (callsign, rounded lat, rounded lng) -> (monotonic_ts, flights)
        self._bubble_cache: dict[tuple, tuple[float, list]] = {}
        self._bubble_lock = threading.Lock()
        # callsign -> monotonic timestamp of the last live-feed miss
        self._missed: dict[str, float] = {}
        self._miss_lock = threading.Lock()

    # ------------------------------------------------------------------
    # API lifecycle
    # ------------------------------------------------------------------

    @property
    def api(self):
        """Lazily-constructed FlightRadar24API instance.

        A fresh instance starts with a clean session - Cloudflare may
        block stale cookies.
        """
        if self._api is None:
            with self._api_lock:
                if self._api is None:
                    self._api = _load_api()(timeout=self.timeout)
                    self._reset_tracker_config()
        return self._api

    def clear_cookies(self) -> None:
        """Clear cookies to avoid FR24 rate-limiting on subsequent calls."""
        with contextlib.suppress(Exception):
            # FlightRadar24API stores its underlying HTTP client privately.
            client = getattr(self._api, "_FlightRadar24API__client", None)
            if client is not None:
                client.clear_cookies()

    def _reset_tracker_config(self) -> None:
        """Exclude ground traffic from the feed (reduces result size)."""
        tracker = self.api.get_flight_tracker_config()
        tracker.gnd = 0
        self.api.set_flight_tracker_config(tracker)

    # ------------------------------------------------------------------
    # Feed queries
    # ------------------------------------------------------------------

    def get_flights_in_bounds(self, bounds) -> list:
        """Fetch the live feed for a bounds dict.  Raises on failure."""
        return self.api.get_flights(bounds=bounds)

    def get_zone_bounds(self, zone: dict):
        return self.api.get_bounds(zone)

    def bubble_flights(self, callsign: str, lat: float, lng: float, speed_mps: float):
        """Return flights in a bubble around a live position.

        The bubble is sized by ground speed to allow for FR24 feed
        staleness.  Lookups for the same callsign/position are memoised
        for a few seconds so the route and aircraft pipelines triggered
        during one enrichment share a single feed call.  Returns [] when
        the position is missing or the feed call fails.
        """
        if lat is None or lng is None:
            return []

        radius_m = bubble_radius_for(speed_mps)
        key = (callsign, round(lat, 3), round(lng, 3))

        with self._bubble_lock:
            cached = self._bubble_cache.get(key)
            now = time.monotonic()
            if cached is not None and now - cached[0] < BUBBLE_MEMO_TTL_S:
                return cached[1]

        self.clear_cookies()
        try:
            bounds = self.api.get_bounds_by_point(lat, lng, radius_m)
            flights = self.api.get_flights(bounds=bounds)
        except Exception as e:
            logger.debug("FR24 bubble fetch failed: %s", e)
            flights = []

        with self._bubble_lock:
            self._bubble_cache[key] = (time.monotonic(), flights)
        return flights

    def match_in_bubble(self, callsign: str, lat: float, lng: float, speed_mps: float):
        """Find the feed flight matching *callsign* within the position bubble.

        Returns the FlightRadar24API Flight object or None (which may mean
        "no match" or "the feed has no such flight right now").
        """
        for flight in self.bubble_flights(callsign, lat, lng, speed_mps):
            if (getattr(flight, "callsign", "") or "").strip() == callsign:
                return flight
        return None

    # ------------------------------------------------------------------
    # Flight details (clickhandler) - full aircraft model text
    # ------------------------------------------------------------------

    def flight_details(self, flight, retries: int = DETAIL_RETRIES) -> dict | None:
        """Fetch flight details with FR24's retry behaviour.  Never raises.

        Sleep of :data:`DETAIL_DELAY_S` is inserted between retries only,
        so a successful first call has zero added latency.
        """
        details = None
        for attempt in range(retries):
            if attempt > 0:
                time.sleep(DETAIL_DELAY_S)
            try:
                details = self.api.get_flight_details(flight)
                break
            except Exception as e:
                if _is_curl_timeout(e):
                    logger.debug(
                        "FR24 flight detail timeout, retrying (%d left)",
                        retries - attempt - 1,
                    )
                elif not isinstance(e, (KeyError, AttributeError, TypeError)):
                    logger.debug("FR24 flight detail error: %s", e)
        return details

    def aircraft_model_text(self, flight, retries: int = DETAIL_RETRIES) -> str:
        """Return the full model name for *flight* ("Boeing 737-800").

        Falls back to the free ``aircraft_code`` (ICAO type code, e.g.
        "B738") from the feed list when the details call fails or has no
        model text.  Returns "" when neither is available.
        """
        details = self.flight_details(flight, retries)
        if details is not None:
            try:
                from utilities.overhead_utilities import clean_field

                plane = clean_field(details["aircraft"]["model"]["text"])
                if plane:
                    return plane
            except (KeyError, TypeError):
                pass
        from utilities.overhead_utilities import clean_field

        return clean_field(getattr(flight, "aircraft_code", ""))

    # ------------------------------------------------------------------
    # Per-callsign live-feed miss tracking (service-specific rate-limit
    # protection).  In-memory only - a restart always retries the feed.
    # ------------------------------------------------------------------

    def recently_missed(self, callsign: str) -> bool:
        """True when the FR24 live feed recently had no flight for *callsign*."""
        with self._miss_lock:
            ts = self._missed.get(callsign)
            if ts is None:
                return False
            if time.monotonic() - ts > MISS_TTL_S:
                del self._missed[callsign]
                return False
            return True

    def record_feed_miss(self, callsign: str) -> None:
        """Record that the live feed had no matching flight for *callsign*."""
        with self._miss_lock:
            self._missed[callsign] = time.monotonic()

    def clear_feed_miss(self, callsign: str) -> None:
        """Clear any recorded miss (a flight was found)."""
        with self._miss_lock:
            self._missed.pop(callsign, None)


# ---------------------------------------------------------------------------
# Module-level singleton access
# ---------------------------------------------------------------------------

_client: FR24Client | None = None
_client_lock = threading.Lock()


def get_client() -> FR24Client:
    global _client
    if _client is None:
        with _client_lock:
            if _client is None:
                _client = FR24Client()
    return _client


def reset_client() -> None:
    """Drop the shared client (used by tests)."""
    global _client
    with _client_lock:
        _client = None
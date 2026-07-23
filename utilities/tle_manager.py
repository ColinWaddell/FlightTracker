"""
TLEManager - fetch and cache TLE data from CelesTrak.

Resolves NORAD catalog IDs (integers) to (name, line1, line2) tuples using
CelesTrak's GP endpoint:

    https://celestrak.org/NORAD/elements/gp.php?CATNR={id}&FORMAT=TLE

Results are cached to disk and refreshed automatically after TLE_CACHE_TTL
seconds.  Thread-safe.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.request

from setup.configuration import CONFIG_PATH, ROOT_PATH, Config, migrate_legacy_json

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TLE_CACHE_TTL = 86400  # 24 hours
TLE_CACHE_PATH = migrate_legacy_json(
    ROOT_PATH / "tle_cache.json", CONFIG_PATH.parent / "tle_cache.json"
)
HTTP_TIMEOUT = 15

# Backoff after a failed refresh: starts at 1 minute, doubles each failure,
# capped at 1 hour. Reset to the minimum on a successful refresh.
BACKOFF_MIN = 60.0
BACKOFF_MAX = 3600.0

GP_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR={catnr}&FORMAT=TLE"


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------


def fetch_tle(norad_id: int) -> tuple[str, str, str] | None:
    """Fetch a single TLE by NORAD catalog number. Returns (name, l1, l2) or None."""
    url = GP_URL.format(catnr=norad_id)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "FlightTracker/1.0 (raspberry-pi)"},
        )
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        logger.error("HTTP error fetching TLE for NORAD %d: %s", norad_id, exc)
        return None

    lines = [line.rstrip() for line in body.splitlines() if line.strip()]
    if len(lines) >= 3 and lines[1].startswith("1 ") and lines[2].startswith("2 "):
        return lines[0].strip(), lines[1], lines[2]

    logger.warning("No valid TLE in response for NORAD %d", norad_id)
    return None


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------


def load_cache() -> dict | None:
    try:
        data = json.loads(TLE_CACHE_PATH.read_text())
        if isinstance(data, dict) and "timestamp" in data and "tles" in data:
            return data
    except Exception:
        pass
    return None


def save_cache(tles: list[tuple[str, str, str]]) -> None:
    try:
        TLE_CACHE_PATH.write_text(
            json.dumps(
                {"timestamp": time.time(), "tles": [list(t) for t in tles]}, indent=2
            )
        )
    except Exception as exc:
        logger.warning("TLE cache write failed: %s", exc)


# ---------------------------------------------------------------------------
# TLEManager
# ---------------------------------------------------------------------------


class TLEManager:
    """
    Manages TLE fetching, caching, and serving for SatelliteScene.

    Usage:
        mgr = TLEManager()
        mgr.start()
        tles = mgr.get()   # blocks briefly on first call, then instant
    """

    def __init__(self):
        self.lock = threading.Lock()
        self.tles: list[tuple[str, str, str]] = []
        self.fetched_at: float = 0.0
        self.ready = threading.Event()
        # Backoff state for failed refreshes.
        self.backoff_seconds: float = 0.0
        self.next_attempt_at: float = 0.0

    def start(self) -> None:
        threading.Thread(target=self.run_loop, daemon=True, name="tle-manager").start()

    def get(self, timeout: float = 30.0) -> list[tuple[str, str, str]]:
        """Block until first fetch completes, then return cached TLE list."""
        self.ready.wait(timeout=timeout)
        with self.lock:
            return list(self.tles)

    def try_get(self) -> list[tuple[str, str, str]] | None:
        """Non-blocking: return cached TLEs if ready, else None."""
        if not self.ready.is_set():
            return None
        with self.lock:
            return list(self.tles)

    def invalidate(self) -> None:
        """Force a refresh on next cycle (e.g. after config change)."""
        with self.lock:
            self.fetched_at = 0.0
            self.backoff_seconds = 0.0
            self.next_attempt_at = 0.0
        self.ready.clear()

    def run_loop(self) -> None:
        # Serve from disk cache immediately if still fresh
        cached = load_cache()
        if cached and (time.time() - cached["timestamp"]) < TLE_CACHE_TTL:
            with self.lock:
                self.tles = [tuple(t) for t in cached["tles"]]
                self.fetched_at = cached["timestamp"]
            self.ready.set()

        while True:
            now = time.time()
            with self.lock:
                age = now - self.fetched_at
                due = age >= TLE_CACHE_TTL and now >= self.next_attempt_at
                in_backoff = self.backoff_seconds > 0.0
            if due:
                self.do_fetch()
                # After a fetch, re-read state to decide how long to sleep.
                with self.lock:
                    in_backoff = self.backoff_seconds > 0.0
                    wait = self.next_attempt_at - time.time() if in_backoff else 300.0
            else:
                wait = max(0.0, self.next_attempt_at - now) if in_backoff else 300.0
            time.sleep(max(1.0, min(wait, 300.0)))  # check at most every 5 min

    def do_fetch(self) -> None:
        norad_ids = Config.instance().satellite_norad_ids
        if not norad_ids:
            self.ready.set()
            return

        logger.debug("TLE refresh starting for %d satellite(s)", len(norad_ids))
        results: list[tuple[str, str, str]] = []
        for norad_id in norad_ids:
            tle = fetch_tle(norad_id)
            if tle:
                logger.debug("TLE fetched: %s (NORAD %d)", tle[0], norad_id)
                results.append(tle)

        if results:
            save_cache(results)
            with self.lock:
                self.tles = results
                self.fetched_at = time.time()
                self.backoff_seconds = 0.0
                self.next_attempt_at = 0.0
            logger.info(
                "TLE refresh complete - %d/%d satellite(s) updated",
                len(results),
                len(norad_ids),
            )
        else:
            with self.lock:
                self.backoff_seconds = (
                    BACKOFF_MIN
                    if self.backoff_seconds <= 0.0
                    else min(self.backoff_seconds * 2.0, BACKOFF_MAX)
                )
                self.next_attempt_at = time.time() + self.backoff_seconds
            logger.warning(
                "TLE refresh returned no results - keeping existing cache; "
                "next retry in %.0fs",
                self.backoff_seconds,
            )

        self.ready.set()

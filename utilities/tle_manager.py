"""
TLEManager — fetch and cache TLE data from CelesTrak.

Resolves satellite display names (e.g. "ISS (ZARYA)") to (name, line1, line2)
tuples by querying CelesTrak's GP name-search endpoint.  Results are cached to
disk alongside config.json and refreshed automatically when the cache is more
than TLE_CACHE_TTL seconds old.

Thread-safe: a single background daemon thread drives all fetches so the main
thread (and scene draw loop) never block on network I/O.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

from setup.configuration import Config, CONFIG_PATH

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TLE_CACHE_TTL = 86400  # 24 hours in seconds
TLE_CACHE_PATH = CONFIG_PATH.parent / "tle_cache.json"

# CelesTrak GP name-search endpoint.
# Returns TLE text for the best-matching satellite with the given name.
# FORMAT=TLE  →  plain 3-line TLE (name / line1 / line2)
_CELESTRAK_URL = (
    "https://celestrak.org/SATCAT/search.php"
    "?NAME={name}&FORMAT=TLE"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fetch_tle(name: str) -> tuple[str, str, str] | None:
    """
    Query CelesTrak for a single satellite name.
    Returns (canonical_name, line1, line2) or None on failure.
    """
    url = _CELESTRAK_URL.format(
        name=urllib.parse.quote(name.strip())
    )
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "FlightTracker/1.0 (raspberry-pi)"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"[tle] fetch failed for '{name}': {exc}")
        return None

    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    # Expect groups of 3: name / line-1 / line-2
    # Line 1 starts with "1 ", line 2 starts with "2 "
    for i in range(len(lines) - 2):
        if lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            return (lines[i], lines[i + 1], lines[i + 2])

    print(f"[tle] no valid TLE found in response for '{name}'")
    return None


def _load_cache() -> dict | None:
    """Load the on-disk TLE cache; returns None if missing or corrupt."""
    try:
        data = json.loads(TLE_CACHE_PATH.read_text())
        if isinstance(data, dict) and "timestamp" in data and "tles" in data:
            return data
    except Exception:
        pass
    return None


def _save_cache(tles: list[tuple[str, str, str]]) -> None:
    """Persist TLE data to disk with a timestamp."""
    try:
        TLE_CACHE_PATH.write_text(
            json.dumps(
                {
                    "timestamp": time.time(),
                    "tles": [list(t) for t in tles],
                },
                indent=2,
            )
        )
    except Exception as exc:
        print(f"[tle] cache write failed: {exc}")


# ---------------------------------------------------------------------------
# TLEManager
# ---------------------------------------------------------------------------


class TLEManager:
    """
    Manages TLE fetching, caching, and serving for SatelliteScene.

    Usage:
        mgr = TLEManager()
        mgr.start()            # kick off background fetch
        tles = mgr.get()       # blocks briefly on first call, then instant
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._tles: list[tuple[str, str, str]] = []
        self._fetched_at: float = 0.0
        self._ready = threading.Event()

    def start(self) -> None:
        """Start the background fetch/refresh daemon."""
        t = threading.Thread(
            target=self._run,
            daemon=True,
            name="tle-manager",
        )
        t.start()

    def get(self, timeout: float = 30.0) -> list[tuple[str, str, str]]:
        """
        Return the current TLE list.  Blocks until the first fetch completes
        (or timeout elapses), then returns instantly on subsequent calls.
        """
        self._ready.wait(timeout=timeout)
        with self._lock:
            return list(self._tles)

    def invalidate(self) -> None:
        """Force a refresh on the next _run cycle (e.g. after config change)."""
        with self._lock:
            self._fetched_at = 0.0
        self._ready.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        """Background loop: load cache → serve → refresh on TTL expiry."""
        # Try to serve from disk cache immediately so the scene can start fast.
        cached = _load_cache()
        if cached and (time.time() - cached["timestamp"]) < TLE_CACHE_TTL:
            with self._lock:
                self._tles = [tuple(t) for t in cached["tles"]]
                self._fetched_at = cached["timestamp"]
            self._ready.set()

        while True:
            now = time.time()
            with self._lock:
                age = now - self._fetched_at

            if age >= TLE_CACHE_TTL:
                self._do_fetch()

            # Check again in 5 minutes
            time.sleep(300)

    def _do_fetch(self) -> None:
        cfg = Config.instance()
        names = cfg.satellite_names
        if not names:
            self._ready.set()
            return

        results: list[tuple[str, str, str]] = []
        for name in names:
            tle = _fetch_tle(name)
            if tle:
                results.append(tle)

        if results:
            _save_cache(results)
            with self._lock:
                self._tles = results
                self._fetched_at = time.time()

        self._ready.set()

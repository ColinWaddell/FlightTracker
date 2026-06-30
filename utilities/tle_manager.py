"""
TLEManager — fetch and cache TLE data from CelesTrak.

Resolves NORAD catalog IDs (integers) to (name, line1, line2) tuples using
CelesTrak's GP endpoint:

    https://celestrak.org/NORAD/elements/gp.php?CATNR={id}&FORMAT=TLE

Results are cached to disk and refreshed automatically after TLE_CACHE_TTL
seconds.  Thread-safe.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.request
from pathlib import Path

from setup.configuration import Config, CONFIG_PATH

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TLE_CACHE_TTL = 86400  # 24 hours
TLE_CACHE_PATH = CONFIG_PATH.parent / "tle_cache.json"
HTTP_TIMEOUT = 15

_GP_URL = "https://celestrak.org/NORAD/elements/gp.php?CATNR={catnr}&FORMAT=TLE"


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------


def _fetch_tle(norad_id: int) -> tuple[str, str, str] | None:
    """Fetch a single TLE by NORAD catalog number. Returns (name, l1, l2) or None."""
    url = _GP_URL.format(catnr=norad_id)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "FlightTracker/1.0 (raspberry-pi)"},
        )
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"[tle] HTTP error for NORAD {norad_id}: {exc}")
        return None

    lines = [l.rstrip() for l in body.splitlines() if l.strip()]
    if len(lines) >= 3 and lines[1].startswith("1 ") and lines[2].startswith("2 "):
        return lines[0].strip(), lines[1], lines[2]

    print(f"[tle] no valid TLE in response for NORAD {norad_id}")
    return None


# ---------------------------------------------------------------------------
# Disk cache
# ---------------------------------------------------------------------------


def _load_cache() -> dict | None:
    try:
        data = json.loads(TLE_CACHE_PATH.read_text())
        if isinstance(data, dict) and "timestamp" in data and "tles" in data:
            return data
    except Exception:
        pass
    return None


def _save_cache(tles: list[tuple[str, str, str]]) -> None:
    try:
        TLE_CACHE_PATH.write_text(
            json.dumps({"timestamp": time.time(), "tles": [list(t) for t in tles]}, indent=2)
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
        mgr.start()
        tles = mgr.get()   # blocks briefly on first call, then instant
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._tles: list[tuple[str, str, str]] = []
        self._fetched_at: float = 0.0
        self._ready = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._run, daemon=True, name="tle-manager").start()

    def get(self, timeout: float = 30.0) -> list[tuple[str, str, str]]:
        """Block until first fetch completes, then return cached TLE list."""
        self._ready.wait(timeout=timeout)
        with self._lock:
            return list(self._tles)

    def invalidate(self) -> None:
        """Force a refresh on next cycle (e.g. after config change)."""
        with self._lock:
            self._fetched_at = 0.0
        self._ready.clear()

    def _run(self) -> None:
        # Serve from disk cache immediately if still fresh
        cached = _load_cache()
        if cached and (time.time() - cached["timestamp"]) < TLE_CACHE_TTL:
            with self._lock:
                self._tles = [tuple(t) for t in cached["tles"]]
                self._fetched_at = cached["timestamp"]
            self._ready.set()

        while True:
            with self._lock:
                age = time.time() - self._fetched_at
            if age >= TLE_CACHE_TTL:
                self._do_fetch()
            time.sleep(300)  # check every 5 minutes

    def _do_fetch(self) -> None:
        norad_ids = Config.instance().satellite_norad_ids
        if not norad_ids:
            self._ready.set()
            return

        results: list[tuple[str, str, str]] = []
        for norad_id in norad_ids:
            tle = _fetch_tle(norad_id)
            if tle:
                print(f"[tle] fetched {tle[0]} (NORAD {norad_id})")
                results.append(tle)

        if results:
            _save_cache(results)
            with self._lock:
                self._tles = results
                self._fetched_at = time.time()
        else:
            print("[tle] fetch returned no results — keeping existing cache")

        self._ready.set()

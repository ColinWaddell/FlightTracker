"""
TLEManager — fetch and cache TLE data from CelesTrak.

Resolves satellite display names (e.g. "ISS (ZARYA)") to (name, line1, line2)
tuples.  Uses three strategies in order:

  1. GP name-search API  — one request per satellite, exact name match.
  2. stations.txt group  — pre-built file of all space stations (includes ISS).
  3. visual.txt group    — pre-built file of ~1000 visually observable objects.

Results are cached to disk alongside config.json and refreshed automatically
after TLE_CACHE_TTL seconds.  Thread-safe.
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

TLE_CACHE_TTL = 86400  # 24 hours
TLE_CACHE_PATH = CONFIG_PATH.parent / "tle_cache.json"
HTTP_TIMEOUT = 15

# CelesTrak GP.php — current query endpoint for General Perturbations data.
# Replaced the legacy /SATCAT/*.txt static files and /SATCAT/search.php?GP& paths.
_GP_NAME_URL = "https://celestrak.org/GP.php?NAME={name}&FORMAT=TLE"

# Pre-built group queries — searched when the name query returns nothing.
_GROUP_URLS = [
    "https://celestrak.org/GP.php?GROUP=stations&FORMAT=TLE",   # space stations (ISS, CSS, …)
    "https://celestrak.org/GP.php?GROUP=visual&FORMAT=TLE",     # visually observable (~1 000 objects)
]

# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def _request(url: str) -> str | None:
    """Fetch a URL and return the response body as a string, or None on error."""
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "FlightTracker/1.0 (raspberry-pi)"},
        )
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:
        print(f"[tle] HTTP error fetching {url}: {exc}")
        return None


def _parse_tles(text: str) -> list[tuple[str, str, str]]:
    """
    Parse a block of 3-line TLE text into a list of (name, line1, line2) tuples.
    Handles trailing whitespace and blank separator lines.
    """
    lines = [l.rstrip() for l in text.splitlines()]
    results = []
    i = 0
    while i < len(lines) - 2:
        if lines[i + 1].startswith("1 ") and lines[i + 2].startswith("2 "):
            results.append((lines[i].strip(), lines[i + 1], lines[i + 2]))
            i += 3
        else:
            i += 1
    return results


def _name_matches(tle_name: str, query: str) -> bool:
    """Case-insensitive comparison, ignoring leading/trailing whitespace."""
    return tle_name.strip().lower() == query.strip().lower()


# ---------------------------------------------------------------------------
# Fetch strategies
# ---------------------------------------------------------------------------


def _fetch_by_gp_api(name: str) -> tuple[str, str, str] | None:
    """
    Try CelesTrak's GP name-search endpoint.

    Attempts two encodings:
      1. Full name with parens URL-encoded   — e.g. ISS%20%28ZARYA%29
      2. Full name with parens un-encoded    — e.g. ISS%20(ZARYA)
    Returns the first matching result.
    """
    stripped = name.strip()
    candidates = [
        _GP_NAME_URL.format(name=urllib.parse.quote(stripped)),           # encode (
        _GP_NAME_URL.format(name=urllib.parse.quote(stripped, safe="()")),# keep (
    ]
    seen: set[str] = set()
    for url in candidates:
        if url in seen:
            continue
        seen.add(url)
        body = _request(url)
        if not body:
            continue
        tles = _parse_tles(body)
        if tles:
            return tles[0]

    print(f"[tle] GP API returned no TLE for '{name}'")
    return None


def _fetch_group_files() -> dict[str, tuple[str, str, str]]:
    """
    Download pre-built group files and return a name → (name, l1, l2) dict.
    Stops after the first successful download per URL.
    """
    combined: dict[str, tuple[str, str, str]] = {}
    for url in _GROUP_URLS:
        body = _request(url)
        if not body:
            continue
        for entry in _parse_tles(body):
            combined[entry[0].strip().lower()] = entry
    return combined


def _fetch_all(names: list[str]) -> list[tuple[str, str, str]]:
    """
    Resolve each configured satellite name to a TLE tuple.
    Tries the GP API first; falls back to group-file search for any misses.
    """
    results: list[tuple[str, str, str]] = []
    missing: list[str] = []

    for name in names:
        tle = _fetch_by_gp_api(name)
        if tle:
            results.append(tle)
        else:
            missing.append(name)

    if missing:
        print(f"[tle] falling back to group files for: {missing}")
        group = _fetch_group_files()
        for name in missing:
            # Try exact match first, then prefix match
            key = name.strip().lower()
            if key in group:
                results.append(group[key])
            else:
                # Partial match — take the first entry whose name contains the query
                for gkey, entry in group.items():
                    if key in gkey or gkey in key:
                        print(f"[tle] matched '{name}' → '{entry[0]}'")
                        results.append(entry)
                        break
                else:
                    print(f"[tle] could not find TLE for '{name}' — skipping")

    return results


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
        # Serve from disk cache immediately if fresh enough
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
        cfg = Config.instance()
        names = cfg.satellite_names
        if not names:
            self._ready.set()
            return

        results = _fetch_all(names)

        if results:
            _save_cache(results)
            with self._lock:
                self._tles = results
                self._fetched_at = time.time()
        else:
            print("[tle] fetch returned no results — keeping existing cache")

        self._ready.set()

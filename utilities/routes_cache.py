"""
Persistent route cache — shared by overhead_fr24 and overhead_tar1090.

Stores route info (plane, origin, destination, airport names) keyed by
callsign in a JSON file with a 24-hour TTL. This avoids repeated API
lookups for the same flight route.

Cache file: <repo_root>/routes_cache.json
"""

import json
import logging
import os
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

CACHE_TTL = 86400  # 24 hours
CACHE_PATH = Path(__file__).parent.parent / "routes_cache.json"

_lock = threading.Lock()
_cache: dict = {}
_loaded = False


def _load():
    """Load the cache from disk if not already loaded."""
    global _cache, _loaded
    if _loaded:
        return
    _loaded = True
    try:
        if CACHE_PATH.exists():
            with open(CACHE_PATH, "r") as f:
                _cache = json.load(f)
            logger.debug("Route cache loaded %d entries from %s",
                         len(_cache), CACHE_PATH)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Route cache load failed: %s — starting fresh", e)
        _cache = {}


def _save():
    """Persist the cache to disk."""
    try:
        with open(CACHE_PATH, "w") as f:
            json.dump(_cache, f, indent=2)
    except OSError as e:
        logger.warning("Route cache save failed: %s", e)


def get(callsign: str) -> dict | None:
    """
    Return cached route info for *callsign* if it exists and is fresh.

    Returns a dict with keys: plane, origin, destination,
    origin_name, destination_name — or None if not cached / expired.
    """
    with _lock:
        _load()
        entry = _cache.get(callsign)
        if entry is None:
            return None
        if time.time() - entry.get("_ts", 0) > CACHE_TTL:
            # Expired — remove and miss
            del _cache[callsign]
            _save()
            return None
        return {k: v for k, v in entry.items() if not k.startswith("_")}


def put(callsign: str, info: dict):
    """
    Store route info for *callsign*.

    *info* should contain: plane, origin, destination,
    origin_name, destination_name.
    """
    with _lock:
        _load()
        entry = dict(info)
        entry["_ts"] = time.time()
        _cache[callsign] = entry
        _save()


def clear():
    """Clear the entire cache."""
    with _lock:
        _cache = {}
        _loaded = True
        _save()
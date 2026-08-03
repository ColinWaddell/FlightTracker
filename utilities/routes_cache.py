"""
Persistent route cache - shared by overhead_fr24, overhead_tar1090, and overhead_osn.

Stores two kinds of entries in a single JSON file, distinguished by their key:

  callsign keys  (e.g. "BAW123")
      plane, origin, destination, origin_name, origin_municipality,
      origin_country, destination_name, destination_municipality,
      destination_country, registration, airline_icao

  mode_s keys    (e.g. "400f5a")
      plane, registration

Both key types use a 24-hour TTL by default.  Pass ``ttl=`` to :func:`put`
to override per-entry (e.g. use CACHE_TTL_MISS for negative results).

Cache file: <platform_data_dir>/routes_cache.json

Changes vs. previous version
------------------------------
- ``put()`` now sets a *dirty* flag instead of writing to disk immediately;
  call :func:`flush` at the end of a processing cycle to persist.  This
  reduces SD-card writes on Raspberry Pi from one-per-entry to
  one-per-poll-cycle.
- Optional *ttl* parameter on ``put()`` stored as ``_ttl`` in the entry so
  negative/miss entries can use a shorter TTL without changing the default.
- ``get()`` honours per-entry ``_ttl`` values (falls back to CACHE_TTL).
- ``get()`` handles ``None`` key gracefully (returns ``None``).
"""

import json
import logging
import threading
import time

from setup.configuration import PLATFORM_DATA_DIR, ROOT_PATH, migrate_legacy_json

logger = logging.getLogger(__name__)

CACHE_TTL = 86400       # 24 hours – positive / aircraft entries
CACHE_TTL_MISS = 3600   # 1 hour   – negative / miss entries
CACHE_PATH = PLATFORM_DATA_DIR / "routes_cache.json"
CACHE_PATH = migrate_legacy_json(ROOT_PATH / "routes_cache.json", CACHE_PATH)

_lock = threading.Lock()
_cache: dict = {}
_loaded = False
_dirty = False


def _load():
    """Load the cache from disk if not already loaded."""
    global _cache, _loaded
    if _loaded:
        return
    _loaded = True
    try:
        if CACHE_PATH.exists():
            with open(CACHE_PATH) as f:
                _cache = json.load(f)
            logger.debug(
                "Route cache loaded %d entries from %s", len(_cache), CACHE_PATH
            )
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Route cache load failed: %s - starting fresh", e)
        _cache = {}


def _save():
    """Persist the cache to disk.  Caller must hold *_lock*."""
    try:
        with open(CACHE_PATH, "w") as f:
            json.dump(_cache, f, indent=2)
    except OSError as e:
        logger.warning("Route cache save failed: %s", e)


def get(key: str) -> dict | None:
    """Return cached info for *key* if it exists and is not expired.

    Returns a dict (internal ``_``-prefixed keys stripped) or ``None`` when
    the key is absent, expired, or *key* is ``None``.
    """
    global _dirty
    with _lock:
        if key is None:
            return None
        _load()
        entry = _cache.get(key)
        if entry is None:
            return None
        ttl = entry.get("_ttl", CACHE_TTL)
        if time.time() - entry.get("_ts", 0) > ttl:
            del _cache[key]
            _dirty = True
            return None
        return {k: v for k, v in entry.items() if not k.startswith("_")}


def put(key: str, info: dict, ttl: int = CACHE_TTL):
    """Store *info* under *key*.

    *ttl* overrides the default 24-hour TTL for this entry.  The change is
    held in memory; call :func:`flush` to persist to disk.
    """
    global _dirty
    with _lock:
        _load()
        entry = dict(info)
        entry["_ts"] = time.time()
        if ttl != CACHE_TTL:
            entry["_ttl"] = ttl
        _cache[key] = entry
        _dirty = True


def flush():
    """Persist the cache to disk if it has been modified since the last flush.

    Call once at the end of each poll cycle rather than after every ``put()``.
    """
    global _dirty
    with _lock:
        if _dirty:
            _save()
            _dirty = False


def clear():
    """Clear the entire cache and persist immediately."""
    global _cache, _loaded, _dirty
    with _lock:
        _cache = {}
        _loaded = True
        _save()
        _dirty = False

"""
Central metadata cache for the lookup layer.

Stores route metadata (keyed by callsign) and aircraft metadata (keyed by
Mode S hex) in a single JSON file.  Live flight position data is **never**
cached here - it belongs to the flight observation pipeline.

File layout (unchanged from the historical routes_cache.json format so
existing on-disk caches remain valid):

  callsign keys  (e.g. "BAW123")
      plane, origin, destination, origin_name, origin_municipality,
      origin_country, destination_name, destination_municipality,
      destination_country, registration, airline_icao

  mode_s keys    (e.g. "400f5a")
      plane, registration, operator_icao, owner

  miss entries (either key type) carry ``"miss": True`` and a 1-hour TTL.

Both key types use a 24-hour TTL by default.  Pass ``ttl=`` to :func:`put`
to override per-entry (e.g. use CACHE_TTL_MISS for negative results).

Changes vs. the historical module:
- ``put()`` sets a *dirty* flag instead of writing to disk immediately;
  call :func:`flush` at the end of a processing cycle to persist.  This
  reduces SD-card writes on Raspberry Pi from one-per-entry to
  one-per-poll-cycle.
- Expired entries are not deleted during :func:`get` so :func:`get_stale`
  can still find them for the stale-fallback path; :func:`flush` purges
  entries older than CACHE_TTL_STALE (7 days).
"""

from __future__ import annotations

import json
import logging
import threading
import time

from setup.configuration import PLATFORM_DATA_DIR, ROOT_PATH, migrate_legacy_json

logger = logging.getLogger(__name__)

CACHE_TTL = 86400  # 24 hours - positive / aircraft entries
CACHE_TTL_MISS = 3600  # 1 hour   - negative / miss entries
CACHE_TTL_STALE = 604800  # 7 days  - stale fallback threshold
STALE_RECACHE_ADVANCE = 14400  # 4 hours - how far to advance _ts on stale re-cache
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


def get(key: str | None) -> dict | None:
    """Return cached info for *key* if it exists and is not expired.

    Returns a dict (internal ``_``-prefixed keys stripped) or ``None`` when
    the key is absent, expired, or *key* is ``None``.

    Expired entries are **not** deleted here so that :func:`get_stale` can
    still find them for the stale-fallback path.  Stale entries beyond the
    7-day :data:`CACHE_TTL_STALE` threshold are purged by :func:`_purge_stale`
    during :func:`flush`.
    """
    with _lock:
        if key is None:
            return None
        _load()
        entry = _cache.get(key)
        if entry is None:
            return None
        ttl = entry.get("_ttl", CACHE_TTL)
        if time.time() - entry.get("_ts", 0) > ttl:
            return None
        return {k: v for k, v in entry.items() if not k.startswith("_")}


def get_stale(key: str | None, max_age: int = CACHE_TTL_STALE) -> dict | None:
    """Return a **raw** expired entry for *key* if it's within *max_age*.

    Unlike :func:`get`, this returns entries that have passed their normal
    TTL but are still younger than *max_age* (default 7 days).  The returned
    dict includes internal ``_``-prefixed keys (notably ``_ts``) so the
    caller can advance the timestamp when re-caching.

    Miss entries (``miss=True``) are never returned - only positive data
    is eligible for stale fallback.

    Returns ``None`` when the key is absent, is a miss, or is older than
    *max_age*.
    """
    with _lock:
        if key is None:
            return None
        _load()
        entry = _cache.get(key)
        if entry is None:
            return None
        if entry.get("miss"):
            return None
        if time.time() - entry.get("_ts", 0) > max_age:
            return None
        return dict(entry)


def put(key: str | None, info: dict, ttl: int = CACHE_TTL, ts: float | None = None):
    """Store *info* under *key*.

    *ttl* overrides the default 24-hour TTL for this entry.  *ts* overrides
    the timestamp (defaults to ``time.time()``); used by the stale-fallback
    path to advance the timestamp by a partial amount rather than resetting
    to now.  The change is held in memory; call :func:`flush` to persist.
    """
    global _dirty
    with _lock:
        if key is None:
            return
        _load()
        entry = dict(info)
        entry["_ts"] = ts if ts is not None else time.time()
        if ttl != CACHE_TTL:
            entry["_ttl"] = ttl
        _cache[key] = entry
        _dirty = True


def _purge_stale():
    """Remove entries older than :data:`CACHE_TTL_STALE`.

    Called from :func:`flush` to prevent the cache growing unbounded when
    entries are preserved past their normal TTL for the stale-fallback path.
    Caller must hold *_lock*.
    """
    global _dirty
    now = time.time()
    stale_keys = [
        k for k, v in _cache.items() if now - v.get("_ts", 0) > CACHE_TTL_STALE
    ]
    for k in stale_keys:
        del _cache[k]
    if stale_keys:
        _dirty = True
        logger.debug("Purged %d stale cache entries (>7 days old)", len(stale_keys))


def flush():
    """Persist the cache to disk if it has been modified since the last flush.

    Also purges entries older than :data:`CACHE_TTL_STALE` (7 days) to
    prevent unbounded growth from expired entries retained for the
    stale-fallback path.  Call once at the end of each poll cycle rather
    than after every ``put()``.
    """
    global _dirty
    with _lock:
        _purge_stale()
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


def delete(keys) -> int:
    """Delete one or more entries from the cache and persist immediately.

    *keys* may be a single string or an iterable of strings.  Returns the
    number of entries actually removed.
    """
    global _dirty
    if isinstance(keys, str):
        keys = [keys]
    with _lock:
        _load()
        removed = 0
        for k in keys:
            if k in _cache:
                del _cache[k]
                removed += 1
        if removed:
            _dirty = True
            _save()
            _dirty = False
        return removed

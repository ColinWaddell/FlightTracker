"""
SQLite-backed metadata cache for the lookup layer.

Stores route metadata (keyed by callsign) and aircraft metadata (keyed by
Mode S hex) in a single SQLite database.  Live flight position data is
**never** cached here - it belongs to the flight observation pipeline.

Replaces the historical single-JSON-file cache (``routes_cache.json``):

- Rows are keyed by ``(kind, key)``; payloads are JSON blobs holding the
  public entry fields, so new ``RouteInfo``/``AircraftInfo`` fields never
  need a schema change.
- Every :func:`put` commits immediately (WAL, ``synchronous=NORMAL``).
  Row-level page writes are dramatically cheaper on a Raspberry Pi SD
  card than the whole-file rewrites this replaces, and the cache now
  survives crashes and settings-page restarts.  ``flush()`` therefore
  only handles housekeeping (stale purge) and is still called once per
  poll cycle.
- On first use, a legacy ``routes_cache.json`` is imported once into the
  database (timestamps preserved so TTL/stale semantics carry over) and
  renamed to ``routes_cache.json.imported`` as a rollback artifact.

Schema (``PRAGMA user_version = 1``)::

    cache(
        kind    TEXT,     -- 'route' | 'aircraft'
        key     TEXT,     -- callsign or lowercase mode-s hex
        ts      REAL,     -- epoch seconds
        ttl     INTEGER,  -- per-entry TTL (CACHE_TTL / CACHE_TTL_MISS)
        miss    INTEGER,  -- negative-entry flag
        payload TEXT,     -- JSON object of public fields
        PRIMARY KEY (kind, key)
    )

Semantics preserved from the JSON cache:

- ``get`` returns the public fields (never ``_``-prefixed internals).
  Miss entries come back as ``{"miss": True}`` so the route pipeline can
  recognise them; positive-but-empty entries (cached blank aircraft)
  come back as ``{}``, not ``None``.
- Expired entries return ``None`` from :func:`get` but remain in the
  database until the 7-day threshold so :func:`get_stale` can serve the
  stale-fallback path.  ``flush`` purges them.
- Miss entries are never eligible for stale fallback.

The database is opened lazily on first use - importing this module does
no I/O beyond the legacy JSON location step.  All access funnels through
a module lock and a single connection (``check_same_thread=False``), the
same serialisation model the JSON cache used; cross-process access (web
app vs. CLI) is handled by WAL + ``busy_timeout``.
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
import sqlite3
import threading
import time
from pathlib import Path

from setup.configuration import PLATFORM_DATA_DIR, ROOT_PATH, migrate_legacy_json

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants - values unchanged from the historical cache
# ---------------------------------------------------------------------------

CACHE_TTL = 86400  # 24 hours - positive / aircraft entries
CACHE_TTL_MISS = 3600  # 1 hour   - negative / miss entries
CACHE_TTL_STALE = 604800  # 7 days  - stale fallback threshold
STALE_RECACHE_ADVANCE = 14400  # 4 hours - how far to advance ts on stale re-cache

SCHEMA_VERSION = 1

# Logical namespaces.  Route entries are keyed by callsign, aircraft
# entries by lowercase mode-s hex; a shared keyspace only ever worked
# because the domains cannot practically collide - keep them explicit.
KIND_ROUTE = "route"
KIND_AIRCRAFT = "aircraft"

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    kind    TEXT    NOT NULL,
    key     TEXT    NOT NULL,
    ts      REAL    NOT NULL,
    ttl     INTEGER NOT NULL,
    miss    INTEGER NOT NULL DEFAULT 0,
    payload TEXT    NOT NULL DEFAULT '{}',
    PRIMARY KEY (kind, key)
)
"""

CACHE_INDEX = "CREATE INDEX IF NOT EXISTS idx_cache_ts ON cache (ts)"

# Database location (platform data dir, alongside config.json).
DB_PATH = PLATFORM_DATA_DIR / "cache.sqlite3"

# Legacy JSON cache.  The migrate_legacy_json call keeps the historical
# behaviour of rescuing a repo-root file into the platform data dir (with
# backup rotation) before the JSON->database import below looks for it.
LEGACY_JSON_PATH = migrate_legacy_json(
    ROOT_PATH / "routes_cache.json", PLATFORM_DATA_DIR / "routes_cache.json"
)

# Mode-s keys are normalised to lowercase hex at both entry points
# (lookups/enrichment.py, lookups/aircraft.py), callsigns never are, so
# this is a safe classifier when importing the flat legacy keyspace.
_MODE_S_KEY_RE = re.compile(r"[0-9a-f]{6}")

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


# ---------------------------------------------------------------------------
# Connection plumbing (private)
# ---------------------------------------------------------------------------


def _prepare(conn):
    """Ensure the schema exists and stamp/upgrade the schema version.

    Caller must hold *_lock* (only ever invoked from :func:`_connect`).
    """
    conn.execute(CACHE_SCHEMA)
    conn.execute(CACHE_INDEX)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    if version > SCHEMA_VERSION:
        # Cache data is reproducible - a future schema we don't understand
        # is simply rebuilt empty.
        logger.warning(
            "Cache schema v%d is newer than supported v%d - recreating cache",
            version,
            SCHEMA_VERSION,
        )
        conn.execute("DROP TABLE IF EXISTS cache")
        conn.execute(CACHE_SCHEMA)
        conn.execute(CACHE_INDEX)
    _import_legacy_json(conn)
    if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _import_legacy_json(conn):
    """Port legacy ``routes_cache.json`` entries into the database.

    One transaction covering the inserts *and* the version stamp, so a
    crash cannot leave imported rows with an unstamped schema.  On success
    the source file is renamed to ``*.imported`` (kept, never deleted, as
    a rollback artifact).  An unreadable file is logged and left in place -
    the same start-fresh behaviour the JSON cache had on corruption.
    """
    if not LEGACY_JSON_PATH.exists():
        return 0
    try:
        raw = json.loads(LEGACY_JSON_PATH.read_text())
    except (OSError, ValueError) as exc:
        logger.warning(
            "Legacy route cache %s unreadable (%s) - starting fresh",
            LEGACY_JSON_PATH,
            exc,
        )
        return 0
    if not isinstance(raw, dict):
        logger.warning(
            "Legacy route cache %s not an object - ignored", LEGACY_JSON_PATH
        )
        return 0

    rows = []
    now = time.time()
    for key, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        ts = entry.get("_ts")
        if not isinstance(ts, (int, float)) or ts <= 0:
            ts = now
        ttl = entry.get("_ttl")
        if not isinstance(ttl, (int, float)) or ttl <= 0:
            ttl = CACHE_TTL
        miss = 1 if entry.get("miss") else 0
        payload = {
            k: v for k, v in entry.items() if not k.startswith("_") and k != "miss"
        }
        kind = KIND_AIRCRAFT if _MODE_S_KEY_RE.fullmatch(key) else KIND_ROUTE
        rows.append((kind, str(key), float(ts), int(ttl), miss, json.dumps(payload)))

    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO cache (kind, key, ts, ttl, miss, payload)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    _retire_legacy_json()
    logger.info("Imported %d cache entries from %s", len(rows), LEGACY_JSON_PATH.name)
    return len(rows)


def _retire_legacy_json():
    """Rename the imported legacy JSON beside itself as a rollback artifact."""
    target = LEGACY_JSON_PATH.with_name(LEGACY_JSON_PATH.name + ".imported")
    try:
        LEGACY_JSON_PATH.rename(target)
    except OSError as exc:
        # Harmless: once the database is stamped, a leftover JSON file is
        # simply ignored.
        logger.warning("Could not retire legacy cache file: %s", exc)


def _move_corrupt_db_aside():
    """Move an unusable database (and WAL sidecars) out of the way."""
    for suffix in ("", "-wal", "-shm"):
        path = Path(str(DB_PATH) + suffix)
        if not path.exists():
            continue
        aside = Path(f"{path}.corrupt-{int(time.time())}")
        try:
            path.rename(aside)
            logger.warning("Moved unusable cache file aside: %s", aside)
        except OSError:
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("Cache file %s unremovable: %s", path, exc)


def _open_and_prepare(path):
    """Open *path* (or in-memory when None) with schema ready; None on failure."""
    conn = None
    try:
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            path or ":memory:",
            timeout=5.0,
            check_same_thread=False,
            isolation_level=None,  # autocommit; migration uses explicit BEGIN
        )
        conn.execute("PRAGMA busy_timeout = 5000")
        if path is not None:
            conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
        _prepare(conn)
        return conn
    except (sqlite3.Error, OSError) as exc:
        logger.warning("Lookup cache open failed for %s: %s", path or ":memory:", exc)
        if conn is not None:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
        return None


def _connect():
    """Return the cached connection, opening/migrating on first use.

    Caller must hold *_lock*.
    """
    global _conn
    if _conn is not None:
        return _conn

    conn = _open_and_prepare(DB_PATH)
    if conn is None:
        # Unopenable or corrupt.  Clear the way and try once more before
        # giving up on persistence entirely.
        _move_corrupt_db_aside()
        conn = _open_and_prepare(DB_PATH)
    if conn is None:
        logger.error(
            "Lookup cache unusable at %s - running with an in-memory cache"
            " (data will not persist)",
            DB_PATH,
        )
        conn = _open_and_prepare(None)  # sqlite3 in-memory cannot realistically fail

    _conn = conn
    return conn


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get(key, kind) -> dict | None:
    """Return cached public fields for *key*, or ``None``.

    Miss entries come back as ``{"miss": True}`` so the route pipeline can
    recognise them; expired entries return ``None`` but remain in the
    database for the :func:`get_stale` fallback.
    """
    if key is None:
        return None
    with _lock:
        row = (
            _connect()
            .execute(
                "SELECT ts, ttl, miss, payload FROM cache WHERE kind = ? AND key = ?",
                (kind, key),
            )
            .fetchone()
        )
    if row is None:
        return None
    ts, ttl, miss, payload = row
    if time.time() - ts > ttl:
        return None
    entry = json.loads(payload) if payload else {}
    if miss:
        entry["miss"] = True
    return entry


def get_stale(key, kind, max_age: int = CACHE_TTL_STALE) -> dict | None:
    """Return an entry for *key* within *max_age* even if past its TTL.

    Unlike :func:`get` this includes freshly-written entries (the stale
    path cares about ``_ts`` arithmetic, not freshness).  The returned
    dict carries ``_ts`` so callers can re-cache with an advanced
    timestamp.  Miss entries are never eligible.
    """
    if key is None:
        return None
    with _lock:
        row = (
            _connect()
            .execute(
                "SELECT ts, miss, payload FROM cache WHERE kind = ? AND key = ?",
                (kind, key),
            )
            .fetchone()
        )
    if row is None:
        return None
    ts, miss, payload = row
    if miss or time.time() - ts > max_age:
        return None
    entry = json.loads(payload) if payload else {}
    entry["_ts"] = ts
    return entry


def put(
    key, info: dict, ttl: int = CACHE_TTL, ts: float | None = None, *, kind
) -> None:
    """Store *info* under (*kind*, *key*) - committed immediately.

    ``ttl`` overrides the per-entry TTL (``CACHE_TTL_MISS`` for negative
    entries); ``ts`` overrides the timestamp, used by the stale-fallback
    path to advance an entry rather than reset it to now.
    """
    if key is None:
        return
    stored_ts = time.time() if ts is None else float(ts)
    payload = {k: v for k, v in info.items() if not k.startswith("_") and k != "miss"}
    with _lock:
        _connect().execute(
            "INSERT INTO cache (kind, key, ts, ttl, miss, payload)"
            " VALUES (?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(kind, key) DO UPDATE SET"
            " ts = excluded.ts, ttl = excluded.ttl, miss = excluded.miss,"
            " payload = excluded.payload",
            (
                kind,
                key,
                stored_ts,
                int(ttl),
                1 if info.get("miss") else 0,
                json.dumps(payload),
            ),
        )


def delete(keys, kind) -> int:
    """Delete entries for *keys* under *kind*; returns the number removed.

    *keys* may be a single string or an iterable.  Deletion is immediate.
    """
    if isinstance(keys, str):
        keys = [keys]
    keys = list(keys)
    if not keys:
        return 0
    placeholders = ", ".join("?" for _ in keys)
    with _lock:
        cur = _connect().execute(
            f"DELETE FROM cache WHERE kind = ? AND key IN ({placeholders})",
            (kind, *keys),
        )
        return cur.rowcount


def clear():
    """Remove every cached entry (all kinds) immediately."""
    with _lock:
        _connect().execute("DELETE FROM cache")


def flush():
    """Housekeeping hook - purge entries past the stale threshold.

    Called once per poll cycle from the overhead facade.  Puts commit
    immediately these days, so there is nothing to persist here.
    """
    with _lock:
        _connect().execute(
            "DELETE FROM cache WHERE ts < ?", (time.time() - CACHE_TTL_STALE,)
        )


def debug_entries(kind=None) -> list[dict]:
    """Dump rows for inspection (web /cached-data page).

    Returns a list of dicts: ``kind``, ``key``, ``ts``, ``ttl``, ``miss``
    and ``entry`` (public fields, miss flag re-injected).  Expired flags
    are left to the caller (they need the display-side "now").
    """
    query = "SELECT kind, key, ts, ttl, miss, payload FROM cache"
    params: tuple = ()
    if kind is not None:
        query += " WHERE kind = ?"
        params = (kind,)
    query += " ORDER BY kind, key"
    with _lock:
        rows = _connect().execute(query, params).fetchall()
    results = []
    for row_kind, key, ts, ttl, miss, payload in rows:
        entry = json.loads(payload) if payload else {}
        if miss:
            entry["miss"] = True
        results.append(
            {
                "kind": row_kind,
                "key": key,
                "ts": ts,
                "ttl": ttl,
                "miss": bool(miss),
                "entry": entry,
            }
        )
    return results

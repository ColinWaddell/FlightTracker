"""
Provider usage tally for the lookup layer.

Counts, per UTC day:

- **Provider tallies** - how often each provider was used for each lookup
  kind, and how often it had nothing:

  | kind       | tallies                                                      |
  |------------|--------------------------------------------------------------|
  | `flights`  | `api_call` per attempt; `aircraft` = sum of observations      |
  |            | actually returned (15 aircraft in the feed bumps +15)         |
  | `routes`   | `attempt` per invocation; `no_result` when the provider       |
  | `aircraft` | answered NOT_FOUND                                            |

  Failures (UNAVAILABLE / crash) record the attempt but never the negative
  outcome - a downed provider is not a "no result", it is a provider that
  never answered.  Skipped providers (unconfigured, quarantined) are not
  counted at all.

- **Cache attempts** for `routes` and `aircraft` - `hit` (including blank
  cached aircraft and negative miss-entries, which answer from cache) or
  `miss` (nothing cached, providers had to run).  `flights` is never
  cached.  Stale fallbacks are deliberately not recorded.

Nothing is written to disk per event: counters live in module memory and
are flushed to SQLite every :data:`FLUSH_EVERY_S`, piggybacking on the
poll cycle (:func:`flush_if_due` from the overhead facade), with a forced
:func:`flush` at interpreter exit and before the settings-page restart.
A crash loses at most one flush interval of counts.

Storage is its own database - `PLATFORM_DATA_DIR / "usage.sqlite3"` - so
cache-clears and cache schema changes never touch usage history (and a
corrupt stats file cannot take out the live cache, or vice versa).

Read your writes: :func:`summary` force-flushes pending counters before
querying, so the web page and JSON API always reflect the current data.
"""

from __future__ import annotations

import atexit
import contextlib
import logging
import sqlite3
import threading
import time

from utilities.lookups import _sqlite
from setup.configuration import PLATFORM_DATA_DIR

logger = logging.getLogger(__name__)

FLUSH_EVERY_S = 60.0  # debounce window for batched writes
SCHEMA_VERSION = 1

# Lookup kinds
KIND_FLIGHTS = "flights"
KIND_ROUTES = "routes"
KIND_AIRCRAFT = "aircraft"

# Outcomes
OUTCOME_ATTEMPT = "attempt"  # routes/aircraft: provider was invoked
OUTCOME_NO_RESULT = "no_result"  # routes/aircraft: answered NOT_FOUND
OUTCOME_API_CALL = "api_call"  # flights: provider was invoked
OUTCOME_AIRCRAFT = "aircraft"  # flights: sum of aircraft returned (value, not events)
OUTCOME_HIT = "hit"  # cache answered the lookup
OUTCOME_MISS = "miss"  # nothing cached, providers had to run

PROVIDER_UPSERT = (
    "INSERT INTO provider_hits (day, kind, provider, outcome, n)"
    " VALUES (?, ?, ?, ?, ?)"
    " ON CONFLICT(day, kind, provider, outcome) DO UPDATE SET n = n + excluded.n"
)

CACHE_UPSERT = (
    "INSERT INTO cache_events (day, kind, outcome, n)"
    " VALUES (?, ?, ?, ?)"
    " ON CONFLICT(day, kind, outcome) DO UPDATE SET n = n + 1"
)

PROVIDER_SCHEMA = """
CREATE TABLE IF NOT EXISTS provider_hits (
    day      TEXT    NOT NULL,
    kind     TEXT    NOT NULL,
    provider TEXT    NOT NULL,
    outcome  TEXT    NOT NULL,
    n        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, kind, provider, outcome)
)
"""

CACHE_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache_events (
    day     TEXT    NOT NULL,
    kind    TEXT    NOT NULL,
    outcome TEXT    NOT NULL,
    n       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (day, kind, outcome)
)
"""

DB_PATH = PLATFORM_DATA_DIR / "usage.sqlite3"

# outcome -> summary key, per kind (see :func:`summary`)
_SUMMARY_KEYS = {
    (KIND_ROUTES, OUTCOME_ATTEMPT): "attempts",
    (KIND_ROUTES, OUTCOME_NO_RESULT): "no_results",
    (KIND_AIRCRAFT, OUTCOME_ATTEMPT): "attempts",
    (KIND_AIRCRAFT, OUTCOME_NO_RESULT): "no_results",
    (KIND_FLIGHTS, OUTCOME_API_CALL): "api_calls",
    (KIND_FLIGHTS, OUTCOME_AIRCRAFT): "aircraft",
}
_DEFAULT_KEYS = {
    KIND_FLIGHTS: ("api_calls", "aircraft"),
    KIND_ROUTES: ("attempts", "no_results"),
    KIND_AIRCRAFT: ("attempts", "no_results"),
}

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
_providers_dirty: dict[tuple[str, str, str, str], int] = {}
_cache_dirty: dict[tuple[str, str, str], int] = {}
_last_flush: float = 0.0


def _collection_enabled() -> bool:
    """Latest provider-usage-logging toggle (settings save updates it live)."""
    from setup.configuration import Config

    try:
        return bool(Config.instance().provider_usage_logging)
    except Exception:  # never let a config hiccup break a lookup
        return True


def _today() -> str:
    """Current UTC day, the tally's time bucket."""
    return time.strftime("%Y-%m-%d", time.gmtime())


def _now() -> float:
    """Debounce clock (monotonic)."""
    return time.monotonic()


# ---------------------------------------------------------------------------
# Connection plumbing (private) - same model as utilities/lookups/cache.py
# ---------------------------------------------------------------------------


def _prepare(conn):
    """Ensure the tally schema exists and stamp the schema version.

    Caller must hold *_lock* (only ever invoked from :func:`_connect`).
    """
    conn.execute(PROVIDER_SCHEMA)
    conn.execute(CACHE_SCHEMA)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version == SCHEMA_VERSION:
        return
    if version > SCHEMA_VERSION:
        logger.warning(
            "Usage schema v%d is newer than supported v%d - recreating tallies",
            version,
            SCHEMA_VERSION,
        )
        conn.execute("DROP TABLE IF EXISTS provider_hits")
        conn.execute("DROP TABLE IF EXISTS cache_events")
        conn.execute(PROVIDER_SCHEMA)
        conn.execute(CACHE_SCHEMA)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


def _open_and_prepare(path):
    """Open *path* (or in-memory when None) with schema ready; None on failure."""
    conn = None
    try:
        conn = _sqlite.open_db(path)
        _prepare(conn)
        return conn
    except (sqlite3.Error, OSError) as exc:
        logger.warning("Usage db open failed for %s: %s", path or ":memory:", exc)
        if conn is not None:
            with contextlib.suppress(sqlite3.Error):
                conn.close()
        return None


def _connect():
    """Return the cached connection, opening the schema on first use.

    Caller must hold *_lock*.
    """
    global _conn
    if _conn is not None:
        return _conn

    conn = _open_and_prepare(DB_PATH)
    if conn is None:
        # Unopenable or corrupt - clear the way and try once more before
        # giving up on persistence entirely.
        _sqlite.move_db_aside(DB_PATH)
        conn = _open_and_prepare(DB_PATH)
    if conn is None:
        logger.error("Usage db unusable at %s - tallies will not persist", DB_PATH)
        conn = _open_and_prepare(None)  # sqlite3 in-memory cannot realistically fail

    _conn = conn
    return conn


# ---------------------------------------------------------------------------
# Recording (in-memory, never touches the disk)
# ---------------------------------------------------------------------------


def record(kind: str, provider: str, outcome: str, n: int = 1) -> None:
    """Tally a provider event (never raises, never touches the disk).

    ``n`` accumulates quantities as well as events - the flights
    `aircraft` tally adds the number of observations returned, so a feed
    of 15 aircraft records ``+15``.  Tallying can be switched off in the
    settings (provider_usage_logging); switching off stops new records
    but leaves recorded history in place.
    """
    if n <= 0 or not _collection_enabled():
        return
    with _lock:
        key = (_today(), kind, provider, outcome)
        _providers_dirty[key] = _providers_dirty.get(key, 0) + n


def record_cache(kind: str, outcome: str) -> None:
    """Tally a cache attempt (`hit` or `miss`) for a lookup."""
    if not _collection_enabled():
        return
    with _lock:
        key = (_today(), kind, outcome)
        _cache_dirty[key] = _cache_dirty.get(key, 0) + 1


# ---------------------------------------------------------------------------
# Flushing
# ---------------------------------------------------------------------------


def flush_if_due() -> None:
    """Write pending tallies if the debounce window has elapsed.

    Called once per poll cycle from the overhead facade.  Never raises.
    """
    with _lock:
        if not _providers_dirty and not _cache_dirty:
            return
        now = _now()
        if now - _last_flush < FLUSH_EVERY_S:
            return
        _flush_pending_locked(now)


def clear() -> None:
    """Erase all recorded provider usage tallies (pending + history)."""
    with _lock:
        _providers_dirty.clear()
        _cache_dirty.clear()
        conn = _connect()
        conn.execute("DELETE FROM provider_hits")
        conn.execute("DELETE FROM cache_events")


def flush() -> None:
    """Write all pending tallies now (shutdown / execv / explicit).

    Never raises: on a write failure the counters stay queued for the
    next flush and the totals survive.
    """
    with _lock:
        _flush_pending_locked(_now())


def _flush_pending_locked(now: float) -> None:
    """Write in-memory tallies to the database.  Caller must hold *_lock*."""
    global _last_flush
    if not _providers_dirty and not _cache_dirty:
        return
    try:
        conn = _connect()
        conn.execute("BEGIN IMMEDIATE")
        try:
            if _providers_dirty:
                conn.executemany(
                    PROVIDER_UPSERT,
                    [
                        (day, kind, provider, outcome, n)
                        for (
                            day,
                            kind,
                            provider,
                            outcome,
                        ), n in _providers_dirty.items()
                    ],
                )
            if _cache_dirty:
                conn.executemany(
                    CACHE_UPSERT,
                    [
                        (day, kind, outcome, n)
                        for (day, kind, outcome), n in _cache_dirty.items()
                    ],
                )
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        _providers_dirty.clear()
        _cache_dirty.clear()
        _last_flush = now
    except (sqlite3.Error, OSError) as exc:
        # Counters stay queued - the next flush retries them.
        logger.warning("Usage flush failed (kept in memory): %s", exc)


def _flush_at_exit():
    """Interpreter-exit hook - best effort, silence on failure."""
    # Never disturb exit: swallow everything.
    with contextlib.suppress(Exception):
        flush()


atexit.register(_flush_at_exit)


# ---------------------------------------------------------------------------
# Readout
# ---------------------------------------------------------------------------


def summary(start: str | None = None, end: str | None = None) -> dict:
    """Aggregate tallies between *start*/*end* (inclusive) or over all history.

    Returns the total (not day-by-day) shape consumed by the web page and
    JSON API.  Pending in-memory tallies are flushed first so the result
    always includes the current data.
    """
    flush()
    clauses = []
    params: list = []
    if start is not None:
        clauses.append("day >= ?")
        params.append(start)
    if end is not None:
        clauses.append("day <= ?")
        params.append(end)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""

    with _lock:
        provider_rows = (
            _connect()
            .execute(
                "SELECT kind, provider, outcome, SUM(n) FROM provider_hits"
                f"{where} GROUP BY kind, provider, outcome",
                params,
            )
            .fetchall()
        )
        cache_rows = (
            _connect()
            .execute(
                "SELECT kind, outcome, SUM(n) FROM cache_events"
                f"{where} GROUP BY kind, outcome",
                params,
            )
            .fetchall()
        )

    providers: dict[str, dict[str, dict[str, int]]] = {
        KIND_FLIGHTS: {},
        KIND_ROUTES: {},
        KIND_AIRCRAFT: {},
    }
    for kind, provider, outcome, total in provider_rows:
        key = _SUMMARY_KEYS.get((kind, outcome), outcome)
        providers.setdefault(kind, {}).setdefault(provider, {})[key] = total
    for kind, provider_map in providers.items():
        defaults = _DEFAULT_KEYS.get(kind, ())
        for bucket in provider_map.values():
            for key in defaults:
                bucket.setdefault(key, 0)

    cache: dict[str, dict[str, int]] = {
        KIND_ROUTES: {"hits": 0, "misses": 0},
        KIND_AIRCRAFT: {"hits": 0, "misses": 0},
    }
    for kind, outcome, total in cache_rows:
        key = "hits" if outcome == OUTCOME_HIT else "misses"
        cache.setdefault(kind, {})[key] = total

    return {
        "range": {"start": start, "end": end},
        "cache": cache,
        "providers": providers,
    }

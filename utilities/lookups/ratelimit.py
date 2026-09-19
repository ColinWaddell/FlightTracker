"""
Per-provider API call limiting for the three lookup pipelines.

A small write-through counter store, deliberately independent of the
provider-usage tallies (``usage.sqlite3``): the tallies are toggle-gated
and debounced, while the limiter must count every call the moment it is
made regardless of that toggle, and a corrupt tally file must never be
able to take the limiter - or the lookups - down with it.

Shape:

* One global mode from the central configuration -
  :attr:`Config.api_limit_mode`: ``"none"`` (limiting off - the default),
  ``"daily"`` or ``"monthly"``.
* Per-provider opt-in and limits ride the provider descriptors via
  :func:`utilities.lookups.config.rate_limit_fields`:
  ``api_limiting_enabled`` (bool, default False) and ``api_limit``
  (int, default 500; ``<= 0`` means unlimited).
* :func:`gate` is the single entry point, used by the three lookup
  pipelines (flights / routes / aircraft).  One gate = one API call,
  per provider across all capabilities (fr24api's routes+aircraft pair
  dedups to one HTTP call but counts as two - conservative, and
  accepted).  Over-limit callers skip the provider exactly like a
  quarantine (fall through, no quarantine recorded, never cached as a
  miss); the limiter logs a single warning per provider per period.
* Startup probes (``ping`` / ``startup_check``) never pass through the
  pipelines and so never consume quota.
* The store fails open: an unusable database allows calls rather than
  taking the lookups down.

Storage is its own database - ``PLATFORM_DATA_DIR / "ratelimit.sqlite3"``.
Every accepted call bumps its ``(provider, period)`` row immediately
(write-through; there is no debounce) so the counter survives a crash
and the status page always reads current data.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
import threading
import time

from setup.configuration import PLATFORM_DATA_DIR
from utilities.lookups import _sqlite
from utilities.lookups.config import DEFAULT_API_LIMIT

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1

# Global modes (Config.api_limit_mode)
MODE_NONE = "none"
MODE_DAILY = "daily"
MODE_MONTHLY = "monthly"
_MODES = (MODE_NONE, MODE_DAILY, MODE_MONTHLY)

SCHEMA = """
CREATE TABLE IF NOT EXISTS calls (
    provider TEXT    NOT NULL,
    period   TEXT    NOT NULL,
    n        INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (provider, period)
)
"""

DB_PATH = PLATFORM_DATA_DIR / "ratelimit.sqlite3"

# Operational state, not history: keep the current bucket plus the two
# before it (per bucket format) and prune the rest when the database
# opens.  Daily rows are "YYYY-MM-DD" (10 chars), monthly "YYYY-MM".
_PRUNE_KEEP_BUCKETS = 2

_UPSERT = (
    "INSERT INTO calls (provider, period, n) VALUES (?, ?, 1)"
    " ON CONFLICT(provider, period) DO UPDATE SET n = n + 1"
)

_lock = threading.Lock()
_conn: sqlite3.Connection | None = None
# (provider, period) pairs already warned about this period.
_warned: set[tuple[str, str]] = set()


# ---------------------------------------------------------------------------
# Configuration plumbing (read live, never raise)
# ---------------------------------------------------------------------------


def _config():
    """The process-wide Config instance (read lazily), or None on failure."""
    from setup.configuration import Config

    return Config.instance()


def _mode() -> str:
    """Latest global limiting mode; "none" (fail-open) when unreadable."""
    try:
        mode = str(_config().api_limit_mode).lower()
    except Exception:  # never let a config hiccup block a lookup
        return MODE_NONE
    return mode if mode in _MODES else MODE_NONE


def _provider_limit(provider: str) -> tuple[bool, int]:
    """``(enabled, limit)`` for *provider* from its descriptor settings.

    Defaults match the descriptor (limiting off, 500 calls); anything
    unreadable counts as disabled.
    """
    try:
        settings = _config().provider_settings(provider)
    except Exception:  # never let a config hiccup block a lookup
        return False, 0
    enabled = bool(settings.get("api_limiting_enabled", False))
    try:
        limit = int(settings.get("api_limit", DEFAULT_API_LIMIT) or 0)
    except (TypeError, ValueError):
        limit = DEFAULT_API_LIMIT
    return enabled, limit


def _period(mode: str, now: float | None = None) -> str:
    """The current UTC bucket for *mode* ("YYYY-MM-DD" / "YYYY-MM")."""
    if now is None:
        now = time.time()
    fmt = "%Y-%m-%d" if mode == MODE_DAILY else "%Y-%m"
    return time.strftime(fmt, time.gmtime(now))


# ---------------------------------------------------------------------------
# Connection plumbing - same model as utilities/lookups/usage.py
# ---------------------------------------------------------------------------


def _prepare(conn):
    """Ensure the schema exists, stamp the version and prune stale buckets.

    Caller must hold *_lock* (only ever invoked from :func:`_connect`).
    """
    conn.execute(SCHEMA)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version > SCHEMA_VERSION:
        logger.warning(
            "Rate-limit schema v%d is newer than supported v%d - recreating",
            version,
            SCHEMA_VERSION,
        )
        conn.execute("DROP TABLE IF EXISTS calls")
        conn.execute(SCHEMA)
    elif version != SCHEMA_VERSION:
        conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    _prune(conn)


def _prune(conn):
    """Drop stale buckets (current period + the two before it are kept).

    Period strings sort lexicographically within one format, so a plain
    string compare against the oldest kept bucket does the job - as long
    as the two formats are pruned separately (a monthly "YYYY-MM" is a
    prefix of a daily "YYYY-MM-DD" and would compare "older" than any
    day inside it).
    """
    month = _period(MODE_MONTHLY)
    cutoff_day = time.strftime(
        "%Y-%m-%d", time.gmtime(time.time() - _PRUNE_KEEP_BUCKETS * 86400)
    )
    year, mon = int(month[:4]), int(month[5:7])
    back = mon - _PRUNE_KEEP_BUCKETS
    while back <= 0:
        back += 12
        year -= 1
    cutoff_month = f"{year:04d}-{back:02d}"
    # Daily rows are exactly 10 chars ("YYYY-MM-DD"); monthly are 7.
    with contextlib.suppress(sqlite3.Error):
        conn.execute(
            "DELETE FROM calls WHERE length(period) = 10 AND period < ?",
            (cutoff_day,),
        )
        conn.execute(
            "DELETE FROM calls WHERE length(period) = 7 AND period < ?",
            (cutoff_month,),
        )


def _open_and_prepare(path):
    """Open *path* (or in-memory when None) with schema ready; None on failure."""
    conn = None
    try:
        conn = _sqlite.open_db(path)
        _prepare(conn)
        return conn
    except (sqlite3.Error, OSError) as exc:
        logger.warning("Rate-limit db open failed for %s: %s", path or ":memory:", exc)
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
        # Unopenable or corrupt - clear the way (moved aside, never
        # destroyed) and try once more before giving up on persistence.
        _sqlite.move_db_aside(DB_PATH)
        conn = _open_and_prepare(DB_PATH)
    if conn is None:
        logger.error(
            "Rate-limit db unusable at %s - counters will not persist", DB_PATH
        )
        conn = _open_and_prepare(None)  # sqlite3 in-memory cannot realistically fail

    _conn = conn
    return conn


# ---------------------------------------------------------------------------
# Counting (write-through: one upsert per accepted call)
# ---------------------------------------------------------------------------


def _bump(provider: str, period: str) -> int:
    """Add one call for *provider* in *period*; return the new total.

    Caller must hold *_lock*.  Raises sqlite3.Error/OSError on failure -
    :func:`gate` turns that into fail-open.
    """
    conn = _connect()
    conn.execute(_UPSERT, (provider, period))
    row = conn.execute(
        "SELECT n FROM calls WHERE provider = ? AND period = ?", (provider, period)
    ).fetchone()
    return int(row[0]) if row else 1


def _used(provider: str, period: str) -> int:
    """Calls already counted for *provider* in *period* (0 when unknown)."""
    with _lock:
        try:
            row = (
                _connect()
                .execute(
                    "SELECT n FROM calls WHERE provider = ? AND period = ?",
                    (provider, period),
                )
                .fetchone()
            )
        except (sqlite3.Error, OSError):
            return 0
        return int(row[0]) if row else 0


def _warn_once(provider: str, mode: str, period: str, used: int, limit: int) -> None:
    """Log the provider's over-limit state once per period."""
    key = (provider, period)
    with _lock:
        if key in _warned:
            return
        _warned.add(key)
    logger.warning(
        "API limit reached: %s has used %d of %d allowed calls this %s period "
        "(%s) - its lookups are skipped until the period rolls over",
        provider,
        used,
        limit,
        mode,
        period,
    )


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def gate(provider: str) -> bool:
    """Record one API call for *provider* and answer whether it may run.

    One gate = one call, per provider across all capabilities.  True
    (call counted) when the provider may proceed; False when limiting is
    active and the provider is at/over its limit - callers then skip it
    exactly like a quarantine (no quarantine recorded, never cached as
    a miss).

    Never counts and never blocks when the global mode is "none" or the
    provider has not opted in (``api_limiting_enabled``).  A provider
    whose ``api_limit`` is ``<= 0`` is unlimited but still counted, so
    the status page can show usage.  Fails open if the counter store is
    unusable - a broken limiter must not take the lookups down.
    """
    mode = _mode()
    if mode == MODE_NONE:
        return True
    enabled, limit = _provider_limit(provider)
    if not enabled:
        return True
    period = _period(mode)
    try:
        used = _bump(provider, period)
    except (sqlite3.Error, OSError) as exc:
        logger.warning("Rate-limit store unusable - allowing %s: %s", provider, exc)
        return True
    if limit <= 0:
        return True
    if used <= limit:
        return True
    _warn_once(provider, mode, period, used, limit)
    return False


def status() -> dict:
    """Per-provider quota snapshot for the status page (never raises).

    Returns ``{"mode": ..., "period": ..., "providers": {pid: {...}}}``
    with one entry per registry provider:
    ``{"enabled": bool, "limit": int, "used": int}``.  ``used`` is 0 for
    providers that are not being counted (limiting off or not opted in).
    """
    mode = _mode()
    period = _period(mode) if mode != MODE_NONE else ""
    providers: dict[str, dict] = {}
    try:
        from utilities.lookups.registry import PROVIDERS

        pids = list(PROVIDERS)
    except Exception:  # registry trouble must not break the status page
        pids = []
    for pid in pids:
        enabled, limit = _provider_limit(pid)
        used = _used(pid, period) if (mode != MODE_NONE and enabled) else 0
        providers[pid] = {"enabled": enabled, "limit": limit, "used": used}
    return {"mode": mode, "period": period, "providers": providers}


def clear() -> None:
    """Erase every counted call (settings reset / tests).  Never raises."""
    with _lock:
        _warned.clear()
        try:
            _connect().execute("DELETE FROM calls")
        except (sqlite3.Error, OSError) as exc:
            logger.warning("Rate-limit clear failed: %s", exc)


def _reset_for_tests() -> None:
    """Drop the cached connection and warning state (test isolation)."""
    global _conn
    with _lock:
        if _conn is not None:
            with contextlib.suppress(sqlite3.Error):
                _conn.close()
        _conn = None
        _warned.clear()

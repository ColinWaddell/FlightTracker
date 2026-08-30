"""
Shared SQLite plumbing for lookup-layer databases (cache + usage tallies).

One place for the house pragmas and the corrupt-file recovery dance so the
two databases stay consistent with each other.  Neither database opens a
connection at import time - callers decide their own lazy-connection model.
"""

from __future__ import annotations

import logging
import sqlite3
import time
from pathlib import Path

logger = logging.getLogger(__name__)


def open_db(path: Path | None) -> sqlite3.Connection:
    """Open a connection with the house settings (caller prepares the schema).

    ``path=None`` opens an in-memory database (the fallback mode).  The
    connection is in autocommit mode (``isolation_level=None``) so every
    single-statement operation is atomic on its own; callers needing
    multi-statement transactions use explicit BEGIN/COMMIT.
    """
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(
        path or ":memory:",
        timeout=5.0,
        check_same_thread=False,
        isolation_level=None,  # autocommit; migrations use explicit BEGIN
    )
    conn.execute("PRAGMA busy_timeout = 5000")
    if path is not None:
        conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def move_db_aside(path: Path) -> None:
    """Move an unusable database (and WAL sidecars) out of the way.

    Used when a database file cannot be opened - it is renamed beside
    itself with a ``.corrupt-<timestamp>`` suffix rather than deleted, so
    nothing is silently destroyed.
    """
    for suffix in ("", "-wal", "-shm"):
        sidecar = Path(f"{path}{suffix}")
        if not sidecar.exists():
            continue
        aside = Path(f"{sidecar}.corrupt-{int(time.time())}")
        try:
            sidecar.rename(aside)
            logger.warning("Moved unusable database file aside: %s", aside)
        except OSError:
            try:
                sidecar.unlink()
            except OSError as exc:
                logger.warning("Database file %s unremovable: %s", sidecar, exc)

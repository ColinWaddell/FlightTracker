"""
In-memory log buffer for the FlightTracker web diagnostic panel.

Uses Python's stdlib ``logging`` module with a single custom handler that
keeps the most recent ``BUFFER_SIZE`` records in a ``collections.deque``.
No disk persistence, no external dependencies.  Restart clears the buffer.

Usage:
    from setup.logging import setup_logging, get_buffer

    setup_logging()                       # call once at startup
    logger = logging.getLogger(__name__)  # in any module
    logger.info("...")

    get_buffer().records()                # from the Flask /logs route
"""

from __future__ import annotations

import collections
import logging
from typing import Any

from setup.configuration import Config

# Hard ceiling on the number of records kept in memory.  Old entries drop
# off the front once the deque is full, so memory usage is bounded by
# BUFFER_SIZE * ~record_size regardless of uptime.
BUFFER_SIZE = 200

# Levels exposed in the settings dropdown, in increasing severity.
LEVEL_NAMES = ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")


class MemoryLogHandler(logging.Handler):
    """Bounded in-memory handler.  Stores small dicts, not formatted strings."""

    def __init__(self, capacity: int = BUFFER_SIZE):
        super().__init__()
        self._records: collections.deque[dict[str, Any]] = collections.deque(
            maxlen=capacity
        )

    def emit(self, record: logging.LogRecord) -> None:
        # logging swallows exceptions raised in emit() after calling
        # handleError(), so we keep this minimal and defensive.
        self._records.append(
            {
                "time": record.created,
                "level": record.levelname,
                "source": record.name,
                "message": record.getMessage(),
            }
        )

    def records(self) -> list[dict[str, Any]]:
        """Return a snapshot of the buffer, newest-first."""
        return list(reversed(self._records))


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_buffer: MemoryLogHandler | None = None


def setup_logging() -> None:
    """Configure the root logger with the in-memory handler.

    Reads the configured level from ``Config`` and applies it to both the
    root logger and the handler.  Safe to call once at startup; subsequent
    calls replace the existing buffer.
    """
    global _buffer

    level_name = Config.instance().log_level
    level = logging.getLevelName(level_name)

    root = logging.getLogger()
    root.setLevel(level)

    # Drop any previous MemoryLogHandler so re-setup doesn't double-log.
    for h in list(root.handlers):
        if isinstance(h, MemoryLogHandler):
            root.removeHandler(h)

    _buffer = MemoryLogHandler(BUFFER_SIZE)
    _buffer.setLevel(level)
    root.addHandler(_buffer)


def get_buffer() -> MemoryLogHandler:
    """Return the active in-memory handler.

    Lazily calls ``setup_logging()`` if it hasn't been called yet, so
    importing modules can't accidentally log into the void.
    """
    if _buffer is None:
        setup_logging()
    assert _buffer is not None
    return _buffer

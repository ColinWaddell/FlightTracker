"""
tar1090 provider package.

Capabilities: flights (live positions from a local receiver).
"""

from __future__ import annotations

from lookups.providers.tar1090.config import PROVIDER  # noqa: F401
from lookups.providers.tar1090.flights import FlightProvider  # noqa: F401

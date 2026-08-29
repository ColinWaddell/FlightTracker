"""
FlightAware AeroAPI provider package.

Capability: routes (origin/destination by callsign).  Requires an
AeroAPI API key; the Personal plan's free monthly credit makes light
per-callsign usage free, but requests are billed per result set.
"""

from __future__ import annotations

from lookups.providers.flightaware.config import PROVIDER  # noqa: F401

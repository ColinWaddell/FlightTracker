"""
airplanes.live provider package.

Capability: flights (live positions from the airplanes.live community
network).  Free, no key required - but the API answers 403 unless the
calling IP is already feeding airplanes.live.  One request per second
maximum.
"""

from __future__ import annotations

from utilities.lookups.providers.airplaneslive.config import PROVIDER  # noqa: F401

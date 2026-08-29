"""
ADSB.im routes provider package.

Capability: routes (callsign -> airport pair via the community standing-
data service tar1090 uses).  Free, no key; requires a live position.
"""

from __future__ import annotations

from lookups.providers.adsbim.config import PROVIDER  # noqa: F401

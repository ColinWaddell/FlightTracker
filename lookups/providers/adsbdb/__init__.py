"""
adsbdb provider package.

Capabilities: routes (callsign airport-pair) and aircraft
(type/registration/operator/owner by mode-s hex).  Free, no API key.
"""

from __future__ import annotations

from lookups.providers.adsbdb.config import PROVIDER  # noqa: F401
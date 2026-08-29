"""
adsbdb provider configuration descriptor.
"""

from __future__ import annotations

from lookups.config import ProviderConfig

PROVIDER = ProviderConfig(
    id="adsbdb",
    name="adsbdb.com",
    description=(
        "Free callsign-route and aircraft database at adsbdb.com. "
        "No API key required."
    ),
    fields=(),
)

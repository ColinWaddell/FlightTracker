"""
HexDB provider configuration descriptor.
"""

from __future__ import annotations

from lookups.config import ProviderConfig

PROVIDER = ProviderConfig(
    id="hexdb",
    name="HexDB",
    description="Free route and aircraft database at hexdb.io. No API key required.",
    fields=(),
)
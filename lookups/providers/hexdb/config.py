"""
hexdb provider configuration descriptor.

The single source of truth for this provider: name, description,
capabilities and settings fields. lookups/registry.py derives the
adapter wiring and startup probe from these.
"""

from __future__ import annotations

from lookups.config import ProviderConfig

PROVIDER = ProviderConfig(
    id="hexdb",
    name="HexDB",
    description=("Free route and aircraft database at hexdb.io. No API key required."),
    capabilities=("routes", "aircraft"),
    fields=(),
)

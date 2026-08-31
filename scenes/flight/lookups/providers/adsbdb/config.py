"""
adsbdb provider configuration descriptor.

The single source of truth for this provider: name, description,
capabilities and settings fields. scenes/flight/lookups/registry.py derives the
adapter wiring and startup probe from these.
"""

from __future__ import annotations

from scenes.flight.lookups.config import ProviderConfig

PROVIDER = ProviderConfig(
    id="adsbdb",
    name="adsbdb.com",
    description=(
        "Free callsign-route and aircraft database at adsbdb.com. No API key required."
    ),
    capabilities=("routes", "aircraft"),
    fields=(),
)

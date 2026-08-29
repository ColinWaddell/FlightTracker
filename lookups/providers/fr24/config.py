"""
fr24 provider configuration descriptor.

The single source of truth for this provider: name, description,
capabilities and settings fields. lookups/registry.py derives the
adapter wiring and startup probe from these.
"""

from __future__ import annotations

from lookups.config import ProviderConfig

PROVIDER = ProviderConfig(
    id="fr24",
    name="Flight Radar 24 (Free)",
    description=(
            "Live flights from the FlightRadar24 feed. Works without an API key"
        ),
    capabilities=("flights", "routes", "aircraft"),
    fields=(),
)

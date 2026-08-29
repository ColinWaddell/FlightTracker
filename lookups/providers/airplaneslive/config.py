"""
airplaneslive provider configuration descriptor.

The single source of truth for this provider: name, description,
capabilities and settings fields. lookups/registry.py derives the
adapter wiring and startup probe from these.
"""

from __future__ import annotations

from lookups.config import ProviderConfig

PROVIDER = ProviderConfig(
    id="airplaneslive",
    name="airplanes.live",
    description=(
            "Free community feeder network aggregator. Please keep request rates",
            "low (max 1/second)."
        ),
    capabilities=("flights",),
    fields=(),
)

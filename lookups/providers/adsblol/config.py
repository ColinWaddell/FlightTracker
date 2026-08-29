"""
adsblol provider configuration descriptor.

The single source of truth for this provider: name, description,
capabilities and settings fields. lookups/registry.py derives the
adapter wiring and startup probe from these.
"""

from __future__ import annotations

from lookups.config import ProviderConfig

PROVIDER = ProviderConfig(
    id="adsblol",
    name="ADSB.lol",
    description=(
        "Community-run ADS-B aggregator (donation funded). Free, no key",
        "required.",
    ),
    capabilities=("flights",),
    fields=(),
)

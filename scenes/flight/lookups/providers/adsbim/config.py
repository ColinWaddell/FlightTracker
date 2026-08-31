"""
adsbim provider configuration descriptor.

The single source of truth for this provider: name, description,
capabilities and settings fields. scenes/flight/lookups/registry.py derives the
adapter wiring and startup probe from these.
"""

from __future__ import annotations

from scenes.flight.lookups.config import ProviderConfig

PROVIDER = ProviderConfig(
    id="adsbim",
    name="ADSB.im Routes",
    description=(
        "Community-sourced route database (the same standing-data service "
        "tar1090 uses). Free, no key required. Needs the aircraft's live "
        "position for the plausibility check."
    ),
    capabilities=("routes",),
    fields=(),
)

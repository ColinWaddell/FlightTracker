"""
ADSB.im routes provider configuration descriptor.
"""

from __future__ import annotations

from lookups.config import ProviderConfig

PROVIDER = ProviderConfig(
    id="adsbim",
    name="ADSB.im Routes",
    description=(
        "Community-sourced route database (the same standing-data service "
        "tar1090 uses). Free, no key required. Needs the aircraft's live "
        "position for the plausibility check."
    ),
    fields=(),
)

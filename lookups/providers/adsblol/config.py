"""
ADSB.lol provider configuration descriptor.
"""

from __future__ import annotations

from lookups.config import ProviderConfig

PROVIDER = ProviderConfig(
    id="adsblol",
    name="ADSB.lol",
    description=(
        "Community-run ADS-B aggregator (donation funded). "
        "Free, no key required."
    ),
    fields=(),
)

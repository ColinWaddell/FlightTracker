"""
adsb.fi provider configuration descriptor.
"""

from __future__ import annotations

from lookups.config import ProviderConfig

PROVIDER = ProviderConfig(
    id="adsbfi",
    name="ADS-B.fi",
    description=(
        "Live aircraft from the adsb.fi community feeder network. Free, "
        "no account or API key required."
    ),
    fields=(),
)

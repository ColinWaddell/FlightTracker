"""
airplanes.live provider configuration descriptor.
"""

from __future__ import annotations

from lookups.config import ProviderConfig

PROVIDER = ProviderConfig(
    id="airplaneslive",
    name="airplanes.live",
    description=(
        "Free community feeder network aggregator. No key required; "
        "please keep request rates low"
    ),
    fields=(),
)

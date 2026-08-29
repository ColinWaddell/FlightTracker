"""
FlightAware AeroAPI provider configuration descriptor.
"""

from __future__ import annotations

from lookups.config import ConfigField, ProviderConfig

PROVIDER = ProviderConfig(
    id="flightaware",
    name="FlightAware AeroAPI",
    description=(
        "Commercial FlightAware API. The Personal plan requires a card on "
        "file and includes $5/month of free credit ($10 for ADS-B feeders). "
        "Used for route lookups per new callsign - position polling would "
        "burn the credit quickly."
    ),
    fields=(
        ConfigField(
            key="api_key",
            label="AeroAPI Key",
            type="password",
            default="",
            required=True,
            sensitive=True,
            description=(
                "Your AeroAPI v4 key (X-API-Key) from the FlightAware AeroAPI portal."
            ),
        ),
    ),
)

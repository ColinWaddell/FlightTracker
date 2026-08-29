"""
AeroDataBox provider configuration descriptor.
"""

from __future__ import annotations

from lookups.config import ConfigField, ProviderConfig

PROVIDER = ProviderConfig(
    id="aerodatabox",
    name="AeroDataBox",
    description=(
        "Commercial flight and aircraft data via RapidAPI. Create a "
        "subscription at rapidapi.com (AeroDataBox) and paste the "
        "X-RapidAPI-Key here."
    ),
    fields=(
        ConfigField(
            key="api_key",
            label="RapidAPI Key",
            type="password",
            default="",
            required=True,
            sensitive=True,
            description="Your RapidAPI key (X-RapidAPI-Key). Stored securely and never displayed.",
        ),
    ),
)

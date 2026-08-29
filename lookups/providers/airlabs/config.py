"""
AirLabs provider configuration descriptor.
"""

from __future__ import annotations

from lookups.config import ConfigField, ProviderConfig

PROVIDER = ProviderConfig(
    id="airlabs",
    name="AirLabs",
    description=(
        "Commercial aviation database. The free plan covers 1,000 "
        "lookups per month - create an API key at airlabs.co."
    ),
    fields=(
        ConfigField(
            key="api_key",
            label="AirLabs API Key",
            type="password",
            default="",
            required=True,
            sensitive=True,
            description=(
                "Your AirLabs API key (airlabs.co - Dashboard > API keys)."
            ),
        ),
    ),
)

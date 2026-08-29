"""
FlightRadar24 API (official, commercial) configuration descriptor.
"""

from __future__ import annotations

from lookups.config import ConfigField, ProviderConfig

PROVIDER = ProviderConfig(
    id="fr24api",
    name="FlightRadar24 API",
    description=(
        "FlightRadar24's official commercial API - the paid, supported "
        "service, separate from the free public feed. Billed per returned "
        "record from a credit balance, so live polling over a busy zone "
        "consumes credits fastest. Create a token under Key Management on "
        'your account at <a href="https://www.flightradar24.com/" '
        'target="_blank" rel="noopener noreferrer">flightradar24.com</a>.'
    ),
    fields=(
        ConfigField(
            key="api_key",
            label="FR24 API Token",
            type="password",
            default="",
            required=True,
            sensitive=True,
            description=(
                "Bearer token from your FR24 account's Key Management page."
            ),
        ),
    ),
)

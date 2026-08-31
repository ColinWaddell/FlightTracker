"""
airlabs provider configuration descriptor.

The single source of truth for this provider: name, description,
capabilities and settings fields. lookups/registry.py derives the
adapter wiring and startup probe from these.
"""

from __future__ import annotations

from lookups.config import ConfigField, ProviderConfig

PROVIDER = ProviderConfig(
    id="airlabs",
    name="AirLabs",
    description=(
        "Commercial aviation database - the free plan covers 1,000 lookups per "
        'month. Create an API key at <a href="https://airlabs.co" '
        'target="_blank" rel="noopener noreferrer">airlabs.co</a>.'
    ),
    capabilities=("routes",),
    fields=(
        ConfigField(
            key="api_key",
            label="AirLabs API Key",
            type="password",
            default="",
            required=True,
            sensitive=True,
            description=("Your AirLabs API key. Stored securely and never displayed."),
        ),
    ),
)

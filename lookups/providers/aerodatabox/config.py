"""
aerodatabox provider configuration descriptor.

The single source of truth for this provider: name, description,
capabilities and settings fields. lookups/registry.py derives the
adapter wiring and startup probe from these.
"""

from __future__ import annotations

from lookups.config import ConfigField, ProviderConfig

PROVIDER = ProviderConfig(
    id="aerodatabox",
    name="AeroDataBox",
    description=(
        "Don't register with AeroDataBox directly. Instead get a key here: <a "
        'href="https://rapidapi.com/aedbx-aedbx/api/aerodatabox" '
        'target="_blank" rel="noopener noreferrer">RapidAPI</a>. You\'ll need to '
        "sign up for an account, search for AeroDataBox, hit the Test button up "
        "the top right and then subscribe to the free plan. After that it'll"
        "show you your key."
    ),
    capabilities=("routes", "aircraft"),
    fields=(
        ConfigField(
            key="api_key",
            label="RapidAPI Key",
            type="password",
            default="",
            required=True,
            sensitive=True,
            description=(
                "Your RapidAPI key (X-RapidAPI-Key). Stored securely and never displayed."
            ),
        ),
    ),
)

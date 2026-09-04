"""
opensky provider configuration descriptor.

The single source of truth for this provider: name, description,
capabilities and settings fields. utilities/lookups/registry.py derives the
adapter wiring and startup probe from these.
"""

from __future__ import annotations

from utilities.lookups.config import ConfigField, ProviderConfig

PROVIDER = ProviderConfig(
    id="opensky",
    name="OpenSky Network",
    description=(
        'Create an API client at <a href="https://opensky-network.org/login" '
        'target="_blank" rel="noopener noreferrer">opensky-network.org</a> '
        "(Account &rarr; API Clients) to get your credentials. A free "
        "registered account is sufficient for 30-second polling."
    ),
    capabilities=("flights",),
    fields=(
        ConfigField(
            key="client_id",
            label="Client ID",
            type="text",
            default="",
            required=False,
            sensitive=False,
            description=("OAuth2 client ID from your OpenSky account settings."),
        ),
        ConfigField(
            key="client_secret",
            label="Client Secret",
            type="password",
            default="",
            required=True,
            sensitive=True,
            description=("OAuth2 client secret. Stored securely and never displayed."),
        ),
    ),
)

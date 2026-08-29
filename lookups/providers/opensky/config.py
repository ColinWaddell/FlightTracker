"""
OpenSky Network provider configuration descriptor.
"""

from __future__ import annotations

from lookups.config import ConfigField, ProviderConfig

PROVIDER = ProviderConfig(
    id="opensky",
    name="OpenSky Network",
    description=(
        "Live aircraft state vectors from the OpenSky Network REST API. "
        "Create an API client at opensky-network.org (Account → API "
        "Clients); a free registered account is sufficient for 30-second "
        "polling."
    ),
    fields=(
        ConfigField(
            key="client_id",
            label="Client ID",
            type="text",
            default="",
            required=True,
            description="OAuth2 client ID from your OpenSky account settings.",
        ),
        ConfigField(
            key="client_secret",
            label="Client Secret",
            type="password",
            default="",
            required=True,
            sensitive=True,
            description="OAuth2 client secret. Stored securely and never displayed.",
        ),
    ),
)

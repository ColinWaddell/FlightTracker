"""
FlightRadar24 provider configuration descriptor.

FR24 needs no user credentials - the descriptor exists to give the provider
a home in the Providers category of the configuration UI.
"""

from __future__ import annotations

from lookups.config import ProviderConfig

PROVIDER = ProviderConfig(
    id="fr24",
    name="FlightRadar24",
    description=(
        "Public FlightRadar24 data. Free, no account required. FR24 is "
        "getting harder to support and may eventually be deprecated."
    ),
    fields=(),
)
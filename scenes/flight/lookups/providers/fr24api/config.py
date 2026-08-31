"""
fr24api provider configuration descriptor.

The single source of truth for this provider: name, description,
capabilities and settings fields. scenes/flight/lookups/registry.py derives the
adapter wiring and startup probe from these.
"""

from __future__ import annotations

from scenes.flight.lookups.config import ConfigField, ProviderConfig

PROVIDER = ProviderConfig(
    id="fr24api",
    name="Flight Radar 24 (Paid)",
    description=(
        "FlightRadar24's official commercial API - the paid, supported service "
        "with a Bearer token from your FR24 account. Billed per returned record "
        "from a credit balance, so live polling over a busy zone burns credits "
        'fastest. <a href="https://www.flightradar24.com/" target="_blank" '
        'rel="noopener noreferrer">flightradar24.com</a>. '
        "<strong>Billing warning:</strong> "
        "Best suited to occasional route/aircraft lookups; leave "
        "continuous polling to the free providers."
    ),
    capabilities=("flights", "routes", "aircraft"),
    fields=(
        ConfigField(
            key="api_key",
            label="FR24 API Token",
            type="password",
            default="",
            required=True,
            sensitive=True,
            description=("Bearer token from your FR24 account's Key Management page."),
        ),
    ),
)

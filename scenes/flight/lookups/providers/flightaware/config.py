"""
flightaware provider configuration descriptor.

The single source of truth for this provider: name, description,
capabilities and settings fields. scenes/flight/lookups/registry.py derives the
adapter wiring and startup probe from these.
"""

from __future__ import annotations

from scenes.flight.lookups.config import ConfigField, ProviderConfig

PROVIDER = ProviderConfig(
    id="flightaware",
    name="FlightAware AeroAPI",
    description=(
        "FlightAware's commercial API. The Personal plan includes $5/month of "
        "free credit and requires a card on file - fine for per-callsign route "
        "lookups, too costly for position polling. Get a key at <a "
        'href="https://www.flightaware.com/aeroapi/portal" target="_blank" '
        'rel="noopener noreferrer">the AeroAPI portal</a>.'
    ),
    capabilities=("routes",),
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

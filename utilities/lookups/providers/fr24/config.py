"""
fr24 provider configuration descriptor.

The single source of truth for this provider: name, description,
capabilities and settings fields. utilities/lookups/registry.py derives the
adapter wiring and startup probe from these.
"""

from __future__ import annotations

from utilities.lookups.config import ProviderConfig, rate_limit_fields

PROVIDER = ProviderConfig(
    id="fr24",
    name="Flight Radar 24 (Free)",
    description=("Live flights from the FlightRadar24 feed. Works without an API key"),
    capabilities=("flights", "routes", "aircraft"),
    # No squawk here: FR24's free feed stopped populating the squawk slot
    # (feed index 6 is '' for every aircraft as of Oct 2026 - verified
    # against 1,200+ live aircraft across two FlightRadarAPI versions).
    # Squawk is only available from FR24's paid api (the "fr24api"
    # provider, which maps the response's "sqr" field).
    fields=rate_limit_fields(),
)

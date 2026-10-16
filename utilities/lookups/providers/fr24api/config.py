"""
fr24api provider configuration descriptor.

The single source of truth for this provider: name, description,
capabilities and settings fields. utilities/lookups/registry.py derives the
adapter wiring and startup probe from these.
"""

from __future__ import annotations

from utilities.lookups.config import ConfigField, ProviderConfig, rate_limit_fields

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
    # Squawk badge kept: the API docs document "sqr" for
    # /api/live/flight-positions/full (plus a "squawks" filter param),
    # so unlike the free feed (see fr24/config.py) squawk is part of
    # the product spec here.  No token exists on this deployment to
    # verify it hands-on - if the paid tier ever stops sending it
    # anyway, users will complain quickly enough.
    live_fields=("squawk",),
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
        *rate_limit_fields(),
    ),
)

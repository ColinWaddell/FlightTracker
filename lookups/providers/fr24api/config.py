"""
fr24api provider configuration descriptor.

The single source of truth for this provider: name, description,
capabilities and settings fields. lookups/registry.py derives the
adapter wiring and startup probe from these.
"""

from __future__ import annotations

from lookups.config import ConfigField, ProviderConfig

PROVIDER = ProviderConfig(
    id="fr24api",
    name="Flight Radar 24 (Paid)",
    description=(
        "FlightRadar24's official commercial API - the paid, supported service",
        "with a Bearer token from your FR24 account. Billed per returned record",
        "from a credit balance, so live polling over a busy zone burns credits",
        'fastest. <a href="https://www.flightradar24.com/" target="_blank"',
        'rel="noopener noreferrer">flightradar24.com</a>.',
        "<strong>Billing warning (measured 2026-08-31):</strong> one",
        "live-positions call bills roughly 8 credits per returned record with a",
        "1-credit minimum even when nothing is returned - a ten-flight zone poll",
        "costs ~80 credits, and rapid re-calls trip the burst limit (HTTP 429).",
        "Responses carry x-fr24-credits-consumed / -remaining headers for",
        "monitoring. Best suited to occasional route/aircraft lookups; leave",
        "continuous polling to the free providers.",
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

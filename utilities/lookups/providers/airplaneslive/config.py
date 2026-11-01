"""
airplaneslive provider configuration descriptor.

The single source of truth for this provider: name, description,
capabilities and settings fields. utilities/lookups/registry.py derives the
adapter wiring and startup probe from these.
"""

from __future__ import annotations

from utilities.lookups.config import ProviderConfig, rate_limit_fields

PROVIDER = ProviderConfig(
    id="airplaneslive",
    name="airplanes.live",
    description=(
        "Free community feeder network aggregator. The API is reserved for "
        "contributors - your IP address must already be feeding airplanes.live "
        "or every request answers 403. Run their "
        '<a href="https://airplanes.live/how-to-feed/" target="_blank" '
        'rel="noopener noreferrer">feed client</a> on the same internet '
        "connection as this display. "
        "Please keep request rates low (max 1/second)."
    ),
    # api.airplanes.live answers HTTP 200 only when the caller's IP is
    # already feeding the network; since Sep 2026 any other source gets
    # 403 with {"error": "Please contact us at contact@airplanes.live ...
    # include any links, a description of the project ..."} (verified
    # live Nov 2026 - a feeding IP gets 200, a non-feeder gets 403).
    capabilities=("flights",),
    live_fields=("squawk",),
    fields=rate_limit_fields(),
)

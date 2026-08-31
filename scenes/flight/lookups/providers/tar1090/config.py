"""
tar1090 provider configuration descriptor.

The single source of truth for this provider: name, description,
capabilities and settings fields. scenes/flight/lookups/registry.py derives the
adapter wiring and startup probe from these.
"""

from __future__ import annotations

from scenes.flight.lookups.config import ConfigField, ProviderConfig

PROVIDER = ProviderConfig(
    id="tar1090",
    name="tar1090",
    description=(
        "Point this at your local tar1090 instance's <code>aircraft.json</code> "
        "endpoint. Currently tested against the latest RPi image from <a "
        'href="https://adsb.im/home" target="_blank" rel="noopener '
        'noreferrer">ADSB.im</a>.'
    ),
    capabilities=("flights",),
    fields=(
        ConfigField(
            key="url",
            label="tar1090 URL",
            type="text",
            default="",
            required=False,
            sensitive=False,
            description=("e.g. http://192.168.1.x/tar1090/data/aircraft.json"),
        ),
    ),
)

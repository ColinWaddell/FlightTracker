"""
tar1090 provider configuration descriptor.
"""

from __future__ import annotations

from lookups.config import ConfigField, ProviderConfig

PROVIDER = ProviderConfig(
    id="tar1090",
    name="tar1090",
    description=(
        "A local / self-hosted tar1090 (or dump1090) receiver. Currently "
        "tested against the latest Raspberry Pi image from ADSB.im."
    ),
    fields=(
        ConfigField(
            key="url",
            label="tar1090 URL",
            type="text",
            default="",
            required=True,
            description=(
                "Point this at your local tar1090 instance's aircraft.json "
                "endpoint, e.g. http://192.168.1.x/tar1090/data/aircraft.json"
            ),
        ),
    ),
)
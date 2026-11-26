"""Tests for the attribution page.

The /attributions page is linked from the shared page footer and lists
the data sources and open-source licences the project relies on.  It
renders hermetically (a static template - no provider state) and is
login-gated like every other page in the web UI.
"""

from __future__ import annotations

from pathlib import Path

import pytest

# Every service or dataset the page must name.  The live sources are
# pinned loosely here (the registry-driven structure test below pins
# them against the code); the bundled data and licence names are
# pinned exactly - those terms are the point of the page.
SOURCES_TO_PIN = (
    "FlightRadar24",
    "OpenSky Network",
    "tar1090",
    "ADS-B.fi",
    "ADSB.lol",
    "airplanes.live",
    "HexDB",
    "adsbdb.com",
    "ADSB.im routeset",
    "AeroDataBox",
    "AirLabs",
    "FlightAware AeroAPI",
    "WeatherAPI.com",
    "CelesTrak",
    "OpenStreetMap",
)

OTHER_TERMS_TO_PIN = (
    "OurAirports",
    "Wikipedia",
    "ODbL",
    "CC BY-SA",
    "CC0",
    "Public domain",
    "AGPL-3.0",
    "GPL-2.0",
    "Apache-2.0",
    "BSD-3-Clause",
    "LGPL-2.1",
    "GUST Font Licence",
    "plane-tracker-rgb-pi",
)

# Registry provider id -> the page's name for that source.  A new
# provider must be given a row on the attribution page or this test
# fails at build time.
PROVIDER_TO_NAME = {
    "fr24": "FlightRadar24",
    # The free and paid FR24 providers share one row on the page.
    "fr24api": "FlightRadar24",
    "opensky": "OpenSky Network",
    "tar1090": "tar1090",
    "adsbfi": "ADS-B.fi",
    "adsblol": "ADSB.lol",
    "airplaneslive": "airplanes.live",
    "hexdb": "HexDB",
    "adsbdb": "adsbdb.com",
    "adsbim": "ADSB.im routeset",
    "aerodatabox": "AeroDataBox",
    "airlabs": "AirLabs",
    "flightaware": "FlightAware AeroAPI",
}

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"


@pytest.fixture
def client():
    from web.app import app

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["authenticated"] = True
    return client


class TestAttributionsPage:
    def test_renders_for_authenticated_user(self, client):
        resp = client.get("/attributions")
        assert resp.status_code == 200

    def test_requires_login(self):
        from web.app import app

        unauthed = app.test_client()
        resp = unauthed.get("/attributions", follow_redirects=False)
        assert resp.status_code == 302

    def test_names_every_registry_provider(self, client):
        """Every live provider the code knows is named on the page."""
        from utilities.lookups.registry import PROVIDERS

        html = client.get("/attributions").get_data(as_text=True)
        for pid, spec in PROVIDERS.items():
            name = PROVIDER_TO_NAME.get(pid)
            assert name is not None, (
                f"provider {pid!r} ({spec.name}) has no entry in the "
                "attribution page's PROVIDER_TO_NAME map"
            )
            assert name in html, pid

    def test_names_bundled_data_and_licence_terms(self, client):
        html = client.get("/attributions").get_data(as_text=True)
        for needle in OTHER_TERMS_TO_PIN:
            assert needle in html, needle

    def test_footer_links_every_page_to_attributions(self, client):
        html = client.get("/status").data.decode()
        assert 'href="/attributions"' in html

    def test_footer_link_present_in_shared_footer(self):
        source = (TEMPLATE_DIR / "footer.html").read_text()
        assert "url_for('attributions')" in source

    def test_carries_no_secrets(self, client):
        """Pure attribution content - no config keys or sensitive values."""
        import re

        from utilities.lookups.config import REDACTED
        from web.app import SENSITIVE_KEYS

        html = client.get("/attributions").get_data(as_text=True)
        for key in SENSITIVE_KEYS:
            assert key not in html, key
        # No settings-style inputs or provider settings forms on the page.
        assert not re.search(r"<form", html)
        assert REDACTED not in html

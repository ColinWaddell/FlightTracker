"""Tests for the self-hosted Ko-fi badge.

The badge (web/templates/kofi.html + web/static/kofi/) is a plain styled
link to the Ko-fi donations page.  It must appear on every page of the
web UI - except the login screen - and must not pull in any third-party
assets or load any JavaScript of its own.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Pages the test-suite can render hermetically (no network / hardware).
# The remaining pages (live-data, update, restarting) get the identical
# Jinja include - covered by the template-source test below.
HERMETIC_PAGES = [
    "/status",
    "/settings",
    "/logs",
    "/cached-data",
    "/api",
    "/cache-clear",
    "/backup/restore",
]

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "web" / "templates"
KOFI_CSS = Path(__file__).resolve().parent.parent / "web" / "static" / "kofi" / "kofi.css"
# Templates that carry the widget include (login.html deliberately does not).
PAGE_TEMPLATES = [
    "api_usage.html",
    "cached_data.html",
    "clear_cache.html",
    "live_data.html",
    "logs.html",
    "restarting.html",
    "restore.html",
    "settings.html",
    "status.html",
    "update.html",
]

KOFI_DONATIONS_URL = "https://ko-fi.com/flighttracker"


@pytest.fixture
def client():
    from web.app import app

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["authenticated"] = True
    return client


@pytest.fixture
def anonymous_client():
    from web.app import app

    return app.test_client()


class TestBadgeOnEveryPage:
    def test_login_page_excludes_widget(self, anonymous_client):
        """The login screen carries no badge at all (footer.html is also
        skipped there, so an in-flow badge would have nothing to sit under).
        """
        resp = anonymous_client.get("/login")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "kofi-donate-button" not in html
        assert "static/kofi/kofi.css" not in html

    @pytest.mark.parametrize("page", HERMETIC_PAGES)
    def test_page_includes_badge_link(self, client, page):
        resp = client.get(page)
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "kofi-donate-button" in html
        assert "static/kofi/kofi.css" in html
        assert f'href="{KOFI_DONATIONS_URL}"' in html

    def test_every_page_template_but_login_includes_widget(self):
        """Contract check: every page template except the login screen
        carries the include, so pages this suite cannot render hermetically
        are covered too."""
        for name in PAGE_TEMPLATES:
            source = (TEMPLATE_DIR / name).read_text()
            assert '{% include "kofi.html" %}' in source, f"{name} missing kofi include"

    def test_login_template_has_no_include(self):
        source = (TEMPLATE_DIR / "login.html").read_text()
        assert '{% include "kofi.html" %}' not in source


class TestBadgeIsAPlainLink:
    def test_badge_template_has_no_script_or_iframe(self):
        """The badge is just a link - no popup, no iframe, no JavaScript."""
        source = (TEMPLATE_DIR / "kofi.html").read_text().lower()
        assert "<script" not in source
        assert "<iframe" not in source

    def test_no_javascript_asset_shipped(self):
        assert not (KOFI_CSS.parent / "kofi.js").exists()


class TestBadgeAssets:
    @pytest.mark.parametrize("asset", ["kofi/kofi.css", "kofi/logomark.png"])
    def test_assets_served(self, client, asset):
        resp = client.get(f"/static/{asset}")
        assert resp.status_code == 200


class TestNoThirdPartyAssets:
    def test_badge_does_not_reference_kofi_cdn(self, client):
        """The original widget loads overlay-widget.js, fonts and images from
        storage.ko-fi.com; the self-hosted badge must not.  Checked on a
        page that carries the badge (/status; login has none at all)."""
        html = client.get("/status").data.decode()
        assert "storage.ko-fi.com" not in html
        assert "overlay-widget" not in html
        # ko-fi.com appears exactly once: the badge link href.
        assert html.count("ko-fi.com") == 1


class TestBadgePlacement:
    def test_mobile_badge_sits_in_flow_below_footer(self):
        """On mobile the badge must not float: it has to sit just below the
        footer.  The widget include comes after the footer include on every
        page, so static in-flow positioning inside the 750px media query is
        what guarantees that placement."""
        css = KOFI_CSS.read_text()
        match = re.search(
            r"@media only screen and \(max-width: 750px\) \{.*?\n\}", css, re.S
        )
        assert match, "max-width: 750px media query missing from kofi.css"
        mobile_block = match.group(0)
        assert ".kofi-wrap" in mobile_block, "kofi-wrap not styled on mobile"
        assert "position: static" in mobile_block, "badge still floats on mobile"

    def test_mobile_badge_is_half_size(self):
        """Colin: badge at half size on mobile (46px pill -> 24px)."""
        css = KOFI_CSS.read_text()
        match = re.search(
            r"@media only screen and \(max-width: 750px\) \{.*?\n\}", css, re.S
        )
        assert match, "max-width: 750px media query missing from kofi.css"
        mobile_block = match.group(0)
        assert "height: 24px" in mobile_block
        assert "width: 18px" in mobile_block  # logomark

"""Tests for the self-hosted Ko-fi support widget.

The widget (web/templates/kofi.html + web/static/kofi/) must be rendered
on every page of the web UI - including the login screen - and must not
pull in any third-party scripts, styles or fonts.
"""

from __future__ import annotations

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
PAGE_TEMPLATES = [
    "api_usage.html",
    "cached_data.html",
    "clear_cache.html",
    "live_data.html",
    "login.html",
    "logs.html",
    "restarting.html",
    "restore.html",
    "settings.html",
    "status.html",
    "update.html",
]


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


class TestWidgetOnEveryPage:
    def test_login_page_includes_widget(self, anonymous_client):
        resp = anonymous_client.get("/login")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "kofi-donate-button" in html
        assert "Support Me" in html

    @pytest.mark.parametrize("page", HERMETIC_PAGES)
    def test_page_includes_widget(self, client, page):
        resp = client.get(page)
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "kofi-donate-button" in html
        assert "static/kofi/kofi.css" in html
        assert "static/kofi/kofi.js" in html

    def test_every_page_template_includes_widget(self):
        """Contract check: all page templates carry the include, so pages
        that this suite cannot render hermetically are covered too."""
        for name in PAGE_TEMPLATES:
            source = (TEMPLATE_DIR / name).read_text()
            assert '{% include "kofi.html" %}' in source, f"{name} missing kofi include"


class TestWidgetAssets:
    @pytest.mark.parametrize(
        "asset", ["kofi/kofi.css", "kofi/kofi.js", "kofi/logomark.png"]
    )
    def test_assets_served(self, client, asset):
        resp = client.get(f"/static/{asset}")
        assert resp.status_code == 200


class TestNoThirdPartyAssets:
    def test_widget_does_not_reference_kofi_cdn(self, anonymous_client):
        """The original widget loads overlay-widget.js, fonts and images from
        storage.ko-fi.com; the self-hosted version must not."""
        html = anonymous_client.get("/login").data.decode()
        assert "storage.ko-fi.com" not in html
        assert "overlay-widget" not in html
        # ko-fi.com appears only in the popup-notice link, twice: once in
        # its href and once in the visible link text.  The iframe URL lives
        # inside the self-hosted kofi.js, never in the page itself.
        assert html.count("ko-fi.com") == 2

"""Tests for the Ko-fi badge.

The badge is a plain anchor inside the shared page footer
(web/templates/footer.html) holding the self-hosted logomark and a
"Support Me" label, and linking to the Ko-fi donations page.  The
footer is included on every page of the web UI - except the login screen,
which therefore carries no badge either.  No third-party assets, no
JavaScript, no stylesheet of its own.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

# Pages the test-suite can render hermetically (no network / hardware).
# The remaining pages (live-data, update, restarting) get the identical
# footer include - covered by the template-source test below.
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
STATIC_KOFI_DIR = Path(__file__).resolve().parent.parent / "web" / "static" / "kofi"
# Templates that carry the footer (login.html deliberately does not).
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


def badge_anchor_from_footer() -> str:
    """Return the badge <a>...</a> block from the shared footer."""
    source = (TEMPLATE_DIR / "footer.html").read_text()
    match = re.search(r"<a [^>]*ko-fi\.com[^>]*>.*?</a>", source, re.S)
    assert match, "ko-fi badge anchor missing from footer.html"
    return match.group(0)


class TestBadgeInFooter:
    def test_login_page_excludes_badge(self, anonymous_client):
        """The login screen carries no footer and therefore no badge."""
        resp = anonymous_client.get("/login")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "ko-fi.com" not in html
        assert "static/kofi/logomark.png" not in html

    @pytest.mark.parametrize("page", HERMETIC_PAGES)
    def test_page_footer_carries_badge_link(self, client, page):
        resp = client.get(page)
        assert resp.status_code == 200
        html = resp.data.decode()
        assert f'href="{KOFI_DONATIONS_URL}"' in html
        assert "static/kofi/logomark.png" in html
        assert "Support Me" in html

    def test_badge_lives_in_shared_footer(self):
        source = (TEMPLATE_DIR / "footer.html").read_text()
        assert f'href="{KOFI_DONATIONS_URL}"' in source
        assert "kofi/logomark.png" in source

    def test_every_page_template_but_login_includes_footer(self):
        """Contract check: every page template except the login screen
        includes the shared footer, so pages this suite cannot render
        hermetically are covered too."""
        for name in PAGE_TEMPLATES:
            source = (TEMPLATE_DIR / name).read_text()
            assert (
                '{% include "footer.html" %}' in source
            ), f"{name} missing footer include"

    def test_login_template_has_no_footer_include(self):
        source = (TEMPLATE_DIR / "login.html").read_text()
        assert '{% include "footer.html" %}' not in source

    def test_old_standalone_widget_is_gone(self):
        """The floating widget (template + stylesheet) has been removed;
        the badge now lives in the footer."""
        assert not (TEMPLATE_DIR / "kofi.html").exists()
        assert not (STATIC_KOFI_DIR / "kofi.css").exists()


class TestBadgeIsAPlainLink:
    def test_badge_is_label_and_image_only(self):
        """The anchor contains exactly the visible "Support Me" text and
        the logomark image - no script, no iframe, nothing else."""
        badge = badge_anchor_from_footer().lower()
        assert "<script" not in badge
        assert "<iframe" not in badge
        assert "<img" in badge
        # Strip the opening/closing anchor tags and the img; only the
        # "Support Me" label remains.
        inner = re.sub(r"<img[^>]*/?>", "", badge)
        inner = re.sub(r"^<a[^>]*>", "", inner).replace("</a>", "")
        assert inner.split() == ["support", "me"]

    def test_no_javascript_asset_shipped(self):
        assert not (STATIC_KOFI_DIR / "kofi.js").exists()

    def test_no_kofi_stylesheet_shipped(self):
        assert not (STATIC_KOFI_DIR / "kofi.css").exists()


class TestBadgeSize:
    def test_badge_is_half_its_previous_size(self):
        """Colin: badge at 50% of its previous size (39px logomark -> 20px)."""
        badge = badge_anchor_from_footer()
        match = re.search(r"<img[^>]*>", badge)
        assert match, "badge img tag missing"
        img = match.group(0)
        assert 'width="20"' in img
        assert 'height="16"' in img


class TestBadgeAssets:
    def test_logomark_served(self, client):
        resp = client.get("/static/kofi/logomark.png")
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

"""Tests for the /status page (provider hold-offs + fetch details)."""

from __future__ import annotations

import time

import pytest


@pytest.fixture
def client():
    from web.app import app

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["authenticated"] = True
    return client


@pytest.fixture(autouse=True)
def reset_quarantine():
    from lookups.quarantine import QUARANTINE

    QUARANTINE.reset()
    yield
    QUARANTINE.reset()


def _seed_last_fetch():
    """Give the shared facade a last-fetch record without fetching."""
    from display import get_overhead_instance

    overhead = get_overhead_instance()
    overhead.last_fetch = {
        "at": time.time(),
        "ok": True,
        "provider_id": "tar1090",
        "source_name": "tar1090",
        "errors": [],
    }


class TestStatusPage:
    def test_renders_for_authenticated_user(self, client):
        resp = client.get("/status")
        assert resp.status_code == 200

    def test_requires_login(self):
        from web.app import app

        unauthed = app.test_client()
        resp = unauthed.get("/status", follow_redirects=False)
        assert resp.status_code == 302

    def test_lists_all_registered_providers(self, client):
        from lookups.registry import PROVIDERS

        html = client.get("/status").get_data(as_text=True)
        for spec in PROVIDERS.values():
            assert spec.name in html, spec.id

    def test_shows_enabled_and_configured_flags(self, client):
        html = client.get("/status").get_data(as_text=True)
        # FR24 needs no credentials, so it is enabled and configured.
        assert "enabled" in html

    def test_shows_hold_off_for_quarantined_provider(self, client):
        from lookups.quarantine import QUARANTINE

        QUARANTINE.record_failure("hexdb")
        html = client.get("/status").get_data(as_text=True)
        assert "min left" in html

    def test_healthy_provider_has_no_hold_off(self, client):
        html = client.get("/status").get_data(as_text=True)
        assert "min left" not in html

    def test_last_fetch_record_displayed(self, client):
        _seed_last_fetch()
        html = client.get("/status").get_data(as_text=True)
        assert "answered" in html
        assert "tar1090" in html

    def test_failed_fetch_shows_errors(self, client):
        from display import get_overhead_instance

        overhead = get_overhead_instance()
        overhead.last_fetch = {
            "at": time.time(),
            "ok": False,
            "provider_id": "",
            "source_name": "",
            "errors": ["tar1090: connection refused"],
        }
        html = client.get("/status").get_data(as_text=True)
        assert "failed" in html
        assert "tar1090: connection refused" in html

    def test_navbar_link_present(self, client):
        html = client.get("/status").get_data(as_text=True)
        assert 'href="/status"' in html

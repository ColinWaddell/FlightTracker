"""Tests for the provider-facing web plumbing in web/app.py.

Covers:
- _parse_provider_form (priority list JSON payloads)
- _parse_provider_settings (providers.<pid>.<field> form keys + mask
  token semantics)
- parse_settings_form provider entries end-to-end
- /debug-config schema-driven redaction
- settings page data masking (secrets never sent to the browser)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def cfg():
    """A Config stand-in with provider plumbing."""
    from setup.configuration import Config

    cfg = Config.__new__(Config)
    cfg.data_store = {}
    return cfg


# ---------------------------------------------------------------------------
# _parse_provider_form
# ---------------------------------------------------------------------------


class TestParseProviderForm:
    def test_valid_json_becomes_provider_list(self):
        from web.app import _parse_provider_form

        form = {
            "flight_providers_json": json.dumps(
                [
                    {"provider": "tar1090", "enabled": True},
                    {"provider": "fr24", "enabled": False},
                ]
            )
        }
        out = _parse_provider_form(form, MagicMock())
        assert out["flight_providers"] == [
            {"provider": "tar1090", "enabled": True},
            {"provider": "fr24", "enabled": False},
        ]

    def test_route_payload_maps_to_route_providers_key(self):
        from web.app import _parse_provider_form

        form = {
            "route_providers_json": json.dumps([{"provider": "hexdb", "enabled": True}])
        }
        out = _parse_provider_form(form, MagicMock())
        assert out["route_providers"] == [{"provider": "hexdb", "enabled": True}]

    def test_unknown_provider_dropped_with_no_crash(self):
        from web.app import _parse_provider_form

        form = {
            "flight_providers_json": json.dumps([{"provider": "nope", "enabled": 1}])
        }
        out = _parse_provider_form(form, MagicMock())
        assert out == {}

    def test_malformed_json_ignored(self):
        from web.app import _parse_provider_form

        out = _parse_provider_form({"flight_providers_json": "{not json"}, MagicMock())
        assert out == {}

    def test_absent_payload_omits_key(self):
        from web.app import _parse_provider_form

        assert _parse_provider_form({}, MagicMock()) == {}


# ---------------------------------------------------------------------------
# _parse_provider_settings - mask semantics through the web path
# ---------------------------------------------------------------------------


class TestParseProviderSettings:
    def test_sensitive_mask_token_keeps_stored_value(self):
        from web.app import _parse_provider_settings

        cfg = MagicMock()
        cfg.provider_settings.return_value = {
            "client_id": "my-id",
            "client_secret": "S3CR3T",
        }

        form = {
            "providers.opensky.client_id": "my-id",
            "providers.opensky.client_secret": "**********",  # untouched in UI
        }
        subtree = _parse_provider_settings(form, cfg)

        assert subtree["opensky"] == {"client_id": "my-id", "client_secret": "S3CR3T"}

    def test_sensitive_empty_string_clears_value(self):
        from web.app import _parse_provider_settings

        cfg = MagicMock()
        cfg.provider_settings.return_value = {"client_secret": "S3CR3T"}

        form = {"providers.opensky.client_secret": ""}
        subtree = _parse_provider_settings(form, cfg)
        assert subtree["opensky"]["client_secret"] == ""

    def test_sensitive_new_value_replaces(self):
        from web.app import _parse_provider_settings

        cfg = MagicMock()
        cfg.provider_settings.return_value = {"client_secret": "OLD"}

        form = {"providers.opensky.client_secret": "NEW-KEY"}
        subtree = _parse_provider_settings(form, cfg)
        assert subtree["opensky"]["client_secret"] == "NEW-KEY"

    def test_unknown_provider_ignored(self):
        from web.app import _parse_provider_settings

        form = {"providers.nosuch.key": "x"}
        assert _parse_provider_settings(form, MagicMock()) == {}

    def test_only_touched_providers_returned(self):
        from web.app import _parse_provider_settings

        cfg = MagicMock()
        form = {"providers.fr24.nothing": ""}
        # fr24 has no fields, so nothing collectable
        subtree = _parse_provider_settings(form, cfg)
        assert "fr24" not in subtree or subtree["fr24"] == {}


# ---------------------------------------------------------------------------
# parse_settings_form integration (provider-related keys)
# ---------------------------------------------------------------------------


class TestParseSettingsFormProviders:
    def _cfg(self):
        """A cfg stand-in with the typed attributes parse_settings_form reads."""
        from types import SimpleNamespace

        return SimpleNamespace(
            flight_lat=55.9,
            flight_lng=-4.3,
            flight_radius=25.0,
            flight_min_altitude=100.0,
            flight_max_altitude=10000.0,
            flight_zone_tl_y=56.0,
            flight_zone_tl_x=-5.0,
            flight_zone_br_y=55.0,
            flight_zone_br_x=-3.0,
            flight_observer_lat=55.5,
            flight_observer_lng=-4.0,
            details_custom_template="",
            display_speed="default",
            log_level="INFO",
            weather_refresh_minutes=15,
            weatherapi_key="",
            web_port=8000,
            providers_subtree={},
            provider_settings=lambda pid: {},
            flight_providers=[{"provider": "fr24", "enabled": True}],
            route_providers=[{"provider": "hexdb", "enabled": True}],
        )

    def test_no_provider_keys_still_yields_max_flight_lookup(self):
        from web.app import parse_settings_form

        out = parse_settings_form({}, self._cfg())
        assert "flight_providers" not in out
        assert out["providers"] == {}
        assert out["max_flight_lookup"] == 5  # int_val's documented default

    def test_provider_usage_logging_toggle_parse(self):
        from web.app import parse_settings_form

        cfg = self._cfg()
        out = parse_settings_form({"provider_usage_logging": "on"}, cfg)
        assert out["provider_usage_logging"] is True
        out = parse_settings_form({}, cfg)
        assert out["provider_usage_logging"] is False

    def test_legacy_data_source_key_not_produced(self):
        from web.app import parse_settings_form

        out = parse_settings_form(
            {"data_source": "tar1090", "tar1090_url": "http://x"}, self._cfg()
        )
        assert "data_source" not in out
        assert "tar1090_url" not in out
        assert "osn_client_secret" not in out
        assert "aerodatabox_api_key" not in out


# ---------------------------------------------------------------------------
# /debug-config redaction
# ---------------------------------------------------------------------------


class TestDebugConfigRedaction:
    def test_top_level_sensitive_keys_redacted(self):
        from web.app import _redact_for_debug

        safe = _redact_for_debug(
            {
                "weatherapi_key": "wkey",
                "web_password_hash": "pbkdf2:...",
                "flight_lat": 55.9,
            }
        )
        assert safe["weatherapi_key"] == "***REDACTED***"
        assert safe["web_password_hash"] == "***REDACTED***"
        assert safe["flight_lat"] == 55.9

    def test_provider_secrets_redacted_schema_driven(self):
        from web.app import _redact_for_debug

        safe = _redact_for_debug(
            {
                "providers": {
                    "opensky": {"client_id": "cid", "client_secret": "S3CR3T"},
                    "hexdb": {},  # no fields at all
                }
            }
        )
        assert safe["providers"]["opensky"]["client_id"] == "cid"
        assert safe["providers"]["opensky"]["client_secret"] == "***REDACTED***"
        assert safe["providers"]["hexdb"] == {}

    def test_empty_secret_not_marked(self):
        from web.app import _redact_for_debug

        safe = _redact_for_debug({"weatherapi_key": ""})
        assert safe["weatherapi_key"] == ""


# ---------------------------------------------------------------------------
# Settings page data masking
# ---------------------------------------------------------------------------


class TestSettingsPageDataMasking:
    def test_provider_secrets_masked_for_browser(self, monkeypatch):
        """provider_settings_view masks sensitive fields in FT_CONFIG."""
        from lookups.config import MASK, provider_settings_view
        from lookups.providers.opensky.config import PROVIDER as OPENSKY

        view = provider_settings_view(
            OPENSKY, {"client_id": "cid", "client_secret": "S3CR3T"}
        )
        assert view["client_id"] == "cid"
        assert view["client_secret"] == MASK
        assert "S3CR3T" not in str(view)

    def test_mask_token_semantics_through_apply(self):
        from lookups.config import MASK, apply_submitted_settings
        from lookups.providers.opensky.config import PROVIDER as OPENSKY

        stored = {"client_id": "cid", "client_secret": "KEEPME"}
        clean, changed = apply_submitted_settings(
            OPENSKY, stored, {"client_secret": MASK}
        )
        assert clean["client_secret"] == "KEEPME"
        assert changed is False

        clean, changed = apply_submitted_settings(
            OPENSKY, stored, {"client_secret": ""}
        )
        assert clean["client_secret"] == ""
        assert changed is True


# ---------------------------------------------------------------------------
# Per-provider guidance (registration links) on the settings page
# ---------------------------------------------------------------------------


class TestProviderGuidance:
    def test_settings_page_carries_registration_links(self):
        """The lost-on-refactor signup guidance renders with its links."""
        from web.app import app

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["authenticated"] = True

        html = client.get("/settings").get_data(as_text=True)
        assert "https://rapidapi.com/aedbx-aedbx/api/aerodatabox" in html
        assert "https://opensky-network.org/login" in html
        assert "adsb.im" in html
        assert (
            "register with AeroDataBox directly" in html
        )  # ' is \\u0027-escaped in the JSON blob
        assert "30-second polling" in html


# ---------------------------------------------------------------------------
# /cached-data page (SQLite-backed route cache listing)
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_cache(tmp_path, monkeypatch):
    """Point lookups.cache at a temp database for the request under test."""
    import lookups.cache as rc

    monkeypatch.setattr(rc, "DB_PATH", tmp_path / "cache.sqlite3")
    monkeypatch.setattr(rc, "LEGACY_JSON_PATH", tmp_path / "routes_cache.json")
    monkeypatch.setattr(rc, "_conn", None)
    yield rc
    if rc._conn is not None:
        rc._conn.close()
        rc._conn = None


class TestCachedDataPage:
    def test_route_rows_render_from_sqlite(self, isolated_cache):
        rc = isolated_cache
        rc.put(
            "BAW123",
            {"plane": "A320", "origin": "LHR", "destination": "GLA"},
            kind=rc.KIND_ROUTE,
        )
        rc.put("ZZZ999", {"miss": True}, ttl=rc.CACHE_TTL_MISS, kind=rc.KIND_ROUTE)

        from web.app import app

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["authenticated"] = True

        html = client.get("/cached-data").get_data(as_text=True)
        assert "BAW123" in html
        assert "A320" in html
        assert "ZZZ999" in html  # miss entries are listed too

    def test_routes_delete_removes_entries(self, isolated_cache):
        rc = isolated_cache
        rc.put("BAW123", {"origin": "LHR", "destination": "GLA"}, kind=rc.KIND_ROUTE)
        rc.put("400f5a", {"plane": "A320"}, kind=rc.KIND_AIRCRAFT)

        from web.app import app

        client = app.test_client()
        with client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["csrf_token"] = "tok"

        resp = client.post(
            "/cached-data/routes/delete",
            data={"keys": "BAW123", "csrf_token": "tok"},
        )
        assert resp.status_code == 302
        assert rc.get("BAW123", rc.KIND_ROUTE) is None
        # kind-scoped delete: the airframe entry (400f5a) survives
        assert rc.get("400f5a", rc.KIND_AIRCRAFT) is not None


# ---------------------------------------------------------------------------
# /api - provider usage page + JSON API
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_usage(tmp_path, monkeypatch):
    """Point the usage tally at a temp db with fresh in-memory state."""
    import lookups.usage as ru

    monkeypatch.setattr(ru, "DB_PATH", tmp_path / "usage.sqlite3")
    monkeypatch.setattr(ru, "_conn", None)
    monkeypatch.setattr(ru, "_providers_dirty", {})
    monkeypatch.setattr(ru, "_cache_dirty", {})
    monkeypatch.setattr(ru, "_last_flush", 0.0)
    yield ru
    if ru._conn is not None:
        ru._conn.close()
        ru._conn = None


def _authenticated_client():
    from web.app import app

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["csrf_token"] = "tok"
    return client


class TestStatusApi:
    def test_page_renders_totals_and_link_tile_exists(self, isolated_usage):
        ru = isolated_usage
        ru.record("routes", "hexdb", "attempt", 5)
        ru.record("routes", "hexdb", "no_result", 2)
        ru.record_cache("aircraft", "hit")
        ru.record("flights", "tar1090", "api_call")
        ru.record("flights", "tar1090", "aircraft", 7)

        html = _authenticated_client().get("/api").get_data(as_text=True)
        assert "API Usage" in html
        assert "hexdb" in html
        assert "tar1090" in html
        assert '/api"' in html

    def test_status_page_links_to_usage(self):
        html = _authenticated_client().get("/status").get_data(as_text=True)
        assert '/api"' in html

    def test_json_shape_matches_summary(self, isolated_usage):
        ru = isolated_usage
        ru.record("routes", "hexdb", "attempt", 5)
        ru.record("flights", "tar1090", "api_call")
        ru.record("flights", "tar1090", "aircraft", 7)
        ru.record_cache("routes", "miss")

        resp = _authenticated_client().get("/api/json")
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["cache"]["routes"] == {"hits": 0, "misses": 1}
        assert data["providers"]["routes"]["hexdb"] == {"attempts": 5, "no_results": 0}
        assert data["providers"]["flights"]["tar1090"] == {
            "api_calls": 1,
            "aircraft": 7,
        }
        assert data["range"] == {"start": None, "end": None}

    def test_range_url_filters_totals(self, isolated_usage, monkeypatch):
        ru = isolated_usage
        monkeypatch.setattr(ru, "_today", lambda: "2026-08-01")
        ru.record("routes", "hexdb", "attempt", 10)
        monkeypatch.setattr(ru, "_today", lambda: "2026-08-20")
        ru.record("routes", "hexdb", "attempt", 4)
        ru.flush()

        data = (
            _authenticated_client()
            .get("/api/2026-08-01/2026-08-01/json")
            .get_json()
        )
        assert data["providers"]["routes"]["hexdb"]["attempts"] == 10
        assert data["range"] == {"start": "2026-08-01", "end": "2026-08-01"}

    def test_malformed_dates_return_400(self, isolated_usage):
        client = _authenticated_client()
        assert client.get("/api/foo/bar/json").status_code == 400
        assert client.get("/api/foo/bar").status_code == 400

    def test_reversed_range_is_swapped(self, isolated_usage, monkeypatch):
        ru = isolated_usage
        monkeypatch.setattr(ru, "_today", lambda: "2026-08-20")
        ru.record("routes", "hexdb", "attempt")
        ru.flush()

        data = (
            _authenticated_client()
            .get("/api/2026-08-31/2026-08-01/json")
            .get_json()
        )
        assert data["range"]["start"] == "2026-08-01"
        assert data["providers"]["routes"]["hexdb"]["attempts"] == 1

    def test_login_required(self, isolated_usage, monkeypatch):
        # remove the existing isolation fixture patches for a clean look? no -
        # just bypass the authenticated session
        from web.app import app

        client = app.test_client()
        resp = client.get("/api")
        assert resp.status_code == 302  # redirected to login

    def test_clear_empties_tallies(self, isolated_usage):
        ru = isolated_usage
        ru.record("routes", "hexdb", "attempt", 9)
        ru.flush()

        client = _authenticated_client()
        with client.session_transaction() as sess:
            sess["csrf_token"] = "tok"

        resp = client.post("/api/clear", data={"csrf_token": "tok"})
        assert resp.status_code == 302
        assert ru.summary()["providers"]["routes"] == {}

    def test_clear_rejects_bad_csrf(self, isolated_usage):
        client = _authenticated_client()
        resp = client.post("/api/clear", data={"csrf_token": "wrong"})
        assert resp.status_code == 403

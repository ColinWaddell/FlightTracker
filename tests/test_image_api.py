"""
Tests for the Image Upload API routes (web/image_api.py).

Builds a bare Flask app, registers the image API on it and drives it
with the test client - mirroring the session/CSRF keys the main app
uses ("authenticated", "csrf_token").  The module-level INBOX and
KEY_FILE are reset per test so the suite stays hermetic.
"""

import base64

import pytest

from flask import Flask

from web.image_api import register_image_api
from utilities import image_inbox as mod


FRAME = bytes(range(256)) * 24
FRAME_B64 = base64.b64encode(FRAME).decode()


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setattr(mod, "KEY_FILE", tmp_path / "image_api_key.json")
    mod.INBOX.clear()
    instance = Flask(__name__)
    instance.secret_key = "test-secret"
    register_image_api(instance)
    yield instance
    mod.INBOX.clear()


@pytest.fixture
def client(app):
    return app.test_client()


def _login(client, csrf="test-csrf"):
    with client.session_transaction() as sess:
        sess["authenticated"] = True
        sess["csrf_token"] = csrf


def _headers(csrf="test-csrf", api_key=None):
    headers = {}
    if csrf is not None:
        headers["X-CSRF-Token"] = csrf
    if api_key is not None:
        headers["X-API-Key"] = api_key
    return headers


def _post_image(client, api_key, body=None):
    payload = {"ttl": 60, "data": [FRAME_B64]} if body is None else body
    return client.post(
        "/api/image",
        json=payload,
        headers=_headers(api_key=api_key),
    )


def _generate_key(client):
    _login(client)
    resp = client.post("/api/image-key", headers=_headers())
    assert resp.status_code == 200
    return resp.get_json()["key"]


@pytest.fixture
def key(client):
    return _generate_key(client)


# ---------------------------------------------------------------------------
# POST /api/image - auth
# ---------------------------------------------------------------------------


def test_rejected_when_no_key_configured(client):
    resp = _post_image(client, api_key="anything")
    assert resp.status_code == 403
    assert "no API key" in resp.get_json()["error"]


def test_rejected_with_wrong_key(client, key):
    resp = _post_image(client, api_key="not-the-key")
    assert resp.status_code == 401


def test_rejected_with_missing_key_header(client, key):
    resp = _post_image(client, api_key=None)
    assert resp.status_code == 401


def test_accepted_with_valid_key(client, key):
    resp = _post_image(client, api_key=key)
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["frames"] == 1
    assert data["ttl"] == 60
    assert mod.INBOX.current() is not None


def test_rejected_after_revocation(client, key):
    resp = client.delete("/api/image-key", headers=_headers())
    assert resp.status_code == 200
    resp = _post_image(client, api_key=key)
    assert resp.status_code == 403
    assert "no API key" in resp.get_json()["error"]


def test_new_key_invalidates_old(client):
    old = _generate_key(client)
    new = _generate_key(client)
    resp = _post_image(client, api_key=old)
    assert resp.status_code == 401
    resp = _post_image(client, api_key=new)
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/image - validation
# ---------------------------------------------------------------------------


def test_rejected_missing_ttl(client, key):
    resp = _post_image(client, api_key=key, body={"data": [FRAME_B64]})
    assert resp.status_code == 400
    assert "ttl" in resp.get_json()["error"]


def test_rejected_bad_frame_length(client, key):
    short = base64.b64encode(FRAME[:-3]).decode()
    resp = _post_image(client, api_key=key, body={"ttl": 60, "data": [short]})
    assert resp.status_code == 400
    assert "6144" in resp.get_json()["error"]


def test_rejected_non_object_body(client, key):
    resp = client.post(
        "/api/image", json=[1, 2], headers=_headers(api_key=key)
    )
    assert resp.status_code == 400


def test_rejected_invalid_json(client, key):
    resp = client.post(
        "/api/image",
        data="not json",
        headers={**_headers(api_key=key), "Content-Type": "application/json"},
    )
    assert resp.status_code == 400


def test_validation_error_names_the_problem(client, key):
    resp = _post_image(client, api_key=key, body={"ttl": 0, "data": [FRAME_B64]})
    assert resp.status_code == 400
    assert "between 1 and" in resp.get_json()["error"]


def test_failed_submit_does_not_disturb_current(client, key):
    _post_image(client, api_key=key)
    current = mod.INBOX.current()
    resp = _post_image(client, api_key=key, body={"data": [FRAME_B64]})
    assert resp.status_code == 400
    assert mod.INBOX.current() is current


def test_replacement_submission(client, key):
    _post_image(client, api_key=key)
    first = mod.INBOX.current()
    resp = _post_image(client, api_key=key, body={"ttl": 30, "data": [FRAME_B64]})
    assert resp.status_code == 200
    second = mod.INBOX.current()
    assert second is not first
    assert second.ttl_seconds == 30


def test_animation_response_reports_effective_timing(client, key):
    body = {"ttl": 60, "frame_delay": 150, "data": [FRAME_B64] * 2}
    resp = _post_image(client, api_key=key, body=body)
    data = resp.get_json()
    assert data["frame_delay_ms"] == 150
    assert data["frame_hold"] == 2  # 150ms / 80ms -> 2 panel frames
    assert data["effective_frame_delay_ms"] == 160


def test_single_frame_response_has_no_timing_fields(client, key):
    resp = _post_image(client, api_key=key)
    data = resp.get_json()
    assert "frame_hold" not in data
    assert "effective_frame_delay_ms" not in data


def test_missing_json_content_type(client, key):
    resp = client.post(
        "/api/image",
        data="garbage",
        headers={**_headers(api_key=key), "Content-Type": "text/plain"},
    )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Key management endpoints
# ---------------------------------------------------------------------------


def test_key_status_requires_auth(client):
    resp = client.get("/api/image-key")
    assert resp.status_code == 401


def test_key_status_false_by_default(client):
    _login(client)
    resp = client.get("/api/image-key")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["configured"] is False
    assert data["key"] is None


def test_key_status_true_after_generate(client, key):
    _login(client)
    resp = client.get("/api/image-key")
    assert resp.get_json()["configured"] is True


def test_key_generate_requires_csrf(client):
    _login(client)
    resp = client.post("/api/image-key")
    assert resp.status_code == 403


def test_key_generate_wrong_csrf(client):
    _login(client, csrf="real")
    resp = client.post("/api/image-key", headers=_headers(csrf="forged"))
    assert resp.status_code == 403


def test_key_generate_returns_key(client):
    _login(client)
    resp = client.post("/api/image-key", headers=_headers())
    assert resp.status_code == 200
    key = resp.get_json()["key"]
    assert len(key) >= 20
    assert mod.api_key_configured() is True
    assert mod.get_api_key() == key


def test_key_status_returns_key(client, key):
    _login(client)
    resp = client.get("/api/image-key")
    assert resp.get_json()["key"] == key


def test_key_revoke(client, key):
    _login(client)
    resp = client.delete("/api/image-key", headers=_headers())
    assert resp.status_code == 200
    assert mod.api_key_configured() is False


def test_key_delete_requires_csrf(client, key):
    _login(client)
    resp = client.delete("/api/image-key")
    assert resp.status_code == 403
    assert mod.api_key_configured() is True


def test_key_generate_requires_auth(client):
    resp = client.post("/api/image-key", headers=_headers())
    assert resp.status_code == 401
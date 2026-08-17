"""Tests for the backup import/export feature.

Covers:
- utilities.updater.compare_versions
- web.app.build_backup_dict
- web.app.parse_backup_json
- web.app routes: /backup/export, /backup/restore (GET/POST), /backup/restore/apply
"""

from __future__ import annotations

import io
import json
from unittest.mock import MagicMock, patch

import pytest

from version import VERSION

# ---------------------------------------------------------------------------
# compare_versions
# ---------------------------------------------------------------------------


class TestCompareVersions:
    def test_older(self):
        from utilities.updater import compare_versions

        assert compare_versions([1, 0, 0], [2, 6, 2]) == -1

    def test_equal(self):
        from utilities.updater import compare_versions

        assert compare_versions([2, 6, 2], [2, 6, 2]) == 0

    def test_newer(self):
        from utilities.updater import compare_versions

        assert compare_versions([9, 9, 9], [2, 6, 2]) == 1

    def test_different_length_equal(self):
        from utilities.updater import compare_versions

        assert compare_versions([2, 6], [2, 6, 0]) == 0

    def test_different_length_newer(self):
        from utilities.updater import compare_versions

        assert compare_versions([2, 6, 1], [2, 6]) == 1

    def test_different_length_older(self):
        from utilities.updater import compare_versions

        assert compare_versions([2, 5], [2, 6, 0]) == -1

    def test_major_takes_precedence(self):
        from utilities.updater import compare_versions

        assert compare_versions([3, 0, 0], [2, 9, 9]) == 1


# ---------------------------------------------------------------------------
# build_backup_dict
# ---------------------------------------------------------------------------


class TestBuildBackupDict:
    def test_returns_copy_of_config(self):
        from web.app import build_backup_dict

        cfg = MagicMock()
        cfg.as_dict.return_value = {"flight_lat": 55.0, "flight_lng": -4.0}

        result = build_backup_dict(cfg)

        assert result["flight_lat"] == 55.0
        assert result["flight_lng"] == -4.0

    def test_version_tagged_with_current_version(self):
        from web.app import build_backup_dict

        cfg = MagicMock()
        cfg.as_dict.return_value = {"flight_lat": 55.0}

        result = build_backup_dict(cfg)

        assert result["_version"] == list(VERSION)

    def test_overwrites_stale_version(self):
        from web.app import build_backup_dict

        cfg = MagicMock()
        cfg.as_dict.return_value = {"flight_lat": 55.0, "_version": [1, 0, 0]}

        result = build_backup_dict(cfg)

        assert result["_version"] == list(VERSION)

    def test_does_not_mutate_original(self):
        from web.app import build_backup_dict

        cfg = MagicMock()
        original = {"flight_lat": 55.0, "_version": [1, 0, 0]}
        cfg.as_dict.return_value = original

        result = build_backup_dict(cfg)

        assert original["_version"] == [1, 0, 0]
        assert result["_version"] == list(VERSION)


# ---------------------------------------------------------------------------
# parse_backup_json
# ---------------------------------------------------------------------------


class TestParseBackupJson:
    def test_valid_with_version(self):
        from web.app import parse_backup_json

        raw = json.dumps({"flight_lat": 55.0, "_version": [1, 2, 3]}).encode()
        data, version, error = parse_backup_json(raw)

        assert error is None
        assert data == {"flight_lat": 55.0, "_version": [1, 2, 3]}
        assert version == [1, 2, 3]

    def test_valid_without_version(self):
        from web.app import parse_backup_json

        raw = json.dumps({"flight_lat": 55.0}).encode()
        data, version, error = parse_backup_json(raw)

        assert error is None
        assert data == {"flight_lat": 55.0}
        assert version is None

    def test_empty_dict_accepted(self):
        from web.app import parse_backup_json

        data, version, error = parse_backup_json(b"{}")

        assert error is None
        assert data == {}
        assert version is None

    def test_malformed_json(self):
        from web.app import parse_backup_json

        data, version, error = parse_backup_json(b"not json at all")

        assert error is not None
        assert data is None
        assert version is None

    def test_non_dict_top_level(self):
        from web.app import parse_backup_json

        data, version, error = parse_backup_json(b"[1, 2, 3]")

        assert error is not None
        assert data is None
        assert version is None

    def test_non_dict_string(self):
        from web.app import parse_backup_json

        data, version, error = parse_backup_json(b'"hello"')

        assert error is not None
        assert data is None

    def test_version_not_a_list(self):
        from web.app import parse_backup_json

        raw = json.dumps({"_version": "2.6.2"}).encode()
        data, version, error = parse_backup_json(raw)

        assert error is None
        assert version is None

    def test_version_list_with_non_ints(self):
        from web.app import parse_backup_json

        raw = json.dumps({"_version": [2, "6", 2]}).encode()
        data, version, error = parse_backup_json(raw)

        assert error is None
        assert version is None

    def test_empty_bytes(self):
        from web.app import parse_backup_json

        data, version, error = parse_backup_json(b"")

        assert error is not None
        assert data is None


# ---------------------------------------------------------------------------
# Web route tests
# ---------------------------------------------------------------------------


@pytest.fixture
def web_client(tmp_path, monkeypatch):
    """Flask test client with Config and backup paths pointed at tmp_path.

    web.app reads Config.instance().web_port at import time, so we patch
    Config before importing.  The module is cached after first import, so
    we also reset the relevant module-level path constants.
    """
    # Patch Config.instance to avoid touching the real config.json.
    mock_cfg = MagicMock()
    mock_cfg.web_port = 8584
    mock_cfg.web_password_hash = ""
    mock_cfg.as_dict.return_value = {"flight_lat": 55.0, "_version": list(VERSION)}
    mock_cfg.is_in_brightness_schedule.return_value = False
    mock_cfg.brightness_schedule_window = (None, None)

    with (
        patch("setup.configuration.Config.instance", return_value=mock_cfg),
        patch("setup.configuration.Config") as MockConfig,
    ):
        MockConfig.instance.return_value = mock_cfg

        import web.app as web_app

        # Point the backup file paths at tmp_path.
        monkeypatch.setattr(web_app, "PLATFORM_DATA_DIR", tmp_path)
        monkeypatch.setattr(
            web_app, "CONFIG_UPDATE_PATH", tmp_path / "config-update.json"
        )
        monkeypatch.setattr(
            web_app, "CONFIG_BACKUP_PATH", tmp_path / "config-backup.json"
        )
        monkeypatch.setattr(
            web_app, "IMPORT_IN_PROGRESS_MARKER", tmp_path / ".import-in-progress"
        )
        monkeypatch.setattr(
            web_app, "IMPORT_FAILED_MARKER", tmp_path / ".import-failed"
        )
        monkeypatch.setattr(web_app, "CONFIG_PATH", tmp_path / "config.json")

        web_app.app.config["TESTING"] = True
        web_app.app.secret_key = "test-secret"

        client = web_app.app.test_client()

        # Log in + establish CSRF token.
        with client.session_transaction() as sess:
            sess["authenticated"] = True
            sess["csrf_token"] = "test-csrf"

        yield client, web_app, mock_cfg, tmp_path


class TestBackupExport:
    def test_export_downloads_json(self, web_client):
        client, web_app, mock_cfg, tmp_path = web_client

        resp = client.get("/backup/export")

        assert resp.status_code == 200
        assert resp.mimetype == "application/json"
        assert "attachment" in resp.headers["Content-Disposition"]
        assert "config-" in resp.headers["Content-Disposition"]
        assert ".json" in resp.headers["Content-Disposition"]

        payload = json.loads(resp.data)
        assert payload["flight_lat"] == 55.0
        assert payload["_version"] == list(VERSION)

    def test_export_includes_api_keys(self, web_client):
        """Backup export must NOT redact secrets (unlike /debug-config)."""
        client, web_app, mock_cfg, tmp_path = web_client
        mock_cfg.as_dict.return_value = {
            "weatherapi_key": "secret-key-123",
            "_version": list(VERSION),
        }

        resp = client.get("/backup/export")
        payload = json.loads(resp.data)

        assert payload["weatherapi_key"] == "secret-key-123"

    def test_export_requires_login(self, web_client):
        client, _, _, _ = web_client

        with client.session_transaction() as sess:
            sess["authenticated"] = False

        resp = client.get("/backup/export")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


class TestBackupRestoreGet:
    def test_restore_page_loads(self, web_client):
        client, _, _, _ = web_client

        resp = client.get("/backup/restore")

        assert resp.status_code == 200
        assert b"overwrite" in resp.data.lower() or b"settings" in resp.data.lower()

    def test_restore_requires_login(self, web_client):
        client, _, _, _ = web_client

        with client.session_transaction() as sess:
            sess["authenticated"] = False

        resp = client.get("/backup/restore")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


class TestBackupRestorePost:
    def _upload(self, client, data, csrf="test-csrf"):
        return client.post(
            "/backup/restore",
            data={
                "csrf_token": csrf,
                "backup_file": (io.BytesIO(data), "backup.json"),
            },
            content_type="multipart/form-data",
        )

    def test_valid_upload_shows_confirm(self, web_client):
        client, _, _, _ = web_client
        raw = json.dumps({"flight_lat": 99.0, "_version": list(VERSION)}).encode()

        resp = self._upload(client, raw)

        assert resp.status_code == 200
        assert b"confirm" in resp.data.lower() or b"import" in resp.data.lower()

    def test_no_file_selected(self, web_client):
        client, _, _, _ = web_client

        resp = client.post(
            "/backup/restore",
            data={"csrf_token": "test-csrf"},
            content_type="multipart/form-data",
        )

        assert resp.status_code == 400
        assert b"no file" in resp.data.lower()

    def test_malformed_json(self, web_client):
        client, _, _, _ = web_client

        resp = self._upload(client, b"not json")

        assert resp.status_code == 400
        assert b"not valid json" in resp.data.lower()

    def test_non_dict_json(self, web_client):
        client, _, _, _ = web_client

        resp = self._upload(client, b"[1, 2, 3]")

        assert resp.status_code == 400
        assert b"not a valid config" in resp.data.lower()

    def test_invalid_csrf(self, web_client):
        client, _, _, _ = web_client
        raw = json.dumps({"flight_lat": 99.0}).encode()

        resp = self._upload(client, raw, csrf="wrong")

        assert resp.status_code == 403

    def test_older_version_warning(self, web_client):
        client, _, _, _ = web_client
        raw = json.dumps({"_version": [1, 0, 0]}).encode()

        resp = self._upload(client, raw)

        assert resp.status_code == 200
        assert b"older version" in resp.data.lower()

    def test_newer_version_warning(self, web_client):
        client, _, _, _ = web_client
        raw = json.dumps({"_version": [9, 9, 9]}).encode()

        resp = self._upload(client, raw)

        assert resp.status_code == 200
        assert b"newer version" in resp.data.lower()

    def test_matching_version_no_warning(self, web_client):
        client, _, _, _ = web_client
        raw = json.dumps({"_version": list(VERSION)}).encode()

        resp = self._upload(client, raw)

        assert resp.status_code == 200
        assert b"version_warning" not in resp.data

    def test_missing_version_warning(self, web_client):
        client, _, _, _ = web_client
        raw = json.dumps({"flight_lat": 1.0}).encode()

        resp = self._upload(client, raw)

        assert resp.status_code == 200
        assert b"does not contain a version" in resp.data.lower()

    def test_stashes_pending_backup(self, web_client):
        client, _, _, tmp_path = web_client
        raw = json.dumps({"flight_lat": 99.0, "_version": [1, 0, 0]}).encode()

        self._upload(client, raw)

        stash_files = list(tmp_path.glob(".pending-backup-*.json"))
        assert len(stash_files) == 1
        stashed = json.loads(stash_files[0].read_text())
        assert stashed["flight_lat"] == 99.0


class TestBackupRestoreApply:
    def _stage(self, client, tmp_path, data):
        """Stage a backup via the upload endpoint and return the nonce."""
        raw = json.dumps(data).encode()
        client.post(
            "/backup/restore",
            data={
                "csrf_token": "test-csrf",
                "backup_file": (io.BytesIO(raw), "backup.json"),
            },
            content_type="multipart/form-data",
        )
        stash_files = list(tmp_path.glob(".pending-backup-*.json"))
        assert stash_files, "upload should have staged a backup"
        return stash_files[0]

    def test_apply_writes_config_update(self, web_client, monkeypatch):
        client, web_app, _, tmp_path = web_client
        self._stage(client, tmp_path, {"flight_lat": 77.0, "_version": [1, 0, 0]})

        # Prevent actual os.execv restart.
        restarted = []
        monkeypatch.setattr(
            web_app, "restart_after", lambda delay=1.0: restarted.append(delay)
        )

        resp = client.post(
            "/backup/restore/apply",
            data={"csrf_token": "test-csrf"},
        )

        assert resp.status_code == 200
        assert restarted == [1.0]
        update_path = tmp_path / "config-update.json"
        assert update_path.exists()
        written = json.loads(update_path.read_text())
        assert written["flight_lat"] == 77.0

    def test_apply_cleans_up_stash(self, web_client, monkeypatch):
        client, web_app, _, tmp_path = web_client
        self._stage(client, tmp_path, {"flight_lat": 77.0})

        monkeypatch.setattr(web_app, "restart_after", lambda delay=1.0: None)

        client.post("/backup/restore/apply", data={"csrf_token": "test-csrf"})

        stash_files = list(tmp_path.glob(".pending-backup-*.json"))
        assert stash_files == []

    def test_apply_without_pending_backup(self, web_client, monkeypatch):
        client, web_app, _, _ = web_client
        monkeypatch.setattr(web_app, "restart_after", lambda delay=1.0: None)

        resp = client.post("/backup/restore/apply", data={"csrf_token": "test-csrf"})

        assert resp.status_code == 400
        assert b"no pending backup" in resp.data.lower()

    def test_apply_invalid_csrf(self, web_client, monkeypatch):
        client, web_app, _, tmp_path = web_client
        self._stage(client, tmp_path, {"flight_lat": 77.0})
        monkeypatch.setattr(web_app, "restart_after", lambda delay=1.0: None)

        resp = client.post("/backup/restore/apply", data={"csrf_token": "wrong"})

        assert resp.status_code == 403

    def test_apply_does_not_touch_config_json(self, web_client, monkeypatch):
        """The apply endpoint must never write config.json directly."""
        client, web_app, _, tmp_path = web_client
        self._stage(client, tmp_path, {"flight_lat": 77.0})
        monkeypatch.setattr(web_app, "restart_after", lambda delay=1.0: None)

        client.post("/backup/restore/apply", data={"csrf_token": "test-csrf"})

        config_path = tmp_path / "config.json"
        assert not config_path.exists(), "apply must not create config.json"

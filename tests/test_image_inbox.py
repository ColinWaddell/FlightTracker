"""
Tests for the image inbox + API key store (utilities/image_inbox.py).

ImageInbox uses an injected clock so TTL expiry is tested deterministically
(no monkeypatching of stdlib time - same lesson as the overhead timeout
tests).  The API key store tests repoint the module's KEY_FILE at a
throwaway path so the real platform data dir is never touched.
"""

import base64
import threading

import pytest

from utilities import image_inbox as mod


# A valid frame: 6144 raw RGB bytes.
FRAME = bytes(range(256)) * 24


def b64(payload=None):
    return base64.b64encode(FRAME if payload is None else payload).decode()


def make_payload(**overrides):
    payload = {"ttl": 60, "data": [b64()]}
    payload.update(overrides)
    return payload


@pytest.fixture
def clock_box():
    return {"now": 1000.0}


@pytest.fixture
def inbox(clock_box):
    return mod.ImageInbox(clock=lambda: clock_box["now"])


@pytest.fixture
def key_path(tmp_path, monkeypatch):
    path = tmp_path / "image_api_key.json"
    monkeypatch.setattr(mod, "KEY_FILE", path)
    return path


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"ttl": 0},
        {"ttl": -5},
        {"ttl": 86401},
        {"ttl": 1.5},
        {"ttl": True},
        {"ttl": "60"},
        {"ttl": None},
        {"data": []},
        {"data": None},
        {"data": "notalist"},
        {"loops": 0},
        {"loops": -1},
        {"loops": True},
        {"loops": 2.5},
        {"frame_delay": 5},
        {"frame_delay": 60001},
        {"frame_delay": "500"},
    ],
)
def test_rejects_bad_overrides(inbox, overrides):
    with pytest.raises(mod.ImageSubmissionError):
        inbox.submit(make_payload(**overrides))


def test_ttl_required(inbox):
    with pytest.raises(mod.ImageSubmissionError, match="ttl"):
        inbox.submit({"data": [b64()]})


def test_rejects_non_object(inbox):
    with pytest.raises(mod.ImageSubmissionError):
        inbox.submit(["nope"])


def test_rejects_bad_frame_length(inbox):
    with pytest.raises(mod.ImageSubmissionError, match="6144"):
        inbox.submit(make_payload(data=[b64(FRAME[:-10])]))


def test_rejects_garbage_base64(inbox):
    with pytest.raises(mod.ImageSubmissionError, match="base64"):
        inbox.submit(make_payload(data=[b64()[:-4] + "!!!!"]))


def test_rejects_non_string_frame(inbox):
    with pytest.raises(mod.ImageSubmissionError):
        inbox.submit(make_payload(data=[FRAME]))


def test_rejects_too_many_frames(inbox):
    with pytest.raises(mod.ImageSubmissionError, match="at most 60"):
        inbox.submit(make_payload(data=[b64()] * 61))


def test_unknown_keys_ignored(inbox):
    inbox.submit(make_payload(future_field="whatever"))
    assert inbox.current() is not None


def test_upper_bounds_accepted(inbox):
    inbox.submit(
        make_payload(ttl=86400, loops=100000, frame_delay=60000)
    )
    current = inbox.current()
    assert current.ttl_seconds == 86400
    assert current.loops == 100000
    assert current.frame_delay_ms == 60000


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------


def test_valid_submission_roundtrip(inbox):
    submission = inbox.submit(make_payload(loops=3, frame_delay=250))
    current = inbox.current()
    assert current is submission
    assert current.frames == [FRAME]
    assert current.loops == 3
    assert current.frame_delay_ms == 250


def test_defaults(inbox):
    inbox.submit(make_payload())
    current = inbox.current()
    assert current.loops is None
    assert current.frame_delay_ms == mod.DEFAULT_FRAME_DELAY_MS
    assert current.ttl_seconds == 60
    assert current.expires_at == 1000.0 + 60


def test_replacement(inbox):
    inbox.submit(make_payload())
    first = inbox.current()
    inbox.submit(make_payload(ttl=30))
    second = inbox.current()
    assert second is not first
    assert second.ttl_seconds == 30


def test_failed_submit_keeps_previous(inbox):
    inbox.submit(make_payload())
    previous = inbox.current()
    with pytest.raises(mod.ImageSubmissionError):
        inbox.submit({"ttl": 0, "data": [b64()]})
    assert inbox.current() is previous


def test_lazy_expiry(inbox, clock_box):
    inbox.submit(make_payload(ttl=10))
    clock_box["now"] = 1009.999
    assert inbox.current() is not None
    clock_box["now"] = 1010.0
    assert inbox.current() is None


def test_resubmit_after_expiry(inbox, clock_box):
    inbox.submit(make_payload(ttl=5))
    clock_box["now"] += 100
    assert inbox.current() is None
    inbox.submit(make_payload(ttl=50))
    assert inbox.current() is not None


def test_clear(inbox):
    inbox.submit(make_payload())
    inbox.clear()
    assert inbox.current() is None


def test_thread_safe_submit_and_read(inbox):
    errors = []

    def writer():
        try:
            for _ in range(50):
                inbox.submit(make_payload())
        except Exception as exc:  # pragma: no cover - surfaces races
            errors.append(exc)

    def reader():
        for _ in range(50):
            inbox.current()

    threads = [threading.Thread(target=writer) for _ in range(4)]
    threads += [threading.Thread(target=reader) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []


# ---------------------------------------------------------------------------
# API key store
# ---------------------------------------------------------------------------


def test_key_generate_and_verify(key_path):
    key = mod.generate_api_key()
    assert mod.api_key_configured() is True
    assert mod.verify_api_key(key) is True
    assert mod.verify_api_key("wrong-key") is False
    # The plaintext key is persisted so the settings UI can display it again.
    assert key in key_path.read_text()
    assert mod.get_api_key() == key


def test_key_generation_revokes_previous(key_path):
    first = mod.generate_api_key()
    second = mod.generate_api_key()
    assert mod.verify_api_key(first) is False
    assert mod.verify_api_key(second) is True


def test_key_revoke(key_path):
    key = mod.generate_api_key()
    mod.revoke_api_key()
    assert mod.api_key_configured() is False
    assert mod.verify_api_key(key) is False


def test_verify_without_key_file(key_path):
    assert mod.api_key_configured() is False
    assert mod.verify_api_key("anything") is False
    assert mod.get_api_key() is None


def test_legacy_hash_only_key_file(key_path):
    """Pre-plaintext releases stored only the SHA-256 hash; verify still works."""
    import hashlib
    import json

    key = "legacy-key"
    key_path.write_text(
        json.dumps({"key_hash": hashlib.sha256(key.encode()).hexdigest()})
    )
    assert mod.api_key_configured() is True
    assert mod.verify_api_key(key) is True
    assert mod.verify_api_key("other") is False
    assert mod.get_api_key() is None  # hash-only: not displayable


def test_verify_with_corrupt_key_file(key_path):
    key_path.write_text("not json at all")
    assert mod.api_key_configured() is False
    assert mod.verify_api_key("anything") is False


def test_generated_keys_unique(key_path):
    keys = {mod.generate_api_key() for _ in range(20)}
    assert len(keys) == 20
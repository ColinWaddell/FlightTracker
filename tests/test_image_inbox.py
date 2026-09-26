"""
Tests for the image inbox + API key store (utilities/image_inbox.py).

ImageInbox uses an injected clock so TTL expiry is tested deterministically
(no monkeypatching of stdlib time - same lesson as the overhead timeout
tests).  The API key is config-backed; key-store tests use the
fresh_config fixture (tests/conftest.py) so nothing touches the real
config.json.
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
    payload = {"data": [b64()]}
    payload.update(overrides)
    return payload


@pytest.fixture
def inbox():
    return mod.ImageInbox()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"data": []},
        {"data": None},
        {"data": "notalist"},
        {"loops": 0},
        {"loops": -1},
        {"loops": True},
        {"loops": 2.5},
        {"frame_ms": 5},
        {"frame_ms": 60001},
        {"frame_ms": "500"},
    ],
)
def test_rejects_bad_overrides(inbox, overrides):
    with pytest.raises(mod.ImageSubmissionError):
        inbox.submit(make_payload(**overrides))


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
    inbox.submit(make_payload(loops=100000, frame_ms=60000))
    current = inbox.current()
    assert current.loops == 100000
    assert current.frame_ms == 60000


# ---------------------------------------------------------------------------
# Behaviour
# ---------------------------------------------------------------------------


def test_valid_submission_roundtrip(inbox):
    submission = inbox.submit(make_payload(loops=3, frame_ms=250))
    current = inbox.current()
    assert current is submission
    assert current.frames == [FRAME]
    assert current.loops == 3
    assert current.frame_ms == 250


def test_defaults(inbox):
    inbox.submit(make_payload())
    current = inbox.current()
    assert current.loops == 1
    assert current.frame_ms == mod.DEFAULT_FRAME_MS


def test_replacement(inbox):
    inbox.submit(make_payload())
    first = inbox.current()
    inbox.submit(make_payload(frame_ms=120))
    second = inbox.current()
    assert second is not first
    assert second.frame_ms == 120


def test_failed_submit_keeps_previous(inbox):
    inbox.submit(make_payload())
    previous = inbox.current()
    with pytest.raises(mod.ImageSubmissionError):
        inbox.submit({"frame_ms": 0, "data": [b64()]})
    assert inbox.current() is previous


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
# API key store (config.json-backed)
# ---------------------------------------------------------------------------


def test_key_generate_and_verify(fresh_config):
    key = mod.generate_api_key()
    assert mod.api_key_configured() is True
    assert mod.verify_api_key(key) is True
    assert mod.verify_api_key("wrong-key") is False
    # The plaintext key is persisted in config.json so the settings UI can
    # display it again.
    assert fresh_config.get("image_api_key") == key
    assert mod.get_api_key() == key


def test_key_generation_revokes_previous(fresh_config):
    first = mod.generate_api_key()
    second = mod.generate_api_key()
    assert mod.verify_api_key(first) is False
    assert mod.verify_api_key(second) is True


def test_key_revoke(fresh_config):
    key = mod.generate_api_key()
    mod.revoke_api_key()
    assert mod.api_key_configured() is False
    assert mod.verify_api_key(key) is False


def test_verify_without_key(fresh_config):
    assert mod.api_key_configured() is False
    assert mod.verify_api_key("anything") is False
    assert mod.get_api_key() is None


def test_generated_keys_unique(fresh_config):
    keys = {mod.generate_api_key() for _ in range(20)}
    assert len(keys) == 20


def test_quantise_frame_ms():
    # Hermetic test config: default display speed -> 80ms per frame.
    assert mod.quantise_frame_ms(80) == (1, 80)
    assert mod.quantise_frame_ms(150) == (2, 160)
    assert mod.quantise_frame_ms(40) == (1, 80)  # below one cycle
    assert mod.quantise_frame_ms(5000) == (62, 4960)  # round(62.5) -> 62

"""
ImageInbox + API key store for the Image Upload API (web/image_api.py).

The inbox is a thread-safe, in-memory store for images pushed to the
display over ``POST /api/image``:

- ``submit()`` validates the payload and stores it, replacing whatever
  was there before (a new upload always takes the screen immediately).
- ``current()`` returns the active submission, or ``None`` once its TTL
  has elapsed (lazily expired, so no background timer is needed).

Submissions are deliberately not persisted - they are lost on restart.

The API key is *not* stored in config.json.  It lives in its own file
under PLATFORM_DATA_DIR (like the TLE cache) so it never appears in
config backups, the /debug-config download, or config imports.  The
key is stored in plaintext (mode 600) so the settings UI can display
it again; older hash-only files keep verifying until the key is
regenerated.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import secrets
import threading
import time

from setup import screen
from setup.configuration import PLATFORM_DATA_DIR

# One frame is raw RGB bytes: WIDTH * HEIGHT pixels, one byte per channel.
FRAME_BYTES = screen.WIDTH * screen.HEIGHT * 3

MAX_FRAMES = 60
MAX_TTL_SECONDS = 86400  # 24h
DEFAULT_FRAME_DELAY_MS = 500
MIN_FRAME_DELAY_MS = 10
MAX_FRAME_DELAY_MS = 60000

# Where the API key hash lives (never in config.json - see module docstring).
KEY_FILE = PLATFORM_DATA_DIR / "image_api_key.json"


class ImageSubmissionError(ValueError):
    """A pushed payload failed validation; the message is user-facing."""


def _require_int(value, name: str, lo: int, hi: int) -> int:
    """Coerce *value* to an int in [lo, hi] or raise ImageSubmissionError."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ImageSubmissionError(f"'{name}' must be an integer")
    if isinstance(value, float) and value != int(value):
        raise ImageSubmissionError(f"'{name}' must be an integer")
    number = int(value)
    if not lo <= number <= hi:
        raise ImageSubmissionError(f"'{name}' must be between {lo} and {hi}")
    return number


def decode_frame(raw) -> bytes:
    """Decode one base64 RGB frame, enforcing the exact panel byte count."""
    if not isinstance(raw, str):
        raise ImageSubmissionError("every entry in 'data' must be a base64 string")
    try:
        decoded = base64.b64decode(raw.strip(), validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ImageSubmissionError(f"invalid base64 frame data: {exc}") from exc
    if len(decoded) != FRAME_BYTES:
        expected_b64 = (FRAME_BYTES + 2) // 3 * 4
        raise ImageSubmissionError(
            f"each frame must be exactly {FRAME_BYTES} raw RGB bytes "
            f"({screen.WIDTH}x{screen.HEIGHT}x3, ~{expected_b64} base64 chars); "
            f"got {len(decoded)}"
        )
    return decoded


class Submission:
    """One accepted image submission."""

    __slots__ = ("frames", "loops", "frame_delay_ms", "expires_at", "ttl_seconds")

    def __init__(
        self,
        frames: list[bytes],
        loops: int | None,
        frame_delay_ms: int,
        ttl_seconds: int,
        received_at: float,
    ):
        self.frames = frames
        self.loops = loops
        self.frame_delay_ms = frame_delay_ms
        self.ttl_seconds = ttl_seconds
        self.expires_at = received_at + ttl_seconds

    def __len__(self) -> int:
        return len(self.frames)


class ImageInbox:
    """Holds the newest accepted submission; thread-safe."""

    def __init__(self, clock=time.time):
        self._lock = threading.Lock()
        self._submission: Submission | None = None
        self._clock = clock

    def submit(self, payload) -> Submission:
        """Validate *payload* and install it as the current submission.

        Raises :class:`ImageSubmissionError` with a user-facing message on
        any validation failure; the previously stored submission (if any)
        is left untouched in that case.
        """
        if not isinstance(payload, dict):
            raise ImageSubmissionError("body must be a JSON object")

        if "ttl" not in payload:
            raise ImageSubmissionError("'ttl' is required")
        ttl = _require_int(payload["ttl"], "ttl", 1, MAX_TTL_SECONDS)

        frames_raw = payload.get("data")
        if not isinstance(frames_raw, list) or not frames_raw:
            raise ImageSubmissionError("'data' must be a non-empty list of frames")
        if len(frames_raw) > MAX_FRAMES:
            raise ImageSubmissionError(f"'data' supports at most {MAX_FRAMES} frames")
        frames = [decode_frame(raw) for raw in frames_raw]

        loops = payload.get("loops")
        if loops is not None:
            loops = _require_int(loops, "loops", 1, 100000)

        frame_delay_ms = payload.get("frame_delay")
        if frame_delay_ms is None:
            frame_delay_ms = DEFAULT_FRAME_DELAY_MS
        else:
            frame_delay_ms = _require_int(
                frame_delay_ms, "frame_delay", MIN_FRAME_DELAY_MS, MAX_FRAME_DELAY_MS
            )

        submission = Submission(
            frames=frames,
            loops=loops,
            frame_delay_ms=frame_delay_ms,
            ttl_seconds=ttl,
            received_at=self._clock(),
        )

        with self._lock:
            self._submission = submission
        return submission

    def current(self) -> Submission | None:
        """The active submission, or None once its TTL has elapsed."""
        with self._lock:
            submission = self._submission
            if submission is not None and self._clock() >= submission.expires_at:
                self._submission = None
                submission = None
            return submission

    def clear(self) -> None:
        """Drop the current submission immediately."""
        with self._lock:
            self._submission = None


# Process-wide singleton.  The Flask thread (web/image_api.py) writes it,
# the display loop (scenes/image/image_scene.py) reads it.
INBOX = ImageInbox()


# ---------------------------------------------------------------------------
# API key store (separate file, never config.json)
# ---------------------------------------------------------------------------


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _load_store() -> dict:
    with open(KEY_FILE, encoding="utf-8") as fh:
        loaded = json.load(fh)
    return loaded if isinstance(loaded, dict) else {}


def generate_api_key() -> str:
    """Create a new API key, store it, and return it.

    The key is stored in plaintext in its own file (mode 600) so the
    settings UI can display it again; it is only ever sent to the API
    in the X-API-Key header.  Generating a new key invalidates the
    previous one.
    """
    key = secrets.token_urlsafe(24)
    store = {"key": key, "created_at": int(time.time())}
    tmp_path = KEY_FILE.with_suffix(KEY_FILE.suffix + ".tmp")
    try:
        PLATFORM_DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(tmp_path, "w", encoding="utf-8") as fh:
            json.dump(store, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_path, KEY_FILE)
        try:
            os.chmod(KEY_FILE, 0o600)
        except OSError:
            pass
    except OSError as exc:
        raise RuntimeError(f"Could not store API key: {exc}") from exc
    return key


def revoke_api_key() -> None:
    """Remove the stored key hash - the API rejects everything afterwards."""
    try:
        KEY_FILE.unlink()
    except OSError:
        pass


def api_key_configured() -> bool:
    """True when an API key (plaintext or legacy hash) is stored."""
    try:
        store = _load_store()
    except (OSError, ValueError):
        return False
    return bool(store.get("key") or store.get("key_hash"))


def get_api_key() -> str | None:
    """The stored plaintext key, or None (absent, or legacy hash-only)."""
    try:
        return _load_store().get("key") or None
    except (OSError, ValueError):
        return None


def verify_api_key(candidate: str) -> bool:
    """Constant-time check of *candidate* against the stored key.

    Accepts both the current plaintext format and the older hash-only
    format, so keys written by earlier versions keep working until the
    key is next regenerated.
    """
    try:
        store = _load_store()
    except (OSError, ValueError):
        return False
    stored_key = store.get("key")
    if stored_key:
        return hmac.compare_digest(str(stored_key), candidate)
    stored_hash = store.get("key_hash", "")
    if stored_hash:
        return hmac.compare_digest(_hash_key(candidate), str(stored_hash))
    return False
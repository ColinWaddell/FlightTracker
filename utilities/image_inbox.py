"""
ImageInbox + API key store for the Image Upload API (web/image_api.py).

The inbox is a thread-safe, in-memory store for images pushed to the
display over ``POST /api/image``:

- ``submit()`` validates the payload and stores it, replacing whatever
  was there before (a new upload always takes the screen immediately).
- ``current()`` returns the newest submission, or ``None`` before the
  first upload (there is no TTL - submissions live until replaced).

Submissions are deliberately not persisted - they are lost on restart.

The API key is stored in config.json like every other setting (key
``image_api_key``); the /debug-config download and the settings page
config snapshot both redact it.
"""

from __future__ import annotations

import base64
import binascii
import hmac
import secrets
import threading

from setup import screen
from setup.configuration import Config

# One frame is raw RGB bytes: WIDTH * HEIGHT pixels, one byte per channel.
FRAME_BYTES = screen.WIDTH * screen.HEIGHT * 3

MAX_FRAMES = 60
DEFAULT_FRAME_MS = 500
MIN_FRAME_MS = 10
MAX_FRAME_MS = 60000


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
    """One accepted image submission.

    The display lifetime is the animation: ``frames`` images each held
    ``frame_ms`` (quantised to render cycles), repeated ``loops``
    times, after which the scene yields back to the normal display.
    """

    __slots__ = ("frames", "loops", "frame_ms")

    def __init__(
        self,
        frames: list[bytes],
        loops: int,
        frame_ms: int,
    ):
        self.frames = frames
        self.loops = loops
        self.frame_ms = frame_ms

    def __len__(self) -> int:
        return len(self.frames)


class ImageInbox:
    """Holds the newest accepted submission; thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        self._submission: Submission | None = None

    def submit(self, payload) -> Submission:
        """Validate *payload* and install it as the current submission.

        Raises :class:`ImageSubmissionError` with a user-facing message on
        any validation failure; the previously stored submission (if any)
        is left untouched in that case.
        """
        if not isinstance(payload, dict):
            raise ImageSubmissionError("body must be a JSON object")

        frames_raw = payload.get("data")
        if not isinstance(frames_raw, list) or not frames_raw:
            raise ImageSubmissionError("'data' must be a non-empty list of frames")
        if len(frames_raw) > MAX_FRAMES:
            raise ImageSubmissionError(f"'data' supports at most {MAX_FRAMES} frames")
        frames = [decode_frame(raw) for raw in frames_raw]

        loops = payload.get("loops")
        loops = 1 if loops is None else _require_int(loops, "loops", 1, 100000)

        frame_ms = payload.get("frame_ms")
        if frame_ms is None:
            frame_ms = DEFAULT_FRAME_MS
        else:
            frame_ms = _require_int(frame_ms, "frame_ms", MIN_FRAME_MS, MAX_FRAME_MS)

        submission = Submission(
            frames=frames,
            loops=loops,
            frame_ms=frame_ms,
        )

        with self._lock:
            self._submission = submission
        return submission

    def current(self) -> Submission | None:
        """The newest accepted submission, or None."""
        with self._lock:
            return self._submission

    def clear(self) -> None:
        """Drop the current submission immediately."""
        with self._lock:
            self._submission = None


# Process-wide singleton.  The Flask thread (web/image_api.py) writes it,
# the display loop (scenes/image/image_scene.py) reads it.
INBOX = ImageInbox()


# ---------------------------------------------------------------------------
# API key store (config.json-backed)
# ---------------------------------------------------------------------------


def _stored_key() -> str:
    """The configured API key."""
    return str(Config.instance().get("image_api_key") or "")


def quantise_frame_ms(frame_ms: int) -> tuple[int, int]:
    """Quantise *frame_ms* to whole display frames.

    The panel renders at frames.PERIOD (scaled by the display speed
    setting), so animation can only change once per render cycle.  ms
    values are rounded to the nearest whole cycle (minimum 1).
    Returns ``(hold, effective_ms)`` where effective_ms is what the
    submission will actually achieve.
    """
    from setup import frames
    from setup.configuration import Config

    period_ms = frames.PERIOD * 1000.0 * Config.instance().display_speed_factor
    hold = max(1, round(frame_ms / period_ms))
    return hold, round(hold * period_ms)


def generate_api_key() -> str:
    """Create a new API key, store it in config.json, and return it.

    The key is stored in plaintext so the settings UI can display it
    again; it is only ever sent to the API in the X-API-Key header.
    Generating a new key invalidates the previous one.
    """
    key = secrets.token_urlsafe(24)
    cfg = Config.instance()
    cfg.set("image_api_key", key)
    cfg.save()
    return key


def revoke_api_key() -> None:
    """Clear the stored key - the API rejects everything afterwards."""
    cfg = Config.instance()
    cfg.set("image_api_key", "")
    cfg.save()


def api_key_configured() -> bool:
    """True when an API key is configured."""
    return bool(_stored_key())


def get_api_key() -> str | None:
    """The configured plaintext key, or None."""
    return _stored_key() or None


def verify_api_key(candidate: str) -> bool:
    """Constant-time check of *candidate* against the configured key."""
    stored = _stored_key()
    if not stored:
        return False
    return hmac.compare_digest(stored.encode(), candidate.encode())

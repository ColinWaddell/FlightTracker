"""
rgbmatrix — desktop dummy implementation.

Drops in as a local package that shadows the real Pi library so the
application can run on macOS/Linux without LED matrix hardware.
Rendering is done via pygame: each 64×32 LED is drawn as a scaled square
with a small gap to simulate the look of the physical panel.

Only the API surface actually used by this codebase is implemented.
"""

from __future__ import annotations

import os
from datetime import datetime

from . import graphics

# ---------------------------------------------------------------------------
# Display constants
# ---------------------------------------------------------------------------

_PIXEL_SIZE = 10  # each LED cell occupies this many screen pixels
_GAP = 1  # dark gap between LED cells (pixels)
_LED_SIZE = _PIXEL_SIZE - _GAP
_BG_COLOUR = (15, 15, 15)  # gap / off-LED colour
_OFF_LED_LEVEL = 8  # brightness of the dim circle shown for off-LEDs
_ANTIALIAS = True  # anti-alias circle edges in the mask
BRIGHTNESS = 1.1  # global brightness boost multiplier (1.0 = no boost)

# Captures (photos & video frame sequences) are saved here
_CAPTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures"
)

_screen = None
_pygame_ready = False
_small_buf = None  # tiny cols×rows Surface (rebuilt per frame)
_mask_surface = None  # full-window multiply mask (built once)
_off_overlay = None  # full-window dim-circle overlay (built once)
_mask_dims = (0, 0)  # (cols, rows) the mask was built for

# Recording state
_recording = False
_rec_dir = None  # folder for the current recording session
_rec_frame = 0  # frame counter within the current recording


# ---------------------------------------------------------------------------
# Options (attribute bag — all values are accepted, most are ignored)
# ---------------------------------------------------------------------------


class RGBMatrixOptions:
    def __init__(self):
        self.hardware_mapping = "adafruit-hat"
        self.rows = 32
        self.cols = 64
        self.chain_length = 1
        self.parallel = 1
        self.row_address_type = 0
        self.multiplexing = 0
        self.pwm_bits = 11
        self.brightness = 100
        self.pwm_lsb_nanoseconds = 130
        self.led_rgb_sequence = "RGB"
        self.pixel_mapper_config = ""
        self.show_refresh_rate = 0
        self.gpio_slowdown = 1
        self.disable_hardware_pulsing = True
        self.drop_privileges = False


# ---------------------------------------------------------------------------
# Canvas
# ---------------------------------------------------------------------------


class FrameCanvas:
    """In-memory pixel buffer matching the 64×32 LED grid."""

    def __init__(self, cols: int, rows: int):
        self._cols = cols
        self._rows = rows
        # Flat list: index = y * cols + x, value = (r, g, b)
        self._buf: list[tuple[int, int, int]] = [(0, 0, 0)] * (cols * rows)

    def SetPixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        if 0 <= x < self._cols and 0 <= y < self._rows:
            self._buf[y * self._cols + x] = (
                max(0, min(255, int(r))),
                max(0, min(255, int(g))),
                max(0, min(255, int(b))),
            )

    def Clear(self) -> None:
        self._buf = [(0, 0, 0)] * (self._cols * self._rows)

    # Not used in this codebase (broken with Pillow 10+) but kept for API compat.
    def SetImage(self, image, offset_x: int = 0, offset_y: int = 0) -> None:
        pass


# ---------------------------------------------------------------------------
# Matrix
# ---------------------------------------------------------------------------


class RGBMatrix:
    def __init__(self, options: RGBMatrixOptions = None):
        if options is None:
            options = RGBMatrixOptions()
        self._rows = options.rows
        self._cols = options.cols
        self._brightness = max(0, min(100, int(options.brightness)))

    @property
    def brightness(self) -> int:
        return self._brightness

    @brightness.setter
    def brightness(self, value: int) -> None:
        self._brightness = max(0, min(100, int(value)))

    def CreateFrameCanvas(self) -> FrameCanvas:
        return FrameCanvas(self._cols, self._rows)

    def SwapOnVSync(self, canvas: FrameCanvas) -> FrameCanvas:
        _render(canvas, self._brightness)
        return canvas


# ---------------------------------------------------------------------------
# pygame renderer — small-buffer → scale → multiply-mask pipeline
# ---------------------------------------------------------------------------


def _ensure_pygame(cols: int, rows: int) -> None:
    global _screen, _pygame_ready
    if _pygame_ready:
        return
    import pygame

    pygame.init()
    w = cols * _PIXEL_SIZE
    h = rows * _PIXEL_SIZE
    _screen = pygame.display.set_mode((w, h))
    pygame.display.set_caption("RGB Matrix — desktop preview")
    _pygame_ready = True

    print(
        "\n"
        "┌──────────────────────────────────────────────────┐\n"
        "│  RGB Matrix simulator — capture keys             │\n"
        "│                                                  │\n"
        "│  P  — save a photo to captures/                  │\n"
        "│  R  — toggle video recording on/off              │\n"
        "└──────────────────────────────────────────────────┘\n"
    )


def _build_mask(cols: int, rows: int) -> None:
    """Build the multiply mask and off-LED overlay (done once at startup)."""
    global _mask_surface, _off_overlay, _mask_dims
    import pygame
    import pygame.gfxdraw

    w = cols * _PIXEL_SIZE
    h = rows * _PIXEL_SIZE

    # Multiply mask: white circle per cell on black.  When multiplied with
    # the scaled colour image, circle areas keep their colour and gaps go
    # black.
    mask = pygame.Surface((w, h))
    mask.fill((0, 0, 0))

    # Off-LED overlay: dim circle per cell.  Added after the multiply so that
    # off-LEDs (which are black after multiply) still show a faint circle.
    overlay = pygame.Surface((w, h))
    overlay.fill((0, 0, 0))

    radius = _LED_SIZE / 2
    off = _OFF_LED_LEVEL

    for y in range(rows):
        cy = int(y * _PIXEL_SIZE + _PIXEL_SIZE / 2)
        for x in range(cols):
            cx = int(x * _PIXEL_SIZE + _PIXEL_SIZE / 2)
            if _ANTIALIAS:
                pygame.gfxdraw.aacircle(mask, cx, cy, int(radius), (255, 255, 255))
                pygame.gfxdraw.filled_circle(mask, cx, cy, int(radius), (255, 255, 255))
                pygame.gfxdraw.aacircle(overlay, cx, cy, int(radius), (off, off, off))
                pygame.gfxdraw.filled_circle(
                    overlay, cx, cy, int(radius), (off, off, off)
                )
            else:
                pygame.draw.circle(mask, (255, 255, 255), (cx, cy), radius)
                pygame.draw.circle(overlay, (off, off, off), (cx, cy), radius)

    _mask_surface = mask
    _off_overlay = overlay
    _mask_dims = (cols, rows)


# ---------------------------------------------------------------------------
# Captures — photos and video frame sequences
# ---------------------------------------------------------------------------


def _timestamp() -> str:
    """Compact sortable timestamp for filenames."""
    return datetime.now().strftime("%Y-%m-%d_%H%M%S")


def _save_photo() -> None:
    """Save the current screen contents as a single PNG."""
    import pygame

    if _screen is None:
        return
    os.makedirs(_CAPTURE_DIR, exist_ok=True)
    path = os.path.join(_CAPTURE_DIR, f"{_timestamp()}.png")
    pygame.image.save(_screen, path)
    print(f"📷  Photo saved: {path}")


def _toggle_recording() -> None:
    """Start or stop a video frame sequence recording."""
    global _recording, _rec_dir, _rec_frame

    if not _recording:
        os.makedirs(_CAPTURE_DIR, exist_ok=True)
        _rec_dir = os.path.join(_CAPTURE_DIR, _timestamp())
        os.makedirs(_rec_dir, exist_ok=True)
        _rec_frame = 0
        _recording = True
        print(f"⏺  Recording started: {_rec_dir}/")
    else:
        print(f"⏹  Recording stopped: {_rec_frame} frames in {_rec_dir}/")
        _recording = False
        _rec_dir = None
        _rec_frame = 0


def _save_video_frame() -> None:
    """Save the current frame as part of an ongoing recording."""
    global _rec_frame
    import pygame

    if not _recording or _screen is None:
        return
    _rec_frame += 1
    path = os.path.join(_rec_dir, f"frame_{_rec_frame:05d}.png")
    pygame.image.save(_screen, path)


def _render(canvas: FrameCanvas, brightness: int) -> None:
    global _small_buf
    import pygame
    import sys

    _ensure_pygame(canvas._cols, canvas._rows)

    # Drain event queue — handle window close and capture keys
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit(0)
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_p:
                _save_photo()
            elif event.key == pygame.K_r:
                _toggle_recording()

    cols = canvas._cols
    rows = canvas._rows
    buf = canvas._buf
    scale = brightness / 100.0 * BRIGHTNESS

    # --- 1. Write LED colours into a tiny cols×rows surface -------------
    if (
        _small_buf is None
        or _small_buf.get_width() != cols
        or _small_buf.get_height() != rows
    ):
        _small_buf = pygame.Surface((cols, rows))
    pa = pygame.PixelArray(_small_buf)
    clamp = lambda v: 255 if v > 255 else (0 if v < 0 else int(v))
    for i, (r, g, b) in enumerate(buf):
        pa[i % cols, i // cols] = (clamp(r * scale), clamp(g * scale), clamp(b * scale))
    del pa  # release PixelArray lock on the surface

    # --- 2. Scale up to full window size (nearest-neighbour) -------------
    pygame.transform.scale(_small_buf, _screen.get_size(), _screen)

    # --- 3. Apply circular multiply mask (built once) -------------------
    if _mask_dims != (cols, rows):
        _build_mask(cols, rows)
    _screen.blit(_mask_surface, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    # --- 4. Add dim off-LED circles so the grid is visible ---------------
    _screen.blit(_off_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    pygame.display.flip()

    # --- 5. Capture frame if recording ---------------------------------
    if _recording:
        _save_video_frame()

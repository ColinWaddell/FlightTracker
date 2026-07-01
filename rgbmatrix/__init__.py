"""
rgbmatrix — desktop dummy implementation.

Drops in as a local package that shadows the real Pi library so the
application can run on macOS/Linux without LED matrix hardware.
Rendering is done via pygame: each 64×32 LED is drawn as a scaled square
with a small gap to simulate the look of the physical panel.

Only the API surface actually used by this codebase is implemented.
"""

from __future__ import annotations

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

_screen = None
_pygame_ready = False
_small_buf = None  # tiny cols×rows Surface (rebuilt per frame)
_mask_surface = None  # full-window multiply mask (built once)
_off_overlay = None  # full-window dim-circle overlay (built once)
_mask_dims = (0, 0)  # (cols, rows) the mask was built for


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


def _render(canvas: FrameCanvas, brightness: int) -> None:
    global _small_buf
    import pygame
    import sys

    _ensure_pygame(canvas._cols, canvas._rows)

    # Drain event queue — handle window close
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit(0)

    cols = canvas._cols
    rows = canvas._rows
    buf = canvas._buf
    scale = brightness / 100.0

    # --- 1. Write LED colours into a tiny cols×rows surface -------------
    if (
        _small_buf is None
        or _small_buf.get_width() != cols
        or _small_buf.get_height() != rows
    ):
        _small_buf = pygame.Surface((cols, rows))
    pa = pygame.PixelArray(_small_buf)
    for i, (r, g, b) in enumerate(buf):
        pa[i % cols, i // cols] = (int(r * scale), int(g * scale), int(b * scale))
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

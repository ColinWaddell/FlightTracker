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

_PIXEL_SIZE = 10   # each LED cell occupies this many screen pixels
_GAP = 1           # dark gap between LED cells (pixels)
_LED_SIZE = _PIXEL_SIZE - _GAP
_BG_COLOUR = (15, 15, 15)   # gap / off-LED colour

_screen = None
_pygame_ready = False


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
# pygame renderer
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


def _render(canvas: FrameCanvas, brightness: int) -> None:
    import pygame
    import sys

    _ensure_pygame(canvas._cols, canvas._rows)

    # Drain event queue — handle window close
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            pygame.quit()
            sys.exit(0)

    scale = brightness / 100.0
    _screen.fill(_BG_COLOUR)

    cols = canvas._cols
    buf = canvas._buf
    for y in range(canvas._rows):
        row_base = y * cols
        py = y * _PIXEL_SIZE
        for x in range(cols):
            r, g, b = buf[row_base + x]
            if r or g or b:
                colour = (int(r * scale), int(g * scale), int(b * scale))
            else:
                colour = (4, 4, 4)   # very dim off-pixel so grid is visible
            pygame.draw.rect(_screen, colour, (x * _PIXEL_SIZE, py, _LED_SIZE, _LED_SIZE))

    pygame.display.flip()

"""
SimulatorPanel - RGBPanel implementation for desktop development.

Uses pygame to render the LED matrix in a window, simulating the look of
the physical panel with circular LEDs on a dark background.  Supports
photo capture (P key) and video recording (R key).

This is the third panel driver alongside rgbpanel_rgbmatrix (Pi 3/4)
and rgbpanel_piomatter (Pi 5).  It's the final fallback in the factory
so the app always runs on a desktop machine.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

from display.rgbpanel import Colour, RGBPanel

# ---------------------------------------------------------------------------
# Display constants
# ---------------------------------------------------------------------------

_PIXEL_SIZE = 10  # each LED cell occupies this many screen pixels
_GAP = 1  # dark gap between LED cells (pixels)
_LED_SIZE = _PIXEL_SIZE - _GAP
_BG_COLOUR = (15, 15, 15)  # gap / off-LED colour
_OFF_LED_LEVEL = 8  # brightness of the dim circle shown for off-LEDs
_ANTIALIAS = True  # anti-alias circle edges in the mask
BRIGHTNESS = 1.0  # global brightness boost multiplier (1.0 = no boost)

# Captures (photos & video frame sequences) are saved here
_CAPTURE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures"
)


# ---------------------------------------------------------------------------
# Canvas - flat pixel buffer matching the LED grid
# ---------------------------------------------------------------------------


class SimulatorCanvas:
    """In-memory pixel buffer matching the LED grid."""

    __slots__ = ("cols", "rows", "buf")

    def __init__(self, cols: int, rows: int):
        self.cols = cols
        self.rows = rows
        # Flat list: index = y * cols + x, value = (r, g, b)
        self.buf: list[tuple[int, int, int]] = [(0, 0, 0)] * (cols * rows)

    def set_pixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        if 0 <= x < self.cols and 0 <= y < self.rows:
            self.buf[y * self.cols + x] = (
                max(0, min(255, int(r))),
                max(0, min(255, int(g))),
                max(0, min(255, int(b))),
            )

    def clear(self) -> None:
        self.buf = [(0, 0, 0)] * (self.cols * self.rows)

    def fill(self, r: int, g: int, b: int) -> None:
        self.buf = [(r, g, b)] * (self.cols * self.rows)


# ---------------------------------------------------------------------------
# BDF font parser
# ---------------------------------------------------------------------------


class _Glyph:
    __slots__ = ("dwidth", "bbx_w", "bbx_h", "bbx_xoff", "bbx_yoff", "rows")

    def __init__(self, dwidth, bbx_w, bbx_h, bbx_xoff, bbx_yoff, rows):
        self.dwidth = dwidth
        self.bbx_w = bbx_w
        self.bbx_h = bbx_h
        self.bbx_xoff = bbx_xoff
        self.bbx_yoff = bbx_yoff
        self.rows = rows


def _parse_bdf(path: str) -> dict[int, _Glyph]:
    """Parse a BDF font file and return a dict mapping code-point → _Glyph."""
    glyphs: dict[int, _Glyph] = {}

    with open(path, encoding="latin-1") as fh:
        lines = fh.readlines()

    encoding = -1
    dwidth = 0
    bbx_w = bbx_h = bbx_xoff = bbx_yoff = 0
    bitmap_lines: list[str] = []
    in_bitmap = False

    for line in lines:
        line = line.rstrip()

        if line.startswith("ENCODING "):
            encoding = int(line.split()[1])
        elif line.startswith("DWIDTH "):
            dwidth = int(line.split()[1])
        elif line.startswith("BBX "):
            parts = line.split()
            bbx_w, bbx_h, bbx_xoff, bbx_yoff = (
                int(parts[1]),
                int(parts[2]),
                int(parts[3]),
                int(parts[4]),
            )
        elif line == "BITMAP":
            in_bitmap = True
            bitmap_lines = []
        elif line == "ENDCHAR":
            if in_bitmap and encoding >= 0:
                rows = []
                bytes_per_row = (bbx_w + 7) // 8
                for hex_row in bitmap_lines:
                    padded = hex_row.ljust(bytes_per_row * 2, "0")
                    val = int(padded[: bytes_per_row * 2], 16)
                    rows.append(val)
                glyphs[encoding] = _Glyph(
                    dwidth,
                    bbx_w,
                    bbx_h,
                    bbx_xoff,
                    bbx_yoff,
                    rows,
                )
            in_bitmap = False
            encoding = -1
        elif in_bitmap:
            bitmap_lines.append(line.strip())

    return glyphs


class SimulatorFont:
    """BDF bitmap font for the simulator."""

    def __init__(self):
        self._glyphs: dict[int, _Glyph] = {}
        self._loaded = False

    def LoadFont(self, path: str) -> None:
        try:
            self._glyphs = _parse_bdf(path)
            self._loaded = True
        except Exception as exc:
            print(f"[SimulatorFont] failed to load {path!r}: {exc}")

    def CharacterWidth(self, codepoint: int) -> int:
        glyph = self._glyphs.get(codepoint)
        return glyph.dwidth if glyph else 0

    def _glyph(self, char: str) -> _Glyph | None:
        cp = ord(char)
        return self._glyphs.get(cp) or self._glyphs.get(ord("?"))


# ---------------------------------------------------------------------------
# Drawing helpers (operate on SimulatorCanvas)
# ---------------------------------------------------------------------------


def _draw_text(canvas, font: SimulatorFont, x: int, y: int, colour, text: str) -> int:
    """Render text onto canvas. Returns total x advance (pixels)."""
    if not font._loaded or not text:
        return 0

    r, g, b = colour.red, colour.green, colour.blue
    cursor_x = x
    start_x = x

    for ch in text:
        glyph = font._glyph(ch)
        if glyph is None:
            continue

        top_y = y - glyph.bbx_yoff - glyph.bbx_h + 1
        bytes_per_row = (glyph.bbx_w + 7) // 8
        total_bits = bytes_per_row * 8

        for i, row_val in enumerate(glyph.rows):
            sy = top_y + i
            for bit in range(glyph.bbx_w):
                if row_val & (1 << (total_bits - 1 - bit)):
                    sx = cursor_x + glyph.bbx_xoff + bit
                    canvas.set_pixel(sx, sy, r, g, b)

        cursor_x += glyph.dwidth

    return cursor_x - start_x


def _draw_line(canvas, x0: int, y0: int, x1: int, y1: int, colour) -> None:
    r, g, b = colour.red, colour.green, colour.blue
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        canvas.set_pixel(x0, y0, r, g, b)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


def _draw_circle(canvas, cx: int, cy: int, radius: int, colour) -> None:
    r, g, b = colour.red, colour.green, colour.blue

    def _plot8(dx, dy):
        canvas.set_pixel(cx + dx, cy + dy, r, g, b)
        canvas.set_pixel(cx - dx, cy + dy, r, g, b)
        canvas.set_pixel(cx + dx, cy - dy, r, g, b)
        canvas.set_pixel(cx - dx, cy - dy, r, g, b)
        canvas.set_pixel(cx + dy, cy + dx, r, g, b)
        canvas.set_pixel(cx - dy, cy + dx, r, g, b)
        canvas.set_pixel(cx + dy, cy - dx, r, g, b)
        canvas.set_pixel(cx - dy, cy - dx, r, g, b)

    x, y = 0, radius
    d = 3 - 2 * radius
    while x <= y:
        _plot8(x, y)
        if d < 0:
            d += 4 * x + 6
        else:
            d += 4 * (x - y) + 10
            y -= 1
        x += 1


def _draw_square(canvas, x0: int, y0: int, x1: int, y1: int, colour) -> None:
    r, g, b = colour.red, colour.green, colour.blue
    for x in range(x0, x1):
        _draw_line(canvas, x, y0, x, y1, Colour(r, g, b))


# ---------------------------------------------------------------------------
# SimulatorPanel
# ---------------------------------------------------------------------------


class SimulatorPanel(RGBPanel):
    """Desktop panel driver using pygame for LED matrix simulation."""

    def __init__(self):
        self._width = 64
        self._height = 32
        self._brightness = 50
        self._screen = None
        self._pygame_ready = False
        self._small_buf = None
        self._mask_surface = None
        self._off_overlay = None
        self._mask_dims = (0, 0)

        # Recording state
        self._recording = False
        self._rec_dir = None
        self._rec_frame = 0

    @property
    def is_pi5(self):
        return False

    # -- RGBPanel interface ------------------------------------------------

    def init_matrix(
        self,
        width=64,
        height=32,
        brightness=50,
        rotation=0,
        hat_pwm=True,
        gpio_slowdown=1,
    ):
        self._width = width
        self._height = height
        self._brightness = brightness

    def create_canvas(self):
        canvas = SimulatorCanvas(self._width, self._height)
        canvas.clear()
        return canvas

    def load_font(self, path):
        font = SimulatorFont()
        font.LoadFont(path)
        return font

    def draw_text(self, canvas, font, x, y, colour, text):
        return _draw_text(canvas, font, x, y, colour, text)

    def draw_line(self, canvas, x0, y0, x1, y1, colour):
        _draw_line(canvas, x0, y0, x1, y1, colour)

    def draw_circle(self, canvas, cx, cy, radius, colour):
        _draw_circle(canvas, cx, cy, radius, colour)

    def set_pixel(self, canvas, x, y, r, g, b):
        canvas.set_pixel(x, y, r, g, b)

    def fill(self, canvas, r, g, b):
        canvas.fill(r, g, b)

    def clear(self, canvas):
        canvas.clear()

    def swap(self, canvas):
        self._render(canvas)
        return canvas

    def set_brightness(self, percent):
        self._brightness = max(0, min(100, percent))

    def draw_square(self, canvas, x0, y0, x1, y1, colour):
        _draw_square(canvas, x0, y0, x1, y1, colour)

    def draw_image(self, canvas, x, y, image):
        """Draw a PIL Image at (x, y), skipping transparent pixels."""
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        rgb = image.convert("RGB")
        alpha = image.split()[3]
        for py in range(image.height):
            for px in range(image.width):
                if alpha.getpixel((px, py)) > 0:
                    r, g, b = rgb.getpixel((px, py))
                    canvas.set_pixel(x + px, y + py, r, g, b)

    def make_colour(self, r, g, b):
        return Colour(r, g, b)

    # -- pygame renderer ---------------------------------------------------

    def _ensure_pygame(self) -> None:
        if self._pygame_ready:
            return
        import pygame

        pygame.init()
        w = self._width * _PIXEL_SIZE
        h = self._height * _PIXEL_SIZE
        self._screen = pygame.display.set_mode((w, h))
        pygame.display.set_caption("RGB Matrix - desktop preview")
        self._pygame_ready = True

        print(
            "\n"
            "┌──────────────────────────────────────────────────┐\n"
            "│  RGB Matrix simulator - capture keys             │\n"
            "│                                                  │\n"
            "│  P  - save a photo to captures/                  │\n"
            "│  R  - toggle video recording on/off              │\n"
            "└──────────────────────────────────────────────────┘\n"
        )

    def _build_mask(self) -> None:
        """Build the multiply mask and off-LED overlay (done once)."""
        import pygame
        import pygame.gfxdraw

        cols = self._width
        rows = self._height
        w = cols * _PIXEL_SIZE
        h = rows * _PIXEL_SIZE

        mask = pygame.Surface((w, h))
        mask.fill((0, 0, 0))

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
                    pygame.gfxdraw.filled_circle(
                        mask, cx, cy, int(radius), (255, 255, 255)
                    )
                    pygame.gfxdraw.aacircle(
                        overlay, cx, cy, int(radius), (off, off, off)
                    )
                    pygame.gfxdraw.filled_circle(
                        overlay, cx, cy, int(radius), (off, off, off)
                    )
                else:
                    pygame.draw.circle(mask, (255, 255, 255), (cx, cy), radius)
                    pygame.draw.circle(overlay, (off, off, off), (cx, cy), radius)

        self._mask_surface = mask
        self._off_overlay = overlay
        self._mask_dims = (cols, rows)

    def _render(self, canvas: SimulatorCanvas) -> None:
        import pygame

        self._ensure_pygame()

        # Drain event queue - handle window close and capture keys
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit(0)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_p:
                    self._save_photo()
                elif event.key == pygame.K_r:
                    self._toggle_recording()

        cols = canvas.cols
        rows = canvas.rows
        buf = canvas.buf
        scale = self._brightness / 100.0 * BRIGHTNESS

        # --- 1. Write LED colours into a tiny colsxrows surface ----------
        if (
            self._small_buf is None
            or self._small_buf.get_width() != cols
            or self._small_buf.get_height() != rows
        ):
            self._small_buf = pygame.Surface((cols, rows))
        pa = pygame.PixelArray(self._small_buf)

        def clamp(v):
            return 255 if v > 255 else (0 if v < 0 else int(v))

        for i, (r, g, b) in enumerate(buf):
            pa[i % cols, i // cols] = (
                clamp(r * scale),
                clamp(g * scale),
                clamp(b * scale),
            )
        del pa  # release PixelArray lock on the surface

        # --- 2. Scale up to full window size (nearest-neighbour) ----------
        pygame.transform.scale(self._small_buf, self._screen.get_size(), self._screen)

        # --- 3. Apply circular multiply mask (built once) ----------------
        if self._mask_dims != (cols, rows):
            self._build_mask()
        self._screen.blit(
            self._mask_surface, (0, 0), special_flags=pygame.BLEND_RGB_MULT
        )

        # --- 4. Add dim off-LED circles so the grid is visible ----------
        self._screen.blit(self._off_overlay, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

        pygame.display.flip()

        # --- 5. Capture frame if recording ------------------------------
        if self._recording:
            self._save_video_frame()

    # -- Captures ----------------------------------------------------------

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().strftime("%Y-%m-%d_%H%M%S")

    def _save_photo(self) -> None:
        import pygame

        if self._screen is None:
            return
        os.makedirs(_CAPTURE_DIR, exist_ok=True)
        path = os.path.join(_CAPTURE_DIR, f"{self._timestamp()}.png")
        pygame.image.save(self._screen, path)
        print(f"📷  Photo saved: {path}")

    def _toggle_recording(self) -> None:
        if not self._recording:
            os.makedirs(_CAPTURE_DIR, exist_ok=True)
            self._rec_dir = os.path.join(_CAPTURE_DIR, self._timestamp())
            os.makedirs(self._rec_dir, exist_ok=True)
            self._rec_frame = 0
            self._recording = True
            print(f"⏺  Recording started: {self._rec_dir}/")
        else:
            print(f"⏹  Recording stopped: {self._rec_frame} frames in {self._rec_dir}/")
            self._recording = False
            self._rec_dir = None
            self._rec_frame = 0

    def _save_video_frame(self) -> None:
        import pygame

        if not self._recording or self._screen is None:
            return
        self._rec_frame += 1
        path = os.path.join(self._rec_dir, f"frame_{self._rec_frame:05d}.png")
        pygame.image.save(self._screen, path)

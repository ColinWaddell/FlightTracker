"""
rgbmatrix.graphics — desktop dummy implementation.

Implements:
    Color       — RGB colour value
    Font        — BDF bitmap font loader
    DrawText    — render a string to a canvas, return x advance
    DrawLine    — Bresenham line
    DrawCircle  — midpoint circle
"""

from __future__ import annotations

import math
from pathlib import Path


# ---------------------------------------------------------------------------
# Color
# ---------------------------------------------------------------------------

class Color:
    """Simple RGB colour, matching the rgbmatrix.graphics.Color API."""

    __slots__ = ("red", "green", "blue")

    def __init__(self, red: int = 0, green: int = 0, blue: int = 0):
        self.red   = max(0, min(255, int(red)))
        self.green = max(0, min(255, int(green)))
        self.blue  = max(0, min(255, int(blue)))

    def __repr__(self) -> str:
        return f"Color({self.red}, {self.green}, {self.blue})"


# ---------------------------------------------------------------------------
# BDF font parser
# ---------------------------------------------------------------------------

class _Glyph:
    __slots__ = ("dwidth", "bbx_w", "bbx_h", "bbx_xoff", "bbx_yoff", "rows")

    def __init__(self, dwidth, bbx_w, bbx_h, bbx_xoff, bbx_yoff, rows):
        self.dwidth   = dwidth    # x advance in pixels
        self.bbx_w    = bbx_w
        self.bbx_h    = bbx_h
        self.bbx_xoff = bbx_xoff
        self.bbx_yoff = bbx_yoff
        self.rows     = rows      # list[int], one int per bitmap row, MSB = leftmost pixel


def _parse_bdf(path: str) -> dict[int, _Glyph]:
    """
    Parse a BDF font file and return a dict mapping Unicode code-point → _Glyph.

    BDF bitmap rows are stored as hex strings.  Each row has ceil(bbx_w / 8)
    bytes; the MSB of byte 0 is the leftmost pixel.
    """
    glyphs: dict[int, _Glyph] = {}

    with open(path, "r", encoding="latin-1") as fh:
        lines = fh.readlines()

    encoding = -1
    dwidth   = 0
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
                int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
            )

        elif line == "BITMAP":
            in_bitmap = True
            bitmap_lines = []

        elif line == "ENDCHAR":
            if in_bitmap and encoding >= 0:
                rows = []
                bytes_per_row = (bbx_w + 7) // 8
                for hex_row in bitmap_lines:
                    # Pad / truncate to expected byte count
                    padded = hex_row.ljust(bytes_per_row * 2, "0")
                    val = int(padded[:bytes_per_row * 2], 16)
                    rows.append(val)
                glyphs[encoding] = _Glyph(dwidth, bbx_w, bbx_h, bbx_xoff, bbx_yoff, rows)
            in_bitmap = False
            encoding = -1

        elif in_bitmap:
            bitmap_lines.append(line.strip())

    return glyphs


# ---------------------------------------------------------------------------
# Font
# ---------------------------------------------------------------------------

class Font:
    """BDF bitmap font.  Matches the rgbmatrix.graphics.Font API."""

    def __init__(self):
        self._glyphs: dict[int, _Glyph] = {}
        self._loaded = False

    def LoadFont(self, path: str) -> None:
        try:
            self._glyphs = _parse_bdf(path)
            self._loaded = True
        except Exception as exc:
            print(f"[rgbmatrix.Font] failed to load {path!r}: {exc}")

    def CharacterWidth(self, codepoint: int) -> int:
        """Return the advance width of a character by Unicode code point.
        Returns 0 if the character is not present in the font."""
        glyph = self._glyphs.get(codepoint)
        return glyph.dwidth if glyph else 0

    def _glyph(self, char: str) -> _Glyph | None:
        cp = ord(char)
        return self._glyphs.get(cp) or self._glyphs.get(ord("?"))


# ---------------------------------------------------------------------------
# DrawText
# ---------------------------------------------------------------------------

def DrawText(canvas, font: Font, x: int, y: int, colour: Color, text: str) -> int:
    """
    Render text onto canvas.

    Parameters
    ----------
    canvas  : FrameCanvas
    font    : Font (BDF)
    x, y    : baseline position (y is where the text baseline sits)
    colour  : Color
    text    : str

    Returns the total x advance (pixels).
    """
    if not font._loaded or not text:
        return 0

    r, g, b = colour.red, colour.green, colour.blue
    cursor_x = x
    start_x  = x

    for ch in text:
        glyph = font._glyph(ch)
        if glyph is None:
            continue

        # For each bitmap row i (0 = top of glyph):
        #   screen_y = y - glyph.bbx_yoff - glyph.bbx_h + 1 + i
        top_y = y - glyph.bbx_yoff - glyph.bbx_h + 1
        bytes_per_row = (glyph.bbx_w + 7) // 8
        total_bits    = bytes_per_row * 8

        for i, row_val in enumerate(glyph.rows):
            sy = top_y + i
            # Shift so that the MSB corresponds to pixel 0
            for bit in range(glyph.bbx_w):
                if row_val & (1 << (total_bits - 1 - bit)):
                    sx = cursor_x + glyph.bbx_xoff + bit
                    canvas.SetPixel(sx, sy, r, g, b)

        cursor_x += glyph.dwidth

    return cursor_x - start_x


# ---------------------------------------------------------------------------
# DrawLine  (Bresenham)
# ---------------------------------------------------------------------------

def DrawLine(canvas, x0: int, y0: int, x1: int, y1: int, colour: Color) -> None:
    r, g, b = colour.red, colour.green, colour.blue
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        canvas.SetPixel(x0, y0, r, g, b)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0  += sx
        if e2 < dx:
            err += dx
            y0  += sy


# ---------------------------------------------------------------------------
# DrawCircle  (midpoint / Bresenham)
# ---------------------------------------------------------------------------

def DrawCircle(canvas, cx: int, cy: int, radius: int, colour: Color) -> None:
    r, g, b = colour.red, colour.green, colour.blue

    def _plot8(dx, dy):
        canvas.SetPixel(cx + dx, cy + dy, r, g, b)
        canvas.SetPixel(cx - dx, cy + dy, r, g, b)
        canvas.SetPixel(cx + dx, cy - dy, r, g, b)
        canvas.SetPixel(cx - dx, cy - dy, r, g, b)
        canvas.SetPixel(cx + dy, cy + dx, r, g, b)
        canvas.SetPixel(cx - dy, cy + dx, r, g, b)
        canvas.SetPixel(cx + dy, cy - dx, r, g, b)
        canvas.SetPixel(cx - dy, cy - dx, r, g, b)

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

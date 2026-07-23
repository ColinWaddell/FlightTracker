"""
Unified BDF font parser and renderer.

Reads .bdf (Bitmap Distribution Format) font files and provides:
  - Glyph:  a single parsed glyph (dwidth, bounding box, pre-decoded bitmap rows)
  - BDFFont: holds parsed glyphs indexed by codepoint, with metrics helpers
  - draw_text(): renders a string onto a canvas, returns advance width

The parser pre-decodes each bitmap row into an integer at load time so
rendering is a simple bit-test loop with no per-frame hex conversion.

draw_text() works with any canvas that exposes one of:
  - set_pixel(x, y, r, g, b)   (SimulatorCanvas / rgbpanel_simulator)
  - putpixel((x, y), (r, g, b)) (PIL Image / rgbpanel_piomatter)

This lets the same .bdf font files and the same renderer be used on
Pi 5 (piomatter/PIL) and on the desktop simulator without duplication.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Glyph:
    """A single BDF glyph with a pre-decoded bitmap.

    Attributes:
        dwidth:    device-width advance (pixels to move right after drawing)
        bbx_w:     bounding-box width
        bbx_h:     bounding-box height
        bbx_xoff:  bounding-box x offset from the pen position
        bbx_yoff:  bounding-box y offset from the baseline (positive = below)
        rows:      list of ints, one per bitmap row (MSB = leftmost pixel)
    """

    dwidth: int
    bbx_w: int
    bbx_h: int
    bbx_xoff: int
    bbx_yoff: int
    rows: list[int] = field(default_factory=list)


class BDFFont:
    """A parsed BDF font with glyph lookup by codepoint.

    Compatible with the rgbmatrix ``graphics.Font`` surface used elsewhere
    in the codebase: ``CharacterWidth(codepoint)`` returns the advance width
    for a single character, matching the C++ binding's method of the same
    name.
    """

    def __init__(self, path: str):
        self.glyphs: dict[int, Glyph] = {}
        self.bounding_box = (0, 0, 0, 0)  # width, height, x_offset, y_offset
        self.ascent = 0
        self.descent = 0
        self._load(path)

    def _load(self, path: str):
        with open(path, encoding="latin-1") as f:
            lines = [line.rstrip("\n") for line in f]

        encoding = -1
        dwidth = 0
        bbx_w = bbx_h = bbx_xoff = bbx_yoff = 0
        bitmap_lines: list[str] = []
        in_bitmap = False

        for line in lines:
            line = line.rstrip()

            if line.startswith("FONTBOUNDINGBOX "):
                parts = line.split()
                self.bounding_box = (
                    int(parts[1]),
                    int(parts[2]),
                    int(parts[3]),
                    int(parts[4]),
                )
            elif line.startswith("FONT_ASCENT "):
                self.ascent = int(line.split()[1])
            elif line.startswith("FONT_DESCENT "):
                self.descent = int(line.split()[1])
            elif line.startswith("ENCODING "):
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
                    self.glyphs[encoding] = Glyph(
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

    def get_glyph(self, codepoint: int) -> Glyph | None:
        """Return the :class:`Glyph` for *codepoint*, or ``None``."""
        return self.glyphs.get(codepoint)

    def CharacterWidth(self, codepoint: int) -> int:
        """Return the advance width for *codepoint* (0 if missing).

        Mirrors the ``graphics.Font.CharacterWidth`` method from the
        rgbmatrix C++ binding so callers can use any font object
        uniformly.
        """
        glyph = self.glyphs.get(codepoint)
        return glyph.dwidth if glyph else 0

    def text_width(self, text: str) -> int:
        """Return the total advance width of *text* in pixels."""
        return sum(self.CharacterWidth(ord(c)) for c in text)


def draw_text(canvas, font: BDFFont, x: int, y: int, colour, text: str) -> int:
    """Draw *text* onto *canvas* at (x, y) using *font*.

    The y coordinate is the **baseline** position, matching the
    rgbmatrix ``graphics.DrawText`` convention.

    The canvas may be either:
      - a PIL ``Image`` (uses ``putpixel``)
      - a ``SimulatorCanvas`` or any object with ``set_pixel(x, y, r, g, b)``

    Returns the total advance width (pixels consumed).
    """
    if not text:
        return 0

    cr, cg, cb = _unpack_colour(colour)

    # Detect canvas type once.
    set_pixel = getattr(canvas, "set_pixel", None)
    if set_pixel is not None:

        def _put(px, py):
            set_pixel(px, py, cr, cg, cb)

    else:
        putpixel = canvas.putpixel

        def _put(px, py):
            putpixel((px, py), (cr, cg, cb))

    advance = 0

    for ch in text:
        glyph = font.get_glyph(ord(ch))

        if glyph is None:
            # Missing glyph - skip by 1 pixel
            advance += 1
            continue

        top_y = y - glyph.bbx_yoff - glyph.bbx_h + 1
        total_bits = ((glyph.bbx_w + 7) // 8) * 8

        for i, row_val in enumerate(glyph.rows):
            sy = top_y + i
            for bit in range(glyph.bbx_w):
                if row_val & (1 << (total_bits - 1 - bit)):
                    _put(x + advance + glyph.bbx_xoff + bit, sy)

        advance += glyph.dwidth

    return advance


def _unpack_colour(colour):
    """Extract (r, g, b) from a colour value.

    Accepts:
      - An object with .red, .green, .blue attributes
      - A plain (r, g, b) tuple
    """
    if hasattr(colour, "red"):
        return colour.red, colour.green, colour.blue
    if isinstance(colour, (tuple, list)) and len(colour) >= 3:
        return colour[0], colour[1], colour[2]
    return 255, 255, 255

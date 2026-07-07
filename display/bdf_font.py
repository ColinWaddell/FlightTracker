"""
Minimal BDF font parser and renderer.

Reads .bdf (Bitmap Distribution Format) font files and provides:
  - BDFFont: holds parsed glyphs indexed by codepoint
  - draw_text(): renders a string onto a PIL Image, returns advance width

This lets us use the existing .bdf font files on Pi 5 (piomatter/PIL)
without converting them to another format.
"""

from PIL import ImageDraw


class BDFFont:
    """A parsed BDF font with glyph lookup by codepoint."""

    def __init__(self, path: str):
        self.glyphs = {}  # codepoint -> glyph dict
        self.bounding_box = (0, 0, 0, 0)  # width, height, x_offset, y_offset
        self.ascent = 0
        self.descent = 0
        self._load(path)

    def _load(self, path: str):
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = [line.rstrip("\n") for line in f]

        i = 0
        current_glyph = None
        in_bitmap = False
        bitmap_rows = []

        while i < len(lines):
            line = lines[i].strip()
            i += 1

            if not line:
                continue

            parts = line.split()

            if parts[0] == "FONTBOUNDINGBOX" and len(parts) >= 5:
                self.bounding_box = (
                    int(parts[1]),
                    int(parts[2]),
                    int(parts[3]),
                    int(parts[4]),
                )

            elif parts[0] == "FONT_ASCENT":
                self.ascent = int(parts[1])

            elif parts[0] == "FONT_DESCENT":
                self.descent = int(parts[1])

            elif parts[0] == "STARTCHAR":
                current_glyph = {
                    "encoding": None,
                    "bbx": None,
                    "dwidth": None,
                    "bitmap": [],
                }
                in_bitmap = False

            elif parts[0] == "ENCODING" and current_glyph is not None:
                current_glyph["encoding"] = int(parts[1])

            elif parts[0] == "DWIDTH" and current_glyph is not None:
                current_glyph["dwidth"] = int(parts[1])

            elif parts[0] == "BBX" and current_glyph is not None:
                current_glyph["bbx"] = (
                    int(parts[1]),
                    int(parts[2]),
                    int(parts[3]),
                    int(parts[4]),
                )

            elif parts[0] == "BITMAP":
                in_bitmap = True
                bitmap_rows = []

            elif parts[0] == "ENDCHAR":
                in_bitmap = False
                if current_glyph is not None:
                    current_glyph["bitmap"] = bitmap_rows
                    enc = current_glyph["encoding"]
                    if enc is not None:
                        self.glyphs[enc] = current_glyph
                    current_glyph = None

            elif in_bitmap:
                # Each line is a hex string representing one row of pixels.
                bitmap_rows.append(line)

    def get_glyph(self, codepoint: int):
        """Return glyph data for a codepoint, or None if not found."""
        return self.glyphs.get(codepoint)


def draw_text(canvas, font: BDFFont, x: int, y: int, colour, text: str) -> int:
    """
    Draw *text* onto a PIL Image *canvas* at (x, y) using *font*.

    The y coordinate is the **baseline** position, matching the
    rgbmatrix graphics.DrawText convention.

    Returns the total advance width (pixels consumed).
    """
    cr, cg, cb = _unpack_colour(colour)
    advance = 0

    for ch in text:
        codepoint = ord(ch)
        glyph = font.get_glyph(codepoint)

        if glyph is None:
            # Missing glyph - skip by 1 pixel
            advance += 1
            continue

        bbx_w, bbx_h, bbx_x, bbx_y = glyph["bbx"] if glyph["bbx"] else (0, 0, 0, 0)
        dwidth = glyph["dwidth"] if glyph["dwidth"] else bbx_w

        # Convert bitmap hex rows to pixels.
        rows = glyph["bitmap"]
        for row_idx, hex_row in enumerate(rows):
            hex_row = hex_row.strip()
            if not hex_row:
                continue

            bits = int(hex_row, 16)
            total_bits = len(hex_row) * 4  # each hex char = 4 bits

            # Align to bbx_w bits (shift right to get the top bbx_w bits)
            if total_bits > bbx_w:
                bits >>= total_bits - bbx_w

            for bit_idx in range(bbx_w):
                if bits & (1 << (bbx_w - 1 - bit_idx)):
                    px = x + advance + bbx_x + bit_idx
                    # y is baseline; bitmap row 0 is top of glyph.
                    # bbx_y is offset from baseline to bottom of bbox.
                    # Top of glyph = y - (bbx_h + bbx_y) + row_idx
                    py = y - (bbx_h + bbx_y) + row_idx
                    if 0 <= px < canvas.width and 0 <= py < canvas.height:
                        canvas.putpixel((px, py), (cr, cg, cb))

        advance += dwidth

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

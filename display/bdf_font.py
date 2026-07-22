"""
Minimal BDF font parser and renderer.

Reads .bdf (Bitmap Distribution Format) font files and provides:
  - BDFFont: holds parsed glyphs indexed by codepoint
  - draw_text(): renders a string onto a PIL Image, returns advance width
  - draw_text_to_target(): renders onto any object with set_pixel(),
    for drivers whose canvas is not a PIL Image

This lets us use the existing .bdf font files on all drivers
(piomatter/PIL, simulator, rgbmatrix) without converting them.
"""


class BDFFont:
    """A parsed BDF font with glyph lookup by codepoint."""

    def __init__(self, path: str):
        self.glyphs = {}  # codepoint -> glyph dict
        self.bounding_box = (0, 0, 0, 0)  # width, height, x_offset, y_offset
        self.ascent = 0
        self.descent = 0
        self._load(path)

    def _load(self, path: str):
        with open(path, encoding="utf-8", errors="replace") as f:
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

    def CharacterWidth(self, codepoint: int) -> int:
        """Return the advance width for a codepoint, or 0 if not found.

        Mirrors the interface of hzeller's graphics.Font.CharacterWidth()
        so callers can use BDFFont as a drop-in replacement.
        """
        glyph = self.glyphs.get(codepoint)
        if glyph is None:
            return 0
        dwidth = glyph["dwidth"]
        if dwidth is not None:
            return dwidth
        bbx = glyph["bbx"]
        return bbx[0] if bbx else 0


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

        advance += _draw_glyph_pil(canvas, glyph, x + advance, y, cr, cg, cb)

    return advance


def draw_text_to_target(target, font: BDFFont, x: int, y: int, colour, text: str,
                        target_width: int, target_height: int) -> int:
    """
    Draw *text* onto a pixel target at (x, y) using *font*.

    The target must implement set_pixel(x, y, r, g, b).
    This is used by drivers whose canvas is not a PIL Image
    (e.g. the rgbmatrix FrameCanvas and the SimulatorCanvas).

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
            advance += 1
            continue

        advance += _draw_glyph_target(
            target, glyph, x + advance, y, cr, cg, cb,
            target_width, target_height
        )

    return advance


def _draw_glyph_pil(canvas, glyph, x: int, y: int, cr, cg, cb) -> int:
    """Render a single glyph onto a PIL Image. Returns dwidth."""
    bbx_w, bbx_h, bbx_x, bbx_y = glyph["bbx"] if glyph["bbx"] else (0, 0, 0, 0)
    dwidth = glyph["dwidth"] if glyph["dwidth"] else bbx_w

    rows = glyph["bitmap"]
    for row_idx, hex_row in enumerate(rows):
        hex_row = hex_row.strip()
        if not hex_row:
            continue

        bits = int(hex_row, 16)
        total_bits = len(hex_row) * 4

        if total_bits > bbx_w:
            bits >>= total_bits - bbx_w

        for bit_idx in range(bbx_w):
            if bits & (1 << (bbx_w - 1 - bit_idx)):
                px = x + bbx_x + bit_idx
                py = y - (bbx_h + bbx_y) + row_idx
                if 0 <= px < canvas.width and 0 <= py < canvas.height:
                    canvas.putpixel((px, py), (cr, cg, cb))

    return dwidth


def _draw_glyph_target(target, glyph, x: int, y: int, cr, cg, cb,
                        target_width: int, target_height: int) -> int:
    """Render a single glyph onto a set_pixel target. Returns dwidth."""
    bbx_w, bbx_h, bbx_x, bbx_y = glyph["bbx"] if glyph["bbx"] else (0, 0, 0, 0)
    dwidth = glyph["dwidth"] if glyph["dwidth"] else bbx_w

    rows = glyph["bitmap"]
    for row_idx, hex_row in enumerate(rows):
        hex_row = hex_row.strip()
        if not hex_row:
            continue

        bits = int(hex_row, 16)
        total_bits = len(hex_row) * 4

        if total_bits > bbx_w:
            bits >>= total_bits - bbx_w

        for bit_idx in range(bbx_w):
            if bits & (1 << (bbx_w - 1 - bit_idx)):
                px = x + bbx_x + bit_idx
                py = y - (bbx_h + bbx_y) + row_idx
                if 0 <= px < target_width and 0 <= py < target_height:
                    target.set_pixel(px, py, cr, cg, cb)

    return dwidth


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

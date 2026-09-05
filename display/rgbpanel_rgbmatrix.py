"""
RGBMatrixPanel - RGBPanel implementation for Pi 3/4 using hzeller's rpi-rgb-led-matrix.

Wraps the rgbmatrix C++ Python bindings (RGBMatrix, RGBMatrixOptions, graphics)
behind the unified RGBPanel interface.
"""

from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

from display.rgbpanel import RGBPanel, channel_permutation

# The rgbmatrix graphics.Font is a C++ binding object with no __dict__, so
# we cannot stash the BDF path on it.  Instead we keep a module-level
# registry mapping each loaded font's id() to the BDF path it was loaded
# from.  Callers that need glyph-level access (e.g. the Scroller, which
# renders pixel columns) can look the path up via bdf_path_for_font() and
# load a BDFFont from the same file.  Fonts live for the program's
# lifetime (held in setup/fonts._loaded_fonts), so id() is stable.
_font_bdf_paths: dict[int, str] = {}


def bdf_path_for_font(font) -> str | None:
    """Return the BDF path a rgbmatrix graphics.Font was loaded from.

    Returns ``None`` for fonts not loaded by :meth:`RGBMatrixPanel.load_font`
    (e.g. a real :class:`display.bdf_font.BDFFont`, which carries its own
    glyph data and doesn't need this lookup).
    """
    return _font_bdf_paths.get(id(font))


class RGBMatrixPanel(RGBPanel):
    """Pi 3/4 panel driver using hzeller rpi-rgb-led-matrix."""

    def __init__(self):
        self.matrix = None
        self._brightness = 50

    @property
    def is_pi5(self):
        return False

    def init_matrix(
        self,
        width=64,
        height=32,
        brightness=50,
        rotation=0,
        hat_pwm=True,
        gpio_slowdown=1,
        colour_order="RGB",
    ):
        options = RGBMatrixOptions()
        options.hardware_mapping = "adafruit-hat-pwm" if hat_pwm else "adafruit-hat"
        options.rows = height
        options.cols = width
        options.chain_length = 1
        options.parallel = 1
        options.row_address_type = 0
        options.multiplexing = 0
        options.pwm_bits = 11
        options.brightness = brightness
        options.pwm_lsb_nanoseconds = 130
        # Validate here (consistent ValueError across backends) before the
        # C++ binding gets a chance to throw its own error lower down.
        channel_permutation(colour_order)
        options.led_rgb_sequence = colour_order
        options.pixel_mapper_config = "Rotate:180" if rotation else ""
        options.show_refresh_rate = 0
        options.gpio_slowdown = gpio_slowdown
        options.disable_hardware_pulsing = True
        options.drop_privileges = True

        self.matrix = RGBMatrix(options=options)
        self._brightness = brightness

    def create_canvas(self):
        canvas = self.matrix.CreateFrameCanvas()
        canvas.Clear()
        return canvas

    def load_font(self, path):
        font = graphics.Font()
        font.LoadFont(path)
        # Record the BDF path so callers that need glyph-level access (e.g.
        # the Scroller, which renders pixel columns) can load a BDFFont from
        # the same file via bdf_path_for_font().  The rgbmatrix graphics.Font
        # is a C++ object with no __dict__, so the path can't live on it.
        _font_bdf_paths[id(font)] = path
        return font

    def _to_color(self, colour):
        """Convert a Colour namedtuple to rgbmatrix graphics.Color if needed."""
        if isinstance(colour, graphics.Color):
            return colour
        return graphics.Color(colour.red, colour.green, colour.blue)

    def draw_text(self, canvas, font, x, y, colour, text):
        return graphics.DrawText(canvas, font, x, y, self._to_color(colour), text)

    def draw_line(self, canvas, x0, y0, x1, y1, colour):
        graphics.DrawLine(canvas, x0, y0, x1, y1, self._to_color(colour))

    def draw_circle(self, canvas, cx, cy, radius, colour):
        graphics.DrawCircle(canvas, cx, cy, radius, self._to_color(colour))

    def set_pixel(self, canvas, x, y, r, g, b):
        canvas.SetPixel(x, y, r, g, b)

    def fill(self, canvas, r, g, b):
        canvas.Fill(r, g, b)

    def clear(self, canvas):
        canvas.Clear()

    def swap(self, canvas):
        return self.matrix.SwapOnVSync(canvas)

    def set_brightness(self, percent):
        self.matrix.brightness = percent
        self._brightness = percent

    def get_brightness(self):
        return self._brightness

    def draw_square(self, canvas, x0, y0, x1, y1, colour):
        c = self._to_color(colour)
        for x in range(x0, x1):
            graphics.DrawLine(canvas, x, y0, x, y1, c)

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
                    canvas.SetPixel(x + px, y + py, r, g, b)

    def make_colour(self, r, g, b):
        return graphics.Color(r, g, b)

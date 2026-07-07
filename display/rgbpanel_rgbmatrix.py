"""
RGBMatrixPanel — RGBPanel implementation for Pi 3/4 using hzeller's rpi-rgb-led-matrix.

Wraps the rgbmatrix C++ Python bindings (RGBMatrix, RGBMatrixOptions, graphics)
behind the unified RGBPanel interface.
"""

from rgbmatrix import graphics, RGBMatrix, RGBMatrixOptions
from display.rgbpanel import RGBPanel, Colour


class RGBMatrixPanel(RGBPanel):
    """Pi 3/4 panel driver using hzeller rpi-rgb-led-matrix."""

    def __init__(self):
        self.matrix = None
        self._brightness = 50

    @property
    def is_pi5(self):
        return False

    def init_matrix(self, width=64, height=32, brightness=50,
                    rotation=0, hat_pwm=True, gpio_slowdown=1):
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
        options.led_rgb_sequence = "RGB"
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
        return font

    def draw_text(self, canvas, font, x, y, colour, text):
        return graphics.DrawText(canvas, font, x, y, colour, text)

    def draw_line(self, canvas, x0, y0, x1, y1, colour):
        graphics.DrawLine(canvas, x0, y0, x1, y1, colour)

    def draw_circle(self, canvas, cx, cy, radius, colour):
        graphics.DrawCircle(canvas, cx, cy, radius, colour)

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

    def draw_square(self, canvas, x0, y0, x1, y1, colour):
        for x in range(x0, x1):
            graphics.DrawLine(canvas, x, y0, x, y1, colour)

    def make_colour(self, r, g, b):
        return graphics.Color(r, g, b)
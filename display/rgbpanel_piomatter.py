"""
PiomatterPanel - RGBPanel implementation for Pi 5 using Adafruit's
adafruit_blinka_raspberry_pi5_piomatter library.

Uses PIL Image as the canvas and the custom BDF parser for font rendering.
Brightness is implemented via colour scaling at swap() time since piomatter
has no hardware brightness control.
"""

import numpy as np
from PIL import Image, ImageDraw

import adafruit_blinka_raspberry_pi5_piomatter as piomatter

from display.rgbpanel import RGBPanel, Colour
from display.bdf_font import BDFFont, draw_text as bdf_draw_text


class PiomatterPanel(RGBPanel):
    """Pi 5 panel driver using adafruit_blinka_raspberry_pi5_piomatter."""

    def __init__(self):
        self.matrix = None
        self.geometry = None
        self.framebuffer = None
        self._width = 64
        self._height = 32
        self._brightness = 50  # 0-100
        self._rotation = 0

    @property
    def is_pi5(self):
        return True

    def init_matrix(
        self,
        width=64,
        height=32,
        brightness=50,
        rotation=0,
        hat_pwm=True,
        gpio_slowdown=1,
    ):
        # hat_pwm and gpio_slowdown are ignored on Pi 5 - piomatter handles
        # PWM and timing internally.
        self._width = width
        self._height = height
        self._brightness = brightness
        self._rotation = rotation

        # Map rotation to piomatter Orientation
        if rotation == 180:
            orientation = piomatter.Orientation.R180
        elif rotation == 90:
            orientation = piomatter.Orientation.CW
        elif rotation == 270:
            orientation = piomatter.Orientation.CCW
        else:
            orientation = piomatter.Orientation.Normal

        self.geometry = piomatter.Geometry(
            width=width,
            height=height,
            n_addr_lines=4,  # 1/4 scan for 32-row panels
            rotation=orientation,
        )

        # Framebuffer is a numpy array that piomatter reads from.
        # We create a PIL Image as the canvas; at swap() time we copy
        # the image data into the framebuffer (with brightness scaling).
        self.framebuffer = np.zeros((height, width, 3), dtype=np.uint8)

        self.matrix = piomatter.PioMatter(
            colorspace=piomatter.Colorspace.RGB888Packed,
            pinout=piomatter.Pinout.AdafruitMatrixBonnet,
            framebuffer=self.framebuffer,
            geometry=self.geometry,
        )

    def create_canvas(self):
        return Image.new("RGB", (self._width, self._height), (0, 0, 0))

    def load_font(self, path):
        return BDFFont(path)

    def draw_text(self, canvas, font, x, y, colour, text):
        return bdf_draw_text(canvas, font, x, y, colour, text)

    def draw_line(self, canvas, x0, y0, x1, y1, colour):
        draw = ImageDraw.Draw(canvas)
        cr, cg, cb = self._unpack_colour(colour)
        draw.line([(x0, y0), (x1, y1)], fill=(cr, cg, cb))

    def draw_circle(self, canvas, cx, cy, radius, colour):
        draw = ImageDraw.Draw(canvas)
        cr, cg, cb = self._unpack_colour(colour)
        bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
        draw.ellipse(bbox, outline=(cr, cg, cb))

    def set_pixel(self, canvas, x, y, r, g, b):
        if 0 <= x < canvas.width and 0 <= y < canvas.height:
            canvas.putpixel((x, y), (r, g, b))

    def fill(self, canvas, r, g, b):
        canvas.paste((r, g, b), [0, 0, canvas.width, canvas.height])

    def clear(self, canvas):
        canvas.paste((0, 0, 0), [0, 0, canvas.width, canvas.height])

    def swap(self, canvas):
        # Apply brightness scaling (0-100 -> 0.0-1.0)
        scale = self._brightness / 100.0

        # Convert PIL Image to numpy array
        pixels = np.asarray(canvas)

        if scale < 1.0:
            pixels = (pixels * scale).astype(np.uint8)

        # Copy into framebuffer and push to display
        self.framebuffer[:] = pixels
        self.matrix.show()

    def set_brightness(self, percent):
        self._brightness = max(0, min(100, percent))

    def draw_square(self, canvas, x0, y0, x1, y1, colour):
        draw = ImageDraw.Draw(canvas)
        cr, cg, cb = self._unpack_colour(colour)
        draw.rectangle([x0, y0, x1, y1], fill=(cr, cg, cb))

    def make_colour(self, r, g, b):
        return Colour(r, g, b)

    @staticmethod
    def _unpack_colour(colour):
        """Extract (r, g, b) from a Colour or tuple."""
        if hasattr(colour, "red"):
            return colour.red, colour.green, colour.blue
        if isinstance(colour, (tuple, list)) and len(colour) >= 3:
            return colour[0], colour[1], colour[2]
        return 255, 255, 255

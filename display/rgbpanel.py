"""
RGBPanel — abstract base class for LED matrix panel drivers.

Provides a unified interface so the rest of the codebase doesn't need
to know whether it's running on a Pi 3/4 (rgbmatrix) or a Pi 5 (piomatter).

Subclasses must implement all abstract methods.
"""

from abc import ABC, abstractmethod
from collections import namedtuple

# Colour type used across all panel drivers.
# This matches the rgbmatrix graphics.Color interface (.red, .green, .blue).
Colour = namedtuple("Colour", ["red", "green", "blue"])


class RGBPanel(ABC):
    """Abstract LED matrix panel driver."""

    @abstractmethod
    def init_matrix(self, width=64, height=32, brightness=50,
                    rotation=0, hat_pwm=True, gpio_slowdown=1):
        """Initialise the matrix hardware. Called once at startup."""
        raise NotImplementedError

    @abstractmethod
    def create_canvas(self):
        """Create and return a fresh canvas (framebuffer) for drawing."""
        raise NotImplementedError

    @abstractmethod
    def load_font(self, path):
        """Load a BDF font file and return a font object."""
        raise NotImplementedError

    @abstractmethod
    def draw_text(self, canvas, font, x, y, colour, text):
        """Draw text at (x, y) with baseline at y. Returns advance width."""
        raise NotImplementedError

    @abstractmethod
    def draw_line(self, canvas, x0, y0, x1, y1, colour):
        """Draw a line from (x0, y0) to (x1, y1)."""
        raise NotImplementedError

    @abstractmethod
    def draw_circle(self, canvas, cx, cy, radius, colour):
        """Draw a circle outline centred at (cx, cy) with given radius."""
        raise NotImplementedError

    @abstractmethod
    def set_pixel(self, canvas, x, y, r, g, b):
        """Set a single pixel to (r, g, b)."""
        raise NotImplementedError

    @abstractmethod
    def fill(self, canvas, r, g, b):
        """Fill the entire canvas with (r, g, b)."""
        raise NotImplementedError

    @abstractmethod
    def clear(self, canvas):
        """Clear the canvas to black."""
        raise NotImplementedError

    @abstractmethod
    def swap(self, canvas):
        """Push the canvas to the display (VSync / show)."""
        raise NotImplementedError

    @abstractmethod
    def set_brightness(self, percent):
        """Set matrix brightness (0-100)."""
        raise NotImplementedError

    @abstractmethod
    def draw_square(self, canvas, x0, y0, x1, y1, colour):
        """Draw a filled rectangle from (x0, y0) to (x1, y1)."""
        raise NotImplementedError

    def make_colour(self, r, g, b):
        """Create a Colour object."""
        return Colour(r, g, b)

    @property
    @abstractmethod
    def is_pi5(self):
        """Return True if this is a Pi 5 driver."""
        raise NotImplementedError
"""
LoadingPulseIndicator - top-right pixel pulses while overhead is fetching.

Replaces the former LoadingPulseScene mixin.  Call tick(frame) once per
frame after the active scene has drawn.
"""

from setup import colours
from setup.configuration import Config

# Default blinker position (used for the classic theme and any unknown theme).
DEFAULT_BLINKER_POSITION = (63, 0)

# Per-theme blinker positions.  Falls back to DEFAULT_BLINKER_POSITION when
# the configured idle theme is not listed here.
BLINKER_POSITIONS = {
    "forecast": (63, 31),
}

BLINKER_STEPS = 10
BLINKER_COLOUR = colours.DARK_GREY


def _blinker_position() -> tuple[int, int]:
    theme = Config.instance().idle_screen_theme
    return BLINKER_POSITIONS.get(theme, DEFAULT_BLINKER_POSITION)


class LoadingPulseIndicator:
    def __init__(self, canvas, panel, overhead):
        self.canvas = canvas
        self.panel = panel
        self.overhead = overhead
        self.count = 0

    def tick(self, frame: int) -> None:
        # Run every 2 frames (matches original @KeyFrame.add(2))
        if frame % 2:
            return

        x, y = _blinker_position()

        if self.overhead.processing:
            brightness = (1 - (self.count / BLINKER_STEPS)) / 2
            brightness = max(0.0, min(1.0, brightness))
            v = int(brightness * BLINKER_COLOUR.red)  # WHITE is (255,255,255)
            self.panel.set_pixel(self.canvas, x, y, v, v, v)
            if self.count >= BLINKER_STEPS - 1:
                self.count = 0
            else:
                self.count += 1
        else:
            self.panel.set_pixel(self.canvas, x, y, 0, 0, 0)
            self.count = 0

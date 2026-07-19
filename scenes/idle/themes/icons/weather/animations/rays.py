"""Sun rays animation — subtle pulsing rays radiating from the icon.

Short ray segments radiate outward from the sprite centre and pulse in
brightness to suggest radiating light.  The rays sit at fixed positions,
so each frame simply overwrites the same pixels — no clearing needed.

Intensity controls ray count and brightness:
    0 — 3 rays, subtle pulse
    1 — 5 rays, medium pulse
    2 — 7 rays, strong pulse
"""

from __future__ import annotations

from display.rgbpanel import Colour
from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

RING0 = [
    Colour(255, 255, 0),
    Colour(200, 200, 0),
    Colour(150, 150, 150),
    Colour(0, 0, 0),
    Colour(0, 0, 0),
    Colour(0, 0, 0),
]
RING1 = [
    Colour(0, 0, 0),
    Colour(255, 255, 0),
    Colour(200, 200, 0),
    Colour(150, 150, 150),
    Colour(0, 0, 0),
    Colour(0, 0, 0),
]
RING2 = [
    Colour(0, 0, 0),
    Colour(0, 0, 0),
    Colour(255, 255, 0),
    Colour(200, 200, 0),
    Colour(150, 150, 150),
    Colour(0, 0, 0),
]


class RaysAnimation(BaseAnimation):
    """Pulsing sun rays radiating from the icon centre."""

    frame_count = 0

    def draw(self, frame_idx: int) -> None:
        index = self.frame_count // 10

        if index >= 4:
            self.frame_count = 0
            index = 0
        else:
            self.frame_count = self.frame_count + 1

        self.draw_circle(7, 7, 5, RING0[index])
        self.draw_circle(7, 7, 6, RING1[index])
        self.draw_circle(7, 7, 7, RING2[index])

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

COLOURS = [Colour(v, v, 0) for v in range(255, 0, -1)] + ([Colour(0, 0, 0)] * 50)
RINGS = 4


class RaysAnimation(BaseAnimation):
    """Pulsing sun rays radiating from the icon centre."""

    frame_count = 0

    def draw(self, frame_idx: int) -> None:
        for ring in range(RINGS):
            self.draw_circle(7, 7, 5 + ring, COLOURS[self.frame_count + ring])

        if self.frame_count >= (len(COLOURS) - RINGS):
            self.frame_count = 0
        else:
            self.frame_count = self.frame_count + 1

"""Sleet animation — mixed rain and snow particles.

Intensity controls particle count:
    0 (light)  — 2 particles (1 rain, 1 snow)
    1 (medium) — 4 particles (2 rain, 2 snow)
    2 (heavy)  — 6 particles (3 rain, 3 snow)

Rain particles fall fast (1px/frame), snow particles fall slower
(1px/2frames) with sway.  The mix creates the characteristic sleet look.
Each frame clears each particle's previous position and lights the new.
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Rain drop colour (light blue)
_RAIN_R, _RAIN_G, _RAIN_B = 80, 130, 220
# Snow flake colour (white)
_SNOW_R, _SNOW_G, _SNOW_B = 230, 230, 240

_RAIN_XS = {0: [4], 1: [3, 10], 2: [2, 7, 12]}
_SNOW_XS = {0: [11], 1: [7, 13], 2: [5, 10, 14]}

_SWAY = (-1, 0, 1, 0)


class SleetAnimation(BaseAnimation):
    """Mixed rain and snow particles."""

    def draw(self, frame_idx: int) -> None:
        h = self.height
        rain_xs = _RAIN_XS.get(self.intensity, _RAIN_XS[1])
        snow_xs = _SNOW_XS.get(self.intensity, _SNOW_XS[1])
        cycle = h * 2

        # Rain drops (fast fall)
        for i, dx in enumerate(rain_xs):
            phase = (i * 2) % h
            row = (frame_idx + phase) % h
            prev_row = (row - 1 + h) % h
            self.set_pixel(dx, prev_row, 0, 0, 0)
            self.set_pixel(dx, row, _RAIN_R, _RAIN_G, _RAIN_B)

        # Snow flakes (slow fall + sway)
        for i, bx in enumerate(snow_xs):
            phase = (i * 3) % cycle
            pos = (frame_idx + phase) % cycle
            row = pos // 2
            prev_row = ((pos - 1) % cycle) // 2
            sway = _SWAY[frame_idx % 4]
            prev_sway = _SWAY[(frame_idx - 1) % 4]
            x = bx + sway
            prev_x = bx + prev_sway
            if 0 <= prev_x < self.width:
                self.set_pixel(prev_x, prev_row, 0, 0, 0)
            if 0 <= x < self.width:
                self.set_pixel(x, row, _SNOW_R, _SNOW_G, _SNOW_B)

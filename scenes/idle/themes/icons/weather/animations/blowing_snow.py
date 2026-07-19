"""Blowing snow animation — wind-driven horizontal snow.

Snow particles move predominantly horizontally (right to left) with a
slight downward drift, simulating strong wind.  Faster and more
horizontal than regular snow.

Intensity controls particle count and wind speed:
    0 — 3 particles, medium wind
    1 — 5 particles, strong wind
    2 — 7 particles, blizzard
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Snow colour
_R = 230
_G = 230
_B = 240

_PARTICLE_YS = {
    0: [1, 2, 4],
    1: [0, 1, 2, 3, 5],
    2: [0, 1, 1, 2, 3, 4, 5],
}

_WIND_SPEED = {0: 2, 1: 3, 2: 4}  # px per frame leftward
_FALL_SPEED = 3  # frames per 1px downward
_REF_HEIGHT = 6


class BlowingSnowAnimation(BaseAnimation):
    """Wind-driven horizontal snow."""

    def draw(self, frame_idx: int) -> None:
        h = self.height
        w = self.width
        ys = _PARTICLE_YS.get(self.intensity, _PARTICLE_YS[1])
        speed = _WIND_SPEED.get(self.intensity, 3)

        ys = [int(y * h / _REF_HEIGHT) for y in ys if y < _REF_HEIGHT]

        for i, py in enumerate(ys):
            phase = (i * 4) % w
            # Move right-to-left: x decreases
            x = w - 1 - (frame_idx * speed + phase) % w
            prev_x = w - 1 - ((frame_idx - 1) * speed + phase) % w

            # Slow downward drift
            row = (py + (frame_idx // _FALL_SPEED)) % h
            prev_row = (py + ((frame_idx - 1) // _FALL_SPEED)) % h

            self.set_pixel(prev_x, prev_row, 0, 0, 0)
            self.set_pixel(x, row, _R, _G, _B)

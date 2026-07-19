"""Dusty animation — fast horizontal dust drift.

Small particles moving quickly to the right, simulating blowing dust.
Intensity controls particle count and speed:
    0 — 3 particles, medium speed
    1 — 5 particles, faster
    2 — 8 particles, fastest
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Dust colour (sandy brown)
_R = 200
_G = 170
_B = 100

# Particle y-positions per intensity (relative to a 6px reference height)
_PARTICLE_YS = {
    0: [1, 3, 4],
    1: [0, 1, 2, 3, 5],
    2: [0, 1, 1, 2, 3, 4, 4, 5],
}

_SPEED = {0: 2, 1: 3, 2: 4}  # px per frame
_REF_HEIGHT = 6


class DustyAnimation(BaseAnimation):
    """Fast horizontal dust drift."""

    def draw(self, frame_idx: int) -> None:
        h = self.height
        w = self.width
        ys = _PARTICLE_YS.get(self.intensity, _PARTICLE_YS[1])
        speed = _SPEED.get(self.intensity, 3)

        # Scale y-positions to actual height
        ys = [int(y * h / _REF_HEIGHT) for y in ys if y < _REF_HEIGHT]

        for i, py in enumerate(ys):
            phase = (i * 3) % w
            x = (frame_idx * speed + phase) % w
            prev_x = ((frame_idx - 1) * speed + phase) % w

            self.set_pixel(prev_x, py, 0, 0, 0)
            self.set_pixel(x, py, _R, _G, _B)

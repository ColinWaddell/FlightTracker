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

# Particle y-positions per intensity (within 6px area)
_PARTICLE_YS = {
    0: [1, 3, 4],
    1: [0, 1, 2, 3, 5],
    2: [0, 1, 1, 2, 3, 4, 4, 5],
}

_SPEED = {0: 2, 1: 3, 2: 4}  # px per frame
_DEFAULT_HEIGHT = 6


class DustyAnimation(BaseAnimation):
    """Fast horizontal dust drift."""

    def _build_frames(self) -> None:
        h = self.height if self.height > 0 else _DEFAULT_HEIGHT
        w = self.width
        ys = _PARTICLE_YS.get(self.intensity, _PARTICLE_YS[1])
        speed = _SPEED.get(self.intensity, 3)

        # Scale y-positions to actual height
        ys = [int(y * h / _DEFAULT_HEIGHT) for y in ys if y < _DEFAULT_HEIGHT]

        # Each particle scrolls right at `speed` px/frame, wraps at width.
        # Stagger particles with phase offsets.
        cycle = w  # one full scroll
        frames: list[dict] = []

        for frame_idx in range(cycle):
            set_pixels: list[tuple] = []

            for i, py in enumerate(ys):
                phase = (i * 3) % cycle
                x = (frame_idx * speed + phase) % w

                set_pixels.append((x, py, _R, _G, _B))

            frames.append({"set": set_pixels})

        self._frames = frames

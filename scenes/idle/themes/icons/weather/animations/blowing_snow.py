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
_DEFAULT_HEIGHT = 6


class BlowingSnowAnimation(BaseAnimation):
    """Wind-driven horizontal snow."""

    def _build_frames(self) -> None:
        h = self.height if self.height > 0 else _DEFAULT_HEIGHT
        w = self.width
        ys = _PARTICLE_YS.get(self.intensity, _PARTICLE_YS[1])
        speed = _WIND_SPEED.get(self.intensity, 3)

        ys = [int(y * h / _DEFAULT_HEIGHT) for y in ys if y < _DEFAULT_HEIGHT]

        cycle = w  # horizontal wrap cycle
        frames: list[dict] = []

        for frame_idx in range(cycle):
            set_pixels: list[tuple] = []
            clear_pixels: list[tuple] = []

            for i, py in enumerate(ys):
                phase = (i * 4) % cycle
                # Move right-to-left: x decreases
                x = (w - 1 - (frame_idx * speed + phase) % w)
                prev_x = (w - 1 - ((frame_idx - 1) * speed + phase) % w)

                # Slow downward drift
                row = (py + (frame_idx // _FALL_SPEED)) % h
                prev_row = (py + ((frame_idx - 1) // _FALL_SPEED)) % h

                set_pixels.append((x, row, _R, _G, _B))
                clear_pixels.append((prev_x, prev_row))

            frames.append({"set": set_pixels, "clear": clear_pixels})

        self._frames = frames
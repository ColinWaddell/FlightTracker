"""Snow animation — drifting flakes falling slowly in the animation area.

Intensity controls flake count and adds slight horizontal sway:
    0 (light)  — 2 flakes, slow fall
    1 (medium) — 3 flakes
    2 (heavy)  — 5 flakes, denser

Flakes fall 1px every 2 frames and sway ±1px horizontally via a baked-in
sine pattern.  Each frame clears the flake's previous position and
lights the new one.
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Snow flake colour (white)
_R = 230
_G = 230
_B = 240

# Flake base x-positions per intensity
_FLAKE_XS = {
    0: [5, 10],
    1: [3, 8, 12],
    2: [2, 5, 8, 11, 14],
}

# Sway pattern: -1, 0, 1, 0 repeating (period 4)
_SWAY = (-1, 0, 1, 0)


class SnowAnimation(BaseAnimation):
    """Drifting snow flakes."""

    def draw(self, frame_idx: int) -> None:
        h = self.height
        xs = _FLAKE_XS.get(self.intensity, _FLAKE_XS[1])
        cycle = h * 2

        for i, bx in enumerate(xs):
            phase = (i * 3) % cycle
            pos = (frame_idx + phase) % cycle
            row = pos // 2  # fall 1px every 2 frames
            prev_row = ((pos - 1) % cycle) // 2

            sway = _SWAY[frame_idx % 4]
            x = bx + sway
            prev_sway = _SWAY[(frame_idx - 1) % 4]
            prev_x = bx + prev_sway

            if 0 <= prev_x < self.width:
                self.set_pixel(prev_x, prev_row, 0, 0, 0)
            if 0 <= x < self.width:
                self.set_pixel(x, row, _R, _G, _B)

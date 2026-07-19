"""Snow animation — drifting flakes falling slowly in the animation area.

Intensity controls flake count and adds slight horizontal sway:
    0 (light)  — 2 flakes, slow fall
    1 (medium) — 3 flakes
    2 (heavy)  — 5 flakes, denser

Flakes fall 1px every 2 frames (achieved by alternating set/clear frames)
and sway ±1px horizontally via a baked-in sine pattern.
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

_DEFAULT_HEIGHT = 6


class SnowAnimation(BaseAnimation):
    """Drifting snow flakes."""

    def _build_frames(self) -> None:
        h = self.height if self.height > 0 else _DEFAULT_HEIGHT
        xs = _FLAKE_XS.get(self.intensity, _FLAKE_XS[1])
        num_flakes = len(xs)

        # Sway pattern: -1, 0, 1, 0 repeating (period 4)
        _sway = (-1, 0, 1, 0)

        # Fall speed: 1px per 2 frames → cycle length = h * 2
        cycle = h * 2
        frames: list[dict] = []

        for frame_idx in range(cycle):
            set_pixels: list[tuple] = []

            for i, bx in enumerate(xs):
                phase = (i * 3) % cycle
                pos = (frame_idx + phase) % cycle
                row = pos // 2  # fall 1px every 2 frames

                sway = _sway[frame_idx % 4]
                x = bx + sway

                if 0 <= x < self.width:
                    set_pixels.append((x, row, _R, _G, _B))

            frames.append({"set": set_pixels})

        self._frames = frames

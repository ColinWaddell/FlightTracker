"""Sleet animation — mixed rain and snow particles.

Intensity controls particle count:
    0 (light)  — 2 particles (1 rain, 1 snow)
    1 (medium) — 4 particles (2 rain, 2 snow)
    2 (heavy)  — 6 particles (3 rain, 3 snow)

Rain particles fall fast (1px/frame), snow particles fall slower
(1px/2frames) with sway.  The mix creates the characteristic sleet look.
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Rain drop colour (light blue)
_RAIN_R, _RAIN_G, _RAIN_B = 80, 130, 220
# Snow flake colour (white)
_SNOW_R, _SNOW_G, _SNOW_B = 230, 230, 240

_RAIN_XS = {0: [4], 1: [3, 10], 2: [2, 7, 12]}
_SNOW_XS = {0: [11], 1: [7, 13], 2: [5, 10, 14]}

_sway = (-1, 0, 1, 0)
_DEFAULT_HEIGHT = 6


class SleetAnimation(BaseAnimation):
    """Mixed rain and snow particles."""

    def _build_frames(self) -> None:
        h = self.height if self.height > 0 else _DEFAULT_HEIGHT
        rain_xs = _RAIN_XS.get(self.intensity, _RAIN_XS[1])
        snow_xs = _SNOW_XS.get(self.intensity, _SNOW_XS[1])

        # Rain cycle = h (fast), snow cycle = h * 2 (slow)
        # Overall cycle = lcm(h, h*2) = h*2
        cycle = h * 2
        frames: list[dict] = []

        for frame_idx in range(cycle):
            set_pixels: list[tuple] = []
            clear_pixels: list[tuple] = []

            # Rain drops (fast fall)
            for i, dx in enumerate(rain_xs):
                phase = (i * 2) % h
                row = (frame_idx + phase) % h
                prev_row = (row - 1 + h) % h
                set_pixels.append((dx, row, _RAIN_R, _RAIN_G, _RAIN_B))
                clear_pixels.append((dx, prev_row))

            # Snow flakes (slow fall + sway)
            for i, bx in enumerate(snow_xs):
                phase = (i * 3) % cycle
                pos = (frame_idx + phase) % cycle
                row = pos // 2
                prev_row = ((pos - 1) % cycle) // 2
                sway = _sway[frame_idx % 4]
                x = bx + sway
                if 0 <= x < self.width:
                    set_pixels.append((x, row, _SNOW_R, _SNOW_G, _SNOW_B))
                    clear_pixels.append((x, prev_row))

            frames.append({"set": set_pixels, "clear": clear_pixels})

        self._frames = frames
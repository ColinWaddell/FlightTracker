"""Mist animation — denser, slower fog.

Similar to fog but with more bands, higher opacity, and a slower drift
(1px per 2 frames).  Intensity controls density:
    0 — 2 bands, dim
    1 — 3 bands, medium
    2 — 4 bands, bright
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

_R = 170
_G = 170
_B = 180

_BANDS = {
    0: [(0, 1, 0.6), (4, 5, 0.5)],
    1: [(0, 1, 0.7), (2, 3, 0.6), (4, 5, 0.5)],
    2: [(0, 1, 0.8), (2, 2, 0.6), (3, 4, 0.7), (5, 5, 0.5)],
}

_DEFAULT_HEIGHT = 6


class MistAnimation(BaseAnimation):
    """Dense, slow-drifting mist bands."""

    def _build_frames(self) -> None:
        h = self.height if self.height > 0 else _DEFAULT_HEIGHT
        w = self.width
        bands = _BANDS.get(self.intensity, _BANDS[1])

        scaled_bands = []
        for y_start, y_end, scale in bands:
            sy = int(y_start * h / _DEFAULT_HEIGHT)
            ey = int(y_end * h / _DEFAULT_HEIGHT)
            scaled_bands.append((sy, ey, scale))

        # Slower drift: 1px per 2 frames → cycle = w * 2
        cycle = w * 2
        frames: list[dict] = []

        for frame_idx in range(cycle):
            drift = frame_idx // 2  # actual pixel offset
            set_pixels: list[tuple] = []
            clear_pixels: list[tuple] = []

            for y_start, y_end, scale in scaled_bands:
                r = int(_R * scale)
                g = int(_G * scale)
                b = int(_B * scale)
                for y in range(y_start, y_end + 1):
                    if y >= h:
                        continue
                    for x in range(w):
                        pattern_pos = (x - drift) % w
                        # Denser pattern than fog: 5 on, 1 off
                        if pattern_pos < 5 or (7 <= pattern_pos < 12):
                            set_pixels.append((x, y, r, g, b))
                        else:
                            clear_pixels.append((x, y))

            frames.append({"set": set_pixels, "clear": clear_pixels})

        self._frames = frames
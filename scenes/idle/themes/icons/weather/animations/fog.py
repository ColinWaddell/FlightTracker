"""Fog animation — slow horizontal-drifting wispy bands.

Fog fills the animation area with semi-transparent horizontal bands that
drift slowly to the right.  Intensity controls band count and opacity:
    0 — 1 band, dim
    1 — 2 bands, medium
    2 — 3 bands, brighter

For no-icon codes (fog has ``None`` icon in ``codes.py``), the animation
fills the full 18px sprite height.
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Fog colour (grey-white)
_R = 160
_G = 160
_B = 170

# Band definitions per intensity: list of (y_start, y_end, brightness_scale)
_BANDS = {
    0: [(0, 1, 0.5)],
    1: [(0, 1, 0.6), (3, 4, 0.5)],
    2: [(0, 1, 0.7), (2, 3, 0.6), (4, 5, 0.5)],
}

_DEFAULT_HEIGHT = 6


class FogAnimation(BaseAnimation):
    """Slow drifting fog bands."""

    def _build_frames(self) -> None:
        h = self.height if self.height > 0 else _DEFAULT_HEIGHT
        w = self.width
        bands = _BANDS.get(self.intensity, _BANDS[1])

        # Scale band y-positions to actual height
        scaled_bands = []
        for y_start, y_end, scale in bands:
            sy = int(y_start * h / _DEFAULT_HEIGHT)
            ey = int(y_end * h / _DEFAULT_HEIGHT)
            scaled_bands.append((sy, ey, scale))

        # Drift cycle: band shifts right 1px per frame, wraps at width
        # Use a pattern of "on" pixels that scrolls.  Each band is a
        # cluster of w//2 pixels with gaps.
        cycle = w  # full scroll takes w frames
        frames: list[dict] = []

        for frame_idx in range(cycle):
            set_pixels: list[tuple] = []

            for y_start, y_end, scale in scaled_bands:
                r = int(_R * scale)
                g = int(_G * scale)
                b = int(_B * scale)
                for y in range(y_start, y_end + 1):
                    if y >= h:
                        continue
                    # Band pattern: 4 on, 2 off, scrolling
                    for x in range(w):
                        pattern_pos = (x - frame_idx) % w
                        if pattern_pos < 4 or (8 <= pattern_pos < 11):
                            set_pixels.append((x, y, r, g, b))

            frames.append({"set": set_pixels})

        self._frames = frames

"""Sun rays animation — subtle pulsing rays radiating from the icon.

Since the sun icon sits in the static area above, the rays animation
plays in the 6px area below.  Short vertical ray segments pulse in
brightness to suggest radiating light.

Intensity controls ray count and brightness:
    0 — 3 rays, subtle pulse
    1 — 5 rays, medium pulse
    2 — 7 rays, strong pulse
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

RAYS = [[1, 9], [2, 9], [3, 9], [7, 5], [7, 4], [7, 3], [11, 9], [12, 9], [13, 9]]

_PULSE = (0.15, 0.25, 0.35, 0.45, 0.35, 0.25)
_PULSE_LEN = len(_PULSE)
_R = 255
_G = 255
_B = 0


class RaysAnimation(BaseAnimation):
    """Pulsing sun rays below the sun icon."""

    def _build_frames(self) -> None:
        frames: list[dict] = []
        for frame_idx in range(_PULSE_LEN):
            set_pixels: list[tuple] = []
            clear_pixels: list[tuple] = []

            scale = _PULSE[frame_idx]
            r = int(_R * scale)
            g = int(_G * scale)
            b = int(_B * scale)

            for x, y in RAYS:
                set_pixels.append((x, y, r, g, b))

            frames.append({"set": set_pixels, "clear": clear_pixels})

        self._frames = frames

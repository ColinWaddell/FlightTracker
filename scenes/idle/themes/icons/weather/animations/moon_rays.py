"""Moon rays animation — subtle, dimmer pulsing glow below the moon icon.

Same concept as ``rays.py`` but with a cool blue-white palette and a
slower, gentler pulse to suggest soft moonlight.
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Moonlight colour (pale blue-white)
_R = 180
_G = 190
_B = 220

_RAY_XS = {
    0: [4, 8, 11],
    1: [2, 5, 8, 10, 13],
    2: [1, 3, 5, 7, 9, 11, 14],
}

# Slower, gentler pulse than sun rays
_PULSE = (0.15, 0.25, 0.35, 0.45, 0.35, 0.25)
_PULSE_LEN = len(_PULSE)
_DEFAULT_HEIGHT = 6


class MoonRaysAnimation(BaseAnimation):
    """Subtle pulsing moonlight glow."""

    def _build_frames(self) -> None:
        h = self.height if self.height > 0 else _DEFAULT_HEIGHT
        xs = _RAY_XS.get(self.intensity, _RAY_XS[1])
        ray_height = min(2, h)

        frames: list[dict] = []
        for frame_idx in range(_PULSE_LEN):
            set_pixels: list[tuple] = []

            scale = _PULSE[frame_idx]
            r = int(_R * scale)
            g = int(_G * scale)
            b = int(_B * scale)

            for x in xs:
                for y in range(ray_height):
                    set_pixels.append((x, y, r, g, b))

            frames.append({"set": set_pixels})

        self._frames = frames

"""Moon rays animation — subtle, dimmer pulsing glow around the moon icon.

Same concept as ``rays.py`` but with a cool blue-white palette and a
slower, gentler pulse to suggest soft moonlight.  Rays sit at fixed
positions, so each frame overwrites the same pixels — no clearing.
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Moonlight colour (pale blue-white)
_R = 180
_G = 190
_B = 220

# Ray x-positions per intensity (rays are short vertical segments at
# the top of the sprite, height 2).
_RAY_XS = {
    0: [4, 8, 11],
    1: [2, 5, 8, 10, 13],
    2: [1, 3, 5, 7, 9, 11, 14],
}

# Slower, gentler pulse than sun rays
_PULSE = (0.15, 0.25, 0.35, 0.45, 0.35, 0.25)
_RAY_HEIGHT = 2


class MoonRaysAnimation(BaseAnimation):
    """Subtle pulsing moonlight glow."""

    def draw(self, frame_idx: int) -> None:
        xs = _RAY_XS.get(self.intensity, _RAY_XS[1])
        scale = _PULSE[frame_idx % len(_PULSE)]
        r = int(_R * scale)
        g = int(_G * scale)
        b = int(_B * scale)
        for x in xs:
            for y in range(_RAY_HEIGHT):
                self.set_pixel(x, y, r, g, b)

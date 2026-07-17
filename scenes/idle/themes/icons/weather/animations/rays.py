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

# Sun ray colour (warm yellow)
_R = 255
_G = 200
_B = 80

_RAY_XS = {
    0: [3, 8, 12],
    1: [2, 5, 8, 10, 13],
    2: [1, 3, 5, 7, 9, 11, 14],
}

# Pulse cycle: brightness ramps up then down
_PULSE = (0.2, 0.4, 0.6, 0.8, 1.0, 0.8, 0.6, 0.4)
_PULSE_LEN = len(_PULSE)
_DEFAULT_HEIGHT = 6


class RaysAnimation(BaseAnimation):
    """Pulsing sun rays below the sun icon."""

    def _build_frames(self) -> None:
        h = self.height if self.height > 0 else _DEFAULT_HEIGHT
        xs = _RAY_XS.get(self.intensity, _RAY_XS[1])

        # Rays are 2px tall vertical segments at the top of the animation area
        ray_height = min(2, h)

        frames: list[dict] = []
        for frame_idx in range(_PULSE_LEN):
            set_pixels: list[tuple] = []
            clear_pixels: list[tuple] = []

            scale = _PULSE[frame_idx]
            r = int(_R * scale)
            g = int(_G * scale)
            b = int(_B * scale)

            for x in xs:
                for y in range(ray_height):
                    set_pixels.append((x, y, r, g, b))
                    # Clear is handled by the next frame's set (dimmer/brighter)
                    # But we need to clear if brightness goes to 0
                    if scale <= 0.2:
                        clear_pixels.append((x, y))

            frames.append({"set": set_pixels, "clear": clear_pixels})

        self._frames = frames
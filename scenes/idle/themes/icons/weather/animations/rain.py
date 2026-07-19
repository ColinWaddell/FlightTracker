"""Rain animation — falling drops.

Intensity controls drop count and fall speed:
    0 (light)  — 2 drops, 1px/frame
    1 (medium) — 4 drops, 1px/frame
    2 (heavy)  — 6 drops, 1px/frame (denser, some staggered)

Drops fall vertically through the animation area.  Each drop has its
own x position and phase offset so they don't all move in lockstep.
Each frame clears the drop's previous position and lights the new one.
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Rain drop colour (light blue)
_R = 80
_G = 130
_B = 220

# Drop x-positions per intensity (spread across the sprite width)
_DROP_XS = {
    0: [4, 11],  # light: 2 drops
    1: [2, 6, 9, 13],  # medium: 4 drops
    2: [1, 4, 7, 9, 12, 14],  # heavy: 6 drops
}


class RainAnimation(BaseAnimation):
    """Falling rain drops."""

    def draw(self, frame_idx: int) -> None:
        h = self.height
        xs = _DROP_XS.get(self.intensity, _DROP_XS[1])

        for i, dx in enumerate(xs):
            phase = (i * 2) % h  # stagger drops
            row = (frame_idx + phase) % h
            prev_row = (row - 1 + h) % h

            # Clear where the drop was last frame (to black — rain lives
            # below the icon, so original is black there).
            self.set_pixel(dx, prev_row, 0, 0, 0)
            # Draw where it is now
            self.set_pixel(dx, row, _R, _G, _B)

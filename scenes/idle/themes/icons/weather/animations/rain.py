"""Rain animation — falling drops in the 6px area below the cloud icon.

Intensity controls drop count and fall speed:
    0 (light)  — 2 drops, 1px/frame
    1 (medium) — 4 drops, 1px/frame
    2 (heavy)  — 6 drops, 1px/frame (denser, some staggered)

Drops fall vertically through the 6px animation area.  Each drop has its
own x position and phase offset so they don't all move in lockstep.
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Rain drop colour (light blue)
_R = 80
_G = 130
_B = 220

# Drop x-positions per intensity (spread across 16px width)
_DROP_XS = {
    0: [4, 11],          # light: 2 drops
    1: [2, 6, 9, 13],    # medium: 4 drops
    2: [1, 4, 7, 9, 12, 14],  # heavy: 6 drops
}

# Animation area height (6px for normal sprites, 18px for no-icon)
_DEFAULT_HEIGHT = 6


class RainAnimation(BaseAnimation):
    """Falling rain drops."""

    def _build_frames(self) -> None:
        h = self.height if self.height > 0 else _DEFAULT_HEIGHT
        xs = _DROP_XS.get(self.intensity, _DROP_XS[1])
        num_drops = len(xs)

        # Each drop cycles through h positions.  We stagger the drops
        # so they start at different rows.  The total frame count is h
        # (one full cycle), and each drop is offset by a phase.
        frames: list[dict] = []

        for frame_idx in range(h):
            set_pixels: list[tuple] = []
            clear_pixels: list[tuple] = []

            for i, dx in enumerate(xs):
                phase = (i * 2) % h  # stagger drops
                row = (frame_idx + phase) % h
                prev_row = (row - 1 + h) % h

                set_pixels.append((dx, row, _R, _G, _B))
                clear_pixels.append((dx, prev_row))

            frames.append({"set": set_pixels, "clear": clear_pixels})

        self._frames = frames
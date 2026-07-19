"""Thunder animation — periodic lightning flash.

The animation area is mostly dark.  Every ``_FLASH_PERIOD`` frames a
zigzag lightning bolt flashes for ``_FLASH_DURATION`` frames, then
clears.

Intensity controls flash brightness and frequency:
    0 — dim flash, longer period
    1 — medium flash
    2 — bright flash, shorter period
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

_FLASH_PERIOD = {0: 40, 1: 30, 2: 24}  # frames between flashes
_FLASH_DURATION = 3  # frames the bolt stays visible

# Lightning bolt zigzag (local coords within 16×6 area)
# A simple Z-shaped bolt
_BOLT = [
    (7, 0),
    (8, 0),
    (8, 1),
    (7, 2),
    (7, 3),
    (8, 4),
    (8, 5),
    (7, 5),
]

# Flash colours per intensity (yellow-white)
_COLOURS = {
    0: (180, 180, 100),
    1: (220, 220, 140),
    2: (255, 255, 180),
}

_DEFAULT_HEIGHT = 6


class ThunderAnimation(BaseAnimation):
    """Periodic lightning flash with no precipitation."""

    def _build_frames(self) -> None:
        h = self.height if self.height > 0 else _DEFAULT_HEIGHT
        period = _FLASH_PERIOD.get(self.intensity, 30)
        r, g, b = _COLOURS.get(self.intensity, _COLOURS[1])

        # Scale bolt y-coords to the animation height
        bolt = [(x, int(y * h / _DEFAULT_HEIGHT)) for x, y in _BOLT]

        frames: list[dict] = []
        for frame_idx in range(period):
            is_flash = frame_idx < _FLASH_DURATION
            if is_flash:
                set_pixels = [(x, y, r, g, b) for x, y in bolt]
            else:
                set_pixels = []

            frames.append({"set": set_pixels})

        self._frames = frames

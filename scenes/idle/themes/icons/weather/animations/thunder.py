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

# Lightning bolt zigzag (local coords).  A simple Z-shaped bolt.
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


class ThunderAnimation(BaseAnimation):
    """Periodic lightning flash with no precipitation."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._was_flashing = False

    def draw(self, frame_idx: int) -> None:
        period = _FLASH_PERIOD.get(self.intensity, 30)
        flash_phase = frame_idx % period
        is_flash = flash_phase < _FLASH_DURATION
        r, g, b = _COLOURS.get(self.intensity, _COLOURS[1])

        if is_flash:
            for x, y in _BOLT:
                self.set_pixel(x, y, r, g, b)
            self._was_flashing = True
        elif self._was_flashing:
            # Clear the bolt on the first dark frame after a flash.
            for x, y in _BOLT:
                self.set_pixel(x, y, 0, 0, 0)
            self._was_flashing = False

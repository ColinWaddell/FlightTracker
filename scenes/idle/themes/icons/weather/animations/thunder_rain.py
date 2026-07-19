"""Thunder + rain animation — falling rain with periodic lightning flash.

Combines the rain drop pattern from ``rain.py`` with the lightning bolt
flash from ``thunder.py``.  Intensity controls both rain density and
flash brightness/frequency.
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Rain drop colour
_RAIN_R, _RAIN_G, _RAIN_B = 80, 130, 220

_DROP_XS = {
    0: [4, 11],
    1: [2, 6, 9, 13],
    2: [1, 4, 7, 9, 12, 14],
}

_FLASH_PERIOD = {0: 40, 1: 30, 2: 24}
_FLASH_DURATION = 3

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

_FLASH_COLOURS = {
    0: (180, 180, 100),
    1: (220, 220, 140),
    2: (255, 255, 180),
}


class ThunderRainAnimation(BaseAnimation):
    """Rain with periodic lightning flashes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._was_flashing = False

    def draw(self, frame_idx: int) -> None:
        h = self.height
        xs = _DROP_XS.get(self.intensity, _DROP_XS[1])
        period = _FLASH_PERIOD.get(self.intensity, 30)
        fr, fg, fb = _FLASH_COLOURS.get(self.intensity, _FLASH_COLOURS[1])

        rain_phase = frame_idx % h
        flash_phase = frame_idx % period
        bolt_set = set(_BOLT)

        # Rain drops
        for i, dx in enumerate(xs):
            phase = (i * 2) % h
            row = (rain_phase + phase) % h
            prev_row = (row - 1 + h) % h
            # Don't overwrite bolt pixels during flash
            if (dx, prev_row) not in bolt_set or flash_phase >= _FLASH_DURATION:
                self.set_pixel(dx, prev_row, 0, 0, 0)
            if (dx, row) not in bolt_set or flash_phase >= _FLASH_DURATION:
                self.set_pixel(dx, row, _RAIN_R, _RAIN_G, _RAIN_B)

        # Lightning flash
        if flash_phase < _FLASH_DURATION:
            for x, y in _BOLT:
                self.set_pixel(x, y, fr, fg, fb)
            self._was_flashing = True
        elif self._was_flashing:
            for x, y in _BOLT:
                self.set_pixel(x, y, 0, 0, 0)
            self._was_flashing = False

"""Thunder + snow animation — falling snow with periodic lightning flash.

Combines the snow flake pattern from ``snow.py`` with the lightning bolt
flash from ``thunder.py``.
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Snow flake colour
_SNOW_R, _SNOW_G, _SNOW_B = 230, 230, 240

_FLAKE_XS = {
    0: [5, 10],
    1: [3, 8, 12],
    2: [2, 5, 8, 11, 14],
}

_FLASH_PERIOD = {0: 40, 1: 30, 2: 24}
_FLASH_DURATION = 3

_BOLT = [
    (7, 0), (8, 0),
    (8, 1),
    (7, 2),
    (7, 3),
    (8, 4),
    (8, 5), (7, 5),
]

_FLASH_COLOURS = {
    0: (180, 180, 100),
    1: (220, 220, 140),
    2: (255, 255, 180),
}

_sway = (-1, 0, 1, 0)
_DEFAULT_HEIGHT = 6


class ThunderSnowAnimation(BaseAnimation):
    """Snow with periodic lightning flashes."""

    def _build_frames(self) -> None:
        h = self.height if self.height > 0 else _DEFAULT_HEIGHT
        xs = _FLAKE_XS.get(self.intensity, _FLAKE_XS[1])
        period = _FLASH_PERIOD.get(self.intensity, 30)
        fr, fg, fb = _FLASH_COLOURS.get(self.intensity, _FLASH_COLOURS[1])

        bolt = [(x, int(y * h / _DEFAULT_HEIGHT)) for x, y in _BOLT]
        bolt_set = set(bolt)

        snow_cycle = h * 2
        # Overall cycle = lcm(snow_cycle, period)
        cycle = snow_cycle * period
        frames: list[dict] = []

        for frame_idx in range(cycle):
            flash_phase = frame_idx % period

            set_pixels: list[tuple] = []
            clear_pixels: list[tuple] = []

            # Snow flakes
            for i, bx in enumerate(xs):
                phase = (i * 3) % snow_cycle
                pos = (frame_idx + phase) % snow_cycle
                row = pos // 2
                prev_row = ((pos - 1) % snow_cycle) // 2
                sway = _sway[frame_idx % 4]
                x = bx + sway
                if 0 <= x < self.width:
                    if (x, row) not in bolt_set or flash_phase >= _FLASH_DURATION:
                        set_pixels.append((x, row, _SNOW_R, _SNOW_G, _SNOW_B))
                    clear_pixels.append((x, prev_row))

            # Lightning flash
            if flash_phase < _FLASH_DURATION:
                for x, y in bolt:
                    set_pixels.append((x, y, fr, fg, fb))
            elif flash_phase == _FLASH_DURATION:
                for x, y in bolt:
                    clear_pixels.append((x, y))

            frames.append({"set": set_pixels, "clear": clear_pixels})

        self._frames = frames
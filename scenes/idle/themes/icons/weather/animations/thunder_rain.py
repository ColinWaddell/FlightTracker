"""Thunder + rain animation — falling rain with random lightning flashes.

Combines the probabilistic rain drop pattern from ``rain.py`` with the
random lightning bolt flash logic from ``_thunder.py`` (via
``ThunderMixin``).  Rain drops fall in the bounding box under the cloud;
lightning bolts flash on top, with bolt pixels taking priority over
rain during a flash.

The box is fixed (shared with rain/snow/sleet):
    top-left     [3, 11]
    bottom-right [11, 14]

Intensity controls rain density (columns + spawn chance) and lightning
frequency/brightness.

    0 (light)  — 2 rain columns, rare dim flashes
    1 (medium) — 4 rain columns, occasional bright flashes
    2 (heavy)  — 6 rain columns, frequent bright flashes
"""

from __future__ import annotations

import random

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation
from scenes.idle.themes.icons.weather.animations.thunder_mixin import ThunderMixin

# Rain drop colour (light blue)
_R = 80
_G = 130
_B = 220

# Bounding box (local coordinates, shared with rain).
_BOX_LEFT = 3
_BOX_RIGHT = 11      # inclusive
_BOX_TOP = 11
_BOX_BOTTOM = 14     # inclusive

# Columns available per intensity.
_COLUMNS = {
    0: [4, 10],              # light: 2 columns
    1: [4, 6, 8, 10],        # medium: 4 columns
    2: [3, 5, 6, 8, 9, 11],  # heavy: 6 columns
}

# Per-frame probability of spawning a new drop.
_SPAWN_CHANCE = {
    0: 0.12,   # light:  ~1.5 drops/sec
    1: 0.25,   # medium: ~3 drops/sec
    2: 0.45,   # heavy:  ~5.6 drops/sec
}

# Fall speed in pixels per frame.
_FALL_SPEED = 1


class _Drop:
    """A single falling rain drop."""

    __slots__ = ("x", "y")

    def __init__(self, x: int, y: int) -> None:
        self.x = x
        self.y = y


class ThunderRainAnimation(ThunderMixin, BaseAnimation):
    """Falling rain with random lightning flashes."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._thunder_init()

        self._columns: list[int] = _COLUMNS.get(
            self.intensity, _COLUMNS[1]
        )
        self._spawn_chance: float = _SPAWN_CHANCE.get(
            self.intensity, _SPAWN_CHANCE[1]
        )

        # Active drops currently in flight.
        self._drops: list[_Drop] = []

        # Seed a few initial drops so the animation starts mid-fall.
        initial_count = self.intensity + 1
        for _ in range(initial_count):
            x = random.choice(self._columns)
            y = random.randint(_BOX_TOP, _BOX_BOTTOM)
            self._drops.append(_Drop(x, y))

        self._first_frame = True

    def draw(self, frame_idx: int) -> None:
        # On the very first frame, draw the seeded drops at their spawn
        # positions so they're visible immediately, then skip the move
        # logic for this frame.
        if self._first_frame:
            self._first_frame = False
            for drop in self._drops:
                self.set_pixel(drop.x, drop.y, _R, _G, _B)
            self._thunder_tick()
            return

        # Bolt pixels that are currently lit — precipitation must not
        # clear or overwrite these during a flash.
        bolt_pixels = self._thunder_active_pixels()

        # --- Pass 1: clear every drop's current pixel -----------------
        for drop in self._drops:
            if (drop.x, drop.y) not in bolt_pixels:
                self.set_pixel(drop.x, drop.y, 0, 0, 0)

        # --- Pass 2: advance each drop --------------------------------
        survivors: list[_Drop] = []
        for drop in self._drops:
            drop.y += _FALL_SPEED
            if drop.y <= _BOX_BOTTOM:
                survivors.append(drop)

        self._drops = survivors

        # --- Pass 3: draw all surviving drops at their new positions --
        for drop in self._drops:
            if (drop.x, drop.y) not in bolt_pixels:
                self.set_pixel(drop.x, drop.y, _R, _G, _B)

        # --- Maybe spawn a new drop ------------------------------------
        if random.random() < self._spawn_chance:
            x = random.choice(self._columns)
            drop = _Drop(x, _BOX_TOP)
            if (drop.x, drop.y) not in bolt_pixels:
                self.set_pixel(drop.x, drop.y, _R, _G, _B)
            self._drops.append(drop)

        # --- Lightning (drawn on top of rain) -------------------------
        self._thunder_tick()

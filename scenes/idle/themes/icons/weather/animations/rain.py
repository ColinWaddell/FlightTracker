"""Rain animation — random falling drops within a bounded box.

Each frame there is a random chance of spawning a new drop in a randomly
chosen column.  Multiple drops can be in flight at once, and because
spawning is probabilistic there is no fixed period or detectable loop.

The rain box is fixed:
    top-left     [3, 11]
    bottom-right [11, 14]

Intensity controls two things:
    - the pool of columns that drops can fall in
    - the per-frame spawn probability (higher = more frequent drops)

    0 (light)  — 2 columns, low spawn chance
    1 (medium) — 4 columns, medium spawn chance
    2 (heavy)  — 6 columns, high spawn chance
"""

from __future__ import annotations

import random

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Rain drop colour (light blue)
_R = 80
_G = 130
_B = 220

# Bounding box for the rain (local coordinates).
_BOX_LEFT = 3
_BOX_RIGHT = 11      # inclusive
_BOX_TOP = 11
_BOX_BOTTOM = 14     # inclusive

# Columns available per intensity (subset of the box's x-range).
_COLUMNS = {
    0: [4, 6, 10],              # light: 2 columns
    1: [4, 6, 8, 10],        # medium: 4 columns
    2: [3, 5, 6, 8, 9, 11],  # heavy: 6 columns
}

# Per-frame probability of spawning a new drop (in a random column).
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


class RainAnimation(BaseAnimation):
    """Falling rain drops within a bounded box."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._columns: list[int] = _COLUMNS.get(
            self.intensity, _COLUMNS[1]
        )
        self._spawn_chance: float = _SPAWN_CHANCE.get(
            self.intensity, _SPAWN_CHANCE[1]
        )

        # Active drops currently in flight.
        self._drops: list[_Drop] = []

        # Seed a few initial drops at random positions so the animation
        # starts mid-fall rather than from an empty box.  More drops for
        # higher intensity.  The drops are drawn on the first ``draw()``
        # call (see ``_first_frame``).
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
            return

        # --- Pass 1: clear every drop's current pixel -----------------
        # The drop was drawn at ``drop.y`` last frame, so that's the
        # pixel we need to clear — not ``prev_y``.
        for drop in self._drops:
            self.set_pixel(drop.x, drop.y, 0, 0, 0)

        # --- Pass 2: advance each drop --------------------------------
        survivors: list[_Drop] = []
        for drop in self._drops:
            drop.y += _FALL_SPEED
            if drop.y <= _BOX_BOTTOM:
                survivors.append(drop)
            # else: drop has left the box — its last pixel was already
            # cleared in pass 1, so nothing remains "on the ground".

        self._drops = survivors

        # --- Pass 3: draw all surviving drops at their new positions --
        for drop in self._drops:
            self.set_pixel(drop.x, drop.y, _R, _G, _B)

        # --- Maybe spawn a new drop ------------------------------------
        # The drop is drawn at _BOX_TOP immediately so the top row is
        # visible for one full frame before the drop advances next tick.
        if random.random() < self._spawn_chance:
            x = random.choice(self._columns)
            drop = _Drop(x, _BOX_TOP)
            self.set_pixel(drop.x, drop.y, _R, _G, _B)
            self._drops.append(drop)

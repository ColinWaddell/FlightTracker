"""Sleet animation — long white stripes falling within a bounded box.

Sleet looks like rain but with elongated white streaks instead of
single-pixel blue drops.  Each streak is a vertical line of 2–3 pixels
that falls at rain speed (1px/frame).  Spawning is probabilistic so
there is no fixed period or detectable loop.

The sleet box is fixed (shared with rain/snow):
    top-left     [3, 11]
    bottom-right [11, 14]

Intensity controls:
    - the pool of columns that streaks fall in
    - the per-frame spawn probability
    - the streak length (longer streaks at higher intensity)

    0 (light)  — 2 columns, low spawn chance, 2px streaks
    1 (medium) — 4 columns, medium spawn chance, 2px streaks
    2 (heavy)  — 6 columns, high spawn chance, 3px streaks
"""

from __future__ import annotations

import random

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Sleet streak colour (white)
_R = 230
_G = 230
_B = 240

# Bounding box for the sleet (local coordinates, shared with rain/snow).
_BOX_LEFT = 3
_BOX_RIGHT = 11      # inclusive
_BOX_TOP = 11
_BOX_BOTTOM = 14     # inclusive

# Columns available per intensity (subset of the box's x-range).
_COLUMNS = {
    0: [4, 10],              # light: 2 columns
    1: [4, 6, 8, 10],        # medium: 4 columns
    2: [3, 5, 6, 8, 9, 11],  # heavy: 6 columns
}

# Per-frame probability of spawning a new streak.
_SPAWN_CHANCE = {
    0: 0.12,   # light:  ~1.5 streaks/sec
    1: 0.25,   # medium: ~3 streaks/sec
    2: 0.45,   # heavy:  ~5.6 streaks/sec
}

# Streak length in pixels per intensity.
_STREAK_LEN = {
    0: 2,
    1: 2,
    2: 3,
}

# Fall speed in pixels per frame.
_FALL_SPEED = 1


class _Streak:
    """A single falling sleet streak (vertical line of N pixels)."""

    __slots__ = ("x", "y", "length")

    def __init__(self, x: int, y: int, length: int) -> None:
        self.x = x
        self.y = y          # bottom pixel of the streak
        self.length = length


class SleetAnimation(BaseAnimation):
    """Falling white sleet streaks within a bounded box."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._columns: list[int] = _COLUMNS.get(
            self.intensity, _COLUMNS[1]
        )
        self._spawn_chance: float = _SPAWN_CHANCE.get(
            self.intensity, _SPAWN_CHANCE[1]
        )
        self._streak_len: int = _STREAK_LEN.get(
            self.intensity, _STREAK_LEN[1]
        )

        # Active streaks currently in flight.
        self._streaks: list[_Streak] = []

        # Seed a few initial streaks at random positions so the animation
        # starts mid-fall rather than from an empty box.  More streaks
        # for higher intensity.  Drawn on the first ``draw()`` call.
        initial_count = self.intensity + 1
        for _ in range(initial_count):
            x = random.choice(self._columns)
            y = random.randint(_BOX_TOP + self._streak_len, _BOX_BOTTOM)
            self._streaks.append(_Streak(x, y, self._streak_len))

        self._first_frame = True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _streak_pixels(self, streak: _Streak) -> list[tuple[int, int]]:
        """Return the local pixel coords for a streak (bottom pixel = y)."""
        return [
            (streak.x, streak.y - i)
            for i in range(streak.length)
            if _BOX_TOP <= streak.y - i <= _BOX_BOTTOM
        ]

    def _clear_streak(self, streak: _Streak) -> None:
        for px, py in self._streak_pixels(streak):
            self.set_pixel(px, py, 0, 0, 0)

    def _draw_streak(self, streak: _Streak) -> None:
        for px, py in self._streak_pixels(streak):
            self.set_pixel(px, py, _R, _G, _B)

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw(self, frame_idx: int) -> None:
        # On the very first frame, draw the seeded streaks at their spawn
        # positions so they're visible immediately, then skip the move
        # logic for this frame.
        if self._first_frame:
            self._first_frame = False
            for streak in self._streaks:
                self._draw_streak(streak)
            return

        # --- Pass 1: clear every streak's current pixels --------------
        for streak in self._streaks:
            self._clear_streak(streak)

        # --- Pass 2: advance each streak ------------------------------
        survivors: list[_Streak] = []
        for streak in self._streaks:
            streak.y += _FALL_SPEED
            # A streak is done when its top pixel has left the box.
            if (streak.y - streak.length + 1) <= _BOX_BOTTOM:
                survivors.append(streak)
            # else: streak has fully left the box — its pixels were
            # already cleared in pass 1, so nothing remains "on the ground".

        self._streaks = survivors

        # --- Pass 3: draw all surviving streaks -----------------------
        for streak in self._streaks:
            self._draw_streak(streak)

        # --- Maybe spawn a new streak --------------------------------
        # The streak is drawn at _BOX_TOP immediately so it's visible for
        # one full frame before it advances next tick.
        if random.random() < self._spawn_chance:
            x = random.choice(self._columns)
            streak = _Streak(x, _BOX_TOP, self._streak_len)
            self._draw_streak(streak)
            self._streaks.append(streak)

"""Thunder + snow animation — falling snow with random lightning flashes.

Combines the cross-shaped snow flake pattern from ``snow.py`` with the
random lightning bolt flash logic from ``_thunder.py`` (via
``ThunderMixin``).  Snow flakes drift in the bounding box under the
cloud; lightning bolts flash on top, with bolt pixels taking priority
over flakes during a flash.

The box is fixed (shared with rain/snow/sleet):
    top-left     [3, 11]
    bottom-right [11, 14]

Intensity controls snow density (columns + spawn chance + sway) and
lightning frequency/brightness.

    0 (light)  — 2 snow columns, rare dim flashes
    1 (medium) — 3 snow columns, occasional bright flashes
    2 (heavy)  — 4 snow columns, frequent bright flashes
"""

from __future__ import annotations

import random

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation
from scenes.idle.themes.icons.weather.animations.thunder_mixin import ThunderMixin

# Snow flake colour (white)
_R = 230
_G = 230
_B = 240

# Bounding box (local coordinates, shared with rain/snow).
_BOX_LEFT = 3
_BOX_RIGHT = 11      # inclusive
_BOX_TOP = 11
_BOX_BOTTOM = 14     # inclusive

# Cross shape: 5 pixel offsets relative to the flake's top-left corner.
#
#   .X.
#   XXX
#   .X.
#
_CROSS = [
    (0, 1),
    (1, 0),
    (1, 1),
    (1, 2),
    (2, 1),
]

# Spawn columns (left-edge x of the 3px-wide cross) per intensity.
_COLUMNS = {
    0: [4, 8],              # light:  2 columns
    1: [3, 6, 9],           # medium: 3 columns
    2: [3, 5, 7, 9],        # heavy:  4 columns
}

# Per-frame probability of spawning a new flake.
_SPAWN_CHANCE = {
    0: 0.06,   # light:  ~0.75 flakes/sec
    1: 0.12,   # medium: ~1.5 flakes/sec
    2: 0.22,   # heavy:  ~2.75 flakes/sec
}

# Sway interval range (frames between sway changes) per intensity.
_SWAY_INTERVAL = {
    0: (8, 16),   # light:  slow, lazy drift
    1: (5, 12),   # medium: medium drift
    2: (3, 8),    # heavy:  frequent shifts
}

# Fall speed in pixels per frame (sub-pixel accumulator).
_FALL_SPEED = 0.5


class _Flake:
    """A single falling snow flake (3×3 cross)."""

    __slots__ = ("x", "y", "sway", "sway_timer", "fall_accum")

    def __init__(self, x: int, y: int, sway_interval: tuple[int, int]) -> None:
        self.x = x
        self.y = y
        self.sway = 0
        lo, hi = sway_interval
        self.sway_timer = random.randint(lo, hi)
        self.fall_accum = 0.0


class ThunderSnowAnimation(ThunderMixin, BaseAnimation):
    """Falling snow with random lightning flashes."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._thunder_init()

        self._columns: list[int] = _COLUMNS.get(
            self.intensity, _COLUMNS[1]
        )
        self._spawn_chance: float = _SPAWN_CHANCE.get(
            self.intensity, _SPAWN_CHANCE[1]
        )
        self._sway_interval: tuple[int, int] = _SWAY_INTERVAL.get(
            self.intensity, _SWAY_INTERVAL[1]
        )

        # Active flakes currently in flight.
        self._flakes: list[_Flake] = []

        # Seed a few initial flakes so the animation starts mid-fall.
        initial_count = self.intensity + 1
        for _ in range(initial_count):
            x = random.choice(self._columns)
            y = random.randint(_BOX_TOP, _BOX_BOTTOM - 1)
            self._flakes.append(_Flake(x, y, self._sway_interval))

        self._first_frame = True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _flake_pixels(self, flake: _Flake) -> list[tuple[int, int]]:
        """Return the absolute local pixel coords for a flake's cross."""
        cx = flake.x + flake.sway
        cy = int(flake.y)
        return [
            (cx + dx, cy + dy)
            for dx, dy in _CROSS
            if _BOX_LEFT <= cx + dx <= _BOX_RIGHT
            and _BOX_TOP <= cy + dy <= _BOX_BOTTOM
        ]

    def _new_sway(self, flake: _Flake) -> None:
        """Pick a new random sway offset, clamped to keep the cross in bounds."""
        lo, hi = self._sway_interval
        flake.sway_timer = random.randint(lo, hi)
        new_sway = random.choice((-1, 0, 1))
        left = flake.x + new_sway
        right = flake.x + new_sway + 2
        if left < _BOX_LEFT or right > _BOX_RIGHT:
            new_sway = 0
        flake.sway = new_sway

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw(self, frame_idx: int) -> None:
        # On the very first frame, draw the seeded flakes at their spawn
        # positions so they're visible immediately, then skip the move
        # logic for this frame.
        if self._first_frame:
            self._first_frame = False
            for flake in self._flakes:
                for px, py in self._flake_pixels(flake):
                    self.set_pixel(px, py, _R, _G, _B)
            self._thunder_tick()
            return

        # Bolt pixels that are currently lit — precipitation must not
        # clear or overwrite these during a flash.
        bolt_pixels = self._thunder_active_pixels()

        # --- Pass 1: clear every flake's current pixels ---------------
        for flake in self._flakes:
            for px, py in self._flake_pixels(flake):
                if (px, py) not in bolt_pixels:
                    self.set_pixel(px, py, 0, 0, 0)

        # --- Pass 2: advance each flake -------------------------------
        survivors: list[_Flake] = []
        for flake in self._flakes:
            flake.fall_accum += _FALL_SPEED
            if flake.fall_accum >= 1.0:
                flake.fall_accum -= 1.0
                flake.y += 1

            flake.sway_timer -= 1
            if flake.sway_timer <= 0:
                self._new_sway(flake)

            if flake.y <= _BOX_BOTTOM:
                survivors.append(flake)

        self._flakes = survivors

        # --- Pass 3: draw all surviving flakes ------------------------
        for flake in self._flakes:
            for px, py in self._flake_pixels(flake):
                if (px, py) not in bolt_pixels:
                    self.set_pixel(px, py, _R, _G, _B)

        # --- Maybe spawn a new flake ----------------------------------
        if random.random() < self._spawn_chance:
            x = random.choice(self._columns)
            flake = _Flake(x, _BOX_TOP, self._sway_interval)
            for px, py in self._flake_pixels(flake):
                if (px, py) not in bolt_pixels:
                    self.set_pixel(px, py, _R, _G, _B)
            self._flakes.append(flake)

        # --- Lightning (drawn on top of snow) -------------------------
        self._thunder_tick()

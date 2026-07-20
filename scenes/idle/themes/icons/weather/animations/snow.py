"""Snow animation — drifting cross-shaped flakes falling within a bounded box.

Each flake is a 3×3 cross (5 pixels) that falls slowly and sways ±1px
horizontally on its own random schedule.  Spawning is probabilistic so
there is no fixed period or detectable loop.

The snow box is fixed (shared with rain):
    top-left     [3, 11]
    bottom-right [11, 14]

Intensity controls:
    - the pool of spawn columns (left-edge x of the 3px-wide cross)
    - the per-frame spawn probability
    - the sway frequency (how often a flake picks a new horizontal offset)

    0 (light)  — 2 columns, low spawn chance, slow sway
    1 (medium) — 3 columns, medium spawn chance, medium sway
    2 (heavy)  — 4 columns, high spawn chance, fast sway

Fall speed is constant (0.5 px/frame → 1px every 2 frames) regardless of
intensity — snow falls slowly; what changes is how many flakes are in
the air.
"""

from __future__ import annotations

import random

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Snow flake colour (white)
_R = 230
_G = 230
_B = 240

# Bounding box for the snow (local coordinates, shared with rain).
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
# Chosen so the cross + ±1px sway stays inside the box.
_COLUMNS = {
    0: [4, 8],              # light:  2 columns
    1: [3, 6, 9],            # medium: 3 columns
    2: [3, 5, 7, 9],         # heavy:  4 columns
}

# Per-frame probability of spawning a new flake.
_SPAWN_CHANCE = {
    0: 0.06,   # light:  ~0.75 flakes/sec
    1: 0.12,   # medium: ~1.5 flakes/sec
    2: 0.22,   # heavy:  ~2.75 flakes/sec
}

# Sway interval range (frames between sway changes) per intensity.
# Lower = sways more often.
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


class SnowAnimation(BaseAnimation):
    """Drifting cross-shaped snow flakes within a bounded box."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

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

        # Seed a few initial flakes at random positions so the animation
        # starts mid-fall rather than from an empty box.  More flakes for
        # higher intensity.  Drawn on the first ``draw()`` call.
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

    def _clear_flake(self, flake: _Flake) -> None:
        for px, py in self._flake_pixels(flake):
            self.set_pixel(px, py, 0, 0, 0)

    def _draw_flake(self, flake: _Flake) -> None:
        for px, py in self._flake_pixels(flake):
            self.set_pixel(px, py, _R, _G, _B)

    def _new_sway(self, flake: _Flake) -> None:
        """Pick a new random sway offset, clamped to keep the cross in bounds."""
        lo, hi = self._sway_interval
        flake.sway_timer = random.randint(lo, hi)
        # Try a random offset of -1, 0, or +1; clamp so the cross stays
        # inside the box.
        new_sway = random.choice((-1, 0, 1))
        left = flake.x + new_sway
        right = flake.x + new_sway + 2  # cross is 3px wide (0..2)
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
                self._draw_flake(flake)
            return

        # --- Pass 1: clear every flake's current pixels ---------------
        for flake in self._flakes:
            self._clear_flake(flake)

        # --- Pass 2: advance each flake -------------------------------
        survivors: list[_Flake] = []
        for flake in self._flakes:
            # Fall: sub-pixel accumulator, move down 1px when ready.
            flake.fall_accum += _FALL_SPEED
            if flake.fall_accum >= 1.0:
                flake.fall_accum -= 1.0
                flake.y += 1

            # Sway: countdown to next horizontal shift.
            flake.sway_timer -= 1
            if flake.sway_timer <= 0:
                self._new_sway(flake)

            if flake.y <= _BOX_BOTTOM:
                survivors.append(flake)
            # else: flake has left the box — its pixels were already
            # cleared in pass 1, so nothing remains "on the ground".

        self._flakes = survivors

        # --- Pass 3: draw all surviving flakes ------------------------
        for flake in self._flakes:
            self._draw_flake(flake)

        # --- Maybe spawn a new flake ----------------------------------
        # The flake is drawn at _BOX_TOP immediately so it's visible for
        # one full frame before it advances next tick.
        if random.random() < self._spawn_chance:
            x = random.choice(self._columns)
            flake = _Flake(x, _BOX_TOP, self._sway_interval)
            self._draw_flake(flake)
            self._flakes.append(flake)

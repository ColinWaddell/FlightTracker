"""Blowing snow animation — wind-driven horizontal snow streaks.

Snow particles move right-to-left across the bounding box with a slight
downward drift, simulating strong wind.  Each particle is a short
horizontal streak (2-3 pixels) that wraps around when it exits the left
edge.  Spawning and row assignment are randomised so there is no fixed
period or detectable loop.

The box is fixed (shared with rain/snow/sleet):
    top-left     [3, 11]
    bottom-right [11, 14]

Intensity controls:
    - the number of particles in flight
    - the wind speed (horizontal px/frame)
    - the streak length

    0 (light)  — 2 particles, medium wind, 2px streaks
    1 (medium) — 3 particles, strong wind, 2px streaks
    2 (heavy)  — 4 particles, blizzard, 3px streaks
"""

from __future__ import annotations

import random

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Snow colour (white)
_R = 230
_G = 230
_B = 240

# Bounding box (local coordinates, shared with rain/snow).
_BOX_LEFT = 3
_BOX_RIGHT = 11  # inclusive
_BOX_TOP = 11
_BOX_BOTTOM = 14  # inclusive

# Number of particles per intensity.
_PARTICLE_COUNT = {
    0: 2,
    1: 3,
    2: 4,
}

# Wind speed in pixels per frame (sub-pixel accumulator).
_WIND_SPEED = {
    0: 0.5,  # light:  slow wind (~1px every 2 frames)
    1: 0.75,  # medium: medium wind (~1px every 1.3 frames)
    2: 1.0,  # heavy:  strong wind (1px/frame)
}

# Streak length in pixels per intensity.
_STREAK_LEN = {
    0: 2,
    1: 2,
    2: 3,
}

# Downward drift speed (pixels per frame, sub-pixel accumulator).
_DRIFT_SPEED = 0.25  # ~1px every 4 frames


class _Particle:
    """A single wind-driven snow streak."""

    __slots__ = ("x", "y", "length", "wind_accum", "drift_accum")

    def __init__(self, x: int, y: int, length: int) -> None:
        self.x = x  # rightmost pixel of the streak
        self.y = y
        self.length = length
        self.wind_accum = 0.0
        self.drift_accum = 0.0


class BlowingSnowAnimation(BaseAnimation):
    """Wind-driven horizontal snow streaks within a bounded box."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self._particle_count: int = _PARTICLE_COUNT.get(
            self.intensity, _PARTICLE_COUNT[1]
        )
        self._wind_speed: int = _WIND_SPEED.get(self.intensity, _WIND_SPEED[1])
        self._streak_len: int = _STREAK_LEN.get(self.intensity, _STREAK_LEN[1])

        # Active particles.
        self._particles: list[_Particle] = []

        # Seed initial particles at random positions.
        for _ in range(self._particle_count):
            x = random.randint(_BOX_LEFT, _BOX_RIGHT)
            y = random.randint(_BOX_TOP, _BOX_BOTTOM)
            self._particles.append(_Particle(x, y, self._streak_len))

        self._first_frame = True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _streak_pixels(self, particle: _Particle) -> list[tuple[int, int]]:
        """Return local pixel coords for a streak (rightmost = x)."""
        return [
            (particle.x - i, particle.y)
            for i in range(particle.length)
            if _BOX_LEFT <= particle.x - i <= _BOX_RIGHT
            and _BOX_TOP <= particle.y <= _BOX_BOTTOM
        ]

    def _clear_streak(self, particle: _Particle) -> None:
        for px, py in self._streak_pixels(particle):
            self.set_pixel(px, py, 0, 0, 0)

    def _draw_streak(self, particle: _Particle) -> None:
        for px, py in self._streak_pixels(particle):
            self.set_pixel(px, py, _R, _G, _B)

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw(self, frame_idx: int) -> None:
        # On the very first frame, draw the seeded particles at their
        # spawn positions so they're visible immediately.
        if self._first_frame:
            self._first_frame = False
            for particle in self._particles:
                self._draw_streak(particle)
            return

        # --- Pass 1: clear every particle's current pixels ------------
        for particle in self._particles:
            self._clear_streak(particle)

        # --- Pass 2: advance each particle ----------------------------
        for particle in self._particles:
            # Wind: move right-to-left (sub-pixel accumulator).
            particle.wind_accum += self._wind_speed
            if particle.wind_accum >= 1.0:
                steps = int(particle.wind_accum)
                particle.wind_accum -= steps
                particle.x -= steps

            # Slow downward drift.
            particle.drift_accum += _DRIFT_SPEED
            if particle.drift_accum >= 1.0:
                particle.drift_accum -= 1.0
                particle.y += 1

            # Wrap around: if the streak has fully exited the left edge,
            # respawn at the right edge at a random row.
            if particle.x - particle.length + 1 < _BOX_LEFT:
                particle.x = _BOX_RIGHT
                particle.y = random.randint(_BOX_TOP, _BOX_BOTTOM)
                particle.wind_accum = 0.0
                particle.drift_accum = 0.0

            # Clamp y if drift pushed it past the bottom.
            if particle.y > _BOX_BOTTOM:
                particle.y = _BOX_TOP

        # --- Pass 3: draw all particles -------------------------------
        for particle in self._particles:
            self._draw_streak(particle)

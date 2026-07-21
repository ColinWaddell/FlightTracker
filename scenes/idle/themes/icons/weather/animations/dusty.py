"""Dusty animation — blowing dust streaks drifting left-to-right.

Dust streaks blow across the full sprite area (no icon for these weather
codes).  Each streak is a short horizontal line of 2–3 pixels moving
rightward with a slight upward drift, simulating wind-blown dust.
Movement uses a sub-pixel accumulator for smooth motion, and particles
wrap around when they exit the right edge.

A TOP_MARGIN constant offsets the usable area downward from the top of
the sprite, in case the on-screen layout needs the animation pushed
down to align with other elements.

Intensity controls:
    - the number of particles in flight
    - the wind speed (horizontal px/frame)
    - the streak length

    0 (light)  — 3 particles, slow wind, 2px streaks
    1 (medium) — 5 particles, medium wind, 2px streaks
    2 (heavy)  — 8 particles, strong wind, 3px streaks
"""

from __future__ import annotations

import random

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation

# Dust colour (sandy brown)
R = 200
G = 170
B = 100

# Sprite dimensions (full 15×15 area — no icon for dusty codes).
SPRITE_WIDTH = 15
SPRITE_HEIGHT = 15

# Top margin: pixels to skip from the top of the sprite before the
# animation area begins.  Adjust if the on-screen layout needs the
# animation pushed down.
TOP_MARGIN = 0

# Effective animation area.
BOX_LEFT = 0
BOX_RIGHT = SPRITE_WIDTH - 1       # inclusive
BOX_TOP = TOP_MARGIN
BOX_BOTTOM = SPRITE_HEIGHT - 1     # inclusive

# Number of particles per intensity.
PARTICLE_COUNT = {
    0: 3,
    1: 5,
    2: 8,
}

# Wind speed in pixels per frame (sub-pixel accumulator, left-to-right).
WIND_SPEED = {
    0: 0.5,    # light:  slow wind (~1px every 2 frames)
    1: 0.75,   # medium: medium wind (~1px every 1.3 frames)
    2: 1.0,    # heavy:  strong wind (1px/frame)
}

# Streak length in pixels per intensity.
STREAK_LEN = {
    0: 2,
    1: 2,
    2: 3,
}

# Upward drift speed (pixels per frame, sub-pixel accumulator).
DRIFT_SPEED = 0.2   # ~1px every 5 frames


class Particle:
    """A single wind-driven dust streak."""

    __slots__ = ("x", "y", "length", "wind_accum", "drift_accum")

    def __init__(self, x: int, y: int, length: int) -> None:
        self.x = x          # leftmost pixel of the streak
        self.y = y
        self.length = length
        self.wind_accum = 0.0
        self.drift_accum = 0.0


class DustyAnimation(BaseAnimation):
    """Blowing dust streaks drifting left-to-right across the sprite."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.particle_count: int = PARTICLE_COUNT.get(
            self.intensity, PARTICLE_COUNT[1]
        )
        self.wind_speed: float = WIND_SPEED.get(
            self.intensity, WIND_SPEED[1]
        )
        self.streak_len: int = STREAK_LEN.get(
            self.intensity, STREAK_LEN[1]
        )

        # Active particles.
        self.particles: list[Particle] = []

        # Seed initial particles at random positions.
        for _ in range(self.particle_count):
            x = random.randint(BOX_LEFT, BOX_RIGHT)
            y = random.randint(BOX_TOP, BOX_BOTTOM)
            self.particles.append(Particle(x, y, self.streak_len))

        self.first_frame = True

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def streak_pixels(self, particle: Particle) -> list[tuple[int, int]]:
        """Return local pixel coords for a streak (leftmost = x)."""
        return [
            (particle.x + i, particle.y)
            for i in range(particle.length)
            if BOX_LEFT <= particle.x + i <= BOX_RIGHT
            and BOX_TOP <= particle.y <= BOX_BOTTOM
        ]

    def clear_streak(self, particle: Particle) -> None:
        for px, py in self.streak_pixels(particle):
            self.set_pixel(px, py, 0, 0, 0)

    def draw_streak(self, particle: Particle) -> None:
        for px, py in self.streak_pixels(particle):
            self.set_pixel(px, py, R, G, B)

    # ------------------------------------------------------------------
    # Draw
    # ------------------------------------------------------------------

    def draw(self, frame_idx: int) -> None:
        # On the very first frame, draw the seeded particles at their
        # spawn positions so they're visible immediately.
        if self.first_frame:
            self.first_frame = False
            for particle in self.particles:
                self.draw_streak(particle)
            return

        # --- Pass 1: clear every particle's current pixels ------------
        for particle in self.particles:
            self.clear_streak(particle)

        # --- Pass 2: advance each particle ----------------------------
        for particle in self.particles:
            # Wind: move left-to-right (sub-pixel accumulator).
            particle.wind_accum += self.wind_speed
            if particle.wind_accum >= 1.0:
                steps = int(particle.wind_accum)
                particle.wind_accum -= steps
                particle.x += steps

            # Slight upward drift.
            particle.drift_accum += DRIFT_SPEED
            if particle.drift_accum >= 1.0:
                particle.drift_accum -= 1.0
                particle.y -= 1

            # Wrap around: if the streak has fully exited the right edge,
            # respawn at the left edge at a random row.
            if particle.x + particle.length - 1 > BOX_RIGHT:
                particle.x = BOX_LEFT
                particle.y = random.randint(BOX_TOP, BOX_BOTTOM)
                particle.wind_accum = 0.0
                particle.drift_accum = 0.0

            # Clamp y if drift pushed it past the top.
            if particle.y < BOX_TOP:
                particle.y = BOX_BOTTOM

        # --- Pass 3: draw all particles -------------------------------
        for particle in self.particles:
            self.draw_streak(particle)

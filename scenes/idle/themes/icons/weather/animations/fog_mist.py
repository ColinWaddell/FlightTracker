"""Shared fog/mist animation engine — patchy background + sinusoidal lines.

Two visual layers combined:

1. **Patchy background** — a per-pixel shimmer (same technique as
   ``rays.py``) applied to a subset of rows.  Each pixel drifts towards
   its own random brightness target at its own speed, producing an
   organic, non-looping, undulating cloud effect.

2. **Sinusoidal lines** — one or more horizontal lines whose y-position
   follows a sine wave.  Each line has its own amplitude, frequency,
   phase, and speed so they don't move in lockstep.  The lines are
   drawn on top of the background.

Callers (``fog.py``, ``mist.py``) set the class-level ``CONFIG``
attribute to a ``FogMistConfig`` that controls the balance between the
two layers, colours, band positions, and intensity scaling.

A ``TOP_MARGIN`` constant offsets the usable area downward from the top
of the sprite, in case the on-screen layout needs the animation pushed
down to align with other elements.
"""

from __future__ import annotations

import math
import random

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation
from setup import frames

# Fixed time step per frame (seconds).
DT = frames.PERIOD

# Sprite dimensions (full 15×15 area — no icon for fog/mist codes).
SPRITE_WIDTH = 15
SPRITE_HEIGHT = 15

# Top margin: pixels to skip from the top of the sprite.
TOP_MARGIN = 0

# Effective animation area.
BOX_LEFT = 0
BOX_RIGHT = SPRITE_WIDTH - 1
BOX_TOP = TOP_MARGIN
BOX_BOTTOM = SPRITE_HEIGHT - 1

# Threshold below which a shimmer pixel is considered to have reached
# its target.
REACHED = 0.01


class SineLine:
    """A sinusoidal horizontal line that undulates up and down.

    The line's y-position at column *x* is::

        base_y + amplitude * sin(frequency * x + phase + speed * t)

    where *t* is the elapsed time (frame_idx * DT).
    """

    __slots__ = ("base_y", "amplitude", "frequency", "phase", "speed")

    def __init__(
        self,
        base_y: int,
        amplitude: float,
        frequency: float,
        phase: float,
        speed: float,
    ) -> None:
        self.base_y = base_y
        self.amplitude = amplitude
        self.frequency = frequency
        self.phase = phase
        self.speed = speed

    def y_at(self, x: int, t: float) -> int:
        """Return the pixel y for column *x* at time *t*."""
        return int(
            self.base_y
            + self.amplitude
            * math.sin(self.frequency * x + self.phase + self.speed * t)
        )


class FogMistConfig:
    """Configuration for the fog/mist animation engine.

    Attributes:
        colour:           (r, g, b) base colour for both layers.
        background_enabled: bool — if False, the patchy shimmer
                          background is skipped entirely and only the
                          sinusoidal lines are drawn.
        bg_rows:          dict[intensity -> list[y]] — rows that get the
                          patchy shimmer background.
        bg_target_range:  dict[intensity -> (min, max)] — shimmer target
                          range for the background (0 = dark, 1 = full
                          colour).
        bg_speed_range:   dict[intensity -> (min, max)] — shimmer
                          transition speed for the background.
        line_count:       dict[intensity -> int] — number of sinusoidal
                          lines.
        line_amplitude:   dict[intensity -> float] — sine wave amplitude
                          in pixels.
        line_frequency:   dict[intensity -> float] — sine wave frequency
                          (radians per pixel of x).
        line_speed:       dict[intensity -> float] — how fast the wave
                          travels (radians per second).
        line_brightness:  dict[intensity -> float] — brightness of the
                          lines relative to the base colour (0-1).
    """

    def __init__(
        self,
        colour: tuple[int, int, int],
        bg_rows: dict[int, list[int]],
        bg_target_range: dict[int, tuple[float, float]],
        bg_speed_range: dict[int, tuple[float, float]],
        line_count: dict[int, int],
        line_amplitude: dict[int, float],
        line_frequency: dict[int, float],
        line_speed: dict[int, float],
        line_brightness: dict[int, float],
        background_enabled: bool = True,
    ) -> None:
        self.colour = colour
        self.background_enabled = background_enabled
        self.bg_rows = bg_rows
        self.bg_target_range = bg_target_range
        self.bg_speed_range = bg_speed_range
        self.line_count = line_count
        self.line_amplitude = line_amplitude
        self.line_frequency = line_frequency
        self.line_speed = line_speed
        self.line_brightness = line_brightness


class FogMistAnimation(BaseAnimation):
    """Shared fog/mist animation: patchy shimmer background + sine lines.

    Subclasses (``FogAnimation``, ``MistAnimation``) set the class-level
    ``CONFIG`` attribute to a ``FogMistConfig`` instance.
    """

    CONFIG: FogMistConfig

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        cfg = self.CONFIG

        # --- Background shimmer state -------------------------------
        self.bg_pixels: list[tuple[int, int]] = []
        self.bg_state: dict[tuple[int, int], dict[str, float]] = {}
        if cfg.background_enabled:
            bg_rows = cfg.bg_rows.get(self.intensity, cfg.bg_rows[1])
            target_range = cfg.bg_target_range.get(
                self.intensity, cfg.bg_target_range[1]
            )
            speed_range = cfg.bg_speed_range.get(self.intensity, cfg.bg_speed_range[1])

            for y in bg_rows:
                if BOX_TOP <= y <= BOX_BOTTOM:
                    for x in range(BOX_LEFT, BOX_RIGHT + 1):
                        self.bg_pixels.append((x, y))

            self.bg_state = {
                (x, y): {
                    "value": random.uniform(*target_range),
                    "target": random.uniform(*target_range),
                    "speed": random.uniform(*speed_range),
                }
                for x, y in self.bg_pixels
            }

        # --- Sine lines --------------------------------------------
        line_count = cfg.line_count.get(self.intensity, cfg.line_count[1])
        amplitude = cfg.line_amplitude.get(self.intensity, cfg.line_amplitude[1])
        frequency = cfg.line_frequency.get(self.intensity, cfg.line_frequency[1])
        line_speed = cfg.line_speed.get(self.intensity, cfg.line_speed[1])

        # Spread lines evenly across the animation area, each with a
        # random phase so they don't move in sync.
        self.lines: list[SineLine] = []
        if line_count > 0 and BOX_BOTTOM > BOX_TOP:
            spacing = (BOX_BOTTOM - BOX_TOP) / (line_count + 1)
            for i in range(line_count):
                base_y = int(BOX_TOP + spacing * (i + 1))
                self.lines.append(
                    SineLine(
                        base_y=base_y,
                        amplitude=amplitude,
                        frequency=frequency,
                        phase=random.uniform(0, 2 * math.pi),
                        speed=line_speed * random.choice((-1, 1)),
                    )
                )

        # Track previously-drawn line pixels so we can clear them next
        # frame (the lines move, so old positions must be erased).
        self.prev_line_pixels: set[tuple[int, int]] = set()

    def draw(self, frame_idx: int) -> None:
        cfg = self.CONFIG
        r, g, b = cfg.colour
        t = frame_idx * DT

        target_range = cfg.bg_target_range.get(self.intensity, cfg.bg_target_range[1])
        speed_range = cfg.bg_speed_range.get(self.intensity, cfg.bg_speed_range[1])
        line_brightness = cfg.line_brightness.get(
            self.intensity, cfg.line_brightness[1]
        )

        # --- Layer 1: patchy shimmer background ---------------------
        if cfg.background_enabled:
            for x, y in self.bg_pixels:
                pixel = self.bg_state[(x, y)]
                value = pixel["value"]
                target = pixel["target"]

                value += (target - value) * min(1.0, pixel["speed"] * DT)

                if abs(target - value) < REACHED:
                    target = random.uniform(*target_range)
                    pixel["target"] = target
                    pixel["speed"] = random.uniform(*speed_range)

                pixel["value"] = value

                shimmer = value * value * (3.0 - 2.0 * value)
                br = max(0, int(r * shimmer))
                bg = max(0, int(g * shimmer))
                bb = max(0, int(b * shimmer))

                self.set_pixel(x, y, br, bg, bb)

        # --- Layer 2: sinusoidal lines ------------------------------
        # Clear previous line positions.
        for px, py in self.prev_line_pixels:
            self.set_pixel(px, py, 0, 0, 0)
        self.prev_line_pixels = set()

        # Draw current line positions.
        lr = max(0, int(r * line_brightness))
        lg = max(0, int(g * line_brightness))
        lb = max(0, int(b * line_brightness))

        for line in self.lines:
            for x in range(BOX_LEFT, BOX_RIGHT + 1):
                y = line.y_at(x, t)
                if BOX_TOP <= y <= BOX_BOTTOM:
                    self.set_pixel(x, y, lr, lg, lb)
                    self.prev_line_pixels.add((x, y))

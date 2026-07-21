"""Sun rays animation — shimmering halo ring around the sun icon.

Each ring pixel drifts towards its own random brightness target at its
own speed, producing an organic, non-looping glow.  Because targets are
continually replaced at irregular times there is no fixed animation
period or detectable loop.

The halo is drawn as a **single ring outline** (radius 6) centred on the
sprite centre (7, 7).  Ring pixels that overlap the static sun icon body
are filtered out via ``original_pixel()`` so the halo surrounds the icon
rather than covering it.  Every ring pixel is written every frame, so
no clearing is needed between frames.

Intensity controls the colour palette:
    0 — mostly yellow
    1 — yellow/orange
    2 — orange/red
"""

from __future__ import annotations

import random

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation
from setup import frames

# Fixed time step per frame (seconds).  The forecast theme ticks
# animations every frame at ~12.5 fps (frames.PERIOD == 0.08).
_DT = frames.PERIOD

# Palette: (base RGB, variation RGB).  The shimmer subtracts
# ``variation * shimmer`` from ``base``, so a shimmer of 0 gives the
# full base colour and a shimmer of 1 darkens it.  Large variation
# values give a dramatic brightness swing.  The same mostly-yellow
# palette is used for all intensity levels.
_PALETTE = ((255, 230, 40), (0, 120, 40))  # mostly yellow

# Single ring radius centred on (7, 7) — outline only, not a filled disc.
_CENTRE = (7, 6)
_RADII = (5,)

# Full target range (0–1) for a dramatic shimmer swing.
_TARGET_MIN = 0.0
_TARGET_MAX = 1.0
# Fast transition speeds so movement is clearly visible each frame.
_SPEED_MIN = 1.5
_SPEED_MAX = 4.0
# Threshold below which a pixel is considered to have reached its target.
_REACHED = 0.01


CIRCLE_POINTS_0 = [
    [5, 2],
    [6, 2],
    [7, 2],
    [8, 2],
    [9, 2],
    [10, 3],
    [11, 4],
    [11, 5],
    [11, 6],
    [11, 7],
    [11, 8],
    [10, 9],
    [9, 10],
    [8, 10],
    [7, 10],
    [6, 10],
    [5, 10],
    [4, 9],
    [3, 8],
    [3, 7],
    [3, 6],
    [3, 5],
    [3, 4],
]

CIRCLE_POINTS_1 = [[8, 1], [9, 0], [10, 0], [11, 0], [12, 1], [13, 2], [13, 3], [13, 4]]

# Per-intensity ring pixel sets.
_CIRCLE_POINTS = {
    0: CIRCLE_POINTS_0,
    1: CIRCLE_POINTS_1,
}


class RaysAnimation(BaseAnimation):
    """Shimmering sun-ray halo ring around the icon centre."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # Collect the ring pixels, keeping only those inside the sprite
        # bounds.  Pixels on the icon body are intentionally kept so the
        # halo can shimmer over the sun's edge.  The pixel set is chosen
        # per intensity so each condition can have its own halo shape.
        cx, cy = _CENTRE
        circle_points = _CIRCLE_POINTS.get(self.intensity, CIRCLE_POINTS_0)
        ring_pixels: set[tuple[int, int]] = set()
        for radius in _RADII:
            for lx, ly in circle_points:
                if not (0 <= lx < self.width and 0 <= ly < self.height):
                    continue
                ring_pixels.add((lx, ly))

        self._pixels: list[tuple[int, int]] = sorted(ring_pixels)

        # Per-pixel shimmer state: each pixel has its own current value,
        # random target, and transition speed.
        self._state: dict[tuple[int, int], dict[str, float]] = {
            (lx, ly): {
                "value": random.uniform(_TARGET_MIN, _TARGET_MAX),
                "target": random.uniform(_TARGET_MIN, _TARGET_MAX),
                "speed": random.uniform(_SPEED_MIN, _SPEED_MAX),
            }
            for lx, ly in self._pixels
        }

    def draw(self, frame_idx: int) -> None:
        base, variation = _PALETTE

        for lx, ly in self._pixels:
            pixel = self._state[(lx, ly)]
            value = pixel["value"]
            target = pixel["target"]

            # Smoothly approach this pixel's current random target.
            value += (target - value) * min(1.0, pixel["speed"] * _DT)

            # Pick a new target once the current one is reached.
            if abs(target - value) < _REACHED:
                target = random.uniform(_TARGET_MIN, _TARGET_MAX)
                pixel["target"] = target
                pixel["speed"] = random.uniform(_SPEED_MIN, _SPEED_MAX)

            pixel["value"] = value

            # Smoothstep makes the shimmer gentler near its extremes.
            shimmer = value * value * (3.0 - 2.0 * value)

            r = max(0, base[0] - int(variation[0] * shimmer))
            g = max(0, base[1] - int(variation[1] * shimmer))
            b = max(0, base[2] - int(variation[2] * shimmer))

            self.set_pixel(lx, ly, r, g, b)

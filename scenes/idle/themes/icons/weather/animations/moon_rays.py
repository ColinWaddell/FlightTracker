"""Moon rays animation — gentle sparkling on the moon icon pixels.

The moon pixels defined by ``MOON_LOCATION`` occasionally light up with
a gentle, non-looping sparkle.  Each pixel has its own random brightness
target and transition speed, so sparkles appear and fade independently
— there is no fixed period or detectable loop.

Most of the time the pixels are dark; a sparkle is a brief rise to a
random brightness followed by a slow fade back down.  This produces an
occasional, organic twinkle rather than a constant glow.

Intensity controls sparkle frequency and brightness:
    0 — rare, dim sparkles
    1 — occasional, medium sparkles
    2 — frequent, bright sparkles
"""

from __future__ import annotations

import random

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation
from setup import frames

# Fixed time step per frame (seconds).
DT = frames.PERIOD

# Moonray colour
RGB_INTENSITY_0 = [255, 240, 60]
RGB_INTENSITY_1 = [255, 255, 255]

# Pixel coordinates of the moon in the sprite.
MOON_INTENSITY_0 = [
    [5, 1],
    [4, 2],
    [3, 3],
    [7, 7],
    [3, 8],
    [4, 9],
    [5, 8],
    [10, 10],
    [11, 9],
    [12, 8],
    [4, 5],
    [5, 7],
    [8, 8],
    [10, 9],
]

MOON_INTENSITY_1 = [
    [10, 0],
    [11, 0],
    [9, 1],
    [10, 1],
    [9, 2],
    [10, 2],
    [10, 3],
    [11, 3],
    [11, 4],
    [12, 4],
    [13, 4],
    [12, 5],
]

# Per-intensity: chance per frame that a dark pixel starts sparkling.
SPARKLE_CHANCE = {
    0: 0.008,  # light:  rare (~1/sec per pixel)
    1: 0.015,  # medium: occasional (~2/sec per pixel)
    2: 0.03,  # heavy:  frequent (~3.75/sec per pixel)
}

# Brightness range a sparkle rises to (0–1).
SPARKLE_PEAK = {
    0: (0.2, 0.5),
    1: (0.3, 0.7),
    2: (0.4, 0.9),
}

# How fast a pixel rises to its peak (higher = faster rise).
RISE_SPEED = {
    0: (1.0, 2.0),
    1: (1.5, 3.0),
    2: (2.0, 4.0),
}

# How fast a pixel fades back to dark (lower = slower fade).
FADE_SPEED = {
    0: (0.3, 0.6),
    1: (0.4, 0.8),
    2: (0.5, 1.0),
}

# Threshold below which a sparkle is considered fully faded.
FADED = 0.01


class _Sparkle:
    """State for a single moon pixel's sparkle."""

    __slots__ = ("brightness", "target", "rising", "speed")

    def __init__(self) -> None:
        self.brightness = 0.0
        self.target = 0.0
        self.rising = False
        self.speed = 0.0


class MoonRaysAnimation(BaseAnimation):
    """Gentle sparkling on the moon icon pixels."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.sparkle_chance = SPARKLE_CHANCE.get(self.intensity, SPARKLE_CHANCE[1])
        self.peak_range = SPARKLE_PEAK.get(self.intensity, SPARKLE_PEAK[1])
        self.rise_range = RISE_SPEED.get(self.intensity, RISE_SPEED[1])
        self.fade_range = FADE_SPEED.get(self.intensity, FADE_SPEED[1])

        # Pixel set depends on intensity (intensity 2 reuses the denser set).
        moon_location = {0: MOON_INTENSITY_0, 1: MOON_INTENSITY_1}.get(
            self.intensity, MOON_INTENSITY_1
        )

        # Per-pixel sparkle state.
        self.state: dict[tuple[int, int], _Sparkle] = {
            (x, y): _Sparkle() for x, y in moon_location
        }

    def draw(self, frame_idx: int) -> None:
        for (x, y), sparkle in self.state.items():
            if sparkle.rising:
                # Rising towards peak brightness.
                sparkle.brightness += (sparkle.target - sparkle.brightness) * min(
                    1.0, sparkle.speed * DT
                )
                if abs(sparkle.target - sparkle.brightness) < FADED:
                    # Reached peak — start fading.
                    sparkle.rising = False
                    sparkle.speed = random.uniform(*self.fade_range)
            elif sparkle.brightness > FADED:
                # Fading back to dark.
                sparkle.brightness -= sparkle.brightness * min(1.0, sparkle.speed * DT)
                if sparkle.brightness < FADED:
                    sparkle.brightness = 0.0
            else:
                # Dark — maybe start a new sparkle.
                if random.random() < self.sparkle_chance:
                    sparkle.rising = True
                    sparkle.target = random.uniform(*self.peak_range)
                    sparkle.speed = random.uniform(*self.rise_range)

            # Smoothstep for a gentler curve.
            s = sparkle.brightness
            shimmer = s * s * (3.0 - 2.0 * s)

            # Blend the sparkle colour on top of the original moon icon
            # pixel.  When the sparkle is fully faded (shimmer=0) the
            # original pixel is restored; when at peak (shimmer=1) the
            # sparkle colour dominates.
            orig_r, orig_g, orig_b = self.original_pixel(x, y)
            (R, G, B) = RGB_INTENSITY_0 if self.intensity == 0 else RGB_INTENSITY_1
            r = max(0, int(orig_r + (R - orig_r) * shimmer))
            g = max(0, int(orig_g + (G - orig_g) * shimmer))
            b = max(0, int(orig_b + (B - orig_b) * shimmer))

            self.set_pixel(x, y, r, g, b)

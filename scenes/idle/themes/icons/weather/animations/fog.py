"""Fog animation — subtle patchy background with prominent sinusoidal lines.

Fog uses the same configuration as mist — a patchy shimmer background
with prominent undulating sinusoidal lines on top.

Uses the shared ``FogMistAnimation`` engine from ``fog_mist.py``.

Intensity controls:
    - the number of sinusoidal lines
    - line brightness
    - the number of background rows

    0 (light)  — 2 lines, 8 bg rows, dim
    1 (medium) — 3 lines, 10 bg rows, medium
    2 (heavy)  — 4 lines, 12 bg rows, bright
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.fog_mist import (
    FogMistAnimation,
    FogMistConfig,
)

# Fog colour (grey-white)
COLOUR = (160, 160, 170)

# Background rows per intensity — same coverage as mist.
BG_ROWS = {
    0: [3, 4, 5, 6, 7, 8, 9, 10],  # 8 rows
    1: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11],  # 10 rows
    2: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],  # 12 rows
}

# Shimmer target range
BG_TARGET_RANGE = {
    0: (0.1, 0.4),  # light:  dim
    1: (0.15, 0.5),  # medium: medium
    2: (0.2, 0.6),  # heavy:  bright
}

# Shimmer transition speed
BG_SPEED_RANGE = {
    0: (0.3, 0.7),
    1: (0.4, 0.9),
    2: (0.5, 1.1),
}

# Sinusoidal lines — same as mist.
LINE_COUNT = {
    0: 2,
    1: 2,
    2: 2,
}

LINE_AMPLITUDE = {
    0: 1.0,
    1: 0.9,
    2: 1.1,
}

LINE_FREQUENCY = {
    0: 0.6,
    1: 0.7,
    2: 0.8,
}

LINE_SPEED = {
    0: 1.5,
    1: 1.8,
    2: 2.0,
}

# Lines are brighter than the background.
LINE_BRIGHTNESS = {
    0: 0.45,
    1: 0.40,
    2: 0.45,
}


CONFIG = FogMistConfig(
    colour=COLOUR,
    background_enabled=False,
    bg_rows=BG_ROWS,
    bg_target_range=BG_TARGET_RANGE,
    bg_speed_range=BG_SPEED_RANGE,
    line_count=LINE_COUNT,
    line_amplitude=LINE_AMPLITUDE,
    line_frequency=LINE_FREQUENCY,
    line_speed=LINE_SPEED,
    line_brightness=LINE_BRIGHTNESS,
)


class FogAnimation(FogMistAnimation):
    """Patchy fog with prominent sinusoidal lines."""

    CONFIG = CONFIG

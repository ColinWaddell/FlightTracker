"""Mist animation — subtle patchy background with prominent sinusoidal lines.

Mist emphasises the sinusoidal lines (more lines, brighter) over a
thinner patchy shimmer background.  The result is a lighter, more
structured mist with visible undulating wave patterns.

Uses the shared ``FogMistAnimation`` engine from ``fog_mist.py``.

Intensity controls:
    - the number of sinusoidal lines
    - line brightness
    - the number of background rows

    0 (light)  — 2 lines, 3 bg rows, dim
    1 (medium) — 3 lines, 4 bg rows, medium
    2 (heavy)  — 4 lines, 5 bg rows, bright
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.fog_mist import (
    FogMistAnimation,
    FogMistConfig,
)

# Mist colour (grey-blue)
COLOUR = (170, 170, 180)

# Background rows per intensity — mist covers more than before but
# less than fog at each intensity level.
BG_ROWS = {
    0: [3, 4, 5, 6, 7, 8, 9, 10],                # 8 rows
    1: [2, 3, 4, 5, 6, 7, 8, 9, 10, 11],         # 10 rows
    2: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],  # 12 rows
}

# Shimmer target range
BG_TARGET_RANGE = {
    0: (0.1, 0.4),     # light:  dim
    1: (0.15, 0.5),    # medium: medium
    2: (0.2, 0.6),     # heavy:  bright
}

# Shimmer transition speed — slightly faster than fog.
BG_SPEED_RANGE = {
    0: (0.3, 0.7),
    1: (0.4, 0.9),
    2: (0.5, 1.1),
}

# Sinusoidal lines — mist has more, brighter lines.
LINE_COUNT = {
    0: 2,
    1: 3,
    2: 4,
}

LINE_AMPLITUDE = {
    0: 1.2,
    1: 1.5,
    2: 2.0,
}

LINE_FREQUENCY = {
    0: 0.6,
    1: 0.7,
    2: 0.8,
}

LINE_SPEED = {
    0: 2.0,
    1: 2.5,
    2: 3.0,
}

# Lines are brighter than the background in mist.
LINE_BRIGHTNESS = {
    0: 0.55,
    1: 0.65,
    2: 0.75,
}


CONFIG = FogMistConfig(
    colour=COLOUR,
    bg_rows=BG_ROWS,
    bg_target_range=BG_TARGET_RANGE,
    bg_speed_range=BG_SPEED_RANGE,
    line_count=LINE_COUNT,
    line_amplitude=LINE_AMPLITUDE,
    line_frequency=LINE_FREQUENCY,
    line_speed=LINE_SPEED,
    line_brightness=LINE_BRIGHTNESS,
)


class MistAnimation(FogMistAnimation):
    """Subtle patchy mist with prominent sinusoidal lines."""

    CONFIG = CONFIG

"""Registry mapping animation name strings to animation engine classes.

Used by ``ForecastSprite`` to instantiate the correct animation engine
from the ``codes.py`` mapping.  Returns ``None`` for a ``None`` animation
name (no animation — e.g., static cloudy conditions).
"""

from __future__ import annotations

from typing import Optional, Type

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation
from scenes.idle.themes.icons.weather.animations.blowing_snow import (
    BlowingSnowAnimation,
)
from scenes.idle.themes.icons.weather.animations.dusty import DustyAnimation
from scenes.idle.themes.icons.weather.animations.fog import FogAnimation
from scenes.idle.themes.icons.weather.animations.mist import MistAnimation
from scenes.idle.themes.icons.weather.animations.moon_rays import MoonRaysAnimation
from scenes.idle.themes.icons.weather.animations.rain import RainAnimation
from scenes.idle.themes.icons.weather.animations.rays import RaysAnimation
from scenes.idle.themes.icons.weather.animations.sleet import SleetAnimation
from scenes.idle.themes.icons.weather.animations.snow import SnowAnimation
from scenes.idle.themes.icons.weather.animations.thunder import ThunderAnimation
from scenes.idle.themes.icons.weather.animations.thunder_rain import (
    ThunderRainAnimation,
)
from scenes.idle.themes.icons.weather.animations.thunder_snow import (
    ThunderSnowAnimation,
)

ANIMATION_REGISTRY: dict[str, Type[BaseAnimation]] = {
    "rain": RainAnimation,
    "snow": SnowAnimation,
    "sleet": SleetAnimation,
    "thunder": ThunderAnimation,
    "thunder_rain": ThunderRainAnimation,
    "thunder_snow": ThunderSnowAnimation,
    "fog": FogAnimation,
    "mist": MistAnimation,
    "dusty": DustyAnimation,
    "rays": RaysAnimation,
    "moon_rays": MoonRaysAnimation,
    "blowing_snow": BlowingSnowAnimation,
}


def get_animation_class(name: str | None) -> Optional[Type[BaseAnimation]]:
    """Return the animation class for *name*, or ``None`` if no animation."""
    if name is None:
        return None
    return ANIMATION_REGISTRY.get(name)
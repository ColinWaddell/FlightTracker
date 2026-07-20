"""Thunder animation — random lightning bolts flashing under the cloud.

Lightning bolts flash briefly in the bounding box beneath the cloud icon.
Each flash picks a random bolt shape and random horizontal position, so
no two flashes look the same and there is no detectable loop.

The thunder box is fixed (shared with rain/snow/sleet):
    top-left     [3, 11]
    bottom-right [11, 14]

Each flash lasts 5 frames: 3 frames at full brightness, then 2 frames
of dimmer afterglow, then dark.  Between flashes the box is empty.

Intensity controls:
    - flash frequency (per-frame chance of a new flash)
    - bolt brightness

    0 (light)  — rare flashes, dimmer bolts
    1 (medium) — occasional flashes, bright bolts
    2 (heavy)  — frequent flashes, brightest bolts
"""

from __future__ import annotations

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation
from scenes.idle.themes.icons.weather.animations.thunder_mixin import ThunderMixin


class ThunderAnimation(ThunderMixin, BaseAnimation):
    """Random lightning bolts flashing under the cloud."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._thunder_init()

    def draw(self, frame_idx: int) -> None:
        self._thunder_tick()

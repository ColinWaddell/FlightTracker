"""ForecastSprite — a static weather icon plus an animated effect layer.

A sprite occupies a 16×18 pixel region on the canvas:

    rows  0–11  static icon (16×12 PNG, drawn once at creation)
    rows 12–17  animation area (6px, ticked every frame)

For condition codes that have no static icon (fog, mist, dusty — where
``codes.py`` specifies ``None`` for the icon), the animation engine
fills the full 18px height.

Lifecycle:
    1. Instantiate with icon name, animation name, intensity, day/night.
    2. Call ``draw()`` every frame to advance the animation.
    3. Call ``destroy()`` to blank the sprite area before discarding.

The sprite internally tracks its frame counter and delegates animation
to the engine selected from the registry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from PIL import Image

from display.rgbpanel import RGBPanel
from scenes.idle.themes.icons.weather.animations.base import BaseAnimation
from scenes.idle.themes.icons.weather.animations.registry import get_animation_class

# -----------------------------------------------------------------------
# Dimensions
# -----------------------------------------------------------------------

SPRITE_WIDTH = 16
SPRITE_HEIGHT = 18
ICON_HEIGHT = 12
ANIMATION_HEIGHT = SPRITE_HEIGHT - ICON_HEIGHT  # 6px

# -----------------------------------------------------------------------
# Icon asset loading (module-level cache, shared with forecast theme)
# -----------------------------------------------------------------------

_ICON_DIR = Path(__file__).parent
_image_cache: dict[str, Image.Image] = {}


def _load_icon(filename: str) -> Image.Image:
    """Load a weather icon PNG, caching the result for reuse."""
    if filename not in _image_cache:
        path = _ICON_DIR / f"{filename}.png"
        _image_cache[filename] = Image.open(path).convert("RGBA")
    return _image_cache[filename]


# -----------------------------------------------------------------------
# ForecastSprite
# -----------------------------------------------------------------------


class ForecastSprite:
    """A weather forecast sprite: static icon + animated effect.

    Args:
        canvas:         Panel canvas object.
        panel:          RGBPanel instance.
        x:              Absolute canvas x of the sprite top-left.
        y:              Absolute canvas y of the sprite top-left.
        icon_name:      Static icon name (without ``.png``), or ``None``
                        if the condition has no static icon.
        animation_name: Animation name from ``codes.py``, or ``None``
                        for static conditions (no animation).
        intensity:      0 = light, 1 = medium, 2 = heavy.
        is_day:         Currently unused by the sprite itself (day/night
                        icon selection is done by the caller), but kept
                        for future per-day/night animation variants.
    """

    def __init__(
        self,
        canvas,
        panel: RGBPanel,
        x: int,
        y: int,
        icon_name: Optional[str],
        animation_name: Optional[str],
        intensity: int,
        is_day: bool = True,
    ) -> None:
        self.canvas = canvas
        self.panel = panel
        self.x = x
        self.y = y
        self.icon_name = icon_name
        self.animation_name = animation_name
        self.intensity = intensity
        self.is_day = is_day
        self.frame: int = 0

        # --- Draw the static icon (once) ---
        self._has_icon = icon_name is not None
        if self._has_icon:
            img = _load_icon(icon_name)
            self.panel.draw_image(self.canvas, x, y, img)

        # --- Instantiate the animation engine ---
        self.animation: Optional[BaseAnimation] = None
        anim_cls = get_animation_class(animation_name)
        if anim_cls is not None:
            if self._has_icon:
                # Animation plays below the icon
                anim_x = x
                anim_y = y + ICON_HEIGHT
                anim_w = SPRITE_WIDTH
                anim_h = ANIMATION_HEIGHT
            else:
                # No icon — animation fills the full sprite area
                anim_x = x
                anim_y = y
                anim_w = SPRITE_WIDTH
                anim_h = SPRITE_HEIGHT

            self.animation = anim_cls(
                x=anim_x,
                y=anim_y,
                width=anim_w,
                height=anim_h,
                intensity=intensity,
                panel=panel,
                canvas=canvas,
            )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def draw(self) -> None:
        """Advance the animation by one frame.

        Called every frame (~12.5 fps) by the theme or test harness.
        Only touches the delta pixels — no full-area clear.
        """
        if self.animation is not None:
            self.animation.tick()
        self.frame += 1

    def destroy(self) -> None:
        """Blank the entire sprite area (16×18).

        Call this before discarding the sprite to avoid leaving stale
        pixels on the canvas.
        """
        # Blank the animation area first (engine knows its exact pixels)
        if self.animation is not None:
            self.animation.reset()

        # Blank the full sprite region to be safe
        for py in range(self.y, self.y + SPRITE_HEIGHT):
            for px in range(self.x, self.x + SPRITE_WIDTH):
                self.panel.set_pixel(self.canvas, px, py, 0, 0, 0)

    @property
    def animation_frame(self) -> int:
        """Current frame index within the animation loop (0-based)."""
        if self.animation is not None:
            return self.animation.frame % self.animation.frame_count
        return 0

    @property
    def animation_frame_count(self) -> int:
        """Total number of frames in the animation loop."""
        if self.animation is not None:
            return self.animation.frame_count
        return 0
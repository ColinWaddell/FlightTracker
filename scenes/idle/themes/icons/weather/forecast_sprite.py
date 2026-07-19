"""ForecastSprite — a static weather icon plus an animated effect layer.

A sprite occupies a 15×18 pixel region on the canvas.  The static icon
(a 15×12 PNG) is drawn once at creation with its top-left corner at
``(0, 3)`` — i.e. inset 3px from the top of the sprite.  The animation
then plays over the **entire** 15×18 area, which means an animation may
draw on top of the icon.

Lifecycle:
    1. Instantiate with icon name, animation name, intensity, day/night.
    2. Call ``draw()`` every frame to advance the animation.
    3. Call ``destroy()`` to blank the sprite area before discarding.

The sprite internally tracks its frame counter and delegates animation
to the engine selected from the registry.  A snapshot of the sprite's
RGB state (icon drawn, nothing animated yet) is passed to the animation
engine so it can restore icon pixels it overwrites between frames.
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

SPRITE_WIDTH = 15
SPRITE_HEIGHT = 18
ICON_HEIGHT = 12  # height of the icon PNG itself
ICON_OFFSET_Y = 3  # y offset of the icon within the sprite
# The animation occupies the full sprite area, so the animation height
# equals the sprite height.  Kept as an export for callers that layout
# around the sprite.
ANIMATION_HEIGHT = SPRITE_HEIGHT

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


def _build_original(
    width: int,
    height: int,
    icon_image: Optional[Image.Image],
    icon_offset: tuple[int, int],
) -> list[list[tuple[int, int, int]]]:
    """Snapshot the sprite's RGB state before any animation runs.

    The grid is ``height`` rows of ``width`` columns of ``(r, g, b)``
    triples.  Pixels outside the icon are black; pixels inside the icon
    carry the icon's own RGB (matching what ``draw_image`` writes to the
    canvas, which skips fully-transparent pixels).
    """
    grid: list[list[tuple[int, int, int]]] = [
        [(0, 0, 0)] * width for _ in range(height)
    ]
    if icon_image is None:
        return grid

    ox, oy = icon_offset
    iw, ih = icon_image.size
    px = icon_image.load()
    for ly in range(height):
        for lx in range(width):
            ix, iy = lx - ox, ly - oy
            if 0 <= ix < iw and 0 <= iy < ih:
                r, g, b, a = px[ix, iy]
                if a > 0:
                    grid[ly][lx] = (r, g, b)
    return grid


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
        icon_image: Optional[Image.Image] = None
        icon_offset = (0, 0)
        if self._has_icon:
            icon_image = _load_icon(icon_name)
            icon_offset = (0, ICON_OFFSET_Y)
            self.panel.draw_image(self.canvas, x, y + ICON_OFFSET_Y, icon_image)

        # --- Snapshot the pre-animation state ---
        original = _build_original(SPRITE_WIDTH, SPRITE_HEIGHT, icon_image, icon_offset)

        # --- Instantiate the animation engine (always full sprite area) ---
        self.animation: Optional[BaseAnimation] = None
        anim_cls = get_animation_class(animation_name)
        if anim_cls is not None:
            self.animation = anim_cls(
                x=x,
                y=y,
                width=SPRITE_WIDTH,
                height=SPRITE_HEIGHT,
                intensity=intensity,
                panel=panel,
                canvas=canvas,
                original=original,
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

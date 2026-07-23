"""Weather sprite helpers — icon drawing + animation lifecycle.

This module provides the helpers the forecast theme uses to manage
weather sprites.  There is no ``ForecastSprite`` class — the theme owns
the lifecycle directly:

    1. ``blank_area()``      — clear the sprite region to black.
    2. ``draw_icon()``       — draw the static icon PNG once.
    3. ``build_original()``  — snapshot the pre-animation colours.
    4. ``create_animation()``— instantiate the animation engine.
    5. ``anim.tick()``       — call every frame to advance the animation.
    6. ``blank_area()``      — clear again at teardown.

The animation engine receives the ``original`` snapshot so it can query
``original_pixel(lx, ly)`` to restore icon pixels it overwrites.  The
engine is fully responsible for clearing its own pixels between frames
— the base class does no automatic restoration.
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
SPRITE_HEIGHT = 15
ICON_HEIGHT = 12  # height of the icon PNG itself
ICON_OFFSET_Y = 0  # y offset of the icon within the sprite
# Kept as an export for callers that layout around the sprite.
ANIMATION_HEIGHT = SPRITE_HEIGHT

# -----------------------------------------------------------------------
# Icon asset loading (module-level cache, shared with forecast theme)
# -----------------------------------------------------------------------

_ICON_DIR = Path(__file__).parent
_image_cache: dict[str, Image.Image] = {}


def _load_icon(filename: str) -> Optional[Image.Image]:
    """Load a weather icon PNG, caching the result for reuse.

    Returns ``None`` if the filename is empty or the PNG doesn't exist.
    """
    if not filename:
        return None
    if filename not in _image_cache:
        path = _ICON_DIR / f"{filename}.png"
        if not path.exists():
            return None
        _image_cache[filename] = Image.open(path).convert("RGBA")
    return _image_cache[filename]


# -----------------------------------------------------------------------
# Lifecycle helpers
# -----------------------------------------------------------------------


def blank_area(panel: RGBPanel, canvas, x: int, y: int) -> None:
    """Blank the full sprite region (SPRITE_WIDTH × SPRITE_HEIGHT) to black."""
    for py in range(y, y + SPRITE_HEIGHT):
        for px in range(x, x + SPRITE_WIDTH):
            panel.set_pixel(canvas, px, py, 0, 0, 0)


def draw_icon(
    panel: RGBPanel, canvas, x: int, y: int, icon_name: Optional[str]
) -> Optional[Image.Image]:
    """Draw the static icon PNG at (x, y + ICON_OFFSET_Y).

    Returns the loaded icon ``Image`` (for passing to ``build_original``),
    or ``None`` if ``icon_name`` is ``None``.
    """
    if icon_name is None:
        return None
    icon_image = _load_icon(icon_name)
    if icon_image is None:
        return None
    panel.draw_image(canvas, x, y + ICON_OFFSET_Y, icon_image)
    return icon_image


def build_original(
    icon_image: Optional[Image.Image],
) -> list[list[tuple[int, int, int]]]:
    """Snapshot the sprite's RGB state before any animation runs.

    The grid is ``SPRITE_HEIGHT`` rows of ``SPRITE_WIDTH`` columns of
    ``(r, g, b)`` triples.  Pixels outside the icon are black; pixels
    inside the icon carry the icon's own RGB (matching what ``draw_image``
    writes to the canvas, which skips fully-transparent pixels).
    """
    return _build_original_grid(
        SPRITE_WIDTH, SPRITE_HEIGHT, icon_image, (0, ICON_OFFSET_Y)
    )


def _build_original_grid(
    width: int,
    height: int,
    icon_image: Optional[Image.Image],
    icon_offset: tuple[int, int],
) -> list[list[tuple[int, int, int]]]:
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


def create_animation(
    panel: RGBPanel,
    canvas,
    x: int,
    y: int,
    icon_name: Optional[str],
    animation_name: Optional[str],
    intensity: int,
) -> Optional[BaseAnimation]:
    """Full sprite setup: blank, draw icon, snapshot, instantiate engine.

    Returns the animation engine (ready to ``tick()`` every frame), or
    ``None`` if ``animation_name`` is ``None`` (static condition).

    The caller is responsible for blanking the area again when
    discarding the animation (see ``blank_area``).
    """
    blank_area(panel, canvas, x, y)
    icon_image = draw_icon(panel, canvas, x, y, icon_name)
    original = build_original(icon_image)

    anim_cls = get_animation_class(animation_name)
    if anim_cls is None:
        return None
    return anim_cls(
        x=x,
        y=y,
        width=SPRITE_WIDTH,
        height=SPRITE_HEIGHT,
        intensity=intensity,
        panel=panel,
        canvas=canvas,
        original=original,
    )

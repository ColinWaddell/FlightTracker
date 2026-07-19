"""Base class for live-draw weather animation engines.

An animation engine owns a rectangular area of the canvas (which may
overlap the static icon) and is called every frame to draw its current
state.  The base class does **no** automatic restoration between frames
— the engine is fully responsible for clearing pixels it no longer
wants and for restoring icon pixels it has overwritten.

The caller (theme) is responsible for the surrounding lifecycle:
blanking the area, drawing the icon once, snapshotting the pre-animation
colours into ``original``, and blanking again at teardown.

Engines can query ``original_pixel(lx, ly)`` to read back what a pixel
looked like before any animation touched it — useful for restoring icon
pixels (``self.set_pixel(lx, ly, *self.original_pixel(lx, ly))``) or
for blending effects that tint the icon rather than overwrite it.

All drawing helpers take **local** coordinates (0,0 = top-left of the
animation area); the base translates them to absolute canvas coordinates
using ``self.x`` and ``self.y``.
"""

from __future__ import annotations

from typing import Optional

from display.rgbpanel import RGBPanel

# Type alias: original[ly][lx] = (r, g, b) before the animation started.
OriginalGrid = list[list[tuple[int, int, int]]]


class BaseAnimation:
    """Live-draw animation engine.

    Args:
        x:        Absolute canvas x of the animation area top-left.
        y:        Absolute canvas y of the animation area top-left.
        width:    Animation area width in pixels.
        height:   Animation area height in pixels.
        intensity: 0 = light, 1 = medium, 2 = heavy.
        panel:    RGBPanel instance (provides draw_circle, draw_line, etc.).
        canvas:   Canvas object from the panel driver.
        original: Snapshot of the area's RGB state after the icon was
                  drawn, before any animation.  ``original[ly][lx]``.
                  When ``None`` the area is assumed all-black.
    """

    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        intensity: int,
        panel: RGBPanel,
        canvas,
        original: Optional[OriginalGrid] = None,
    ) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.intensity = max(0, min(2, intensity))
        self.panel = panel
        self.canvas = canvas
        self.frame: int = 0
        self._original: OriginalGrid = original or [
            [(0, 0, 0)] * width for _ in range(height)
        ]

    # ------------------------------------------------------------------
    # Original-state lookup
    # ------------------------------------------------------------------

    def original_pixel(self, lx: int, ly: int) -> tuple[int, int, int]:
        """Return the RGB at local (lx, ly) before the animation started.

        Out-of-bounds coordinates return black ``(0, 0, 0)``.
        """
        if 0 <= ly < self.height and 0 <= lx < self.width:
            return self._original[ly][lx]
        return (0, 0, 0)

    # ------------------------------------------------------------------
    # Drawing helpers (local coordinates — offset applied automatically)
    # ------------------------------------------------------------------

    def set_pixel(self, lx: int, ly: int, r: int, g: int, b: int) -> None:
        """Set a single pixel at local (lx, ly) to (r, g, b)."""
        self.panel.set_pixel(self.canvas, self.x + lx, self.y + ly, r, g, b)

    def draw_line(self, x0: int, y0: int, x1: int, y1: int, colour) -> None:
        """Draw a line between two local-coordinate points."""
        self.panel.draw_line(
            self.canvas,
            self.x + x0,
            self.y + y0,
            self.x + x1,
            self.y + y1,
            colour,
        )

    def draw_circle(self, cx: int, cy: int, radius: int, colour) -> None:
        """Draw a circle outline centred at local (cx, cy)."""
        self.panel.draw_circle(self.canvas, self.x + cx, self.y + cy, radius, colour)

    def draw_square(self, x0: int, y0: int, x1: int, y1: int, colour) -> None:
        """Draw a filled rectangle between two local-coordinate corners."""
        self.panel.draw_square(
            self.canvas,
            self.x + x0,
            self.y + y0,
            self.x + x1,
            self.y + y1,
            colour,
        )

    def draw_text(self, font, lx: int, ly: int, colour, text: str) -> int:
        """Draw text at local (lx, ly).  Returns the advance width."""
        return self.panel.draw_text(
            self.canvas, font, self.x + lx, self.y + ly, colour, text
        )

    def make_colour(self, r: int, g: int, b: int):
        """Create a Colour object via the panel driver."""
        return self.panel.make_colour(r, g, b)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def tick(self) -> None:
        """Advance one frame: call ``draw()`` and increment the counter."""
        self.draw(self.frame)
        self.frame += 1

    def draw(self, frame_idx: int) -> None:
        """Draw this frame onto the canvas in local coordinates.

        Override in subclasses.  The base does **not** restore the area
        between frames — you must clear pixels you no longer want
        (via ``self.set_pixel(lx, ly, 0, 0, 0)`` or
        ``self.set_pixel(lx, ly, *self.original_pixel(lx, ly))`` for
        pixels that sit on the icon).
        """
        raise NotImplementedError

    def reset(self) -> None:
        """Reset the frame counter.

        Does **not** touch the canvas — if the engine needs to clear its
        pixels on teardown it should override this and do so explicitly.
        The caller is expected to blank the area when discarding the
        animation.
        """
        self.frame = 0

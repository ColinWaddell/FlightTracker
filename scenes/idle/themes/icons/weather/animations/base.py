"""Base class for all weather animation engines.

An animation engine owns a rectangular region of the sprite and produces
a looping sequence of frames.  Each frame is a *delta* — a set of pixels
to light and a set of pixels to blank — so that ``tick()`` only touches
the pixels that actually change between consecutive frames.  This keeps
the per-frame redraw cost minimal on low-powered devices.

Frame tables are expressed in *local* coordinates (0,0 = top-left of the
animation area).  The engine translates them to absolute canvas
coordinates at draw time using ``self.x`` and ``self.y``.

Subclasses must populate ``self._frames`` — a list of dicts with keys:

    ``"set"``:   list of (x, y, r, g, b) tuples — pixels to light
    ``"clear"``: list of (x, y) tuples          — pixels to blank

Both lists are optional (default to empty).  ``"clear"`` should contain
the pixels that were *set* in the previous frame so they are erased
before the new frame is drawn.
"""

from __future__ import annotations

from display.rgbpanel import RGBPanel


class BaseAnimation:
    """Abstract base for delta-based weather animations.

    Args:
        x:        Absolute canvas x of the animation area top-left.
        y:        Absolute canvas y of the animation area top-left.
        width:    Animation area width in pixels.
        height:   Animation area height in pixels.
        intensity: 0 = light, 1 = medium, 2 = heavy.
        panel:    RGBPanel instance for drawing.
        canvas:   Canvas object from the panel driver.
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
    ) -> None:
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.intensity = max(0, min(2, intensity))
        self.panel = panel
        self.canvas = canvas
        self.frame: int = 0
        self._frames: list[dict] = []
        self._build_frames()

    # ------------------------------------------------------------------
    # Subclass hook
    # ------------------------------------------------------------------

    def _build_frames(self) -> None:
        """Populate ``self._frames`` with the lookup table.

        Override in subclasses.  Each entry is::

            {"set": [(x, y, r, g, b), ...], "clear": [(x, y), ...]}

        Coordinates are local (0-based within the animation area).
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def frame_count(self) -> int:
        """Number of frames in the animation loop."""
        return len(self._frames)

    def tick(self) -> None:
        """Advance one frame and draw the delta onto the canvas."""
        if not self._frames:
            return

        current = self._frames[self.frame % len(self._frames)]

        # Blank pixels from the previous frame
        for lx, ly in current.get("clear", ()):
            self.panel.set_pixel(
                self.canvas,
                self.x + lx,
                self.y + ly,
                0,
                0,
                0,
            )

        # Light pixels for the current frame
        for lx, ly, r, g, b in current.get("set", ()):
            self.panel.set_pixel(
                self.canvas,
                self.x + lx,
                self.y + ly,
                r,
                g,
                b,
            )

        self.frame += 1

    def reset(self) -> None:
        """Blank every pixel that any frame could set, then reset frame to 0."""
        if not self._frames:
            self.frame = 0
            return

        seen: set[tuple[int, int]] = set()
        for f in self._frames:
            for lx, ly, *_ in f.get("set", ()):
                seen.add((lx, ly))
        for lx, ly in seen:
            self.panel.set_pixel(
                self.canvas,
                self.x + lx,
                self.y + ly,
                0,
                0,
                0,
            )
        self.frame = 0
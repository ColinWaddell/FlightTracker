"""Base class for all weather animation engines.

An animation engine owns a rectangular region of the sprite — which may
overlap the static icon — and produces a looping sequence of frames.
Each frame is a set of pixels to light; restoration of the previous
frame's pixels is handled automatically by the base class.

Restoration model
-----------------
The base class is given an ``original`` grid: a snapshot of the sprite's
RGB state *after* the icon was drawn and *before* any animation touched
it.  For pixels outside the icon this is black ``(0,0,0)``; for pixels
inside the icon it is the icon's own colour.

On every ``tick()`` the base first restores every pixel the previous
frame lit back to its ``original`` value, then draws the current frame's
``set`` pixels.  This means:

* a pixel that should return to **black** → its original is ``(0,0,0)``,
  so restoring blanks it;
* a pixel drawn **over the icon** → its original is the icon colour, so
  restoring re-paints the icon.

Engines therefore never need to declare which pixels to clear — they
only declare what to ``set`` each frame.  A pixel only remains lit if
it appears in the current frame's ``set`` list; anything not re-set is
restored automatically.

Frame tables are expressed in *local* coordinates (0,0 = top-left of the
animation area).  The engine translates them to absolute canvas
coordinates at draw time using ``self.x`` and ``self.y``.

Subclasses must populate ``self._frames`` — a list of dicts with a
single key:

    ``"set"``: list of (x, y, r, g, b) tuples — pixels to light

The ``"set"`` key is optional (defaults to empty).
"""

from __future__ import annotations

from typing import Optional

from display.rgbpanel import RGBPanel

# Type alias: original[ly][lx] = (r, g, b) before the animation started.
OriginalGrid = list[list[tuple[int, int, int]]]


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
        original: Snapshot of the sprite's RGB state before the
                  animation started (``original[ly][lx]``).  When
                  ``None`` the area is assumed to be all-black.
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
        self._frames: list[dict] = []
        # Snapshot of the sprite before the animation started drawing.
        self._original: OriginalGrid = original or [
            [(0, 0, 0)] * width for _ in range(height)
        ]
        # Local coordinates of pixels currently lit by the animation.
        self._active: set[tuple[int, int]] = set()
        self._build_frames()

    # ------------------------------------------------------------------
    # Subclass hook
    # ------------------------------------------------------------------

    def _build_frames(self) -> None:
        """Populate ``self._frames`` with the lookup table.

        Override in subclasses.  Each entry is::

            {"set": [(x, y, r, g, b), ...]}

        Coordinates are local (0-based within the animation area).
        No ``"clear"`` key is used — restoration is automatic.
        """
        raise NotImplementedError

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

    def _restore(self, pixels) -> None:
        """Restore the given local pixels to their original RGB values."""
        for lx, ly in pixels:
            r, g, b = self.original_pixel(lx, ly)
            self.panel.set_pixel(self.canvas, self.x + lx, self.y + ly, r, g, b)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def frame_count(self) -> int:
        """Number of frames in the animation loop."""
        return len(self._frames)

    def tick(self) -> None:
        """Advance one frame: restore previous pixels, then draw new ones."""
        if not self._frames:
            return

        current = self._frames[self.frame % len(self._frames)]

        # Restore everything we lit last frame to its original state.
        if self._active:
            self._restore(self._active)
            self._active.clear()

        # Light this frame's pixels and remember them for next time.
        for lx, ly, r, g, b in current.get("set", ()):
            self.panel.set_pixel(self.canvas, self.x + lx, self.y + ly, r, g, b)
            self._active.add((lx, ly))

        self.frame += 1

    def reset(self) -> None:
        """Restore all active pixels to original, then reset frame to 0."""
        if self._active:
            self._restore(self._active)
            self._active.clear()
        self.frame = 0

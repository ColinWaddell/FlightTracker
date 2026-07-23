"""
Scroller - pre-rendered content scroller with built-in dirty-pixel updates.

Pre-renders content to a PIL Image, then slides it across a viewport.
Each frame, only pixels that changed since the previous frame are written
to the panel — no full-region blanking required.

Supports two modes:

  - **Linear scroll** (default): position auto-advances each tick.
    Content starts at the right edge of the viewport and moves left.
    When the content has fully scrolled off the left edge, ``tick()``
    returns ``True`` to signal completion.  Used for the plane-details strip.

  - **Manual offset**: caller sets the offset directly via ``set_offset()``
    and calls ``tick()`` to render.  Used for the journey bounce scroller
    where the ``LineScroller`` state machine controls positioning.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from setup.themes import TC, THEME_BG


class Scroller:
    """A scrolling viewport with diff-based dirty updates.

    Args:
        panel       : RGBPanel instance (for set_pixel / draw_square)
        canvas      : the panel canvas to draw onto
        x, y        : viewport position on the real canvas (top-left)
        width       : viewport width in pixels
        height      : viewport height in pixels
        bg_colour   : background colour (Colour namedtuple or (r,g,b) tuple)
        speed       : pixels to advance per tick (linear mode only)
    """

    def __init__(
        self,
        panel,
        canvas,
        x: int,
        y: int,
        width: int,
        height: int,
        bg_colour=None,
        speed: int = 1,
        # Deprecated — kept for backward compatibility but ignored.
        gap_pixels: int = 0,
    ):
        self.panel = panel
        self.canvas = canvas
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.speed = speed

        if bg_colour is None:
            bg_colour = TC(THEME_BG)
        cr, cg, cb = _unpack_colour(bg_colour)
        self._bg = (cr, cg, cb)

        # Content state
        self._content: np.ndarray | None = None  # shape (height, content_w, 3)
        self._content_width = 0

        # Position: the x-coordinate of the content's left edge
        # relative to the viewport's left edge.
        #   width  = content starts at the right edge (off-screen)
        #   0      = content left-aligned with viewport
        #  -width  = content has fully scrolled off the left edge
        self._position = 0

        # Previous frame buffer — what we last drew to the canvas.
        # Initialised to None so the first tick does a full draw.
        self._prev: np.ndarray | None = None

        # Paused state — when True, tick() renders but does not advance.
        self._paused = False

        # Reusable viewport buffer (avoids per-frame allocation)
        self._viewport = np.full((self.height, self.width, 3), self._bg, dtype=np.uint8)

    # ------------------------------------------------------------------
    # Content management
    # ------------------------------------------------------------------

    def set_content(self, image: Image.Image) -> None:
        """Set the content strip from a PIL Image.

        The image height must match the scroller height.
        Resets position to the right edge of the viewport (content enters
        from the right) and forces a full redraw on the next tick.
        """
        if image.height != self.height:
            raise ValueError(
                f"Content image height {image.height} does not match "
                f"scroller height {self.height}"
            )
        if image.mode != "RGB":
            image = image.convert("RGB")
        self._content = np.asarray(image, dtype=np.uint8)
        self._content_width = image.width
        self._position = self.width  # start at the right edge
        self._prev = None  # force full redraw

    def set_content_blank(self) -> None:
        """Set content to a blank strip (all background colour).

        Forces a full redraw on next tick to clear any previously drawn pixels.
        """
        blank = Image.new("RGB", (self.width, self.height), self._bg)
        self.set_content(blank)

    @property
    def content_width(self) -> int:
        return self._content_width

    @property
    def offset(self) -> int:
        """Current position (negative = scrolled left of viewport)."""
        return self._position

    # ------------------------------------------------------------------
    # Offset control (manual / bounce mode)
    # ------------------------------------------------------------------

    def set_offset(self, offset: int) -> None:
        """Jump to a specific offset (manual / bounce mode).

        The next ``tick()`` will render at this offset.
        Does not advance further (the caller controls position).
        """
        self._position = offset

    def reset(self) -> None:
        """Reset position to 0 and force a full redraw on next tick."""
        self._position = 0
        self._prev = None

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def tick(self) -> bool:
        """Render the current viewport to the canvas.

        In linear mode (default), advances the position left by ``speed``
        first.  In manual mode (after ``set_offset()``), renders at the
        current position.

        Returns True when the content has fully scrolled off the left edge
        (linear mode only).  In manual mode always returns False.
        """
        if self._content is None:
            return False

        # Advance position leftward in linear mode
        if not self._paused:
            self._position -= self.speed

        # Build the viewport frame (what should be visible now)
        frame = self._build_viewport()

        # Diff against previous frame and write only changed pixels
        self._render_diff(frame)

        # Signal completion when content has fully left the left edge
        if not self._paused:
            return self._position + self._content_width <= 0
        return False

    def _build_viewport(self) -> np.ndarray:
        """Build the current viewport as a (height, width, 3) uint8 array.

        Reuses an internal buffer to avoid allocating a new array every frame.

        Position is the x-coordinate of the content's left edge relative
        to the viewport.  Content pixel (cx, cy) appears at viewport
        column (position + cx) when 0 <= position + cx < width.
        """
        # Reset the buffer to background colour in-place
        self._viewport[:] = self._bg

        if self._content is None or self._content_width == 0:
            return self._viewport

        pos = self._position

        # Calculate the overlap between content and viewport
        # Content spans [pos, pos + content_width)
        # Viewport spans [0, width)
        start = max(0, pos)
        end = min(self.width, pos + self._content_width)

        if start < end:
            # Content is visible — copy the overlapping region
            src_start = start - pos  # content x offset
            src_end = end - pos
            self._viewport[:, start:end] = self._content[:, src_start:src_end]

        return self._viewport

    def _render_diff(self, frame: np.ndarray) -> None:
        """Write only changed pixels to the canvas."""
        if self._prev is None:
            # First frame or after reset — write everything
            changed = np.ones((self.height, self.width), dtype=bool)
        else:
            changed = np.any(frame != self._prev, axis=2)

        if not changed.any():
            self._prev = frame.copy()
            return

        # Get coordinates of changed pixels, ordered column-by-column
        ys, xs = np.where(changed)
        # Sort by column (x) then row (y) so updates go top-to-bottom
        # within each column before moving to the next column.
        order = np.argsort(xs, kind="stable")
        ys, xs = ys[order], xs[order]

        for py, px in zip(ys, xs):
            r, g, b = frame[py, px]
            self.panel.set_pixel(
                self.canvas,
                self.x + int(px),
                self.y + int(py),
                int(r),
                int(g),
                int(b),
            )

        self._prev = frame.copy()

    # ------------------------------------------------------------------
    # Clearing
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """Blank the viewport area on the canvas and reset internal state."""
        cr, cg, cb = self._bg
        for py in range(self.height):
            for px in range(self.width):
                self.panel.set_pixel(
                    self.canvas, self.x + px, self.y + py, cr, cg, cb
                )
        self._prev = None

    def force_full_redraw(self) -> None:
        """Force the next tick to write every pixel (not just changed ones)."""
        self._prev = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unpack_colour(colour):
    """Extract (r, g, b) from a colour value."""
    if hasattr(colour, "red"):
        return colour.red, colour.green, colour.blue
    if isinstance(colour, (tuple, list)) and len(colour) >= 3:
        return colour[0], colour[1], colour[2]
    return 0, 0, 0


# ---------------------------------------------------------------------------
# Content rendering helpers
# ---------------------------------------------------------------------------


def render_spans_to_image(
    spans: list, height: int, bg_colour=None
) -> Image.Image:
    """Pre-render a list of (colour, font, text) spans to a PIL Image.

    The image width is the total advance width of all spans.
    The image height is ``height`` pixels, with text baseline at
    ``height - 1`` (bottom-aligned, matching the flight scene layout
    where the scroller sits at the bottom of the panel).

    Args:
        spans     : list of (colour, BDFFont, text) tuples
        height    : image height in pixels
        bg_colour : background colour (defaults to black)

    Returns:
        PIL Image (RGB)
    """
    from display.bdf_font import draw_text as bdf_draw_text

    if bg_colour is None:
        bg = (0, 0, 0)
    else:
        bg = _unpack_colour(bg_colour)

    # Measure total width
    total_width = 0
    for colour, font, text in spans:
        for ch in text:
            total_width += font.CharacterWidth(ord(ch))

    if total_width == 0:
        total_width = 1  # avoid zero-width image

    img = Image.new("RGB", (total_width, height), bg)

    x = 0
    baseline = height - 1
    for colour, font, text in spans:
        x += bdf_draw_text(img, font, x, baseline, colour, text)

    return img


def render_text_to_image(
    text: str, font, height: int, colour, bg_colour=None
) -> Image.Image:
    """Pre-render a single text string to a PIL Image.

    Args:
        text      : the string to render
        font      : BDFFont instance
        height    : image height in pixels
        colour    : text colour
        bg_colour : background colour (defaults to black)

    Returns:
        PIL Image (RGB)
    """
    from display.bdf_font import draw_text as bdf_draw_text

    if bg_colour is None:
        bg = (0, 0, 0)
    else:
        bg = _unpack_colour(bg_colour)

    total_width = sum(font.CharacterWidth(ord(c)) for c in text)
    if total_width == 0:
        total_width = 1

    img = Image.new("RGB", (total_width, height), bg)
    bdf_draw_text(img, font, 0, height - 1, colour, text)
    return img
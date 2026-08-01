from __future__ import annotations

from enum import Enum, auto

from display.rendered_pixel import PixelColumn, RenderedPixels
from display.spans import Span, Spans
from setup import screen

EASING_STEPS = (1, 0, 0, 1, 1, 0, 1, 1, 1)
INITIAL_TICKS = 100
PAUSE_TICKS = 25


class BounceState(Enum):
    INITIAL = auto()
    REVEAL = auto()
    PAUSE = auto()
    RETRACT = auto()


def _tick_offset(tick: int) -> int:
    return 1 if tick >= len(EASING_STEPS) else EASING_STEPS[tick]


def _render_span(span: Span) -> RenderedPixels:
    """Render one span into sparse columns with y relative to its baseline."""
    font = span.font
    width = sum(
        glyph.dwidth if (glyph := font.get_glyph(ord(ch))) else 1 for ch in span.text
    )
    columns: RenderedPixels = [{} for _ in range(width)]
    advance = 0

    for ch in span.text:
        glyph = font.get_glyph(ord(ch))
        if glyph is None:
            advance += 1
            continue

        # Baseline is y=0. This is the existing draw_text() BDF placement
        # formula with the caller's baseline removed.
        top_y = -glyph.bbx_yoff - glyph.bbx_h + 1
        total_bits = ((glyph.bbx_w + 7) // 8) * 8

        for row_index, row_value in enumerate(glyph.rows):
            pixel_y = top_y + row_index

            for bit in range(glyph.bbx_w):
                if not row_value & (1 << (total_bits - 1 - bit)):
                    continue

                pixel_x = advance + glyph.bbx_xoff + bit
                if 0 <= pixel_x < width:
                    columns[pixel_x][pixel_y] = span.colour

        advance += glyph.dwidth

    return columns


def _render_spans(spans: Spans) -> RenderedPixels:
    rendered: RenderedPixels = []
    for span in spans:
        rendered += _render_span(span)
    return rendered


class Scroller:
    """Render and horizontally scroll coloured text spans in a viewport.

    ``x`` is the viewport's left edge. ``y`` is the text baseline.
    ``width`` is the number of physical display columns owned by the viewport.
    """

    def __init__(
        self,
        panel,
        canvas,
        x: int,
        y: int,
        width: int,
        spans: Spans,
        *,
        bounce: bool = False,
    ) -> None:
        if width <= 0:
            raise ValueError("Scroller width must be greater than zero")

        self.panel = panel
        self.canvas = canvas
        self.x = x
        self.y = y
        self.width = width
        self.bounce = bounce

        self._spans = spans
        self._rendered = _render_spans(spans)
        self._displayed: list[PixelColumn] = [{} for _ in range(width)]

        self.position = 0 if bounce else width
        self.state = BounceState.INITIAL
        self.timer = 0
        self.loop_count = 0
        self._looped = False

    @property
    def content_width(self) -> int:
        return len(self._rendered)

    @property
    def scroll_max(self) -> int:
        return max(0, self.content_width - self.width)

    def all_looped(self) -> bool:
        """Whether the complete content has been visible at least once."""
        return self._looped or (self.bounce and self.scroll_max == 0)

    def draw(self) -> None:
        """Advance one animation frame and apply only changed pixels."""
        if self.bounce:
            # Matches the old LineScroller: tick first, then draw.
            self._advance_bounce()
            self._draw_viewport()
        else:
            # Matches the old plane scroller: draw first, then move.
            self._draw_viewport()
            self._advance_continuous()

    def update(self, spans: Spans) -> None:
        """Replace content while preserving the current animation position.

        Pixels currently owned by the scroller are blanked first. The new
        content is then rendered at the retained position, clamped only where
        the new content makes that position invalid.
        """
        self._blank_displayed()
        self._spans = spans
        self._rendered = _render_spans(spans)
        self._clamp_after_update()
        self._draw_viewport()

    def clear(self) -> None:
        self._blank_displayed()

    def reset(self) -> None:
        """Blank the viewport and restart this scroller from its initial state."""
        self._blank_displayed()
        self.position = 0 if self.bounce else self.width
        self.state = BounceState.INITIAL
        self.timer = 0
        self.loop_count = 0
        self._looped = False

    def _advance_continuous(self) -> None:
        self.position -= 1

        if self.position + self.content_width < 0:
            self.position = self.width
            self.loop_count += 1
            self._looped = True

    def _advance_bounce(self) -> None:
        old_state = self.state

        if old_state == BounceState.REVEAL:
            self.position -= _tick_offset(self.timer)
        elif old_state == BounceState.RETRACT:
            self.position += _tick_offset(self.timer)

        if old_state == BounceState.INITIAL:
            if self.scroll_max > 0 and self.timer >= INITIAL_TICKS:
                self.state = BounceState.REVEAL
                self.timer = 0
            elif self.scroll_max == 0:
                self._looped = True

        elif old_state == BounceState.REVEAL:
            if self.position <= -self.scroll_max:
                self.position = -self.scroll_max
                self.state = BounceState.PAUSE
                self.timer = 0

        elif old_state == BounceState.PAUSE:
            self._looped = True
            if self.timer >= PAUSE_TICKS:
                self.state = (
                    BounceState.RETRACT
                    if self.position <= -self.scroll_max
                    else BounceState.INITIAL
                )
                self.timer = 0

        elif old_state == BounceState.RETRACT and self.position >= 0:
            self.position = 0
            self.loop_count += 1
            self._looped = True
            self.state = BounceState.PAUSE
            self.timer = 0

        self.timer += 1

    def _clamp_after_update(self) -> None:
        if self.bounce:
            if self.scroll_max == 0:
                self.position = 0
                self.state = BounceState.INITIAL
                self.timer = 0
                self._looped = True
                return

            self.position = max(-self.scroll_max, min(0, self.position))
            return

        if self.position + self.content_width < 0:
            self.position = self.width

    def _draw_viewport(self) -> None:
        desired: list[PixelColumn] = [{} for _ in range(self.width)]

        # Work is bounded by viewport width. The rest of the rendered text is
        # never inspected until it reaches the viewport.
        for viewport_x in range(self.width):
            source_x = viewport_x - self.position
            if not 0 <= source_x < self.content_width:
                continue

            visible_column = desired[viewport_x]
            for relative_y, colour in self._rendered[source_x].items():
                physical_y = self.y + relative_y
                if 0 <= physical_y < screen.HEIGHT:
                    visible_column[physical_y] = colour

        for viewport_x, (old, new) in enumerate(zip(self._displayed, desired)):
            physical_x = self.x + viewport_x
            if not 0 <= physical_x < screen.WIDTH:
                continue

            for physical_y in old.keys() | new.keys():
                old_colour = old.get(physical_y)
                new_colour = new.get(physical_y)

                if old_colour == new_colour:
                    continue

                if new_colour is None:
                    self.panel.set_pixel(
                        self.canvas,
                        physical_x,
                        physical_y,
                        0,
                        0,
                        0,
                    )
                else:
                    self.panel.set_pixel(
                        self.canvas,
                        physical_x,
                        physical_y,
                        new_colour.red,
                        new_colour.green,
                        new_colour.blue,
                    )

        self._displayed = desired

    def _blank_displayed(self) -> None:
        for viewport_x, column in enumerate(self._displayed):
            physical_x = self.x + viewport_x
            if not 0 <= physical_x < screen.WIDTH:
                continue

            for physical_y in column:
                self.panel.set_pixel(
                    self.canvas,
                    physical_x,
                    physical_y,
                    0,
                    0,
                    0,
                )

        self._displayed = [{} for _ in range(self.width)]

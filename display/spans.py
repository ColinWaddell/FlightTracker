# display/spans.py

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, TypeAlias

from display.bdf_font import BDFFont
from display.rendered_pixel import Colour

if TYPE_CHECKING:
    from display.rgbpanel import RGBPanel


class Span(NamedTuple):
    colour: Colour
    font: BDFFont
    text: str

    @property
    def width(self) -> int:
        """Pixel advance width of this span's text in its font."""
        return sum(self.font.CharacterWidth(ord(c)) for c in self.text)


Spans: TypeAlias = list[Span]


def spans_width(spans: Spans) -> int:
    """Total pixel width of a list of spans."""
    return sum(span.width for span in spans)


def draw_spans(panel: RGBPanel, canvas, spans: Spans, x: int, y: int) -> int:
    """Draw spans left-to-right at baseline ``y`` starting at ``x``.

    Returns the total advance width drawn (``x`` delta).
    """
    start_x = x
    for span in spans:
        x += panel.draw_text(canvas, span.font, x, y, span.colour, span.text)
    return x - start_x


def font_text_width(font: BDFFont, text: str) -> int:
    """Pixel advance width of ``text`` in ``font``."""
    return sum(font.CharacterWidth(ord(c)) for c in text)


# ---------------------------------------------------------------------------
# Placed spans — a Span with an (x, y) baseline position, used by scenes
# that draw text at fixed positions (e.g. the satellite telemetry panel).
# ---------------------------------------------------------------------------


class PlacedSpan(NamedTuple):
    """A :class:`Span` positioned at a baseline ``(x, y)`` on the canvas."""

    span: Span
    x: int
    y: int

    @property
    def width(self) -> int:
        """Pixel advance width of this placed span's text."""
        return self.span.width


PlacedSpans: TypeAlias = list[PlacedSpan]


def draw_placed_spans(panel: RGBPanel, canvas, placed_spans: PlacedSpans) -> None:
    """Draw each placed span at its own ``(x, y)`` baseline position."""
    for ps in placed_spans:
        panel.draw_text(canvas, ps.span.font, ps.x, ps.y, ps.span.colour, ps.span.text)


def erase_placed_spans(
    panel: RGBPanel, canvas, placed_spans: PlacedSpans, bg_colour: Colour
) -> None:
    """Overdraw each placed span's text in ``bg_colour`` at its position."""
    for ps in placed_spans:
        panel.draw_text(canvas, ps.span.font, ps.x, ps.y, bg_colour, ps.span.text)

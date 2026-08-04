"""Full-name journey label - bounce-scrolled ``"IATA>name"`` lines."""

from __future__ import annotations

from display.scroller import Scroller
from display.spans import Span, Spans
from setup import fonts, screen
from setup.configuration import Config
from setup.themes import (
    TC,
    THEME_BG,
    THEME_LOCATION_DESTINATION,
    THEME_LOCATION_DESTINATION_ARROW,
    THEME_LOCATION_DESTINATION_FULL,
    THEME_LOCATION_ORIGIN,
    THEME_LOCATION_ORIGIN_ARROW,
    THEME_LOCATION_ORIGIN_FULL,
)
from utilities.flight import Flight

# Baselines for the two scrolled lines (origin on top, destination below).
_FULL_LINE_Y = (6, 14)

ABBREVIATIONS = {
    "International": "Intl",
    "international": "Intl",
    "Airport": "",
    "airport": "",
    "Regional": "Reg",
    "regional": "Reg",
    "Municipal": "Muni",
    "municipal": "Muni",
}


def abbreviate(name: str) -> str:
    for long, short in ABBREVIATIONS.items():
        name = name.replace(long, short)
    return " ".join(name.split())


def _resolve_name(
    flight: Flight,
    flight_key_name: str,
    flight_key_muni: str,
    flight_key_country: str,
    style: int,
) -> str:
    if style == 1:
        return getattr(flight, flight_key_name, "") or ""
    if style == 2:
        return abbreviate(getattr(flight, flight_key_name, "") or "")
    if style == 3:
        return getattr(flight, flight_key_muni, "") or ""
    if style == 4:
        municipality = getattr(flight, flight_key_muni, "") or ""
        country = getattr(flight, flight_key_country, "") or ""
        return (
            f"{municipality}, {country}"
            if municipality and country
            else municipality or country
        )
    return getattr(flight, flight_key_name, "") or ""


def build_journey_spans(
    cfg: Config, flight: Flight, icon_required: bool = False
) -> tuple[Spans, Spans]:
    style = cfg.airport_display_style
    origin_name = _resolve_name(
        flight, "origin_name", "origin_municipality", "origin_country", style
    )
    destination_name = _resolve_name(
        flight,
        "destination_name",
        "destination_municipality",
        "destination_country",
        style,
    )

    font = fonts.small_symbols
    origin = flight.origin or cfg.journey_blank_filler
    destination = flight.destination or cfg.journey_blank_filler

    if icon_required:
        # The entire [code][arrow][name] line scrolls as one unit.
        origin_spans: Spans = [
            Span(TC(THEME_LOCATION_ORIGIN), font, origin),
            Span(TC(THEME_LOCATION_ORIGIN_ARROW), font, ">"),
            Span(TC(THEME_LOCATION_ORIGIN_FULL), font, f"{origin_name or 'Unknown'}"),
        ]
        destination_spans: Spans = [
            Span(TC(THEME_LOCATION_DESTINATION), font, destination),
            Span(TC(THEME_LOCATION_DESTINATION_ARROW), font, "<"),
            Span(
                TC(THEME_LOCATION_DESTINATION_FULL),
                font,
                f"{destination_name or 'Unknown'}",
            ),
        ]
    else:
        # Only the name scrolls; the code+arrow prefix is drawn statically.
        origin_spans = [
            Span(TC(THEME_LOCATION_ORIGIN_FULL), font, f"{origin_name or 'Unknown'}"),
        ]
        destination_spans = [
            Span(
                TC(THEME_LOCATION_DESTINATION_FULL),
                font,
                f"{destination_name or 'Unknown'}",
            ),
        ]
    return origin_spans, destination_spans


class FullNameLabel:
    """Bounce-scrolled origin/destination full names with an ``IATA>`` prefix.

    Owns two :class:`Scroller` instances (created on first draw, rebuilt on
    route change).  ``loop_completed`` becomes ``True`` once both scrollers
    have revealed their full content at least once.
    """

    def __init__(self, panel):
        self.panel = panel
        self.origin_scroller: Scroller | None = None
        self.dest_scroller: Scroller | None = None
        self.origin_spans: Spans | None = None
        self.dest_spans: Spans | None = None
        self.first_draw = True
        self._icon_required = False
        self.loop_completed = False

    def reset(self) -> None:
        for scroller in (self.origin_scroller, self.dest_scroller):
            if scroller is not None:
                scroller.clear()
        self.origin_scroller = None
        self.dest_scroller = None
        self.origin_spans = None
        self.dest_spans = None
        self.first_draw = True
        self._icon_required = False
        self.loop_completed = False

    def draw(
        self,
        canvas,
        flight: Flight,
        text_x_origin: int,
        available_width: int,
        icon_required: bool = False,
    ) -> None:
        cfg = Config.instance()
        origin_spans, dest_spans = build_journey_spans(cfg, flight, icon_required)

        if self.first_draw or self._icon_required != icon_required:
            self._icon_required = icon_required
            self.panel.draw_square(
                canvas, text_x_origin, 0, screen.WIDTH - 1, 16, TC(THEME_BG)
            )
            self._setup(
                canvas,
                cfg,
                flight,
                origin_spans,
                dest_spans,
                text_x_origin,
                available_width,
                icon_required,
            )
            self.first_draw = False
        else:
            if origin_spans != self.origin_spans:
                assert self.origin_scroller is not None
                self.origin_scroller.update(origin_spans)
                self.origin_spans = origin_spans
            if dest_spans != self.dest_spans:
                assert self.dest_scroller is not None
                self.dest_scroller.update(dest_spans)
                self.dest_spans = dest_spans

        assert self.origin_scroller is not None
        assert self.dest_scroller is not None

        self.origin_scroller.draw()
        self.dest_scroller.draw()

        # Keep two overflowing bounce lines approximately synchronised when
        # their state transitions diverge (preserved from the original code).
        if (
            self.origin_scroller.scroll_max > 0
            and self.dest_scroller.scroll_max > 0
            and self.origin_scroller.state != self.dest_scroller.state
        ):
            self.origin_scroller.timer = 0
            self.dest_scroller.timer = 0

        if self.origin_scroller.all_looped() and self.dest_scroller.all_looped():
            self.loop_completed = True

    def _setup(
        self,
        canvas,
        cfg: Config,
        flight: Flight,
        origin_spans: Spans,
        dest_spans: Spans,
        text_x_origin: int,
        available_width: int,
        icon_required: bool = False,
    ) -> None:
        for scroller in (self.origin_scroller, self.dest_scroller):
            if scroller is not None:
                scroller.clear()

        if icon_required:
            # The entire [code][arrow][name] scrolls as one unit from
            # text_x_origin with the full available width.
            self.origin_spans = origin_spans
            self.dest_spans = dest_spans
            self.origin_scroller = Scroller(
                self.panel,
                canvas,
                text_x_origin,
                _FULL_LINE_Y[0],
                max(1, available_width),
                origin_spans,
                bounce=True,
            )
            self.dest_scroller = Scroller(
                self.panel,
                canvas,
                text_x_origin,
                _FULL_LINE_Y[1],
                max(1, available_width),
                dest_spans,
                bounce=True,
            )
            return

        # Static prefix: draw [code][arrow] at text_x_origin, then scroll
        # only the name in the remaining width.
        font = fonts.small_symbols
        origin = flight.origin or cfg.journey_blank_filler
        destination = flight.destination or cfg.journey_blank_filler

        origin_x = text_x_origin + self.panel.draw_text(
            canvas,
            font,
            text_x_origin,
            _FULL_LINE_Y[0] + 1,
            TC(THEME_LOCATION_ORIGIN),
            origin,
        )
        origin_x += self.panel.draw_text(
            canvas,
            font,
            origin_x,
            _FULL_LINE_Y[0] + 1,
            TC(THEME_LOCATION_ORIGIN_ARROW),
            ">",
        )

        dest_x = text_x_origin + self.panel.draw_text(
            canvas,
            font,
            text_x_origin,
            _FULL_LINE_Y[1] + 1,
            TC(THEME_LOCATION_DESTINATION),
            destination,
        )
        dest_x += self.panel.draw_text(
            canvas,
            font,
            dest_x,
            _FULL_LINE_Y[1] + 1,
            TC(THEME_LOCATION_DESTINATION_ARROW),
            "<",
        )

        self.origin_spans = origin_spans
        self.dest_spans = dest_spans
        self.origin_scroller = Scroller(
            self.panel,
            canvas,
            origin_x,
            _FULL_LINE_Y[0],
            max(1, text_x_origin + available_width - origin_x),
            origin_spans,
            bounce=True,
        )
        self.dest_scroller = Scroller(
            self.panel,
            canvas,
            dest_x,
            _FULL_LINE_Y[1],
            max(1, text_x_origin + available_width - dest_x),
            dest_spans,
            bounce=True,
        )

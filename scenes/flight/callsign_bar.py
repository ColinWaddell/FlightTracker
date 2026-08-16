"""Info bar widget - callsign or airline name in the middle bar row.

Two modes, selected at construction via ``cfg.info_bar_mode``:

* :class:`CallsignBar` - draws the callsign with numeric/alpha colouring
  via :class:`Span` objects, plus the dividing bar and N/M index.
* :class:`AirlineNameBar` - looks up the airline name from
  ``assets/airlines.json`` via the resolved ICAO code and bounce-scrolls
  it using the :class:`Scroller`, same font/position as the callsign bar.

Both modes use :func:`build_info_spans` so that every text string -
callsign, airline name, or fallback - gets the same numeric/alpha
colour scheme (digits in ``THEME_FLIGHT_NUMERIC``, everything else in
``THEME_FLIGHT_ALPHA``).
"""

from __future__ import annotations

from assets.airlines.lookups import icao_to_airline
from display.scroller import Scroller
from display.spans import Span, Spans, draw_spans
from scenes.flight.airline_logo import airline_icao_from_flight
from setup import fonts, screen
from setup.configuration import Config
from setup.themes import (
    TC,
    THEME_AIRLINE,
    THEME_BG,
    THEME_DATA_INDEX,
    THEME_DIVIDING_BAR,
    THEME_FLIGHT_ALPHA,
    THEME_FLIGHT_NUMERIC,
)
from utilities.flight import Flight

# Shared layout constants (same as the original draw_callsign).
BAR_STARTING_POSITION = (0, 20)
BAR_PADDING = 2
FLIGHT_NO_POSITION = (0, 23)
FLIGHT_NO_TEXT_HEIGHT = 8
FLIGHT_NO_FONT = fonts.small
DATA_INDEX_POSITION = (52, 23)
DATA_INDEX_FONT = fonts.extrasmall


def airline_name_from_flight(flight: Flight) -> str:
    """Look up the airline name from the flight's resolved ICAO code."""
    icao = airline_icao_from_flight(flight)
    if not icao:
        return ""

    return icao_to_airline(icao) or ""


def build_info_spans(callsign: str = "", airline: str = "") -> Spans:
    """Build spans for the info bar.

    If both ``callsign`` and ``airline`` are supplied, the output is
    ``"[callsign] [airline]"`` (with a space separator).  If only one is
    supplied, it is rendered alone with no leading or trailing space.

    The callsign uses the numeric/alpha colour scheme (digits in
    ``THEME_FLIGHT_NUMERIC``, other characters in ``THEME_FLIGHT_ALPHA``).
    The airline name uses a single ``THEME_AIRLINE`` colour.
    """
    spans: Spans = []

    if callsign:
        spans.extend(_numeric_alpha_spans(callsign))

    if airline:
        if spans:
            spans.append(Span(TC(THEME_AIRLINE), FLIGHT_NO_FONT, " "))
        spans.append(Span(TC(THEME_AIRLINE), FLIGHT_NO_FONT, airline))

    return spans


def _numeric_alpha_spans(text: str) -> Spans:
    """Split ``text`` into per-character spans with numeric/alpha colouring.

    Digits use ``THEME_FLIGHT_NUMERIC``; all other characters use
    ``THEME_FLIGHT_ALPHA``.  Consecutive characters with the same colour
    are grouped into a single span for efficiency.
    """
    if not text:
        return []
    spans: Spans = []
    current_colour = None
    current_chars: list[str] = []

    for ch in text:
        colour = TC(THEME_FLIGHT_NUMERIC) if ch.isnumeric() else TC(THEME_FLIGHT_ALPHA)
        if colour != current_colour:
            if current_chars:
                spans.append(
                    Span(current_colour, FLIGHT_NO_FONT, "".join(current_chars))
                )
            current_colour = colour
            current_chars = [ch]
        else:
            current_chars.append(ch)

    if current_chars:
        spans.append(Span(current_colour, FLIGHT_NO_FONT, "".join(current_chars)))

    return spans


class CallsignBar:
    """Draws the callsign with numeric/alpha colouring, dividing bar + index."""

    def __init__(self, panel, cfg: Config | None = None):
        self.panel = panel
        self.cfg = cfg or Config.instance()
        self.last_callsign_drawn: str | None = None
        self.last_index_drawn: int | None = None
        self.last_flight_count_drawn: int | None = None

    def reset(self) -> None:
        self.last_callsign_drawn = None
        self.last_index_drawn = None
        self.last_flight_count_drawn = None

    @property
    def loop_completed(self) -> bool:
        """Static text - always considered fully revealed."""
        return True

    def draw(self, canvas, flights: list, flight_index: int) -> None:
        callsign = flights[flight_index].callsign
        flight_count = len(flights)
        index = flight_index

        if (
            callsign == self.last_callsign_drawn
            and index == self.last_index_drawn
            and flight_count == self.last_flight_count_drawn
        ):
            return

        self.last_callsign_drawn = callsign
        self.last_index_drawn = index
        self.last_flight_count_drawn = flight_count

        self.panel.draw_square(
            canvas,
            0,
            BAR_STARTING_POSITION[1] - (FLIGHT_NO_TEXT_HEIGHT // 2),
            screen.WIDTH - 1,
            BAR_STARTING_POSITION[1] + (FLIGHT_NO_TEXT_HEIGHT // 2),
            TC(THEME_BG),
        )
        flight_no_text_length = 0
        if callsign and callsign != "N/A":
            spans = build_info_spans(callsign=callsign)
            flight_no_text_length = draw_spans(
                self.panel,
                canvas,
                spans,
                FLIGHT_NO_POSITION[0],
                FLIGHT_NO_POSITION[1],
            )

        if flight_count > 1:
            self.panel.draw_square(
                canvas,
                DATA_INDEX_POSITION[0] - BAR_PADDING,
                BAR_STARTING_POSITION[1] - (FLIGHT_NO_TEXT_HEIGHT // 2),
                screen.WIDTH,
                BAR_STARTING_POSITION[1] + (FLIGHT_NO_TEXT_HEIGHT // 2),
                TC(THEME_BG),
            )
            self.panel.draw_line(
                canvas,
                flight_no_text_length + BAR_PADDING,
                BAR_STARTING_POSITION[1],
                DATA_INDEX_POSITION[0] - BAR_PADDING - 1,
                BAR_STARTING_POSITION[1],
                TC(THEME_DIVIDING_BAR),
            )
            self.panel.draw_text(
                canvas,
                DATA_INDEX_FONT,
                DATA_INDEX_POSITION[0],
                DATA_INDEX_POSITION[1],
                TC(THEME_DATA_INDEX),
                f"{index + 1}/{flight_count}",
            )
        else:
            self.panel.draw_line(
                canvas,
                flight_no_text_length + BAR_PADDING if flight_no_text_length else 0,
                BAR_STARTING_POSITION[1],
                screen.WIDTH,
                BAR_STARTING_POSITION[1],
                TC(THEME_DIVIDING_BAR),
            )


class AirlineNameBar:
    """Bounce-scrolls the airline name in the info bar position."""

    def __init__(self, panel, cfg: Config | None = None):
        self.panel = panel
        self.cfg = cfg or Config.instance()
        self.scroller: Scroller | None = None
        self.spans: Spans | None = None
        self.last_flight_id: str | None = None
        self.last_index_drawn: int | None = None
        self.last_flight_count_drawn: int | None = None
        # Flight count the scroller was built for, so a change in the
        # number of tracked flights (which alters the viewport width)
        # forces a rebuild even when the displayed flight_id is unchanged.
        self.last_flight_count_for_scroller: int | None = None

    def reset(self) -> None:
        if self.scroller is not None:
            self.scroller.clear()
        self.scroller = None
        self.spans = None
        self.last_flight_id = None
        self.last_index_drawn = None
        self.last_flight_count_drawn = None
        self.last_flight_count_for_scroller = None

    @property
    def loop_completed(self) -> bool:
        """True when the bounce-scrolled airline name has been fully revealed."""
        if self.scroller is None:
            return True
        return self.scroller.all_looped()

    def draw(self, canvas, flights: list, flight_index: int) -> None:
        flight = flights[flight_index]
        flight_count = len(flights)
        index = flight_index
        flight_id = flight.flight_id

        # Rebuild scroller when the flight changes (different airline
        # name) or when the flight count changes (the viewport width
        # depends on whether the N/M index is drawn).
        if (
            flight_id != self.last_flight_id
            or flight_count != self.last_flight_count_for_scroller
        ):
            self.last_flight_id = flight_id
            self.last_flight_count_for_scroller = flight_count
            name = airline_name_from_flight(flight)
            callsign = flight.callsign or (flight.registration or "")

            if self.cfg.info_bar_mode == "callsign_airline":
                if callsign and name:
                    self.spans = build_info_spans(callsign=callsign, airline=name)
                elif callsign:
                    self.spans = build_info_spans(callsign=callsign)
                else:
                    self.spans = build_info_spans(callsign="Unknown")
            elif self.cfg.info_bar_mode == "airline":
                if name:
                    self.spans = build_info_spans(airline=name)
                elif callsign:
                    self.spans = build_info_spans(callsign=callsign)
                else:
                    self.spans = build_info_spans(callsign="Unknown")
            else:  # callsign mode
                if callsign:
                    self.spans = build_info_spans(callsign=callsign)
                else:
                    self.spans = build_info_spans(callsign="")

            if self.scroller is not None:
                self.scroller.clear()

            # Blank the bar region.
            self.panel.draw_square(
                canvas,
                0,
                BAR_STARTING_POSITION[1] - (FLIGHT_NO_TEXT_HEIGHT // 2),
                screen.WIDTH - 1,
                BAR_STARTING_POSITION[1] + (FLIGHT_NO_TEXT_HEIGHT // 2),
                TC(THEME_BG),
            )

            self.scroller = Scroller(
                self.panel,
                canvas,
                FLIGHT_NO_POSITION[0],
                FLIGHT_NO_POSITION[1] - 1,
                DATA_INDEX_POSITION[0] - 2 if flight_count > 1 else screen.WIDTH,
                self.spans,
                bounce=True,
            )
            self.scroller.draw()
        elif self.scroller is not None:
            self.scroller.draw()

        # Draw the N/M index (same as callsign mode).
        if flight_count > 1 and (
            index != self.last_index_drawn
            or flight_count != self.last_flight_count_drawn
        ):
            self.last_index_drawn = index
            self.last_flight_count_drawn = flight_count
            self.panel.draw_square(
                canvas,
                DATA_INDEX_POSITION[0] - BAR_PADDING,
                BAR_STARTING_POSITION[1] - (FLIGHT_NO_TEXT_HEIGHT // 2),
                screen.WIDTH,
                BAR_STARTING_POSITION[1] + (FLIGHT_NO_TEXT_HEIGHT // 2),
                TC(THEME_BG),
            )
            self.panel.draw_text(
                canvas,
                DATA_INDEX_FONT,
                DATA_INDEX_POSITION[0],
                DATA_INDEX_POSITION[1],
                TC(THEME_DATA_INDEX),
                f"{index + 1}/{flight_count}",
            )


def make_callsign_bar(cfg: Config, panel):
    """Return the info bar widget for the configured display mode."""
    if cfg.info_bar_mode in ("airline", "callsign_airline"):
        return AirlineNameBar(panel, cfg)
    return CallsignBar(panel, cfg)

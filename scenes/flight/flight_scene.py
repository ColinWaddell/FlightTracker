"""
FlightScene - callsign bar, origin->destination journey, scrolling telemetry.

Shown when flight data is available.  Priority 1 (beats IdleScene).

Merges the three former mixin scenes:
    FlightDetailsScene -> draw_callsign()
    JourneyScene       -> draw_journey()
    PlaneDetailsScene  -> draw_plane_details()

Owns its own flight data.  Call on_data(new_flights) whenever the overhead
source produces a fresh result; the scene decides internally whether that
warrants a full reset (callsigns changed) or a silent telemetry swap.

Screen layout:
    rows  0-15  JourneyWidget (origin -> destination)
    rows 16-24  Callsign bar + optional N/M index
    rows 23-31  Scrolling plane details (make/model or telemetry)
"""

from __future__ import annotations

import logging
import time

from display.scroller import Scroller
from display.spans import Span, Spans
from setup import fonts, screen
from setup.configuration import Config
from setup.themes import (
    TC,
    THEME_ARROW,
    THEME_BG,
    THEME_DATA_INDEX,
    THEME_DIVIDING_BAR,
    THEME_FLIGHT_ALPHA,
    THEME_FLIGHT_NUMERIC,
    THEME_LOCATION_DESTINATION,
    THEME_LOCATION_DESTINATION_ARROW,
    THEME_LOCATION_DESTINATION_FULL,
    THEME_LOCATION_ORIGIN,
    THEME_LOCATION_ORIGIN_ARROW,
    THEME_LOCATION_ORIGIN_FULL,
    THEME_PLANE,
    THEME_PLANE_TLM,
    THEME_PLANE_TLM_UNITS,
)
from utilities.flight import TELEMETRY_FIELDS, Flight

logger = logging.getLogger(__name__)

PRIORITY = 1

# Seconds to wait before retrying after a failed overhead fetch.
# Prevents log spam and rapid reconnection attempts when the data
# source is unreachable.
ERROR_BACKOFF_S = 60

# ---------------------------------------------------------------------------
# Data update helpers
# ---------------------------------------------------------------------------


def callsigns_match(a: list, b: list) -> bool:
    return {f.flight_id for f in a} == {f.flight_id for f in b}


def telemetry_changed(old: list, new: list) -> bool:
    lookup = {f.flight_id: f for f in old}
    for flight in new:
        prev = lookup.get(flight.flight_id)
        if prev and any(
            getattr(flight, k) != getattr(prev, k) for k in TELEMETRY_FIELDS
        ):
            return True
    return False


# ---------------------------------------------------------------------------
# Callsign bar
# ---------------------------------------------------------------------------

BAR_STARTING_POSITION = (0, 20)
BAR_PADDING = 2
FLIGHT_NO_POSITION = (1, 23)
FLIGHT_NO_TEXT_HEIGHT = 8
FLIGHT_NO_FONT = fonts.small
DATA_INDEX_POSITION = (52, 23)
DATA_INDEX_TEXT_HEIGHT = 6
DATA_INDEX_FONT = fonts.extrasmall

# ---------------------------------------------------------------------------
# Plane details (scrolling bar)
# ---------------------------------------------------------------------------

PLANE_DETAILS_Y = 30
PLANE_DETAILS_HEIGHT = 8

# ---------------------------------------------------------------------------
# Journey widget
# ---------------------------------------------------------------------------


FULL_LINE_Y = (6, 14)

IATA_ORIGIN_X = 1
IATA_DESTINATION_X = 40
ARROW_TIP_X = 34
ARROW_TIP_Y = 7
ARROW_WIDTH = 4
ARROW_HEIGHT = 8

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


# ---------------------------------------------------------------------------
# FlightScene
# ---------------------------------------------------------------------------


class FlightScene:
    """
    Priority-1 scene.  Draws the full flight display when flights are present.

    Args:
        canvas : panel canvas
        panel  : RGBPanel instance for drawing operations
    """

    priority = PRIORITY

    def __init__(self, canvas, panel, overhead, refresh_interval: float):
        """
        Args:
            canvas           : panel canvas
            panel            : RGBPanel instance
            overhead         : Overhead instance (FR24 or tar1090)
            refresh_interval : seconds between data fetches
        """
        self.canvas = canvas
        self.panel = panel
        self.overhead = overhead
        self.refresh_interval = refresh_interval

        # Kick the first fetch immediately
        self.overhead.grab_data()
        self.last_grab_time = time.time()

        # Internal flight state - owned entirely by this scene
        self.flights: list = []
        self.flight_index: int = 0
        self.all_looped_flag: bool = False
        self.frame: int = 0

        # Journey state
        self.journey_first_draw = True
        self.journey_mode: str | None = None
        self.origin_scroller: Scroller | None = None
        self.dest_scroller: Scroller | None = None
        self.origin_spans: Spans | None = None
        self.dest_spans: Spans | None = None
        self.journey_loop_completed = False
        self.last_origin: str | None = None
        self.last_dest: str | None = None

        # Plane details state
        self.details_scroller: Scroller | None = None
        self.details_spans: Spans | None = None
        self.last_details_mode: int | None = None

        # Callsign bar cache - only redraw when these change
        self.last_callsign_drawn: str | None = None
        self.last_index_drawn: int | None = None
        self.last_flight_count_drawn: int | None = None

        # Error backoff - log once, hold off before retrying
        self.error_logged: bool = False
        self.retry_at: float = 0.0

    # ------------------------------------------------------------------
    # Data ownership
    # ------------------------------------------------------------------

    def poll(self) -> None:
        """
        Called every frame by SceneManager.kick().
        Consumes new overhead data and triggers fresh fetches on interval.
        Errors are logged once and suppressed until the backoff expires.
        """
        now = time.time()

        if self.overhead.error is not None:
            if not self.error_logged:
                logger.warning(
                    "Overhead fetch failed: %s - retrying in %ds",
                    self.overhead.error,
                    ERROR_BACKOFF_S,
                )
                self.error_logged = True
                self.retry_at = now + ERROR_BACKOFF_S
            if now >= self.retry_at:
                # Backoff expired - clear state and kick a fresh grab.
                # grab_data() resets the error flag internally.
                self.error_logged = False
                self.overhead.grab_data()
                self.last_grab_time = now
            return

        # Successful state - clear any lingering backoff flags.
        self.error_logged = False
        self.retry_at = 0.0

        if self.overhead.new_data:
            self.on_data(self.overhead.data)  # accessing .data clears new_data flag

        if (
            now - self.last_grab_time >= self.refresh_interval
            and not self.overhead.processing
            and not self.overhead.new_data
            and self.all_looped
        ):
            self.overhead.grab_data()
            self.last_grab_time = now

    def on_data(self, new_flights: list) -> None:
        """
        Called by Display.run() when the overhead source has fresh data.
        Decides whether to fully reset (callsigns changed) or silently
        swap telemetry values without interrupting the scroll.
        """
        old_flights = self.flights
        there_is_data = len(old_flights) > 0

        if not callsigns_match(old_flights, new_flights):
            self.flight_index = 0
            self.all_looped_flag = False
            self.flights = new_flights
            if there_is_data:
                self.reset()
        else:
            # Same flights - always pick up the latest data so that
            # route info, plane model, or airport names that were
            # incomplete on a previous fetch (or filled in from the
            # route cache) are reflected.  No reset needed; the
            # scroller continues uninterrupted.
            self.flights = new_flights

    @property
    def all_looped(self) -> bool:
        """True when the scene has cycled through all flights at least once,
        or when there are 0-1 flights (no meaningful looping to wait for)."""
        return self.all_looped_flag or len(self.flights) <= 1

    # ------------------------------------------------------------------
    # Scene protocol
    # ------------------------------------------------------------------

    def has_data(self) -> bool:
        return len(self.flights) > 0

    def active(self) -> bool:
        return len(self.flights) > 0

    def on_enter(self) -> None:
        """Called by SceneManager on scene transition. Clears canvas then resets."""
        self.panel.clear(self.canvas)
        self.reset()

    def reset(self) -> None:
        self.frame = 0

        for scroller in (
            self.origin_scroller,
            self.dest_scroller,
            self.details_scroller,
        ):
            if scroller is not None:
                scroller.clear()

        self.journey_first_draw = True
        self.journey_mode = None
        self.origin_scroller = None
        self.dest_scroller = None
        self.origin_spans = None
        self.dest_spans = None
        self.journey_loop_completed = False
        self.last_origin = None
        self.last_dest = None

        self.details_scroller = None
        self.details_spans = None
        self.last_details_mode = None

        self.last_callsign_drawn = None
        self.last_index_drawn = None
        self.last_flight_count_drawn = None

    def draw(self) -> None:
        self.frame += 1
        self.draw_callsign()
        self.draw_journey()
        self.draw_plane_details()

    # ------------------------------------------------------------------
    # Callsign bar
    # ------------------------------------------------------------------

    def draw_callsign(self) -> None:
        callsign = self.flights[self.flight_index].callsign
        flight_count = len(self.flights)
        index = self.flight_index

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
            self.canvas,
            0,
            BAR_STARTING_POSITION[1] - (FLIGHT_NO_TEXT_HEIGHT // 2),
            screen.WIDTH - 1,
            BAR_STARTING_POSITION[1] + (FLIGHT_NO_TEXT_HEIGHT // 2),
            TC(THEME_BG),
        )
        flight_no_text_length = 0
        if callsign and callsign != "N/A":
            for ch in callsign:
                ch_length = self.panel.draw_text(
                    self.canvas,
                    FLIGHT_NO_FONT,
                    FLIGHT_NO_POSITION[0] + flight_no_text_length,
                    FLIGHT_NO_POSITION[1],
                    (
                        TC(THEME_FLIGHT_NUMERIC)
                        if ch.isnumeric()
                        else TC(THEME_FLIGHT_ALPHA)
                    ),
                    ch,
                )
                flight_no_text_length += ch_length

        if flight_count > 1:
            self.panel.draw_square(
                self.canvas,
                DATA_INDEX_POSITION[0] - BAR_PADDING,
                BAR_STARTING_POSITION[1] - (FLIGHT_NO_TEXT_HEIGHT // 2),
                screen.WIDTH,
                BAR_STARTING_POSITION[1] + (FLIGHT_NO_TEXT_HEIGHT // 2),
                TC(THEME_BG),
            )
            self.panel.draw_line(
                self.canvas,
                flight_no_text_length + BAR_PADDING,
                BAR_STARTING_POSITION[1],
                DATA_INDEX_POSITION[0] - BAR_PADDING - 1,
                BAR_STARTING_POSITION[1],
                TC(THEME_DIVIDING_BAR),
            )
            self.panel.draw_text(
                self.canvas,
                DATA_INDEX_FONT,
                DATA_INDEX_POSITION[0],
                DATA_INDEX_POSITION[1],
                TC(THEME_DATA_INDEX),
                f"{index + 1}/{flight_count}",
            )
        else:
            self.panel.draw_line(
                self.canvas,
                flight_no_text_length + BAR_PADDING if flight_no_text_length else 0,
                BAR_STARTING_POSITION[1],
                screen.WIDTH,
                BAR_STARTING_POSITION[1],
                TC(THEME_DIVIDING_BAR),
            )

    # ------------------------------------------------------------------
    # Journey widget
    # ------------------------------------------------------------------

    def draw_journey(self) -> None:
        cfg = Config.instance()
        flight = self.flights[self.flight_index]
        origin = flight.origin
        destination = flight.destination

        route_changed = origin != self.last_origin or destination != self.last_dest
        if route_changed:
            for scroller in (self.origin_scroller, self.dest_scroller):
                if scroller is not None:
                    scroller.clear()

            self.journey_first_draw = True
            self.journey_mode = None
            self.origin_scroller = None
            self.dest_scroller = None
            self.origin_spans = None
            self.dest_spans = None
            self.journey_loop_completed = False
            self.last_origin = origin
            self.last_dest = destination

        if cfg.airport_display_style == 0:
            if self.journey_mode != "iata":
                for scroller in (self.origin_scroller, self.dest_scroller):
                    if scroller is not None:
                        scroller.clear()
                self.origin_scroller = None
                self.dest_scroller = None
                self.origin_spans = None
                self.dest_spans = None
                self.journey_mode = "iata"
                self.journey_first_draw = True
                self.journey_loop_completed = False

            if not self.journey_loop_completed:
                self.draw_iata_mode(cfg, flight)
                self.journey_first_draw = False
            return

        origin_spans, dest_spans = self.build_journey_spans(cfg, flight)

        if self.journey_mode != "full" or self.journey_first_draw:
            self.journey_mode = "full"
            self.panel.draw_square(
                self.canvas, 0, 0, screen.WIDTH - 1, 16, TC(THEME_BG)
            )
            self.setup_full_mode(origin_spans, dest_spans)
            self.journey_first_draw = False
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

        # Preserve the old behaviour that keeps two overflowing bounce lines
        # approximately synchronised when their state transitions diverge.
        if (
            self.origin_scroller.scroll_max > 0
            and self.dest_scroller.scroll_max > 0
            and self.origin_scroller.state != self.dest_scroller.state
        ):
            self.origin_scroller.timer = 0
            self.dest_scroller.timer = 0

        if self.origin_scroller.all_looped() and self.dest_scroller.all_looped():
            self.journey_loop_completed = True

    def draw_iata_mode(self, cfg, flight: Flight) -> None:
        origin = flight.origin or cfg.journey_blank_filler
        destination = flight.destination or cfg.journey_blank_filler
        home_code = cfg.home_airport_code

        self.panel.draw_square(self.canvas, 0, 0, screen.WIDTH - 1, 15, TC(THEME_BG))

        font = fonts.large_bold if origin == home_code else fonts.large
        self.panel.draw_text(
            self.canvas, font, IATA_ORIGIN_X, 12, TC(THEME_LOCATION_ORIGIN), origin
        )
        font = fonts.large_bold if destination == home_code else fonts.large
        self.panel.draw_text(
            self.canvas,
            font,
            IATA_DESTINATION_X,
            12,
            TC(THEME_LOCATION_DESTINATION),
            destination,
        )

        ax, ay = ARROW_TIP_X, ARROW_TIP_Y
        x = ax - ARROW_WIDTH
        y1 = ay - (ARROW_HEIGHT // 2)
        y2 = ay + (ARROW_HEIGHT // 2)
        self.panel.set_pixel(
            self.canvas,
            ax,
            ay,
            TC(THEME_ARROW).red,
            TC(THEME_ARROW).green,
            TC(THEME_ARROW).blue,
        )
        for _ in range(ARROW_WIDTH):
            self.panel.draw_line(self.canvas, x, y1, x, y2, TC(THEME_ARROW))
            x += 1
            y1 += 1
            y2 -= 1

        self.journey_loop_completed = True

    def build_journey_spans(self, cfg, flight: Flight) -> tuple[Spans, Spans]:
        origin = flight.origin or cfg.journey_blank_filler
        destination = flight.destination or cfg.journey_blank_filler
        style = cfg.airport_display_style

        def resolve_name(
            flight_key_name: str,
            flight_key_muni: str,
            flight_key_country: str,
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

        origin_name = resolve_name(
            "origin_name", "origin_municipality", "origin_country"
        )
        destination_name = resolve_name(
            "destination_name",
            "destination_municipality",
            "destination_country",
        )

        font = fonts.small_symbols

        origin_spans: Spans = [
            Span(TC(THEME_LOCATION_ORIGIN), font, origin),
            Span(TC(THEME_LOCATION_ORIGIN_ARROW), font, ">"),
            Span(
                TC(THEME_LOCATION_ORIGIN_FULL),
                font,
                f"{origin_name or 'Unknown'} ",
            ),
        ]
        destination_spans: Spans = [
            Span(TC(THEME_LOCATION_DESTINATION), font, destination),
            Span(TC(THEME_LOCATION_DESTINATION_ARROW), font, "<"),
            Span(
                TC(THEME_LOCATION_DESTINATION_FULL),
                font,
                f"{destination_name or 'Unknown'} ",
            ),
        ]

        return origin_spans, destination_spans

    def setup_full_mode(self, origin_spans: Spans, dest_spans: Spans) -> None:
        for scroller in (self.origin_scroller, self.dest_scroller):
            if scroller is not None:
                scroller.clear()

        self.origin_spans = origin_spans
        self.dest_spans = dest_spans
        self.origin_scroller = Scroller(
            self.panel,
            self.canvas,
            0,
            FULL_LINE_Y[0],
            screen.WIDTH,
            origin_spans,
            bounce=True,
        )
        self.dest_scroller = Scroller(
            self.panel,
            self.canvas,
            0,
            FULL_LINE_Y[1],
            screen.WIDTH,
            dest_spans,
            bounce=True,
        )

    # ------------------------------------------------------------------
    # Plane details (scrolling bar)
    # ------------------------------------------------------------------

    def build_spans(self, cfg) -> Spans:
        return self.telemetry_spans(cfg) if cfg.details == 1 else self.model_spans()

    def model_spans(self) -> Spans:
        text = self.flights[self.flight_index].plane
        return [Span(TC(THEME_PLANE), fonts.regular, text.upper())]

    def telemetry_spans(self, cfg) -> Spans:
        flight = self.flights[self.flight_index]
        altitude_ft = flight.altitude or 0
        ground_speed_kts = flight.ground_speed or 0
        heading = flight.heading or 0

        if cfg.height_unit == "ft":
            alt_val = str(int(altitude_ft))
            alt_unit = "ft"
        else:
            alt_val = str(int(altitude_ft * 0.3048))
            alt_unit = "m"

        if cfg.speed_unit == "kts":
            speed_val = str(int(ground_speed_kts))
            speed_unit = "kts"
        elif cfg.speed_unit == "mph":
            speed_val = str(int(ground_speed_kts * 1.15078))
            speed_unit = "mph"
        else:
            speed_val = str(int(ground_speed_kts * 1.852))
            speed_unit = "kmh"

        f = fonts.small_symbols
        val = TC(THEME_PLANE_TLM)
        ico = TC(THEME_PLANE_TLM_UNITS)

        return [
            Span(ico, f, "^"),
            Span(val, f, alt_val),
            Span(ico, f, alt_unit),
            Span(val, f, " "),
            Span(ico, f, "~"),
            Span(val, f, speed_val),
            Span(ico, f, speed_unit),
            Span(val, f, " "),
            Span(ico, f, "}"),
            Span(val, f, str(heading)),
            Span(ico, f, "*"),
        ]

    def draw_plane_details(self) -> None:
        cfg = Config.instance()
        current_mode = cfg.details
        spans = self.build_spans(cfg)

        if self.details_scroller is None or current_mode != self.last_details_mode:
            if self.details_scroller is not None:
                self.details_scroller.clear()

            self.details_scroller = Scroller(
                self.panel,
                self.canvas,
                0,
                PLANE_DETAILS_Y,
                screen.WIDTH,
                spans,
                bounce=False,
            )
            self.details_spans = spans
            self.last_details_mode = current_mode

        elif spans != self.details_spans:
            # Telemetry/model changes retain the current scroll position.
            self.details_scroller.update(spans)
            self.details_spans = spans

        previous_loop_count = self.details_scroller.loop_count
        self.details_scroller.draw()

        if (
            self.details_scroller.loop_count > previous_loop_count
            and len(self.flights) > 1
            and self.journey_loop_completed
        ):
            self.flight_index = (self.flight_index + 1) % len(self.flights)
            self.all_looped_flag = (not self.flight_index) or self.all_looped_flag
            self.reset()

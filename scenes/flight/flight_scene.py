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
from enum import Enum, auto

from setup import fonts, screen
from setup.configuration import Config
from display.scroller import Scroller, render_spans_to_image
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

PLANE_DISTANCE_FROM_TOP = 31
PLANE_TEXT_HEIGHT = 8

# ---------------------------------------------------------------------------
# Journey widget
# ---------------------------------------------------------------------------

EASING_STEPS = (1, 0, 0, 1, 1, 0, 1, 1, 1)


def tick_to_offset(tick: int) -> int:
    return 1 if tick >= len(EASING_STEPS) else EASING_STEPS[tick]


INITIAL_TICKS = 100
PAUSE_TICKS = 25

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


class BounceState(Enum):
    INITIAL = auto()
    REVEAL = auto()
    PAUSE = auto()
    RETRACT = auto()


class LineScroller:
    def __init__(self):
        self.reset()

    def reset(self):
        self.state = BounceState.INITIAL
        self.timer = 0
        self.position = 0
        self.scroll_max = 0
        self.loop_count = 0
        self.loop_done = False

    def tick(self) -> int:
        st = self.state

        if st == BounceState.REVEAL:
            self.position -= tick_to_offset(self.timer)
        elif st == BounceState.RETRACT:
            self.position += tick_to_offset(self.timer)

        if st == BounceState.INITIAL:
            if self.scroll_max > 0 and self.timer >= INITIAL_TICKS:
                self.state = BounceState.REVEAL
                self.timer = 0
            elif self.scroll_max == 0:
                self.loop_done = True
        elif st == BounceState.REVEAL:
            if self.position <= -self.scroll_max:
                self.position = -self.scroll_max
                self.state = BounceState.PAUSE
                self.timer = 0
        elif st == BounceState.PAUSE:
            self.loop_done = True
            if self.timer >= PAUSE_TICKS:
                self.state = (
                    BounceState.RETRACT
                    if self.position <= -self.scroll_max
                    else BounceState.INITIAL
                )
                self.timer = 0
        elif st == BounceState.RETRACT and self.position >= 0:
            self.position = 0
            self.loop_count += 1
            self.loop_done = True
            self.state = BounceState.PAUSE
            self.timer = 0

        self.timer += 1
        return self.position


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
        self.origin_scroll = LineScroller()
        self.dest_scroll = LineScroller()
        self._origin_scroller = Scroller(
            panel, canvas,
            x=0, y=0, width=screen.WIDTH, height=8,
            bg_colour=TC(THEME_BG), speed=0,
        )
        self._dest_scroller = Scroller(
            panel, canvas,
            x=0, y=8, width=screen.WIDTH, height=8,
            bg_colour=TC(THEME_BG), speed=0,
        )
        self.journey_loop_completed = False
        self.last_origin: str | None = None
        self.last_dest: str | None = None
        self.origin_name = ""
        self.dest_name = ""

        # Plane details state — Scroller handles scrolling + dirty updates
        self._plane_scroller = Scroller(
            panel, canvas,
            x=0, y=PLANE_DISTANCE_FROM_TOP - PLANE_TEXT_HEIGHT,
            width=screen.WIDTH, height=PLANE_TEXT_HEIGHT + 1,
            bg_colour=TC(THEME_BG),
            speed=1,
        )
        self._plane_spans: list | None = None
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
        self.journey_first_draw = True
        self.journey_mode = None
        self.origin_scroll.reset()
        self.dest_scroll.reset()
        self._origin_scroller.reset()
        self._dest_scroller.reset()
        self.journey_loop_completed = False
        self.last_origin = None
        self.last_dest = None
        self.origin_name = ""
        self.dest_name = ""
        self._plane_scroller.reset()
        self._plane_spans = None
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

        if origin != self.last_origin or destination != self.last_dest:
            self.journey_first_draw = True
            self.journey_mode = None
            self.origin_scroll.reset()
            self.dest_scroll.reset()
            self.journey_loop_completed = False
            self.last_origin = origin
            self.last_dest = destination

        if cfg.airport_display_style == 0:
            if not self.journey_loop_completed:
                self.draw_iata_mode(cfg, flight)
            return

        if self.journey_mode != "full" or self.journey_first_draw:
            self.journey_mode = "full"
            # Clear the journey area before setup draws the static text.
            self.panel.draw_square(
                self.canvas, 0, 0, screen.WIDTH - 1, 16, TC(THEME_BG)
            )
            self.setup_full_mode(cfg, flight)
            self._origin_scroller.force_full_redraw()
            self._dest_scroller.force_full_redraw()
            self.journey_first_draw = False

        for line_idx, (linescroller, scroller) in enumerate(
            ((self.origin_scroll, self._origin_scroller),
             (self.dest_scroll, self._dest_scroller))
        ):
            position = linescroller.tick()
            # LineScroller position is 0 or negative (scrolls left).
            # Scroller position is the content's left edge x-coordinate,
            # so a negative LineScroller position maps directly.
            scroller.set_offset(position)
            scroller.tick()

        if (
            self.origin_scroll.scroll_max > 0
            and self.dest_scroll.scroll_max > 0
            and self.origin_scroll.state != self.dest_scroll.state
        ):
            self.origin_scroll.timer = 0
            self.dest_scroll.timer = 0

        origin_done = self.origin_scroll.loop_done or self.origin_scroll.scroll_max == 0
        dest_done = self.dest_scroll.loop_done or self.dest_scroll.scroll_max == 0
        if origin_done and dest_done:
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

    def setup_full_mode(self, cfg, flight: Flight) -> None:
        origin = flight.origin or cfg.journey_blank_filler
        destination = flight.destination or cfg.journey_blank_filler

        style = cfg.airport_display_style

        def resolve_name(
            flight_key_name, flight_key_muni, flight_key_country, abbrev=False
        ):
            if style == 1:
                name = getattr(flight, flight_key_name, "") or ""
            elif style == 2:
                name = abbreviate(getattr(flight, flight_key_name, "") or "")
            elif style == 3:
                name = getattr(flight, flight_key_muni, "") or ""
            elif style == 4:
                muni = getattr(flight, flight_key_muni, "") or ""
                country = getattr(flight, flight_key_country, "") or ""
                name = f"{muni}, {country}" if muni and country else (muni or country)
            else:
                name = getattr(flight, flight_key_name, "") or ""
            return name

        origin_name = resolve_name(
            "origin_name", "origin_municipality", "origin_country"
        )
        dest_name = resolve_name(
            "destination_name", "destination_municipality", "destination_country"
        )

        self.origin_name = (origin_name or "Unknown") + " "
        self.dest_name = (dest_name or "Unknown") + " "

        from display.scroller import render_text_to_image

        # Measure the static part (IATA code + arrow) for each line.
        # The arrow glyph (" >" or " <") is 9px wide in small_symbols.
        origin_static_w = sum(
            fonts.small_symbols.CharacterWidth(ord(c)) for c in origin
        ) + fonts.small_symbols.CharacterWidth(ord(">"))
        dest_static_w = sum(
            fonts.small_symbols.CharacterWidth(ord(c)) for c in destination
        ) + fonts.small_symbols.CharacterWidth(ord("<"))

        # The scrolling viewport for the airport name starts just after
        # the static part and extends to the right edge of the screen.
        origin_viewport_x = origin_static_w
        origin_viewport_w = screen.WIDTH - origin_viewport_x
        dest_viewport_x = dest_static_w
        dest_viewport_w = screen.WIDTH - dest_viewport_x

        # Draw the static IATA code + arrow directly onto the canvas.
        # Origin line (y=0-7, baseline y=7)
        self.panel.draw_text(
            self.canvas, fonts.small_symbols, 0, 7,
            TC(THEME_LOCATION_ORIGIN), origin,
        )
        self.panel.draw_text(
            self.canvas, fonts.small_symbols,
            sum(fonts.small_symbols.CharacterWidth(ord(c)) for c in origin), 7,
            TC(THEME_LOCATION_ORIGIN_ARROW), ">",
        )
        # Destination line (y=8-15, baseline y=15)
        self.panel.draw_text(
            self.canvas, fonts.small_symbols, 0, 15,
            TC(THEME_LOCATION_DESTINATION), destination,
        )
        self.panel.draw_text(
            self.canvas, fonts.small_symbols,
            sum(fonts.small_symbols.CharacterWidth(ord(c)) for c in destination), 15,
            TC(THEME_LOCATION_DESTINATION_ARROW), "<",
        )

        # Pre-render just the airport name to a PIL image for the scrollers.
        origin_name_img = render_text_to_image(
            self.origin_name, fonts.small_symbols, height=8,
            colour=TC(THEME_LOCATION_ORIGIN_FULL), bg_colour=TC(THEME_BG),
        )
        dest_name_img = render_text_to_image(
            self.dest_name, fonts.small_symbols, height=8,
            colour=TC(THEME_LOCATION_DESTINATION_FULL), bg_colour=TC(THEME_BG),
        )

        # Reconfigure the scrollers for the name-only viewport.
        self._origin_scroller.x = origin_viewport_x
        self._origin_scroller.width = origin_viewport_w
        self._origin_scroller.set_content(origin_name_img)

        self._dest_scroller.x = dest_viewport_x
        self._dest_scroller.width = dest_viewport_w
        self._dest_scroller.set_content(dest_name_img)

        # Configure the LineScroller bounce state machines.
        # scroll_max is how far the name can scroll left while still
        # filling the viewport.
        self.origin_scroll.reset()
        self.dest_scroll.reset()
        self.origin_scroll.scroll_max = max(0, origin_name_img.width - origin_viewport_w)
        self.dest_scroll.scroll_max = max(0, dest_name_img.width - dest_viewport_w)

    # ------------------------------------------------------------------
    # Plane details (scrolling bar)
    # ------------------------------------------------------------------

    def build_spans(self, cfg) -> list:
        return self.telemetry_spans(cfg) if cfg.details == 1 else self.model_spans()

    def model_spans(self) -> list:
        text = self.flights[self.flight_index].plane
        return [(TC(THEME_PLANE), fonts.regular, text.upper())]

    def telemetry_spans(self, cfg) -> list:
        flight = self.flights[self.flight_index]
        altitude_ft = flight.altitude or 0
        ground_speed_kts = flight.ground_speed or 0
        heading = flight.heading or 0

        if cfg.units == "i":
            alt_val = str(int(altitude_ft))
            alt_unit = "ft"
            speed_val = str(int(ground_speed_kts * 1.15078))
            speed_unit = "mph"
        else:
            alt_val = str(int(altitude_ft * 0.3048))
            alt_unit = "m"
            speed_val = str(int(ground_speed_kts * 1.852))
            speed_unit = "kmh"

        f = fonts.small_symbols
        val = TC(THEME_PLANE_TLM)
        ico = TC(THEME_PLANE_TLM_UNITS)

        return [
            (ico, f, "^"),
            (val, f, alt_val),
            (ico, f, alt_unit),
            (val, f, " "),
            (ico, f, "~"),
            (val, f, speed_val),
            (ico, f, speed_unit),
            (val, f, " "),
            (ico, f, "}"),
            (val, f, str(heading)),
            (ico, f, "*"),
        ]

    def draw_plane_details(self) -> None:
        cfg = Config.instance()
        current_mode = cfg.details

        if current_mode != self.last_details_mode:
            self._plane_scroller.reset()
            self._plane_spans = None
            self.last_details_mode = current_mode

        spans = self.build_spans(cfg)

        # Re-render content only when spans change.
        # set_content() automatically positions the content at the
        # right edge of the viewport so it scrolls in from the right.
        if spans != self._plane_spans:
            self._plane_spans = spans
            content = render_spans_to_image(
                spans, height=self._plane_scroller.height,
                bg_colour=TC(THEME_BG),
            )
            self._plane_scroller.set_content(content)

        # tick() advances position left by speed, renders the viewport,
        # and returns True when the content has fully scrolled off the left.
        done = self._plane_scroller.tick()
        if done:
            if len(self.flights) > 1 and self.journey_loop_completed:
                self.flight_index = (self.flight_index + 1) % len(self.flights)
                self.all_looped_flag = (not self.flight_index) or self.all_looped_flag
                self.reset()

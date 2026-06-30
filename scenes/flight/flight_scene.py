"""
FlightScene — callsign bar, origin→destination journey, scrolling telemetry.

Shown when flight data is available.  Priority 1 (beats IdleScene).

Merges the three former mixin scenes:
    FlightDetailsScene → _draw_callsign()
    JourneyScene       → _draw_journey()
    PlaneDetailsScene  → _draw_plane_details()

Owns its own flight data.  Call on_data(new_flights) whenever the overhead
source produces a fresh result; the scene decides internally whether that
warrants a full reset (callsigns changed) or a silent telemetry swap.

Screen layout:
    rows  0-15  JourneyWidget (origin → destination)
    rows 16-24  Callsign bar + optional N/M index
    rows 23-31  Scrolling plane details (make/model or telemetry)
"""

from __future__ import annotations

import time
from enum import Enum, auto

from rgbmatrix import graphics

from setup import fonts, screen
from setup.themes import TC
from setup.themes import (
    THEME_BG,
    THEME_FLIGHT_ALPHA,
    THEME_FLIGHT_NUMERIC,
    THEME_DIVIDING_BAR,
    THEME_DATA_INDEX,
    THEME_PLANE,
    THEME_PLANE_TLM,
    THEME_PLANE_TLM_UNITS,
    THEME_ARROW,
    THEME_LOCATION_ORIGIN,
    THEME_LOCATION_DESTINATION,
    THEME_LOCATION_ORIGIN_FULL,
    THEME_LOCATION_DESTINATION_FULL,
    THEME_LOCATION_ORIGIN_ARROW,
    THEME_LOCATION_DESTINATION_ARROW,
)
from setup.configuration import Config

PRIORITY = 1

# ---------------------------------------------------------------------------
# Data update helpers
# ---------------------------------------------------------------------------

_TELEMETRY_FIELDS = ("altitude", "ground_speed", "heading")


def _callsigns_match(a: list, b: list) -> bool:
    return {f["callsign"] for f in a} == {f["callsign"] for f in b}


def _telemetry_changed(old: list, new: list) -> bool:
    lookup = {f["callsign"]: f for f in old}
    for flight in new:
        prev = lookup.get(flight["callsign"])
        if prev and any(flight.get(k) != prev.get(k) for k in _TELEMETRY_FIELDS):
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

_EASING_STEPS = (1, 0, 0, 1, 1, 0, 1, 1, 1)


def _tick_to_offset(tick: int) -> int:
    return 1 if tick >= len(_EASING_STEPS) else _EASING_STEPS[tick]


INITIAL_TICKS = 100
PAUSE_TICKS = 25

_FULL_LINE_Y = (7, 15)

_IATA_ORIGIN_X = 1
_IATA_DESTINATION_X = 40
_ARROW_TIP_X = 34
_ARROW_TIP_Y = 7
_ARROW_WIDTH = 4
_ARROW_HEIGHT = 8

_ABBREVIATIONS = {
    "International": "Intl",
    "international": "Intl",
    "Airport": "",
    "airport": "",
    "Regional": "Reg",
    "regional": "Reg",
    "Municipal": "Muni",
    "municipal": "Muni",
}


def _abbreviate(name: str) -> str:
    for long, short in _ABBREVIATIONS.items():
        name = name.replace(long, short)
    return " ".join(name.split())


def _font_text_width(font, text: str) -> int:
    return sum(font.CharacterWidth(ord(c)) for c in text)


class _BounceState(Enum):
    INITIAL = auto()
    REVEAL = auto()
    PAUSE = auto()
    RETRACT = auto()


class _LineScroller:
    def __init__(self):
        self.reset()

    def reset(self):
        self.state = _BounceState.INITIAL
        self.timer = 0
        self.position = 0
        self.scroll_max = 0
        self.loop_count = 0
        self.loop_done = False

    def tick(self) -> int:
        st = self.state

        if st == _BounceState.REVEAL:
            self.position -= _tick_to_offset(self.timer)
        elif st == _BounceState.RETRACT:
            self.position += _tick_to_offset(self.timer)

        if st == _BounceState.INITIAL:
            if self.scroll_max > 0 and self.timer >= INITIAL_TICKS:
                self.state = _BounceState.REVEAL
                self.timer = 0
            elif self.scroll_max == 0:
                self.loop_done = True
        elif st == _BounceState.REVEAL:
            if self.position <= -self.scroll_max:
                self.position = -self.scroll_max
                self.state = _BounceState.PAUSE
                self.timer = 0
        elif st == _BounceState.PAUSE:
            if self.timer >= PAUSE_TICKS:
                self.state = (
                    _BounceState.RETRACT
                    if self.position <= -self.scroll_max
                    else _BounceState.INITIAL
                )
                self.timer = 0
        elif st == _BounceState.RETRACT:
            if self.position >= 0:
                self.position = 0
                self.loop_count += 1
                self.loop_done = True
                self.state = _BounceState.PAUSE
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
        canvas      : rgbmatrix FrameCanvas
        draw_square : callable(x0, y0, x1, y1, colour)
    """

    priority = PRIORITY

    def __init__(self, canvas, draw_square, overhead, refresh_interval: float):
        """
        Args:
            canvas           : rgbmatrix FrameCanvas
            draw_square      : callable(x0, y0, x1, y1, colour)
            overhead         : Overhead instance (FR24 or tar1090)
            refresh_interval : seconds between data fetches
        """
        self.canvas = canvas
        self.draw_square = draw_square
        self._overhead = overhead
        self._refresh_interval = refresh_interval

        # Kick the first fetch immediately
        self._overhead.grab_data()
        self._last_grab_time = time.time()

        # Internal flight state — owned entirely by this scene
        self._flights: list = []
        self._index: int = 0
        self._all_looped: bool = False
        self._frame: int = 0

        # Journey state
        self._journey_first_draw = True
        self._journey_mode: str | None = None
        self._origin_scroll = _LineScroller()
        self._dest_scroll = _LineScroller()
        self._journey_loop_completed = False
        self._last_origin: str | None = None
        self._last_dest: str | None = None
        self._origin_name = ""
        self._dest_name = ""

        # Plane details state
        self._plane_position: int = screen.WIDTH
        self._last_details_mode: int | None = None

    # ------------------------------------------------------------------
    # Data ownership
    # ------------------------------------------------------------------

    def poll(self) -> None:
        """
        Called every frame by SceneManager.poll_all().
        Consumes new overhead data and triggers fresh fetches on interval.
        """
        if self._overhead.error is not None:
            print(f"overhead data grab failed: {self._overhead.error}")
            return

        if self._overhead.new_data:
            self.on_data(self._overhead.data)  # accessing .data clears new_data flag

        now = time.time()
        if (
            now - self._last_grab_time >= self._refresh_interval
            and not self._overhead.processing
            and not self._overhead.new_data
            and self.all_looped
        ):
            self._overhead.grab_data()
            self._last_grab_time = now

    def on_data(self, new_flights: list) -> None:
        """
        Called by Display.run() when the overhead source has fresh data.
        Decides whether to fully reset (callsigns changed) or silently
        swap telemetry values without interrupting the scroll.
        """
        old_flights = self._flights
        there_is_data = len(old_flights) > 0

        if not _callsigns_match(old_flights, new_flights):
            self._index = 0
            self._all_looped = False
            self._flights = new_flights
            if there_is_data:
                self.reset()
        elif _telemetry_changed(old_flights, new_flights):
            # Silent swap — scroller continues uninterrupted
            self._flights = new_flights

    @property
    def all_looped(self) -> bool:
        """True when the scene has cycled through all flights at least once,
        or when there are 0-1 flights (no meaningful looping to wait for)."""
        return self._all_looped or len(self._flights) <= 1

    # ------------------------------------------------------------------
    # Scene protocol
    # ------------------------------------------------------------------

    def has_data(self) -> bool:
        return len(self._flights) > 0

    def active(self) -> bool:
        return len(self._flights) > 0

    def reset(self) -> None:
        self._frame = 0
        self._journey_first_draw = True
        self._journey_mode = None
        self._origin_scroll.reset()
        self._dest_scroll.reset()
        self._journey_loop_completed = False
        self._last_origin = None
        self._last_dest = None
        self._origin_name = ""
        self._dest_name = ""
        self._plane_position = screen.WIDTH

    def draw(self) -> None:
        self._frame += 1
        self._draw_callsign()
        self._draw_journey()
        self._draw_plane_details()

    # ------------------------------------------------------------------
    # Callsign bar
    # ------------------------------------------------------------------

    def _draw_callsign(self) -> None:
        self.draw_square(
            0,
            BAR_STARTING_POSITION[1] - (FLIGHT_NO_TEXT_HEIGHT // 2),
            screen.WIDTH - 1,
            BAR_STARTING_POSITION[1] + (FLIGHT_NO_TEXT_HEIGHT // 2),
            TC(THEME_BG),
        )

        callsign = self._flights[self._index].get("callsign", "")
        flight_no_text_length = 0
        if callsign and callsign != "N/A":
            for ch in callsign:
                ch_length = graphics.DrawText(
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

        if len(self._flights) > 1:
            self.draw_square(
                DATA_INDEX_POSITION[0] - BAR_PADDING,
                BAR_STARTING_POSITION[1] - (FLIGHT_NO_TEXT_HEIGHT // 2),
                screen.WIDTH,
                BAR_STARTING_POSITION[1] + (FLIGHT_NO_TEXT_HEIGHT // 2),
                TC(THEME_BG),
            )
            graphics.DrawLine(
                self.canvas,
                flight_no_text_length + BAR_PADDING,
                BAR_STARTING_POSITION[1],
                DATA_INDEX_POSITION[0] - BAR_PADDING - 1,
                BAR_STARTING_POSITION[1],
                TC(THEME_DIVIDING_BAR),
            )
            graphics.DrawText(
                self.canvas,
                DATA_INDEX_FONT,
                DATA_INDEX_POSITION[0],
                DATA_INDEX_POSITION[1],
                TC(THEME_DATA_INDEX),
                f"{self._index + 1}/{len(self._flights)}",
            )
        else:
            graphics.DrawLine(
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

    def _draw_journey(self) -> None:
        cfg = Config.instance()
        flight = self._flights[self._index]
        origin = flight.get("origin")
        destination = flight.get("destination")

        if origin != self._last_origin or destination != self._last_dest:
            self._journey_first_draw = True
            self._journey_mode = None
            self._origin_scroll.reset()
            self._dest_scroll.reset()
            self._journey_loop_completed = False
            self._last_origin = origin
            self._last_dest = destination

        if not cfg.full_airport_name:
            if not self._journey_loop_completed:
                self._draw_iata_mode(cfg, flight)
            return

        if self._journey_mode != "full" or self._journey_first_draw:
            self._journey_mode = "full"
            self._setup_full_mode(cfg, flight)
            self.draw_square(0, 0, screen.WIDTH - 1, 16, TC(THEME_BG))
            self._journey_first_draw = False

        for line_idx, scroller in enumerate((self._origin_scroll, self._dest_scroll)):
            prev_x = scroller.position
            new_x = scroller.tick()
            if (
                prev_x != new_x
                or scroller.state == _BounceState.REVEAL
                or scroller.state == _BounceState.RETRACT
            ):
                self._undraw_full_line(cfg, flight, line_idx, prev_x)
            self._draw_full_line(cfg, flight, line_idx, new_x)

        if self._origin_scroll.scroll_max > 0 and self._dest_scroll.scroll_max > 0:
            if self._origin_scroll.state != self._dest_scroll.state:
                self._origin_scroll.timer = 0
                self._dest_scroll.timer = 0

        origin_done = (
            self._origin_scroll.loop_done or self._origin_scroll.scroll_max == 0
        )
        dest_done = self._dest_scroll.loop_done or self._dest_scroll.scroll_max == 0
        if origin_done and dest_done:
            self._journey_loop_completed = True

    def _draw_iata_mode(self, cfg, flight: dict) -> None:
        origin = flight.get("origin", "") or cfg.journey_blank_filler
        destination = flight.get("destination", "") or cfg.journey_blank_filler
        home_code = cfg.home_airport_code

        self.draw_square(0, 0, screen.WIDTH - 1, 15, TC(THEME_BG))

        font = fonts.large_bold if origin == home_code else fonts.large
        graphics.DrawText(
            self.canvas, font, _IATA_ORIGIN_X, 12, TC(THEME_LOCATION_ORIGIN), origin
        )
        font = fonts.large_bold if destination == home_code else fonts.large
        graphics.DrawText(
            self.canvas,
            font,
            _IATA_DESTINATION_X,
            12,
            TC(THEME_LOCATION_DESTINATION),
            destination,
        )

        ax, ay = _ARROW_TIP_X, _ARROW_TIP_Y
        x = ax - _ARROW_WIDTH
        y1 = ay - (_ARROW_HEIGHT // 2)
        y2 = ay + (_ARROW_HEIGHT // 2)
        self.canvas.SetPixel(
            ax, ay, TC(THEME_ARROW).red, TC(THEME_ARROW).green, TC(THEME_ARROW).blue
        )
        for _ in range(_ARROW_WIDTH):
            graphics.DrawLine(self.canvas, x, y1, x, y2, TC(THEME_ARROW))
            x += 1
            y1 += 1
            y2 -= 1

        self._journey_loop_completed = True

    def _setup_full_mode(self, cfg, flight: dict) -> None:
        origin = flight.get("origin") or cfg.journey_blank_filler
        destination = flight.get("destination") or cfg.journey_blank_filler
        origin_name = flight.get("origin_name") or ""
        dest_name = flight.get("destination_name") or ""

        if cfg.abbreviate_name:
            origin_name = _abbreviate(origin_name)
            dest_name = _abbreviate(dest_name)

        self._origin_name = origin_name or "Unknown"
        self._dest_name = dest_name or "Unknown"

        for scroller, iata, name, arrow in (
            (self._origin_scroll, origin, self._origin_name, ">"),
            (self._dest_scroll, destination, self._dest_name, "<"),
        ):
            scroller.reset()
            w = _font_text_width(fonts.small, f"{iata}{arrow}{name}")
            scroller.scroll_max = max(0, w - screen.WIDTH)

    def _draw_full_line(self, cfg, flight: dict, line_idx: int, x_offset: int) -> None:
        if line_idx == 0:
            iata = flight.get("origin") or cfg.journey_blank_filler
            name = self._origin_name
            arrow = ">"
            colour_code = TC(THEME_LOCATION_ORIGIN)
            colour_name = TC(THEME_LOCATION_ORIGIN_FULL)
            colour_arrow = TC(THEME_LOCATION_ORIGIN_ARROW)
        else:
            iata = flight.get("destination") or cfg.journey_blank_filler
            name = self._dest_name
            arrow = "<"
            colour_code = TC(THEME_LOCATION_DESTINATION)
            colour_name = TC(THEME_LOCATION_DESTINATION_FULL)
            colour_arrow = TC(THEME_LOCATION_DESTINATION_ARROW)

        y = _FULL_LINE_Y[line_idx]
        x = x_offset
        x += graphics.DrawText(
            self.canvas, fonts.small_symbols, x, y, colour_code, iata
        )
        x += graphics.DrawText(
            self.canvas, fonts.small_symbols, x, y, colour_arrow, arrow
        )
        graphics.DrawText(self.canvas, fonts.small_symbols, x, y, colour_name, name)

    def _undraw_full_line(
        self, cfg, flight: dict, line_idx: int, x_offset: int
    ) -> None:
        iata = (
            (flight.get("origin") or cfg.journey_blank_filler)
            if line_idx == 0
            else (flight.get("destination") or cfg.journey_blank_filler)
        )
        name = self._origin_name if line_idx == 0 else self._dest_name
        arrow = ">" if line_idx == 0 else "<"
        graphics.DrawText(
            self.canvas,
            fonts.small_symbols,
            x_offset,
            _FULL_LINE_Y[line_idx],
            TC(THEME_BG),
            f"{iata}{arrow}{name}",
        )

    # ------------------------------------------------------------------
    # Plane details (scrolling bar)
    # ------------------------------------------------------------------

    def _build_spans(self, cfg) -> list:
        return self._telemetry_spans(cfg) if cfg.details == 1 else self._model_spans()

    def _model_spans(self) -> list:
        text = self._flights[self._index].get("plane", "")
        return [(TC(THEME_PLANE), fonts.regular, text)]

    def _telemetry_spans(self, cfg) -> list:
        flight = self._flights[self._index]
        altitude_ft = flight.get("altitude", 0) or 0
        ground_speed_kts = flight.get("ground_speed", 0) or 0
        heading = flight.get("heading", 0) or 0

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

    def _spans_width(self, spans: list) -> int:
        return sum(font.CharacterWidth(ord(c)) for _, font, text in spans for c in text)

    def _draw_spans(self, spans: list, x: int, y: int) -> int:
        start_x = x
        for colour, font, text in spans:
            x += graphics.DrawText(self.canvas, font, x, y, colour, text)
        return x - start_x

    def _draw_plane_details(self) -> None:
        cfg = Config.instance()
        current_mode = cfg.details

        if current_mode != self._last_details_mode:
            self._plane_position = screen.WIDTH
            self._last_details_mode = current_mode

        spans = self._build_spans(cfg)

        self.draw_square(
            0,
            PLANE_DISTANCE_FROM_TOP - PLANE_TEXT_HEIGHT,
            screen.WIDTH,
            screen.HEIGHT,
            TC(THEME_BG),
        )

        total_width = self._draw_spans(
            spans, self._plane_position, PLANE_DISTANCE_FROM_TOP
        )

        self._plane_position -= 1
        if self._plane_position + total_width < 0:
            self._plane_position = screen.WIDTH
            if len(self._flights) > 1:
                self._index = (self._index + 1) % len(self._flights)
                self._all_looped = (not self._index) or self._all_looped
                self.reset()

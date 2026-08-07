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
from scenes.flight.airline_logo import AirlineLogoWidget, NullWidget
from scenes.flight.callsign_bar import make_callsign_bar
from scenes.flight.custom_details import build_custom_spans
from scenes.flight.journey import make_label
from setup import fonts, screen
from setup.configuration import Config
from setup.themes import (
    TC,
    THEME_BG,
    THEME_PLANE,
    THEME_PLANE_TLM,
    THEME_PLANE_TLM_UNITS,
)
from utilities.flight import TELEMETRY_FIELDS

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
    if len(a) != len(b):
        return False
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
# ---------------------------------------------------------------------------
# Callsign bar - delegated to a widget built once at construction via
# make_callsign_bar() in scenes/flight/callsign_bar.py.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Plane details (scrolling bar)
# ---------------------------------------------------------------------------

PLANE_DETAILS_Y = 30
PLANE_DETAILS_HEIGHT = 8

# ---------------------------------------------------------------------------
# Journey widget
# ---------------------------------------------------------------------------
# The journey rendering (short-code vs full-name) is delegated to a label
# widget built once at construction via make_label().  The airline icon
# widget (AirlineLogoWidget or NullWidget) is also built once.  Both live
# in scenes/flight/journey/ and scenes/flight/airline_logo.py.
# ---------------------------------------------------------------------------

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

        # Airline icon + journey label - built once from current config.
        # Settings changes force a restart, so selection at construction is
        # safe and avoids per-frame config branching.
        cfg = Config.instance()
        self.airline_logo = (
            AirlineLogoWidget(panel) if cfg.show_airline_icon else NullWidget()
        )
        self.journey_label = make_label(cfg, panel)
        self.callsign_bar = make_callsign_bar(cfg, panel)
        # Track route changes so the label can reset its scrollers.
        self.last_origin: str | None = None
        self.last_dest: str | None = None

        # Plane details state
        self.details_scroller: Scroller | None = None
        self.details_spans: Spans | None = None
        self.last_details_mode: int | None = None

        # Error backoff - log once, hold off before retrying
        self.error_logged: bool = False
        self.retry_at: float = 0.0

        # Deferred background clear.  reset() sets this flag instead of
        # drawing immediately so the clear only happens on the next draw()
        # call - i.e. when this scene is actually the active scene.  This
        # prevents reset() (triggered from poll() -> on_data()) from
        # blacking out another scene's canvas while it is displayed.
        self._needs_bg_clear: bool = False

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

        # Defer the top-half blank (journey band + icon area, rows 0-15)
        # to the next draw() call.  reset() can be invoked from poll() ->
        # on_data() while a different scene (e.g. SatelliteScene) is the
        # active scene; drawing here would clobber that scene's canvas.
        # The flag is consumed at the top of draw(), which only runs when
        # this scene is the one being displayed.
        self._needs_bg_clear = True

        self.airline_logo.reset()
        self.journey_label.reset()
        self.callsign_bar.reset()
        self.last_origin = None
        self.last_dest = None

        if self.details_scroller is not None:
            self.details_scroller.clear()
        self.details_scroller = None
        self.details_spans = None
        self.last_details_mode = None

    def draw(self) -> None:
        # Consume the deferred background clear from reset().  This only
        # runs when this scene is the active scene, so it never clobbers
        # another scene's canvas.
        if self._needs_bg_clear:
            self.panel.draw_square(
                self.canvas, 0, 0, screen.WIDTH - 1, 15, TC(THEME_BG)
            )
            self._needs_bg_clear = False

        self.frame += 1
        self.airline_logo.draw(self.canvas, self.flights[self.flight_index])
        self.draw_callsign()
        self.draw_journey()
        self.draw_plane_details()

    # ------------------------------------------------------------------
    # Callsign bar
    # ------------------------------------------------------------------

    def draw_callsign(self) -> None:
        self.callsign_bar.draw(self.canvas, self.flights, self.flight_index)

    # ------------------------------------------------------------------
    # Journey widget
    # ------------------------------------------------------------------

    def draw_journey(self) -> None:
        flight = self.flights[self.flight_index]
        origin = flight.origin
        destination = flight.destination

        route_changed = origin != self.last_origin or destination != self.last_dest
        if route_changed:
            self.journey_label.reset()
            self.last_origin = origin
            self.last_dest = destination

        # Journey text starts after the icon (1px gap) when an icon was
        # drawn; otherwise starts at x=1 (the original margin).
        icon_width = self.airline_logo.width
        if icon_width:
            # Icon mode: start at x=16 (no gap) and extend 1px wider.
            journey_x = icon_width + 1
            journey_width = screen.WIDTH - journey_x
        else:
            journey_x = 1
            journey_width = screen.WIDTH - journey_x
        icon_required = icon_width > 0

        self.journey_label.draw(
            self.canvas, flight, journey_x, journey_width, icon_required
        )

    # ------------------------------------------------------------------
    # Plane details (scrolling bar)
    # ------------------------------------------------------------------

    def build_spans(self, cfg) -> Spans:
        if cfg.details == 1:
            return self.telemetry_spans(cfg)
        if cfg.details == 2:
            return build_custom_spans(
                cfg.details_custom_template,
                self.flights[self.flight_index],
                cfg,
            )
        return self.model_spans()

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
            and self.journey_label.loop_completed
            and self.callsign_bar.loop_completed
        ):
            self.flight_index = (self.flight_index + 1) % len(self.flights)
            self.all_looped_flag = (not self.flight_index) or self.all_looped_flag
            self.reset()

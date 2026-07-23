"""
AstronomyIdleTheme - planet positions on a horizon strip.

Layout (64x32):
  Rows 0-7:   Clock + date (reuses the forecast theme's clock/date logic)
  Rows 9-24:  Horizon strip — 180° of sky centred on the observer's
              meridian.  Left = East (northern hemisphere) or West
              (southern hemisphere).  Coloured dots for each visible
              body, positioned by azimuth, height by elevation.
  Rows 25-31: Cycling planet name label with soft crossfade.

The horizon direction (East-left vs West-left) is automatically
determined from the observer's latitude — no user config needed.

Config options (under theme.astronomy in config.json):
  bodies:          list of body keys to display
  label_duration:  seconds each body name stays on screen
  horizon_labels:  show E/W/S/N markers on the horizon strip
"""

from __future__ import annotations

import datetime
import time

from scenes.idle.idle_scene import BaseIdleScene
from scenes.idle.themes.theme_utilities import font_text_width
from setup import fonts, frames
from setup.configuration import Config
from setup.screen import WIDTH as SCREEN_WIDTH
from setup.themes import TC, THEME_BG
from utilities.planet_tracker import PlanetTracker

# ---------------------------------------------------------------------------
# Layout constants — all positions are relative, nothing hardcoded to
# screen edges.  Adjust these to tweak the layout.
# ---------------------------------------------------------------------------

# Clock / date area (top)
CLOCK_FONT = fonts.small
CLOCK_POSITION = (0, 6)
DATE_FONT = CLOCK_FONT
DATE_POSITION_Y = CLOCK_POSITION[1]

# Day abbreviations
_DAY_ABBREVS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# Date format: 0 = YYYY-MM-DD, 1 = DD-MM-YYYY, 2 = MM-DD-YYYY
DATE_DAY_FIRST = {0: True, 1: True, 2: False}
DAY_DATE_SPACE_PX = 0

# Horizon strip area
STRIP_Y_ORIGIN = 9          # top y of the strip
STRIP_HEIGHT = 14           # pixel height (rows 9-22 inclusive)
STRIP_BOTTOM_Y = STRIP_Y_ORIGIN + STRIP_HEIGHT - 1  # y of horizon line (22)

# Label area (bottom)
LABEL_FONT = fonts.extrasmall  # 4x6
LABEL_FONT_HEIGHT = 5
LABEL_Y = 31                  # baseline for planet name
LABEL_AREA_Y_ORIGIN = 24      # top y of the label/connector area

# Fade timing
FADE_DURATION = 1.0           # seconds for crossfade in/out

# Dot rendering
DOT_RADIUS = 0                # 0 = single pixel, 1 = 3x3 cross

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------


def _lerp_colour(c1, c2, t: float):
    """Linear interpolate between two Colour namedtuples."""
    t = max(0.0, min(1.0, t))
    from display.rgbpanel import Colour
    return Colour(
        int(c1.red + (c2.red - c1.red) * t),
        int(c1.green + (c2.green - c1.green) * t),
        int(c1.blue + (c2.blue - c1.blue) * t),
    )


def _fade_colour(colour, bg_colour, alpha: float):
    """Fade a colour toward the background by (1 - alpha).

    alpha=1.0 → full colour, alpha=0.0 → background colour.
    """
    return _lerp_colour(bg_colour, colour, alpha)


# ---------------------------------------------------------------------------
# AstronomyIdleTheme
# ---------------------------------------------------------------------------


class AstronomyIdleTheme(BaseIdleScene):
    """Astronomy idle layout — horizon strip with planet positions."""

    # ------------------------------------------------------------------
    # Theme state
    # ------------------------------------------------------------------

    def theme_init(self) -> None:
        self.tracker = PlanetTracker.instance()

        # Clock/date caching
        self.last_time: str | None = None
        self.last_date: str | None = None

        # Horizon strip state
        self._strip_drawn = False
        self._last_positions: list = []

        # Label cycling state
        self._label_index = 0
        self._label_phase = "show"  # "show" | "fade_out" | "fade_in"
        self._phase_start: float = 0.0
        self._last_label_text: str | None = None
        self._last_connector_x: int | None = None
        self._last_connector_y_start: int | None = None
        self._last_connector_y_end: int | None = None
        self._loading_drawn = False

    def theme_reset(self) -> None:
        self.last_time = None
        self.last_date = None
        self._strip_drawn = False
        self._last_positions = []
        self._label_index = 0
        self._label_phase = "show"
        self._phase_start = 0.0
        self._last_label_text = None
        self._last_connector_x = None
        self._last_connector_y_start = None
        self._last_connector_y_end = None
        self._loading_drawn = False

    # ------------------------------------------------------------------
    # draw() — per-frame animation for smooth fades
    # ------------------------------------------------------------------

    def draw(self) -> None:
        """Override draw() to support per-frame fade animation.

        The clock and horizon strip update at ~1 fps (throttled).
        The label area updates every frame for smooth crossfading.
        """
        self.frame += 1

        now = time.monotonic()

        # Check if ephemeris is still loading
        if self.tracker.loading:
            self._draw_loading()
            return

        # Throttle clock/strip to ~1 fps
        if self.frame % int(frames.PER_SECOND) == 0:
            count = self.frame // int(frames.PER_SECOND)
            self._draw_slow_content(count)

        # Draw the label area every frame for smooth fading
        self._draw_label_area(now)

    # ------------------------------------------------------------------
    # Loading state
    # ------------------------------------------------------------------

    def _draw_loading(self) -> None:
        """Show a loading message while the ephemeris downloads."""
        # Only draw once (static message, no animation needed)
        if self._loading_drawn:
            return

        self.panel.draw_square(
            self.canvas,
            0, 0,
            SCREEN_WIDTH - 1, 31,
            TC(THEME_BG),
        )

        from setup.themes import THEME_FORECAST_TIME
        loading_font = fonts.small
        msg = "LOADING"
        msg_width = font_text_width(loading_font, msg)
        msg_x = (SCREEN_WIDTH - msg_width) // 2
        self.panel.draw_text(
            self.canvas,
            loading_font,
            msg_x, 16,
            TC(THEME_FORECAST_TIME),
            msg,
        )

        sub_font = fonts.extrasmall
        sub_msg = "EPHEMERIS"
        sub_width = font_text_width(sub_font, sub_msg)
        sub_x = (SCREEN_WIDTH - sub_width) // 2
        self.panel.draw_text(
            self.canvas,
            sub_font,
            sub_x, 24,
            TC(THEME_FORECAST_TIME),
            sub_msg,
        )

        self._loading_drawn = True

    # ------------------------------------------------------------------
    # Slow content (1 fps): clock, date, horizon strip
    # ------------------------------------------------------------------

    def _draw_slow_content(self, count: int) -> None:
        self._draw_clock()
        self._draw_date()
        self._draw_horizon_strip()

    def _draw_clock(self) -> None:
        cfg = Config.instance()
        now = datetime.datetime.now()
        if cfg.clock_24hr:
            time_str = now.strftime("%H:%M")
        else:
            hour = int(now.strftime("%I"))
            time_str = f"{hour}:{now.strftime('%M')}"

        if self.last_time == time_str:
            return

        if self.last_time is not None:
            self.panel.draw_text(
                self.canvas,
                CLOCK_FONT,
                CLOCK_POSITION[0],
                CLOCK_POSITION[1],
                TC(THEME_BG),
                self.last_time[:5],
            )

        self.last_time = time_str

        # Use the forecast theme's time colour for consistency
        from setup.themes import THEME_FORECAST_TIME
        self.panel.draw_text(
            self.canvas,
            CLOCK_FONT,
            CLOCK_POSITION[0],
            CLOCK_POSITION[1],
            TC(THEME_FORECAST_TIME),
            time_str,
        )

    def _draw_date(self) -> None:
        cfg = Config.instance()
        now = datetime.datetime.now()

        day_name = _DAY_ABBREVS[now.weekday()].upper()
        day = now.day
        month = now.month

        day_first = DATE_DAY_FIRST.get(cfg.date_format, True)
        date_str = (f"{day}/{month}" if day_first else f"{month}/{day}")

        current_date = day_name + " " + date_str
        if self.last_date == current_date:
            return

        if self.last_date is not None:
            old_day_name = self.last_date[:3]
            old_date_str = self.last_date[4:]
            old_date_width = font_text_width(DATE_FONT, old_date_str)
            old_date_x = SCREEN_WIDTH + 1 - old_date_width
            old_day_x = (
                old_date_x
                - DAY_DATE_SPACE_PX
                - font_text_width(DATE_FONT, old_day_name)
            )
            from setup.themes import THEME_CURRENT_DAY, THEME_CURRENT_DATE
            self.panel.draw_text(
                self.canvas,
                DATE_FONT,
                old_day_x,
                DATE_POSITION_Y,
                TC(THEME_BG),
                old_day_name,
            )
            self.panel.draw_text(
                self.canvas,
                DATE_FONT,
                old_date_x,
                DATE_POSITION_Y,
                TC(THEME_BG),
                old_date_str,
            )

        self.last_date = current_date

        from setup.themes import THEME_CURRENT_DAY, THEME_CURRENT_DATE
        date_width = font_text_width(DATE_FONT, date_str)
        date_x = SCREEN_WIDTH + 1 - date_width
        day_x = date_x - DAY_DATE_SPACE_PX - font_text_width(DATE_FONT, day_name)

        self.panel.draw_text(
            self.canvas,
            DATE_FONT,
            day_x,
            DATE_POSITION_Y,
            TC(THEME_CURRENT_DAY),
            day_name,
        )
        self.panel.draw_text(
            self.canvas,
            DATE_FONT,
            date_x,
            DATE_POSITION_Y,
            TC(THEME_CURRENT_DATE),
            date_str,
        )

    # ------------------------------------------------------------------
    # Horizon strip
    # ------------------------------------------------------------------

    def _draw_horizon_strip(self) -> None:
        """Draw the horizon line, cardinal labels, and planet dots."""
        cfg = Config.instance()
        astro_cfg = cfg.theme_astronomy
        lat = cfg.observer_lat
        lng = cfg.observer_lng
        bodies = astro_cfg.get("bodies", [])
        show_labels = astro_cfg.get("horizon_labels", True)

        positions = self.tracker.get_positions(lat, lng, bodies)

        # Check if positions changed (or first draw)
        changed = positions != self._last_positions or not self._strip_drawn

        if changed:
            # Clear the strip area
            self.panel.draw_square(
                self.canvas,
                0, STRIP_Y_ORIGIN,
                SCREEN_WIDTH - 1, STRIP_Y_ORIGIN + STRIP_HEIGHT - 1,
                TC(THEME_BG),
            )

            # Draw horizon line
            from setup.themes import THEME_ASTRO_HORIZON
            self.panel.draw_line(
                self.canvas,
                0, STRIP_BOTTOM_Y,
                SCREEN_WIDTH - 1, STRIP_BOTTOM_Y,
                TC(THEME_ASTRO_HORIZON),
            )

            # Draw cardinal direction labels
            if show_labels:
                self._draw_horizon_labels(lat)

            # Draw each visible body as a dot
            for pos in positions:
                if not pos.above_horizon:
                    continue

                x = PlanetTracker.azimuth_to_strip_x(
                    pos.az_deg, lat, SCREEN_WIDTH
                )
                if x is None:
                    continue

                y = PlanetTracker.elevation_to_strip_y(
                    pos.el_deg, STRIP_HEIGHT, STRIP_Y_ORIGIN
                )

                colour = TC(pos.colour_key)

                if DOT_RADIUS > 0:
                    self.panel.draw_circle(
                        self.canvas, x, y, DOT_RADIUS, colour
                    )
                else:
                    # Single pixel dot
                    r, g, b = colour.red, colour.green, colour.blue
                    self.panel.set_pixel(self.canvas, x, y, r, g, b)

            self._strip_drawn = True
            self._last_positions = list(positions)

    def _draw_horizon_labels(self, lat: float) -> None:
        """Draw E/W labels on the horizon line.

        Labels are drawn ON the horizon line (same y), replacing the
        line pixels at those positions.  No centre N/S marker.
        """
        from setup.themes import THEME_ASTRO_HORIZON_LABEL

        northern = PlanetTracker.is_northern_hemisphere(lat)
        label_font = fonts.extrasmall
        colour = TC(THEME_ASTRO_HORIZON_LABEL)

        if northern:
            # East on left, West on right
            left_label = "E"
            right_label = "W"
        else:
            # West on left, East on right
            left_label = "W"
            right_label = "E"

        # Draw labels at the very bottom of the screen
        label_y = 31

        # Erase previous labels at both edges (3px wide each)
        self.panel.draw_square(
            self.canvas, 0, label_y, 4, label_y, TC(THEME_BG)
        )
        right_x = SCREEN_WIDTH - font_text_width(label_font, right_label)
        self.panel.draw_square(
            self.canvas, right_x, label_y, SCREEN_WIDTH - 1, label_y,
            TC(THEME_BG),
        )

        # Left label at x=0
        self.panel.draw_text(
            self.canvas, label_font, 0, label_y, colour, left_label
        )

        # Right label
        self.panel.draw_text(
            self.canvas, label_font, right_x, label_y, colour, right_label
        )

    # ------------------------------------------------------------------
    # Label area — cycling planet names with soft crossfade
    # ------------------------------------------------------------------

    def _get_visible_bodies(self) -> list:
        """Return bodies that are above horizon AND on the visible strip."""
        cfg = Config.instance()
        lat = cfg.observer_lat
        lng = cfg.observer_lng
        bodies = cfg.theme_astronomy.get("bodies", [])
        positions = self.tracker.get_positions(lat, lng, bodies)
        result = []
        for p in positions:
            if not p.above_horizon:
                continue
            x = PlanetTracker.azimuth_to_strip_x(p.az_deg, lat, SCREEN_WIDTH)
            if x is not None:
                result.append(p)
        return result

    def _draw_label_area(self, now: float) -> None:
        """Draw the cycling planet name with crossfade and connector line."""
        cfg = Config.instance()
        label_duration = cfg.theme_astronomy.get("label_duration", 3)
        visible = self._get_visible_bodies()

        if not visible:
            # No visible bodies — show nothing
            self._erase_label()
            return

        # Initialise phase timing on first call
        if self._phase_start == 0.0:
            self._phase_start = now
            self._label_phase = "show"
            self._label_index = 0

        # State machine: show → fade_out → fade_in → show → ...
        phase_elapsed = now - self._phase_start

        if self._label_phase == "show":
            if phase_elapsed >= label_duration:
                self._label_phase = "fade_out"
                self._phase_start = now
                phase_elapsed = 0.0

        elif self._label_phase == "fade_out":
            if phase_elapsed >= FADE_DURATION:
                self._label_index = (self._label_index + 1) % len(visible)
                self._label_phase = "fade_in"
                self._phase_start = now
                phase_elapsed = 0.0

        elif self._label_phase == "fade_in":
            if phase_elapsed >= FADE_DURATION:
                self._label_phase = "show"
                self._phase_start = now
                phase_elapsed = 0.0

        # Compute alpha for current phase
        alpha = 1.0
        if self._label_phase == "fade_out":
            alpha = 1.0 - (phase_elapsed / FADE_DURATION)
        elif self._label_phase == "fade_in":
            alpha = phase_elapsed / FADE_DURATION

        alpha = max(0.0, min(1.0, alpha))

        # Get current body
        body = visible[self._label_index % len(visible)]

        # Compute label text and colour
        label_text = body.name
        body_colour = TC(body.colour_key)
        bg_colour = TC(THEME_BG)
        faded_colour = _fade_colour(body_colour, bg_colour, alpha)

        # Compute connector line position
        lat = cfg.observer_lat
        connector_x = PlanetTracker.azimuth_to_strip_x(
            body.az_deg, lat, SCREEN_WIDTH
        )
        connector_colour = _fade_colour(
            TC("ASTRO_CONNECTOR"), bg_colour, alpha
        )

        # Erase previous label text and in-strip connector line
        self._erase_label()

        # Draw connector line inside the strip: from 1px below the
        # planet dot down to 1px above the horizon bar.  This line
        # fades in/out with the label text.
        if connector_x is not None:
            dot_y = PlanetTracker.elevation_to_strip_y(
                body.el_deg, STRIP_HEIGHT, STRIP_Y_ORIGIN
            )
            line_start = dot_y + 1
            line_end = STRIP_BOTTOM_Y - 1
            if line_end >= line_start:
                self.panel.draw_line(
                    self.canvas,
                    connector_x, line_start,
                    connector_x, line_end,
                    connector_colour,
                )
                self._last_connector_y_start = line_start
                self._last_connector_y_end = line_end
            else:
                self._last_connector_y_start = None
                self._last_connector_y_end = None
        else:
            self._last_connector_y_start = None
            self._last_connector_y_end = None

        # Draw label text, centred on the screen
        label_width = font_text_width(LABEL_FONT, label_text)
        label_x = (SCREEN_WIDTH - label_width) // 2
        self.panel.draw_text(
            self.canvas,
            LABEL_FONT,
            label_x,
            LABEL_Y,
            faded_colour,
            label_text,
        )

        # Cache for erasure next frame
        self._last_label_text = label_text
        self._last_connector_x = connector_x

    def _erase_label(self) -> None:
        """Erase the previously drawn label text and in-strip connector.

        Only erases the exact pixels of the connector line (from
        dot_y+1 to horizon-1), never the full strip height.  This
        ensures planet dots and the horizon bar are never damaged.
        """
        if self._last_label_text is not None:
            label_width = font_text_width(LABEL_FONT, self._last_label_text)
            label_x = (SCREEN_WIDTH - label_width) // 2
            self.panel.draw_text(
                self.canvas,
                LABEL_FONT,
                label_x,
                LABEL_Y,
                TC(THEME_BG),
                self._last_label_text,
            )

        if (self._last_connector_x is not None
                and self._last_connector_y_start is not None
                and self._last_connector_y_end is not None):
            # Erase only the exact connector pixels
            self.panel.draw_line(
                self.canvas,
                self._last_connector_x, self._last_connector_y_start,
                self._last_connector_x, self._last_connector_y_end,
                TC(THEME_BG),
            )

        self._last_label_text = None
        self._last_connector_x = None
        self._last_connector_y_start = None
        self._last_connector_y_end = None

    # ------------------------------------------------------------------
    # draw_content — called by base class if draw() not overridden
    # ------------------------------------------------------------------

    def draw_content(self, count: int) -> None:
        # This is only called if draw() is not overridden.
        # Our draw() override handles everything.
        pass

"""
ForecastIdleTheme - weather forecast idle screen.

Displays weather icons for upcoming forecast periods.  The number and
spacing of icons depends on the ``theme.forecast.duration`` config setting:

  - ``3hour``  : now + next 2 hours
  - ``12hour`` : now + 4 h + 8 h
  - ``3day``   : today + next 2 days

Icons are drawn from the PNG files in ``icons/weather/`` using the
``code_to_weather`` mapping.  Day/night variants are selected via
``utilities.sun_times.is_daytime()``.

Above each icon a short label is shown: the day-of-week abbreviation
(3-day mode) or the hour (3-hour / 12-hour mode).  Below each icon a
temperature label is shown: min/max for 3-day mode, or the expected
temperature for hourly modes.  Temperature labels use
``temperature_to_colour`` for colouring and the 4x6 font.

Redraw caching: the list of slot tuples actually rendered is stashed
in ``self.last_slots``; the canvas is only redrawn when the underlying
data changes, avoiding constant flicker.
"""

from __future__ import annotations

import datetime

from scenes.idle.idle_scene import BaseIdleScene
from scenes.idle.themes.icons.weather.codes import code_to_weather
from scenes.idle.themes.icons.weather.forecast_sprite import (
    SPRITE_WIDTH,
    blank_area,
    create_animation,
)
from scenes.idle.themes.theme_utilities import font_text_width, temperature_to_colour
from setup import fonts, frames
from setup.configuration import Config
from setup.screen import WIDTH as SCREEN_WIDTH
from setup.themes import (
    TC,
    THEME_BG,
    THEME_CURRENT_DATE,
    THEME_CURRENT_DAY,
    THEME_FORECAST_TOP_TEXT,
    THEME_FORECAST_TIME,
)
from utilities.sun_times import is_daytime

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

LABEL_FONT = fonts.extrasmall  # 4x6
LABEL_FONT_HEIGHT = 5  # pixel height of 4x6 glyphs

ICON_POSITIONS_X = (3, 23, 43)  # x positions for 3 sprites on a 64px panel
# Sprite is 18px tall (12px icon + 6px animation).
# Layout: top label (~5px) + sprite (18px) + bottom label (~5px) = 28px
# within 32px panel → 4px spare, split as 2px top margin + 2px bottom.
ICON_POSITIONS_Y = 12  # y position for sprite top-left
TOP_LABEL_Y = 12  # baseline for the label above the sprite
BOTTOM_LABEL_Y = 32  # baseline for the label below the sprite

_DAY_ABBREVS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# ---------------------------------------------------------------------------
# Clock / Date / Day-of-week constants (copied from ClassicIdleTheme)
# ---------------------------------------------------------------------------

# Clock
CLOCK_FONT = fonts.small
CLOCK_AMPM_FONT = fonts.small
CLOCK_POSITION = (0, 6)
AMPM_POSITION_Y = 5

# Date — sits on the same line as the clock, positioned after it.
DATE_FONT = CLOCK_FONT
DATE_POSITION_Y = CLOCK_POSITION[1]
# Date format: 0 = YYYY-MM-DD, 1 = DD-MM-YYYY, 2 = MM-DD-YYYY
# Formats 0 and 1 both render as DD/MM (day before month);
# format 2 renders as MM/DD (month before day).
DATE_DAY_FIRST = {0: True, 1: True, 2: False}

# Pixel gap between the day abbreviation and the date on the clock line.
DAY_DATE_SPACE_PX = 0

# Day of week
DAY_FONT = fonts.small
DAY_POSITION = (2, 23)


class ForecastIdleTheme(BaseIdleScene):
    """Forecast idle layout - weather icons for upcoming periods."""

    # ------------------------------------------------------------------
    # Theme-specific state
    # ------------------------------------------------------------------

    def theme_init(self) -> None:
        self.last_slots: list[tuple] | None = None
        self.last_time: str | None = None
        self.last_date: str | None = None
        self._last_date_x: int = 0
        self.last_day: str | None = None
        self.animations: list = []
        self._anim_positions: list[tuple[int, int]] = []

    def theme_reset(self) -> None:
        self._destroy_animations()
        self.last_slots = None
        self.last_time = None
        self.last_date = None
        self.last_day = None

    # ------------------------------------------------------------------
    # draw() — overridden for per-frame animation
    # ------------------------------------------------------------------
    #
    # The base class throttles draw_content() to ~1 fps.  The forecast
    # theme needs per-frame animation (~12.5 fps) but only per-second
    # data evaluation.  We override draw() to:
    #   - tick sprite animations every frame
    #   - call draw_content() (clock/date/day + forecast evaluation)
    #     once per second

    def draw(self) -> None:
        self.frame += 1

        # Tick animations every frame
        for anim in self.animations:
            anim.tick()

        # Throttle data evaluation to ~1 fps
        if self.frame % int(frames.PER_SECOND):
            return

        count = self.frame // int(frames.PER_SECOND)
        self.draw_content(count)

    # ------------------------------------------------------------------
    # draw_content - called once per second by draw()
    # ------------------------------------------------------------------

    def draw_content(self, count: int) -> None:
        self.draw_clock()
        self.draw_date()

        weather = self.weather.get()
        if weather is None:
            return

        cfg = Config.instance()
        duration = cfg.theme_forecast.get("duration", "3hour")
        lat = cfg.observer_lat
        lng = cfg.observer_lng

        slots = self._compute_slots(weather, duration, lat, lng)
        if slots is None:
            return

        # Skip redraw if nothing changed
        if slots == self.last_slots:
            return

        # Destroy old animations and clear canvas for full redraw
        self._destroy_animations()
        self.panel.clear(self.canvas)

        # Re-draw clock/date/day after clear (they were drawn above but
        # the clear wiped them)
        self.last_time = None
        self.last_date = None
        self.last_day = None
        self.draw_clock()
        self.draw_date()

        # Create new animations and draw labels
        for i, slot in enumerate(slots):
            condition_code, is_day, top_label, bottom_label, temp_c = slot
            x = ICON_POSITIONS_X[i]

            icon_name, animation_name, intensity = code_to_weather(
                condition_code, not is_day
            )

            anim = create_animation(
                panel=self.panel,
                canvas=self.canvas,
                x=x,
                y=ICON_POSITIONS_Y,
                icon_name=icon_name,
                animation_name=animation_name,
                intensity=intensity,
            )
            if anim is not None:
                self.animations.append(anim)
                self._anim_positions.append((x, ICON_POSITIONS_Y))

            # Draw top label (day name or hour)
            if top_label:
                label_width = font_text_width(LABEL_FONT, top_label)
                label_x = x + round((SPRITE_WIDTH - label_width) / 2)
                self.panel.draw_text(
                    self.canvas,
                    LABEL_FONT,
                    label_x,
                    TOP_LABEL_Y,
                    TC(THEME_FORECAST_TOP_TEXT),
                    top_label,
                )

            # Draw bottom label (temperature)
            if bottom_label:
                # bottom_label is a list of (text, colour) segments
                total_width = sum(
                    font_text_width(LABEL_FONT, seg[0]) for seg in bottom_label
                )
                seg_x = x + round((SPRITE_WIDTH - total_width) / 2)
                for seg_text, seg_colour in bottom_label:
                    self.panel.draw_text(
                        self.canvas,
                        LABEL_FONT,
                        seg_x,
                        BOTTOM_LABEL_Y,
                        seg_colour,
                        seg_text,
                    )
                    seg_x += font_text_width(LABEL_FONT, seg_text)

        self.last_slots = slots

    def _destroy_animations(self) -> None:
        """Blank each animation's area and clear the list."""
        for x, y in self._anim_positions:
            blank_area(self.panel, self.canvas, x, y)
        self.animations = []
        self._anim_positions = []

    # ------------------------------------------------------------------
    # Clock (copied from ClassicIdleTheme)
    # ------------------------------------------------------------------

    def draw_clock(self) -> None:
        cfg = Config.instance()
        now = datetime.datetime.now()
        if cfg.clock_24hr:
            time_str = now.strftime("%H:%M")
        else:
            # Strip leading zero from 12-hour format (cross-platform:
            # %-I is Linux-only, %#I is Windows-only).
            hour = int(now.strftime("%I"))
            time_str = f"{hour}:{now.strftime('%M')}"

        current_time = time_str 
        if self.last_time == current_time:
            return

        # Undraw old value
        if self.last_time is not None:
            self.panel.draw_text(
                self.canvas,
                CLOCK_FONT,
                CLOCK_POSITION[0],
                CLOCK_POSITION[1],
                TC(THEME_BG),
                self.last_time[:5],
            )


        self.last_time = current_time

        self.panel.draw_text(
            self.canvas,
            CLOCK_FONT,
            CLOCK_POSITION[0],
            CLOCK_POSITION[1],
            TC(THEME_FORECAST_TIME),
            time_str,
        )


    # ------------------------------------------------------------------
    # Date (copied from ClassicIdleTheme)
    # ------------------------------------------------------------------

    def draw_date(self) -> None:
        """Draw day abbreviation + date (e.g. WED2/3) right-aligned.

        The date sits on the same line as the clock, right-aligned to
        the panel width.  The day short-name uses THEME_CURRENT_DAY and
        the date uses THEME_CURRENT_DATE.  The date is DD/MM or MM/DD
        depending on the configured date format.  Leading zeros are
        stripped.

        Caches the full drawn string so we only redraw when it changes.
        """
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

        # Right-align the date to the panel width, then place the day
        # name DAY_DATE_SPACE_PX pixels to its left.  The font has a
        # blank right column so we shift 1px past the panel edge without
        # cropping any letters.
        date_width = font_text_width(DATE_FONT, date_str)
        date_x = SCREEN_WIDTH + 1 - date_width
        day_x = date_x - DAY_DATE_SPACE_PX - font_text_width(DATE_FONT, day_name)

        # Undraw old value (both segments in background colour)
        if self.last_date is not None:
            old_day_name = self.last_date[:3]
            old_date_str = self.last_date[4:]  # skip the space at index 3
            old_date_width = font_text_width(DATE_FONT, old_date_str)
            old_date_x = SCREEN_WIDTH + 1 - old_date_width
            old_day_x = (
                old_date_x
                - DAY_DATE_SPACE_PX
                - font_text_width(DATE_FONT, old_day_name)
            )
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
        self._last_date_x = date_x

        # Draw new value: day name in THEME_CURRENT_DAY, date in THEME_CURRENT_DATE
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
    # Forecast slot selection
    # ------------------------------------------------------------------

    def _compute_slots(
        self,
        weather: dict,
        duration: str,
        lat: float,
        lng: float,
    ) -> list[tuple] | None:
        """Return a list of slot tuples for the 3 forecast periods.

        Each tuple is:
            (condition_code, is_day, top_label, bottom_label, temp_c)

        ``bottom_label`` is a list of (text, colour) segments for
        multi-colour rendering (e.g. min/max in different colours).
        """
        now = datetime.datetime.now()

        if duration == "3day":
            return self._daily_slots(weather, now, lat, lng)

        # 3hour and 12hour use hourly data
        hourly = weather.get("hourly", [])
        if not hourly:
            return None

        indices = [0, 4, 8] if duration == "12hour" else [0, 1, 2]

        slots = []
        for idx in indices:
            if idx >= len(hourly):
                return None
            hour = hourly[idx]
            condition_code = hour.get("condition_code", 0)
            temp_c = hour.get("temp_c", 0.0)
            slot_time = now + datetime.timedelta(hours=idx)
            day = is_daytime(lat, lng, slot_time)
            top_label = self._format_hour(slot_time)
            bottom_label = [(self._format_temp(temp_c), temperature_to_colour(temp_c))]
            slots.append((condition_code, day, top_label, bottom_label, temp_c))

        return slots

    def _daily_slots(
        self, weather: dict, now: datetime.datetime, lat, lng
    ) -> list[tuple] | None:
        """Return 3 daily forecast slots (today + next 2 days).

        Daily forecasts always use the day icon variant.  The bottom
        label shows min/max temperature with light blue for min and
        warm yellow for max.
        """
        daily = weather.get("daily", [])
        if len(daily) < 3:
            return None

        slots = []
        for day_offset in range(3):
            if day_offset == 0:
                now = datetime.datetime.now()
                is_day = is_daytime(lat, lng, now)
            else:
                is_day = True

            day_data = daily[day_offset]
            condition_code = day_data.get("condition_code", 0)
            temp_min = day_data.get("mintemp_c", 0.0)
            temp_max = day_data.get("maxtemp_c", 0.0)
            day_date = now + datetime.timedelta(days=day_offset)
            top_label = _DAY_ABBREVS[day_date.weekday()]
            min_str = self._format_temp_value(temp_min)
            max_str = self._format_temp_value(temp_max)
            bottom_label = [
                (min_str, temperature_to_colour(temp_min)),
                (max_str, temperature_to_colour(temp_max)),
            ]
            # Use the average temperature for colouring
            temp_avg = (temp_min + temp_max) / 2
            slots.append((condition_code, is_day, top_label, bottom_label, temp_avg))

        return slots

    # ------------------------------------------------------------------
    # Temperature formatting
    # ------------------------------------------------------------------

    @staticmethod
    def _convert_temp(temp_c: float) -> float:
        """Convert Celsius to the configured unit."""
        cfg = Config.instance()
        if cfg.units == "i":
            return temp_c * 9.0 / 5.0 + 32
        return temp_c

    def _format_temp_value(self, temp_c: float) -> str:
        """Format a temperature as an integer string (no unit), respecting units."""
        return str(round(self._convert_temp(temp_c)))

    def _format_temp(self, temp_c: float) -> str:
        """Format a temperature for the hourly label, respecting units."""
        return str(round(self._convert_temp(temp_c)))

    @staticmethod
    def _format_hour(slot_time: datetime.datetime) -> str:
        """Format the hour respecting the 12/24h clock setting."""
        cfg = Config.instance()
        if cfg.clock_24hr:
            return str(slot_time.hour)
        # 12-hour format: 1-12 with no leading zero, plus AM/PM suffix
        hour = slot_time.hour % 12
        if hour == 0:
            hour = 12
        ampm = "AM" if slot_time.hour < 12 else "PM"
        return f"{hour}{ampm}"

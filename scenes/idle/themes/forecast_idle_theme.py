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
from pathlib import Path

from PIL import Image

from scenes.idle.idle_scene import BaseIdleScene
from scenes.idle.themes.icons.weather.codes import weather_icon
from scenes.idle.themes.theme_utilities import font_text_width, temperature_to_colour
from setup import fonts
from setup.configuration import Config
from setup.themes import (
    TC,
    THEME_BG,
    THEME_CURRENT_DATE,
    THEME_CURRENT_DAY,
    THEME_TEXT,
    THEME_TIME,
    THEME_TIME_AMPM,
    THEME_WEATHER_10C,
    THEME_WEATHER_20C,
)
from utilities.sun_times import is_daytime

# ---------------------------------------------------------------------------
# Icon directory & cache
# ---------------------------------------------------------------------------

_ICON_DIR = Path(__file__).parent / "icons" / "weather"

# Module-level cache: filename -> PIL Image (loaded once, reused).
_image_cache: dict[str, Image.Image] = {}


def _load_icon(filename: str) -> Image.Image:
    """Load a weather icon PNG, caching the result for reuse."""
    if filename not in _image_cache:
        path = _ICON_DIR / filename
        _image_cache[filename] = Image.open(path).convert("RGBA")
    return _image_cache[filename]


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

LABEL_FONT = fonts.extrasmall  # 4x6
LABEL_FONT_HEIGHT = 5  # pixel height of 4x6 glyphs

ICON_POSITIONS_X = (3, 23, 43)  # x positions for 3 icons on a 64px panel
ICON_POSITIONS_Y = 10  # y position for all icons (16px tall)
TOP_LABEL_Y = 8  # baseline for the label above the icon
BOTTOM_LABEL_Y = 31  # baseline for the label below the icon

_DAY_ABBREVS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# ---------------------------------------------------------------------------
# Clock / Date / Day-of-week constants (copied from ClassicIdleTheme)
# ---------------------------------------------------------------------------

# Clock
CLOCK_FONT = fonts.regular
CLOCK_AMPM_FONT = fonts.extrasmall
CLOCK_POSITION = (1, 8)
AMPM_POSITION_Y = 6

# Date
DATE_FONT = fonts.small
DATE_POSITION = (1, 31)
DATE_FORMATS = [
    "%Y-%m-%d",  # 0 = YYYY-MM-DD
    "%-d-%-m-%Y",  # 1 = DD-MM-YYYY
    "%-m-%-d-%Y",  # 2 = MM-DD-YYYY
]

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
        self.last_day: str | None = None

    def theme_reset(self) -> None:
        self.last_slots = None
        self.last_time = None
        self.last_date = None
        self.last_day = None

    # ------------------------------------------------------------------
    # draw_content - called once per second by BaseIdleScene.draw()
    # ------------------------------------------------------------------

    def draw_content(self, count: int) -> None:
        self.draw_clock()
        self.draw_date()
        self.draw_day()

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

        # Clear and redraw
        self.panel.clear(self.canvas)
        for i, slot in enumerate(slots):
            condition_code, is_day, top_label, bottom_label, temp_c = slot
            x = ICON_POSITIONS_X[i]

            # Draw icon
            filename = weather_icon(condition_code, is_day)
            img = _load_icon(filename)
            self.panel.draw_image(self.canvas, x, ICON_POSITIONS_Y, img)

            # Draw top label (day name or hour)
            if top_label:
                label_width = font_text_width(LABEL_FONT, top_label)
                label_x = x + round((16 - label_width) / 2)
                self.panel.draw_text(
                    self.canvas,
                    LABEL_FONT,
                    label_x,
                    TOP_LABEL_Y,
                    TC(THEME_TEXT),
                    top_label,
                )

            # Draw bottom label (temperature)
            if bottom_label:
                # bottom_label is a list of (text, colour) segments
                total_width = sum(
                    font_text_width(LABEL_FONT, seg[0]) for seg in bottom_label
                )
                seg_x = x + round((16 - total_width) / 2)
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

    # ------------------------------------------------------------------
    # Clock (copied from ClassicIdleTheme)
    # ------------------------------------------------------------------

    def draw_clock(self) -> None:
        cfg = Config.instance()
        now = datetime.datetime.now()
        if cfg.clock_24hr:
            time_str = now.strftime("%H:%M")
            ampm_str = None
        else:
            time_str = now.strftime("%-I:%M")
            ampm_str = now.strftime("%p")

        current_time = time_str + (ampm_str or "")
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
            if ampm_str:
                old_ampm = "AM" if "AM" in self.last_time else "PM"
                ampm_position_x = CLOCK_POSITION[0] + font_text_width(
                    CLOCK_FONT, self.last_time[:5]
                )
                self.panel.draw_text(
                    self.canvas,
                    CLOCK_AMPM_FONT,
                    ampm_position_x + 1,
                    AMPM_POSITION_Y,
                    TC(THEME_BG),
                    old_ampm,
                )

        self.last_time = current_time

        self.panel.draw_text(
            self.canvas,
            CLOCK_FONT,
            CLOCK_POSITION[0],
            CLOCK_POSITION[1],
            TC(THEME_TIME),
            time_str,
        )
        if ampm_str:
            ampm_position_x = CLOCK_POSITION[0] + font_text_width(CLOCK_FONT, time_str)
            self.panel.draw_text(
                self.canvas,
                CLOCK_AMPM_FONT,
                ampm_position_x + 1,
                AMPM_POSITION_Y,
                TC(THEME_TIME_AMPM),
                ampm_str,
            )

    # ------------------------------------------------------------------
    # Date (copied from ClassicIdleTheme)
    # ------------------------------------------------------------------

    def draw_date(self) -> None:
        cfg = Config.instance()
        fmt = (
            DATE_FORMATS[cfg.date_format]
            if cfg.date_format < len(DATE_FORMATS)
            else DATE_FORMATS[0]
        )
        current_date = datetime.datetime.now().strftime(fmt)
        if self.last_date == current_date:
            return

        if self.last_date is not None:
            self.panel.draw_text(
                self.canvas,
                DATE_FONT,
                DATE_POSITION[0],
                DATE_POSITION[1],
                TC(THEME_BG),
                self.last_date,
            )
        self.last_date = current_date
        self.panel.draw_text(
            self.canvas,
            DATE_FONT,
            DATE_POSITION[0],
            DATE_POSITION[1],
            TC(THEME_CURRENT_DATE),
            current_date,
        )

    # ------------------------------------------------------------------
    # Day of week (copied from ClassicIdleTheme)
    # ------------------------------------------------------------------

    def draw_day(self) -> None:
        current_day = datetime.datetime.now().strftime("%A")
        if self.last_day == current_day:
            return

        if self.last_day is not None:
            self.panel.draw_text(
                self.canvas,
                DAY_FONT,
                DAY_POSITION[0],
                DAY_POSITION[1],
                TC(THEME_BG),
                self.last_day,
            )
        self.last_day = current_day
        self.panel.draw_text(
            self.canvas,
            DAY_FONT,
            DAY_POSITION[0],
            DAY_POSITION[1],
            TC(THEME_CURRENT_DAY),
            current_day,
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
            return self._daily_slots(weather, now)

        # 3hour and 12hour use hourly data
        hourly = weather.get("hourly", [])
        if not hourly:
            return None

        if duration == "12hour":
            indices = [0, 4, 8]
        else:  # "3hour" (default)
            indices = [0, 1, 2]

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
        self,
        weather: dict,
        now: datetime.datetime,
    ) -> list[tuple] | None:
        """Return 3 daily forecast slots (today + next 2 days).

        Daily forecasts always use the day icon variant.  The bottom
        label shows min/max temperature with light blue for min and
        warm yellow for max.
        """
        daily = weather.get("daily", [])
        if len(daily) < 3:
            return None

        min_colour = TC(THEME_WEATHER_10C)
        max_colour = TC(THEME_WEATHER_20C)

        slots = []
        for day_offset in range(3):
            day_data = daily[day_offset]
            condition_code = day_data.get("condition_code", 0)
            temp_min = day_data.get("mintemp_c", 0.0)
            temp_max = day_data.get("maxtemp_c", 0.0)
            day_date = now + datetime.timedelta(days=day_offset)
            top_label = _DAY_ABBREVS[day_date.weekday()]
            min_str = self._format_temp_value(temp_min)
            max_str = self._format_temp_value(temp_max)
            bottom_label = [
                (min_str, min_colour),
                (max_str, max_colour),
            ]
            # Use the average temperature for colouring
            temp_avg = (temp_min + temp_max) / 2
            slots.append((condition_code, True, top_label, bottom_label, temp_avg))

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
        # 12-hour format: 1-12 with no leading zero
        hour = slot_time.hour % 12
        if hour == 0:
            hour = 12
        return str(hour)

"""
ClassicIdleTheme - clock, date, day-of-week, and weather bar.

The original idle screen layout.  Inherits scene-protocol boilerplate
from BaseIdleScene and implements draw_content() with the classic
clock/date/weather layout.
"""

from __future__ import annotations

import datetime
from math import ceil

from scenes.idle.idle_scene import BaseIdleScene
from scenes.idle.themes.theme_utilities import (
    _RAINFALL_SENSITIVITY_LEVELS,
    RAINFALL_12HR_MARKERS,
    RAINFALL_COLUMN_WIDTH,
    RAINFALL_GRAPH_HEIGHT,
    RAINFALL_GRAPH_ORIGIN,
    RAINFALL_HOURS,
    RAINFALL_OVERSPILL_FLASH_ENABLED,
    font_text_width,
    temperature_to_colour,
)
from setup import fonts
from setup.configuration import Config
from setup.themes import (
    TC,
    THEME_BG,
    THEME_CURRENT_DATE,
    THEME_CURRENT_DAY,
    THEME_TIME,
    THEME_TIME_AMPM,
)

# ---------------------------------------------------------------------------
# Constants
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

# Temperature display
TEMPERATURE_FONT = fonts.extrasmall
TEMPERATURE_FONT_HEIGHT = 5
TEMPERATURE_POSITION = (48, TEMPERATURE_FONT_HEIGHT + 1)


class ClassicIdleTheme(BaseIdleScene):
    """
    Classic idle layout: clock, date, day-of-week, weather temperature +
    rainfall graph.
    """

    # ------------------------------------------------------------------
    # Theme-specific state
    # ------------------------------------------------------------------

    def theme_init(self) -> None:
        """Called by BaseIdleScene.__init__ to let the theme set up state."""
        self.last_time: str | None = None
        self.last_date: str | None = None
        self.last_day: str | None = None
        self.last_temp_str: str | None = None
        self.last_temp_c: float | None = None
        self.last_rain_data: list | None = None

    def theme_reset(self) -> None:
        """Called by BaseIdleScene.reset() to clear theme-specific state."""
        self.last_time = None
        self.last_date = None
        self.last_day = None
        self.last_temp_str = None
        self.last_temp_c = None
        self.last_rain_data = None

    # ------------------------------------------------------------------
    # draw_content - called once per second by BaseIdleScene.draw()
    # ------------------------------------------------------------------

    def draw_content(self, count: int) -> None:
        self.draw_clock()
        self.draw_date()
        self.draw_day()
        self.draw_weather(count)

    # ------------------------------------------------------------------
    # Clock
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
    # Date
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
    # Day of week
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
    # Weather
    # ------------------------------------------------------------------

    def erase_temperature(self) -> None:
        """Erase the previously-drawn temperature string, if any."""
        if self.last_temp_str is not None:
            self.panel.draw_text(
                self.canvas,
                TEMPERATURE_FONT,
                TEMPERATURE_POSITION[0],
                TEMPERATURE_POSITION[1],
                TC(THEME_BG),
                self.last_temp_str,
            )
            self.last_temp_str = None

    def draw_temperature(self, temp_c: float) -> None:
        """Render the temperature value in the configured units."""
        cfg = Config.instance()
        display_temp = temp_c * 9.0 / 5.0 + 32 if cfg.units == "i" else temp_c
        unit_char = "F" if cfg.units == "i" else "C"
        temp_str = f"{round(display_temp)}°{unit_char}".rjust(5)
        self.panel.draw_text(
            self.canvas,
            TEMPERATURE_FONT,
            TEMPERATURE_POSITION[0],
            TEMPERATURE_POSITION[1],
            temperature_to_colour(temp_c),
            temp_str,
        )
        self.last_temp_c = temp_c
        self.last_temp_str = temp_str

    def erase_rainfall(self) -> None:
        """Erase the previously-drawn rainfall graph, if any."""
        if self.last_rain_data is not None:
            self.draw_rainfall_graph(self.last_rain_data, TC(THEME_BG))
            self.last_rain_data = None

    def draw_weather(self, count: int) -> None:
        cfg = Config.instance()
        weather = self.weather.get()

        # --- Temperature ---
        if cfg.weather_mode < 1:
            # Mode disabled: erase if previously drawn
            self.erase_temperature()
        else:
            temp_c = weather["temp_c"] if weather else None
            self.erase_temperature()
            if temp_c is not None:
                self.draw_temperature(temp_c)

        # --- Rainfall graph ---
        if cfg.weather_mode < 2:
            self.erase_rainfall()
            return

        rain_data = self.rainfall_data(weather)

        # Erase stale graph when data changes
        if self.last_rain_data is not None and self.last_rain_data != rain_data:
            self.draw_rainfall_graph(self.last_rain_data, TC(THEME_BG))

        if rain_data:
            flash_enabled = RAINFALL_OVERSPILL_FLASH_ENABLED and bool(count % 2)
            self.draw_rainfall_graph(rain_data, flash_enabled=flash_enabled)
            self.last_rain_data = list(rain_data)

    def rainfall_data(self, weather: dict | None) -> list | None:
        if weather is None:
            return None
        forecast = weather["forecast"]
        start = datetime.datetime.now().hour
        slice = forecast[start : start + RAINFALL_HOURS]
        return [
            {"precip_mm": precip, "temp_c": temp, "hour": (start + i) % 24}
            for i, (temp, precip) in enumerate(slice)
        ]

    def draw_rainfall_graph(
        self, rain_data: list, graph_colour=None, flash_enabled: bool = False
    ) -> None:
        columns = range(
            0, RAINFALL_HOURS * RAINFALL_COLUMN_WIDTH, RAINFALL_COLUMN_WIDTH
        )
        for data, column_x in zip(rain_data, columns):
            rainfall_max = _RAINFALL_SENSITIVITY_LEVELS[
                Config.instance().rain_sensitivity
            ]
            rain_height = int(
                ceil(data["precip_mm"] * (RAINFALL_GRAPH_HEIGHT / rainfall_max))
            )
            if rain_height > RAINFALL_GRAPH_HEIGHT:
                flash_height = min(
                    rain_height - RAINFALL_GRAPH_HEIGHT, RAINFALL_GRAPH_HEIGHT + 1
                )
                rain_height = RAINFALL_GRAPH_HEIGHT
            else:
                flash_height = 0

            hourly_marker = RAINFALL_12HR_MARKERS and data["hour"] in (0, 12)
            x1 = RAINFALL_GRAPH_ORIGIN[0] + column_x
            x2 = x1 + RAINFALL_COLUMN_WIDTH
            y1 = RAINFALL_GRAPH_ORIGIN[1] + (1 if hourly_marker else 0)
            y2 = RAINFALL_GRAPH_ORIGIN[1] - rain_height

            colour = (
                graph_colour
                if graph_colour is not None
                else temperature_to_colour(data["temp_c"])
            )
            self.panel.draw_square(self.canvas, x1, y1, x2, y2, colour)

            if flash_height and flash_enabled and graph_colour is None:
                self.panel.draw_square(
                    self.canvas,
                    x1,
                    RAINFALL_GRAPH_ORIGIN[1] - RAINFALL_GRAPH_HEIGHT,
                    x2,
                    RAINFALL_GRAPH_ORIGIN[1] - RAINFALL_GRAPH_HEIGHT + flash_height - 1,
                    TC(THEME_BG),
                )

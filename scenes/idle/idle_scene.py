"""
IdleScene - clock, date, day-of-week, and weather bar.

Shown whenever no flight data is available. Always has_data() -> True
(priority 0 fallback). Weather is fetched on a background daemon thread
so it never blocks the draw loop.

"""

from __future__ import annotations

import datetime
import json
import threading
import urllib.request
from math import ceil

from rgbmatrix import graphics

from setup import fonts, frames, screen
from setup.themes import TC
from setup.themes import (
    THEME_BG,
    THEME_TIME,
    THEME_TIME_AMPM,
    THEME_CURRENT_DATE,
    THEME_CURRENT_DAY,
    THEME_WEATHER_00C,
    THEME_WEATHER_01C,
    THEME_WEATHER_10C,
    THEME_WEATHER_15C,
    THEME_WEATHER_20C,
    THEME_WEATHER_25C,
    THEME_WEATHER_35C,
)
from setup.configuration import Config

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PRIORITY = 0

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

# Weather - shared constants also referenced by FlightScene for the
# temperature-to-colour mapping used in the rainfall graph.
WEATHERAPI_URL = (
    "http://api.weatherapi.com/v1/forecast.json"
    "?key={key}&q={lat},{lng}&days=2&aqi=no&alerts=no"
)
WEATHER_REFRESH_SECONDS = 300
RAINFALL_HOURS = 24
RAINFALL_12HR_MARKERS = True
RAINFALL_GRAPH_ORIGIN = (39, 15)
RAINFALL_COLUMN_WIDTH = 1
RAINFALL_GRAPH_HEIGHT = 8
_RAINFALL_SENSITIVITY_LEVELS = (
    1,
    3,
    9,
)  # mm full-scale per sensitivity level (Egypt/UK/Singapore)
RAINFALL_OVERSPILL_FLASH_ENABLED = True

TEMPERATURE_FONT = fonts.extrasmall
TEMPERATURE_FONT_HEIGHT = 5
TEMPERATURE_POSITION = (48, TEMPERATURE_FONT_HEIGHT + 1)

TEMPERATURE_THRESHOLDS = [
    (0, THEME_WEATHER_00C),
    (1, THEME_WEATHER_01C),
    (10, THEME_WEATHER_10C),
    (15, THEME_WEATHER_15C),
    (20, THEME_WEATHER_20C),
    (25, THEME_WEATHER_25C),
    (35, THEME_WEATHER_35C),
]


# ---------------------------------------------------------------------------
# Temperature -> colour (module-level so it can be imported by other modules)
# ---------------------------------------------------------------------------


def temperature_to_colour(temp_c: float) -> graphics.Color:
    """Map a temperature in C to an interpolated theme colour."""
    lo_temp, lo_key = TEMPERATURE_THRESHOLDS[0]
    hi_temp, hi_key = TEMPERATURE_THRESHOLDS[1]

    for i in range(1, len(TEMPERATURE_THRESHOLDS) - 1):
        if temp_c > TEMPERATURE_THRESHOLDS[i][0]:
            lo_temp, lo_key = TEMPERATURE_THRESHOLDS[i]
            hi_temp, hi_key = TEMPERATURE_THRESHOLDS[i + 1]

    c_lo = TC(lo_key)
    c_hi = TC(hi_key)

    if temp_c >= hi_temp:
        ratio = 1.0
    elif temp_c > lo_temp:
        ratio = (temp_c - lo_temp) / (hi_temp - lo_temp)
    else:
        ratio = 0.0

    return graphics.Color(
        int(c_lo.red + (c_hi.red - c_lo.red) * ratio),
        int(c_lo.green + (c_hi.green - c_lo.green) * ratio),
        int(c_lo.blue + (c_hi.blue - c_lo.blue) * ratio),
    )


# ---------------------------------------------------------------------------
# Background weather fetcher
# ---------------------------------------------------------------------------


class WeatherFetcher(threading.Thread):
    """
    Daemon thread that fetches from weatherapi.com on startup and then
    every WEATHER_REFRESH_SECONDS thereafter. Thread-safe via a lock.
    """

    def __init__(self):
        super().__init__(daemon=True, name="weather-fetch")
        self.lock = threading.Lock()
        self.weather_data: dict | None = None
        self.stop_event = threading.Event()

    def run(self) -> None:
        self.do_fetch()  # immediate fetch on start
        while not self.stop_event.wait(WEATHER_REFRESH_SECONDS):
            self.do_fetch()

    def do_fetch(self) -> None:
        cfg = Config.instance()

        if not cfg.weatherapi_key:
            return

        url = WEATHERAPI_URL.format(
            key=cfg.weatherapi_key,
            lat=cfg.flight_lat,
            lng=cfg.flight_lng,
        )

        for _ in range(3):
            try:
                req = urllib.request.Request(url)

                with urllib.request.urlopen(req, timeout=5) as resp:
                    raw = json.loads(resp.read().decode())

                parsed = {
                    "temp_c": float(raw["current"]["temp_c"]),
                    "forecast": [
                        (float(h["temp_c"]), float(h["precip_mm"]))
                        for day in raw["forecast"]["forecastday"]
                        for h in day["hour"]
                    ],
                }

                with self.lock:
                    self.weather_data = parsed

                return

            except Exception:
                pass  # retry

    def get(self) -> dict | None:
        with self.lock:
            return self.weather_data

    def stop(self) -> None:
        self.stop_event.set()


# ---------------------------------------------------------------------------
# IdleScene
# ---------------------------------------------------------------------------


def font_text_width(font, text: str) -> int:
    return sum(font.CharacterWidth(ord(c)) for c in text)


class IdleScene:
    """
    Priority-0 fallback scene.  Draws clock, date, day-of-week and
    (optionally) weather temperature + rainfall graph.

    draw() is called every frame by SceneManager but internally limits
    most updates to once per second to avoid redundant canvas writes.
    """

    priority = PRIORITY

    def __init__(self, canvas, draw_square):
        self.canvas = canvas
        self.draw_square = draw_square

        # Scene frame counter
        self.frame: int = 0

        # Clock
        self.last_time: str | None = None

        # Date
        self.last_date: str | None = None

        # Day
        self.last_day: str | None = None

        # Weather
        self.last_temp_str: str | None = None
        self.last_temp_c: float | None = None
        self.last_rain_data: list | None = None

        # Start background weather fetch immediately.
        self.weather = WeatherFetcher()
        self.weather.start()

    # ------------------------------------------------------------------
    # Scene protocol
    # ------------------------------------------------------------------

    def poll(self) -> None:
        pass  # weather is handled by the background WeatherFetcher thread

    def has_data(self) -> bool:
        return True  # always the guaranteed fallback

    def active(self) -> bool:
        return True  # never interrupted mid-draw

    def on_enter(self) -> None:
        """Called by SceneManager on scene transition. Clears canvas then resets."""
        self.canvas.Clear()
        self.reset()

    def reset(self) -> None:
        """Clear cached draw state so everything redraws on next tick."""
        self.frame = 0
        self.last_time = None
        self.last_date = None
        self.last_day = None
        self.last_temp_str = None
        self.last_temp_c = None
        self.last_rain_data = None

    def draw(self) -> None:
        """Called every frame. Updates at ~1 fps."""
        self.frame += 1
        if self.frame % int(frames.PER_SECOND):
            return

        count = self.frame // int(frames.PER_SECOND)
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
            graphics.DrawText(
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
                graphics.DrawText(
                    self.canvas,
                    CLOCK_AMPM_FONT,
                    ampm_position_x + 1,
                    AMPM_POSITION_Y,
                    TC(THEME_BG),
                    old_ampm,
                )

        self.last_time = current_time

        graphics.DrawText(
            self.canvas,
            CLOCK_FONT,
            CLOCK_POSITION[0],
            CLOCK_POSITION[1],
            TC(THEME_TIME),
            time_str,
        )
        if ampm_str:
            ampm_position_x = CLOCK_POSITION[0] + font_text_width(CLOCK_FONT, time_str)
            graphics.DrawText(
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
            graphics.DrawText(
                self.canvas,
                DATE_FONT,
                DATE_POSITION[0],
                DATE_POSITION[1],
                TC(THEME_BG),
                self.last_date,
            )
        self.last_date = current_date
        graphics.DrawText(
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
            graphics.DrawText(
                self.canvas,
                DAY_FONT,
                DAY_POSITION[0],
                DAY_POSITION[1],
                TC(THEME_BG),
                self.last_day,
            )
        self.last_day = current_day
        graphics.DrawText(
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
            graphics.DrawText(
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
        graphics.DrawText(
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
            self.draw_square(x1, y1, x2, y2, colour)

            if flash_height and flash_enabled and graph_colour is None:
                self.draw_square(
                    x1,
                    RAINFALL_GRAPH_ORIGIN[1] - RAINFALL_GRAPH_HEIGHT,
                    x2,
                    RAINFALL_GRAPH_ORIGIN[1] - RAINFALL_GRAPH_HEIGHT + flash_height - 1,
                    TC(THEME_BG),
                )

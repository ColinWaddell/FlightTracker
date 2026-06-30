"""
IdleScene — clock, date, day-of-week, and weather bar.

Shown whenever no flight data is available. Always has_data() → True
(priority 0 fallback). Weather is fetched on a background daemon thread
so it never blocks the draw loop.

Merges the four former mixin scenes:
    ClockScene  →  _draw_clock()
    DateScene   →  _draw_date()
    DayScene    →  _draw_day()
    WeatherScene → _draw_weather()
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
AMPM_POSITION = (44, 5)

# Date
DATE_FONT = fonts.small
DATE_POSITION = (1, 31)
_DATE_FORMATS = [
    "%Y-%m-%d",  # 0 = YYYY-MM-DD
    "%-d-%-m-%Y",  # 1 = DD-MM-YYYY
    "%-m-%-d-%Y",  # 2 = MM-DD-YYYY
]

# Day of week
DAY_FONT = fonts.small
DAY_POSITION = (2, 23)

# Weather — shared constants also referenced by FlightScene for the
# temperature-to-colour mapping used in the rainfall graph.
_WEATHERAPI_URL = (
    "http://api.weatherapi.com/v1/forecast.json"
    "?key={key}&q={lat},{lng}&days=2&aqi=no&alerts=no"
)
WEATHER_REFRESH_SECONDS = 300
RAINFALL_HOURS = 24
RAINFALL_12HR_MARKERS = True
RAINFALL_GRAPH_ORIGIN = (39, 15)
RAINFALL_COLUMN_WIDTH = 1
RAINFALL_GRAPH_HEIGHT = 8
RAINFALL_MAX_VALUE = 3  # mm — columns taller than this flash
RAINFALL_OVERSPILL_FLASH_ENABLED = True

TEMPERATURE_FONT = fonts.extrasmall
TEMPERATURE_FONT_HEIGHT = 5
TEMPERATURE_POSITION = (48, TEMPERATURE_FONT_HEIGHT + 1)

_TEMPERATURE_THRESHOLDS = [
    (0, THEME_WEATHER_00C),
    (1, THEME_WEATHER_01C),
    (10, THEME_WEATHER_10C),
    (15, THEME_WEATHER_15C),
    (20, THEME_WEATHER_20C),
    (25, THEME_WEATHER_25C),
    (35, THEME_WEATHER_35C),
]


# ---------------------------------------------------------------------------
# Temperature → colour (module-level so it can be imported by other modules)
# ---------------------------------------------------------------------------


def temperature_to_colour(temp_c: float) -> graphics.Color:
    """Map a temperature in °C to an interpolated theme colour."""
    lo_temp, lo_key = _TEMPERATURE_THRESHOLDS[0]
    hi_temp, hi_key = _TEMPERATURE_THRESHOLDS[1]

    for i in range(1, len(_TEMPERATURE_THRESHOLDS) - 1):
        if temp_c > _TEMPERATURE_THRESHOLDS[i][0]:
            lo_temp, lo_key = _TEMPERATURE_THRESHOLDS[i]
            hi_temp, hi_key = _TEMPERATURE_THRESHOLDS[i + 1]

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


class _WeatherFetcher(threading.Thread):
    """
    Daemon thread that fetches from weatherapi.com on startup and then
    every WEATHER_REFRESH_SECONDS thereafter.  Thread-safe via a lock.
    """

    def __init__(self):
        super().__init__(daemon=True, name="weather-fetch")
        self._lock = threading.Lock()
        self._data: dict | None = None
        self._stop = threading.Event()

    def run(self) -> None:
        self._do_fetch()  # immediate fetch on start
        while not self._stop.wait(WEATHER_REFRESH_SECONDS):
            self._do_fetch()

    def _do_fetch(self) -> None:
        cfg = Config.instance()
        if not cfg.weatherapi_key:
            return
        url = _WEATHERAPI_URL.format(
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
                with self._lock:
                    self._data = parsed
                return
            except Exception:
                pass  # retry

    def get(self) -> dict | None:
        with self._lock:
            return self._data

    def stop(self) -> None:
        self._stop.set()


# ---------------------------------------------------------------------------
# IdleScene
# ---------------------------------------------------------------------------


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
        self._frame: int = 0

        # Clock
        self._last_time: str | None = None

        # Date
        self._last_date: str | None = None

        # Day
        self._last_day: str | None = None

        # Weather
        self._last_temp_str: str | None = None
        self._last_temp_c: float | None = None
        self._last_rain_data: list | None = None

        # Start background weather fetch immediately.
        self._weather = _WeatherFetcher()
        self._weather.start()

    # ------------------------------------------------------------------
    # Scene protocol
    # ------------------------------------------------------------------

    def poll(self) -> None:
        pass  # weather is handled by the background _WeatherFetcher thread

    def has_data(self) -> bool:
        return True  # always the guaranteed fallback

    def active(self) -> bool:
        return True  # never interrupted mid-draw

    def reset(self) -> None:
        """Clear cached draw state so everything redraws on next tick."""
        self._frame = 0
        self._last_time = None
        self._last_date = None
        self._last_day = None
        self._last_temp_str = None
        self._last_temp_c = None
        self._last_rain_data = None

    def draw(self) -> None:
        """Called every frame.  Updates at ~1 fps."""
        self._frame += 1
        if self._frame % int(frames.PER_SECOND):
            return

        count = self._frame // int(frames.PER_SECOND)
        self._draw_clock()
        self._draw_date()
        self._draw_day()
        self._draw_weather(count)

    # ------------------------------------------------------------------
    # Clock
    # ------------------------------------------------------------------

    def _draw_clock(self) -> None:
        cfg = Config.instance()
        now = datetime.datetime.now()
        if cfg.clock_24hr:
            time_str = now.strftime("%H:%M")
            ampm_str = None
        else:
            time_str = now.strftime("%-I:%M")
            ampm_str = now.strftime("%p")

        current_time = time_str + (ampm_str or "")
        if self._last_time == current_time:
            return

        # Undraw old value
        if self._last_time is not None:
            graphics.DrawText(
                self.canvas,
                CLOCK_FONT,
                CLOCK_POSITION[0],
                CLOCK_POSITION[1],
                TC(THEME_BG),
                self._last_time[:5],
            )
            if ampm_str:
                old_ampm = "AM" if "AM" in self._last_time else "PM"
                graphics.DrawText(
                    self.canvas,
                    CLOCK_AMPM_FONT,
                    AMPM_POSITION[0],
                    AMPM_POSITION[1],
                    TC(THEME_BG),
                    old_ampm,
                )

        self._last_time = current_time

        graphics.DrawText(
            self.canvas,
            CLOCK_FONT,
            CLOCK_POSITION[0],
            CLOCK_POSITION[1],
            TC(THEME_TIME),
            time_str,
        )
        if ampm_str:
            graphics.DrawText(
                self.canvas,
                CLOCK_AMPM_FONT,
                AMPM_POSITION[0],
                AMPM_POSITION[1],
                TC(THEME_TIME_AMPM),
                ampm_str,
            )

    # ------------------------------------------------------------------
    # Date
    # ------------------------------------------------------------------

    def _draw_date(self) -> None:
        cfg = Config.instance()
        fmt = (
            _DATE_FORMATS[cfg.date_format]
            if cfg.date_format < len(_DATE_FORMATS)
            else _DATE_FORMATS[0]
        )
        current_date = datetime.datetime.now().strftime(fmt)
        if self._last_date == current_date:
            return

        if self._last_date is not None:
            graphics.DrawText(
                self.canvas,
                DATE_FONT,
                DATE_POSITION[0],
                DATE_POSITION[1],
                TC(THEME_BG),
                self._last_date,
            )
        self._last_date = current_date
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

    def _draw_day(self) -> None:
        current_day = datetime.datetime.now().strftime("%A")
        if self._last_day == current_day:
            return

        if self._last_day is not None:
            graphics.DrawText(
                self.canvas,
                DAY_FONT,
                DAY_POSITION[0],
                DAY_POSITION[1],
                TC(THEME_BG),
                self._last_day,
            )
        self._last_day = current_day
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

    def _draw_weather(self, count: int) -> None:
        cfg = Config.instance()
        weather = self._weather.get()

        # --- Temperature ---
        if cfg.weather_mode < 1:
            # Mode disabled: erase if previously drawn
            if self._last_temp_str is not None:
                graphics.DrawText(
                    self.canvas,
                    TEMPERATURE_FONT,
                    TEMPERATURE_POSITION[0],
                    TEMPERATURE_POSITION[1],
                    TC(THEME_BG),
                    self._last_temp_str,
                )
                self._last_temp_str = None
        else:
            temp_c = weather["temp_c"] if weather else None
            # Erase old value first
            if self._last_temp_str is not None:
                graphics.DrawText(
                    self.canvas,
                    TEMPERATURE_FONT,
                    TEMPERATURE_POSITION[0],
                    TEMPERATURE_POSITION[1],
                    TC(THEME_BG),
                    self._last_temp_str,
                )
                self._last_temp_str = None
            if temp_c is not None:
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
                self._last_temp_c = temp_c
                self._last_temp_str = temp_str

        # --- Rainfall graph ---
        if cfg.weather_mode < 2:
            if self._last_rain_data is not None:
                self._draw_rainfall_graph(self._last_rain_data, TC(THEME_BG))
                self._last_rain_data = None
            return

        rain_data = self._rainfall_data(weather)

        # Erase stale graph when data changes
        if self._last_rain_data is not None and self._last_rain_data != rain_data:
            self._draw_rainfall_graph(self._last_rain_data, TC(THEME_BG))

        if rain_data:
            flash_enabled = RAINFALL_OVERSPILL_FLASH_ENABLED and bool(count % 2)
            self._draw_rainfall_graph(rain_data, flash_enabled=flash_enabled)
            self._last_rain_data = list(rain_data)

    def _rainfall_data(self, weather: dict | None) -> list | None:
        if weather is None:
            return None
        forecast = weather["forecast"]
        start = datetime.datetime.now().hour
        slice_ = forecast[start : start + RAINFALL_HOURS]
        return [
            {"precip_mm": precip, "temp_c": temp, "hour": (start + i) % 24}
            for i, (temp, precip) in enumerate(slice_)
        ]

    def _draw_rainfall_graph(
        self, rain_data: list, graph_colour=None, flash_enabled: bool = False
    ) -> None:
        columns = range(
            0, RAINFALL_HOURS * RAINFALL_COLUMN_WIDTH, RAINFALL_COLUMN_WIDTH
        )
        for data, column_x in zip(rain_data, columns):
            rain_height = int(
                ceil(data["precip_mm"] * (RAINFALL_GRAPH_HEIGHT / RAINFALL_MAX_VALUE))
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

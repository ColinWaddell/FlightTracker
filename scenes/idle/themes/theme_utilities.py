"""
Shared utilities for idle screen themes.

Contains the WeatherService singleton (a daemon-thread weather fetcher
accessible by any theme or future scheduler), the temperature-to-colour
mapping, and assorted constants/helpers used across themes.
"""

from __future__ import annotations

import json
import threading
import urllib.request

from display.rgbpanel import Colour
from setup.themes import (
    TC,
    THEME_WEATHER_00C,
    THEME_WEATHER_01C,
    THEME_WEATHER_10C,
    THEME_WEATHER_15C,
    THEME_WEATHER_20C,
    THEME_WEATHER_25C,
    THEME_WEATHER_35C,
)

# ---------------------------------------------------------------------------
# Weather API constants
# ---------------------------------------------------------------------------

WEATHERAPI_URL = (
    "http://api.weatherapi.com/v1/forecast.json"
    "?key={key}&q={lat},{lng}&days=2&aqi=no&alerts=no"
)
WEATHER_REFRESH_SECONDS = 300

# ---------------------------------------------------------------------------
# Rainfall graph constants (shared by classic + forecast themes)
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Temperature thresholds -> theme colour keys
# ---------------------------------------------------------------------------

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
# Temperature -> colour
# ---------------------------------------------------------------------------


def temperature_to_colour(temp_c: float) -> Colour:
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

    return Colour(
        int(c_lo.red + (c_hi.red - c_lo.red) * ratio),
        int(c_lo.green + (c_hi.green - c_lo.green) * ratio),
        int(c_lo.blue + (c_hi.blue - c_lo.blue) * ratio),
    )


# ---------------------------------------------------------------------------
# Font helper
# ---------------------------------------------------------------------------


def font_text_width(font, text: str) -> int:
    return sum(font.CharacterWidth(ord(c)) for c in text)


# ---------------------------------------------------------------------------
# WeatherService - singleton daemon-thread weather fetcher
# ---------------------------------------------------------------------------


class WeatherService(threading.Thread):
    """
    Singleton daemon thread that fetches from weatherapi.com on startup and
    then every WEATHER_REFRESH_SECONDS thereafter. Thread-safe via a lock.

    Any consumer (idle theme, future scheduler, etc.) can call
    WeatherService.instance().get() to read the latest cached data.
    """

    _instance: WeatherService | None = None
    _instance_lock = threading.Lock()

    @classmethod
    def instance(cls) -> WeatherService:
        """Return the singleton, starting it if necessary."""
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
                cls._instance.start()
            return cls._instance

    def __init__(self):
        super().__init__(daemon=True, name="weather-service")
        self.lock = threading.Lock()
        self.weather_data: dict | None = None
        self.stop_event = threading.Event()

    def run(self) -> None:
        self.do_fetch()  # immediate fetch on start
        while not self.stop_event.wait(WEATHER_REFRESH_SECONDS):
            self.do_fetch()

    def do_fetch(self) -> None:
        from setup.configuration import Config

        cfg = Config.instance()

        if not cfg.weatherapi_key:
            return

        url = WEATHERAPI_URL.format(
            key=cfg.weatherapi_key,
            lat=cfg.observer_lat,
            lng=cfg.observer_lng,
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

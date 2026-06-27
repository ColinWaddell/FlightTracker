import urllib.request
import datetime
import time
import json
from math import ceil
from functools import lru_cache

from rgbmatrix import graphics
from utilities.animator import Animator
from setup import fonts, frames
from setup.themes import TC
from setup.themes import (
    THEME_BG,
    THEME_WEATHER_00C, THEME_WEATHER_01C, THEME_WEATHER_10C,
    THEME_WEATHER_15C, THEME_WEATHER_20C, THEME_WEATHER_25C, THEME_WEATHER_35C,
)
from setup.configuration import Config

# WeatherAPI.com endpoint — 2-day forecast, no AQI/alerts
_WEATHERAPI_URL = (
    "http://api.weatherapi.com/v1/forecast.json"
    "?key={key}&q={lat},{lng}&days=2&aqi=no&alerts=no"
)

WEATHER_RETRIES = 3

# Temperature → theme key lookup (thresholds in °C)
_TEMPERATURE_THRESHOLDS = [
    (0,  THEME_WEATHER_00C),
    (1,  THEME_WEATHER_01C),
    (10, THEME_WEATHER_10C),
    (15, THEME_WEATHER_15C),
    (20, THEME_WEATHER_20C),
    (25, THEME_WEATHER_25C),
    (35, THEME_WEATHER_35C),
]

# Scene constants
WEATHER_REFRESH_SECONDS  = 300
RAINFALL_HOURS           = 24
RAINFALL_12HR_MARKERS    = True
RAINFALL_GRAPH_ORIGIN    = (39, 15)
RAINFALL_COLUMN_WIDTH    = 1
RAINFALL_GRAPH_HEIGHT    = 8
RAINFALL_MAX_VALUE       = 3   # mm — columns taller than this will flash
RAINFALL_OVERSPILL_FLASH_ENABLED = True

TEMPERATURE_REFRESH_SECONDS = 60
TEMPERATURE_FONT            = fonts.extrasmall
TEMPERATURE_FONT_HEIGHT     = 5
TEMPERATURE_POSITION        = (48, TEMPERATURE_FONT_HEIGHT + 1)


class WeatherError(Exception):
    pass


# ---------------------------------------------------------------------------
# WeatherAPI fetch — cached by (lat, lng, key, ttl bucket)
# ---------------------------------------------------------------------------

@lru_cache(maxsize=4)
def _fetch_weatherapi(lat: float, lng: float, key: str, ttl_hash: int):
    """Fetch and return the raw weatherapi.com response dict."""
    del ttl_hash  # only used as a cache-busting key
    url = _WEATHERAPI_URL.format(key=key, lat=lat, lng=lng)
    for _ in range(WEATHER_RETRIES):
        try:
            with urllib.request.urlopen(urllib.request.Request(url), timeout=5) as resp:
                return json.loads(resp.read().decode())
        except Exception:
            pass
    raise WeatherError("weatherapi.com request failed after retries")


def _ttl_hash(seconds: int = 300) -> int:
    return round(time.time() / seconds)


def _parse_weather(raw: dict) -> dict:
    """
    Returns:
        {
            "temp_c": float,                          # current temperature
            "forecast": [(temp_c, precip_mm), ...]   # 48 hourly entries (2 days)
        }
    """
    temp_c = float(raw["current"]["temp_c"])
    forecast = [
        (float(h["temp_c"]), float(h["precip_mm"]))
        for day in raw["forecast"]["forecastday"]
        for h in day["hour"]
    ]
    return {"temp_c": temp_c, "forecast": forecast}


# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def _temperature_to_colour(temp_c: float) -> graphics.Color:
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
        int(c_lo.red   + (c_hi.red   - c_lo.red)   * ratio),
        int(c_lo.green + (c_hi.green - c_lo.green) * ratio),
        int(c_lo.blue  + (c_hi.blue  - c_lo.blue)  * ratio),
    )


# ---------------------------------------------------------------------------
# Scene mixin
# ---------------------------------------------------------------------------

class WeatherScene(object):
    def __init__(self):
        super().__init__()
        self._weather_cache    = None   # parsed weather dict
        self._last_temp_c      = None
        self._last_temp_str    = None
        self._last_rain_data   = None   # list of dicts rendered last frame
        self.current_weather   = None   # parsed weather dict (refreshed each cycle)

    # ── Internal helpers ──────────────────────────────────────────────────

    def _cfg(self):
        return Config.instance()

    def _fetch(self):
        """Fetch current weather from weatherapi.com. Returns parsed dict or None."""
        cfg = self._cfg()
        if not cfg.weatherapi_key:
            return None
        try:
            raw = _fetch_weatherapi(
                cfg.flight_lat, cfg.flight_lng,
                cfg.weatherapi_key,
                _ttl_hash(WEATHER_REFRESH_SECONDS),
            )
            return _parse_weather(raw)
        except WeatherError:
            _fetch_weatherapi.cache_clear()
            return None

    def _current_temp_c(self) -> float | None:
        if self.current_weather is None:
            return None
        return self.current_weather["temp_c"]

    def _rainfall_data(self):
        """
        Return 24 hourly dicts starting from the current hour:
            {"precip_mm": float, "temp_c": float, "hour": int}
        """
        if self.current_weather is None:
            return None
        forecast = self.current_weather["forecast"]  # 48 entries
        start = datetime.datetime.now().hour
        slice_ = forecast[start: start + RAINFALL_HOURS]
        return [
            {
                "precip_mm": precip,
                "temp_c":    temp,
                "hour":      (start + i) % 24,
            }
            for i, (temp, precip) in enumerate(slice_)
        ]

    # ── Rainfall graph drawing ────────────────────────────────────────────

    def draw_rainfall_and_temperature(self, rain_data, graph_colour=None, flash_enabled=False):
        columns = range(0, RAINFALL_HOURS * RAINFALL_COLUMN_WIDTH, RAINFALL_COLUMN_WIDTH)

        for data, column_x in zip(rain_data, columns):
            rain_height = int(ceil(
                data["precip_mm"] * (RAINFALL_GRAPH_HEIGHT / RAINFALL_MAX_VALUE)
            ))

            if rain_height > RAINFALL_GRAPH_HEIGHT:
                flash_height = min(rain_height - RAINFALL_GRAPH_HEIGHT, RAINFALL_GRAPH_HEIGHT + 1)
                rain_height  = RAINFALL_GRAPH_HEIGHT
            else:
                flash_height = 0

            hourly_marker = RAINFALL_12HR_MARKERS and data["hour"] in (0, 12)

            x1 = RAINFALL_GRAPH_ORIGIN[0] + column_x
            x2 = x1 + RAINFALL_COLUMN_WIDTH
            y1 = RAINFALL_GRAPH_ORIGIN[1] + (1 if hourly_marker else 0)
            y2 = RAINFALL_GRAPH_ORIGIN[1] - rain_height

            colour = graph_colour if graph_colour is not None else _temperature_to_colour(data["temp_c"])
            self.draw_square(x1, y1, x2, y2, colour)

            if flash_height and flash_enabled and graph_colour is None:
                self.draw_square(
                    x1,
                    RAINFALL_GRAPH_ORIGIN[1] - RAINFALL_GRAPH_HEIGHT,
                    x2,
                    RAINFALL_GRAPH_ORIGIN[1] - RAINFALL_GRAPH_HEIGHT + flash_height - 1,
                    TC(THEME_BG),
                )

    # ── Keyframes ─────────────────────────────────────────────────────────

    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def weather_update(self, count):
        """Refresh weather data on the configured interval."""
        if not (count % WEATHER_REFRESH_SECONDS):
            self.current_weather = self._fetch()

    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def rainfall(self, count):
        cfg = self._cfg()
        if cfg.weather_mode < 2:
            # Clear graph if it was previously drawn
            if self._last_rain_data is not None:
                self.draw_rainfall_and_temperature(self._last_rain_data, TC(THEME_BG))
                self._last_rain_data = None
            return

        if len(self._data):
            self._last_rain_data = None
            return

        rain_data = self._rainfall_data()

        # Erase stale graph when data changes
        if self._last_rain_data is not None and self._last_rain_data != rain_data:
            self.draw_rainfall_and_temperature(self._last_rain_data, TC(THEME_BG))

        if rain_data:
            flash_enabled = RAINFALL_OVERSPILL_FLASH_ENABLED and bool(count % 2)
            self.draw_rainfall_and_temperature(rain_data, flash_enabled=flash_enabled)
            self._last_rain_data = list(rain_data)

    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def temperature(self, count):
        cfg = self._cfg()
        if cfg.weather_mode < 1:
            # Clear temperature if it was previously drawn
            if self._last_temp_str is not None:
                graphics.DrawText(
                    self.canvas, TEMPERATURE_FONT,
                    TEMPERATURE_POSITION[0], TEMPERATURE_POSITION[1],
                    TC(THEME_BG), self._last_temp_str,
                )
                self._last_temp_str = None
            return

        if len(self._data):
            return

        temp_c = self._current_temp_c()

        # Erase old value
        if self._last_temp_str is not None:
            graphics.DrawText(
                self.canvas, TEMPERATURE_FONT,
                TEMPERATURE_POSITION[0], TEMPERATURE_POSITION[1],
                TC(THEME_BG), self._last_temp_str,
            )

        if temp_c is not None:
            if cfg.units == "i":
                display_temp = temp_c * 9.0 / 5.0 + 32
                unit_char = "F"
            else:
                display_temp = temp_c
                unit_char = "C"

            temp_str = f"{round(display_temp)}°{unit_char}".rjust(5)
            graphics.DrawText(
                self.canvas, TEMPERATURE_FONT,
                TEMPERATURE_POSITION[0], TEMPERATURE_POSITION[1],
                _temperature_to_colour(temp_c),  # colour always based on °C
                temp_str,
            )
            self._last_temp_c   = temp_c
            self._last_temp_str = temp_str

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
    "?key={key}&q={lat},{lng}&days=3&aqi=no&alerts=no"
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
# Weather data parsing
# ---------------------------------------------------------------------------

# Fields copied verbatim from raw["current"] into the parsed dict.
_CURRENT_FLOAT_FIELDS = (
    "temp_c",
    "wind_kph",
    "pressure_mb",
    "precip_mm",
    "feelslike_c",
    "windchill_c",
    "heatindex_c",
    "dewpoint_c",
    "vis_km",
    "uv",
    "gust_kph",
)
_CURRENT_INT_FIELDS = (
    "wind_degree",
    "humidity",
    "cloud",
    "will_it_rain",
    "chance_of_rain",
    "will_it_snow",
    "chance_of_snow",
)
_CURRENT_STR_FIELDS = ("wind_dir",)

# Fields copied verbatim from raw["forecast"]["forecastday"][n]["day"].
_DAY_FLOAT_FIELDS = (
    "maxtemp_c",
    "mintemp_c",
    "avgtemp_c",
    "maxwind_kph",
    "totalprecip_mm",
    "totalsnow_cm",
)
_DAY_INT_FIELDS = (
    "avghumidity",
    "daily_will_it_rain",
    "daily_chance_of_rain",
    "daily_will_it_snow",
    "daily_chance_of_snow",
)


def _coerce(value, caster, default):
    """Safely cast *value* with *caster*, returning *default* on failure."""
    try:
        return caster(value)
    except (TypeError, ValueError):
        return default


def _parse_current(raw_current: dict) -> dict:
    """Extract and type-coerce the fields we care about from the API current block."""
    out = {}
    for key in _CURRENT_FLOAT_FIELDS:
        out[key] = _coerce(raw_current.get(key), float, 0.0)
    for key in _CURRENT_INT_FIELDS:
        out[key] = _coerce(raw_current.get(key), int, 0)
    for key in _CURRENT_STR_FIELDS:
        out[key] = str(raw_current.get(key, ""))
    # condition is a nested object
    out["condition_code"] = _coerce(
        raw_current.get("condition", {}).get("code"), int, 0
    )
    out["description"] = raw_current.get("condition", {}).get("text")
    return out


def _parse_day(raw_day: dict) -> dict:
    """Extract and type-coerce the fields we care about from a forecast day block."""
    out = {}
    for key in _DAY_FLOAT_FIELDS:
        out[key] = _coerce(raw_day.get(key), float, 0.0)
    for key in _DAY_INT_FIELDS:
        out[key] = _coerce(raw_day.get(key), int, 0)
    out["condition_code"] = _coerce(raw_day.get("condition", {}).get("code"), int, 0)
    return out


def _parse_astro(raw_astro: dict) -> dict:
    """Extract sunrise/sunset (and moon) strings from a forecast astro block.

    WeatherAPI returns these as strings like "06:30 AM" / "07:45 PM".
    We keep them as raw strings; callers parse them to ``datetime.time``
    via ``utilities.sun_times.parse_time`` (which handles the HH:MM part).
    Missing values default to empty strings.
    """
    out = {}
    for key in ("sunrise", "sunset", "moonrise", "moonset", "moon_phase"):
        out[key] = str(raw_astro.get(key, "")) if raw_astro else ""
    out["moon_illumination"] = _coerce(
        raw_astro.get("moon_illumination") if raw_astro else None, int, 0
    )
    return out


def _parse_hourly(raw_forecast_days: list) -> list[dict]:
    """Flatten all forecast hours into dicts with temp, precip, and condition code.

    The API returns 24 hours per day starting at 0:00 local time.  We
    only need the forecast from the current hour onwards, so the first
    ``current_hour`` entries (hours already elapsed today) are dropped.
    All time information in the API is in local time.
    """
    import datetime

    current_hour = datetime.datetime.now().hour

    out = []
    for day in raw_forecast_days:
        for h in day.get("hour", []):
            out.append(
                {
                    "temp_c": _coerce(h.get("temp_c"), float, 0.0),
                    "precip_mm": _coerce(h.get("precip_mm"), float, 0.0),
                    "condition_code": _coerce(
                        h.get("condition", {}).get("code"), int, 0
                    ),
                }
            )

    # Drop hours that have already elapsed today (e.g. if it's 2 AM,
    # discard elements 0 and 1 so the list starts at the current hour).
    return out[current_hour:]


def _parse_weather(raw: dict) -> dict:
    """Filter the full WeatherAPI response down to the fields we use.

    Returns a dict with current-condition fields at the root level,
    plus ``hourly`` and ``daily`` lists.  Missing or malformed values
    are coerced to safe defaults rather than raising.

    ``astro`` holds today's sunrise/sunset (and moon) strings parsed
    from the first forecast day's ``astro`` block, used by the
    Current Conditions idle theme.
    """
    current = raw.get("current", {})
    forecast = raw.get("forecast", {}).get("forecastday", [])

    parsed = _parse_current(current)
    parsed["hourly"] = _parse_hourly(forecast)
    parsed["daily"] = [_parse_day(d.get("day", {})) for d in forecast]

    # Today's astro block (sunrise/sunset) for the conditions theme.
    astro_raw = forecast[0].get("astro", {}) if forecast else {}
    parsed["astro"] = _parse_astro(astro_raw)

    return parsed


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

                parsed = _parse_weather(raw)

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

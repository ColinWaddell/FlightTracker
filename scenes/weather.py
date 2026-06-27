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

import sys

# Weather API
WEATHER_API_URL    = "https://taps-aff.co.uk/api/"
OPENWEATHER_API_URL = "https://api.openweathermap.org/data/2.5/"
WEATHER_RETRIES    = 3

# Temperature → theme key lookup
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
RAINFALL_REFRESH_SECONDS = 300
RAINFALL_HOURS           = 24
RAINFALL_12HR_MARKERS    = True
RAINFALL_GRAPH_ORIGIN    = (39, 15)
RAINFALL_COLUMN_WIDTH    = 1
RAINFALL_GRAPH_HEIGHT    = 8
RAINFALL_MAX_VALUE       = 3   # mm
RAINFALL_OVERSPILL_FLASH_ENABLED = True

TEMPERATURE_REFRESH_SECONDS = 60
TEMPERATURE_FONT            = fonts.extrasmall
TEMPERATURE_FONT_HEIGHT     = 5
TEMPERATURE_POSITION        = (48, TEMPERATURE_FONT_HEIGHT + 1)


class WeatherError(Exception):
    pass


@lru_cache()
def _grab_weather_tapsaff(location, ttl_hash=None):
    del ttl_hash
    retries = WEATHER_RETRIES
    while retries:
        try:
            request = urllib.request.Request(WEATHER_API_URL + location)
            raw = urllib.request.urlopen(request, timeout=3).read()
            return json.loads(raw.decode("utf-8"))
        except Exception:
            retries -= 1
    raise WeatherError(f"Failed to fetch weather for '{location}' after {WEATHER_RETRIES} retries")


@lru_cache()
def _grab_weather_openweather(location, apikey, units, ttl_hash=None):
    del ttl_hash
    retries = WEATHER_RETRIES
    while retries:
        try:
            url = (f"{OPENWEATHER_API_URL}weather?q={location}"
                   f"&appid={apikey}&units={units}")
            raw = urllib.request.urlopen(urllib.request.Request(url), timeout=3).read()
            content = json.loads(raw.decode("utf-8"))
            return content["main"]["temp"]
        except Exception:
            retries -= 1
    raise WeatherError(f"Failed to fetch OWM temp for '{location}' after {WEATHER_RETRIES} retries")


def _get_ttl_hash(seconds=60):
    return round(time.time() / seconds)


def _temperature_to_colour(temp):
    """Map temperature (°C) to a theme colour, interpolating between thresholds."""
    min_temp, min_key = _TEMPERATURE_THRESHOLDS[0]
    max_temp, max_key = _TEMPERATURE_THRESHOLDS[1]

    for i in range(1, len(_TEMPERATURE_THRESHOLDS) - 1):
        if temp > _TEMPERATURE_THRESHOLDS[i][0]:
            min_temp, min_key = _TEMPERATURE_THRESHOLDS[i]
            max_temp, max_key = _TEMPERATURE_THRESHOLDS[i + 1]

    c_min = TC(min_key)
    c_max = TC(max_key)

    if temp >= max_temp:
        ratio = 1.0
    elif temp > min_temp:
        ratio = (temp - min_temp) / (max_temp - min_temp)
    else:
        ratio = 0.0

    return graphics.Color(
        int(c_min.red   + (c_max.red   - c_min.red)   * ratio),
        int(c_min.green + (c_max.green - c_min.green) * ratio),
        int(c_min.blue  + (c_max.blue  - c_min.blue)  * ratio),
    )


class WeatherScene(object):
    def __init__(self):
        super().__init__()
        self._last_upcoming_rain_and_temp = None
        self._last_temperature = None
        self._last_temperature_str = None
        self.upcoming_rain_and_temp = None
        self.current_temperature = None

    def _cfg(self):
        return Config.instance()

    def _owm_units(self):
        return "imperial" if self._cfg().units == "i" else "metric"

    def _grab_temperature(self):
        cfg = self._cfg()
        apikey = cfg.openweather_api_key
        location = cfg.weather_location

        if apikey:
            try:
                return _grab_weather_openweather(
                    location, apikey, self._owm_units(),
                    ttl_hash=_get_ttl_hash()
                )
            except WeatherError:
                _grab_weather_openweather.cache_clear()

        try:
            weather = _grab_weather_tapsaff(location, ttl_hash=_get_ttl_hash())
            temp_c = weather["temp_c"]
            if cfg.units == "i":
                return temp_c * 9.0 / 5.0 + 32
            return temp_c
        except WeatherError:
            _grab_weather_tapsaff.cache_clear()
            return None

    def _grab_rainfall(self):
        cfg = self._cfg()
        location = cfg.weather_location
        try:
            weather = _grab_weather_tapsaff(location, ttl_hash=_get_ttl_hash())
            forecast_today    = weather["forecast"][0]["hourly"]
            forecast_tomorrow = weather["forecast"][1]["hourly"]
            hourly_forecast   = forecast_today + forecast_tomorrow
            hourly_data = [
                {"precip_mm": h["precip_mm"], "temp_c": h["temp_c"], "hour": h["hour"]}
                for h in hourly_forecast
            ]
            current_hour = datetime.datetime.now().hour
            return hourly_data[current_hour: current_hour + RAINFALL_HOURS]
        except (WeatherError, KeyError, IndexError):
            return None

    def draw_rainfall_and_temperature(self, rainfall_and_temperature,
                                      graph_colour=None, flash_enabled=False):
        columns = range(0, RAINFALL_HOURS * RAINFALL_COLUMN_WIDTH, RAINFALL_COLUMN_WIDTH)

        for data, column_x in zip(rainfall_and_temperature, columns):
            rain_height = int(ceil(
                data["precip_mm"] * (RAINFALL_GRAPH_HEIGHT / RAINFALL_MAX_VALUE)
            ))

            if rain_height > RAINFALL_GRAPH_HEIGHT:
                flash_height = rain_height - RAINFALL_GRAPH_HEIGHT
                if flash_height > RAINFALL_GRAPH_HEIGHT:
                    flash_height = RAINFALL_GRAPH_HEIGHT + 1
                rain_height = RAINFALL_GRAPH_HEIGHT
            else:
                flash_height = 0

            hourly_marker = RAINFALL_12HR_MARKERS and data["hour"] in (0, 12)

            x1 = RAINFALL_GRAPH_ORIGIN[0] + column_x
            x2 = x1 + RAINFALL_COLUMN_WIDTH
            y1 = RAINFALL_GRAPH_ORIGIN[1] + (1 if hourly_marker else 0)
            y2 = RAINFALL_GRAPH_ORIGIN[1] - rain_height

            square_colour = (
                graph_colour if graph_colour is not None
                else _temperature_to_colour(data["temp_c"])
            )

            self.draw_square(x1, y1, x2, y2, square_colour)

            if flash_height and flash_enabled and graph_colour is None:
                self.draw_square(
                    x1,
                    RAINFALL_GRAPH_ORIGIN[1] - RAINFALL_GRAPH_HEIGHT,
                    x2,
                    RAINFALL_GRAPH_ORIGIN[1] - RAINFALL_GRAPH_HEIGHT + flash_height - 1,
                    TC(THEME_BG),
                )

    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def rainfall(self, count):
        cfg = self._cfg()
        if not cfg.rainfall_enabled or not cfg.weather_graph:
            return

        if len(self._data):
            self._last_upcoming_rain_and_temp = None
            return

        if not (count % RAINFALL_REFRESH_SECONDS):
            self.upcoming_rain_and_temp = self._grab_rainfall()

        if self._last_upcoming_rain_and_temp != self.upcoming_rain_and_temp:
            if self._last_upcoming_rain_and_temp is not None:
                self.draw_rainfall_and_temperature(
                    self._last_upcoming_rain_and_temp, TC(THEME_BG)
                )

        if self.upcoming_rain_and_temp:
            flash_enabled = (
                RAINFALL_OVERSPILL_FLASH_ENABLED and bool(count % 2)
            )
            self.draw_rainfall_and_temperature(
                self.upcoming_rain_and_temp, flash_enabled=flash_enabled
            )
            self._last_upcoming_rain_and_temp = self.upcoming_rain_and_temp.copy()

    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def temperature(self, count):
        if len(self._data):
            return

        if not (count % TEMPERATURE_REFRESH_SECONDS):
            self.current_temperature = None
            self.current_temperature = self._grab_temperature()

        if self._last_temperature_str is not None:
            graphics.DrawText(
                self.canvas, TEMPERATURE_FONT,
                TEMPERATURE_POSITION[0], TEMPERATURE_POSITION[1],
                TC(THEME_BG), self._last_temperature_str,
            )

        if self.current_temperature is not None:
            unit_char = "F" if self._cfg().units == "i" else "C"
            temp_str = f"{round(self.current_temperature)}°{unit_char}".rjust(5)
            temp_colour = _temperature_to_colour(
                self.current_temperature
                if self._cfg().units == "m"
                else (self.current_temperature - 32) * 5 / 9  # convert back to °C for colour
            )
            graphics.DrawText(
                self.canvas, TEMPERATURE_FONT,
                TEMPERATURE_POSITION[0], TEMPERATURE_POSITION[1],
                temp_colour, temp_str,
            )
            self._last_temperature       = self.current_temperature
            self._last_temperature_str   = temp_str

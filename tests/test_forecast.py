"""Tests for the forecast idle theme and weather icon helper."""

from datetime import datetime

from scenes.idle.themes.icons.weather.codes import code_to_icon, code_to_weather
from scenes.idle.themes.theme_utilities import _parse_hourly


# ---------------------------------------------------------------------------
# code_to_icon / code_to_weather helpers
# ---------------------------------------------------------------------------


class TestCodeToIcon:
    def test_clear_day(self):
        icon, animation = code_to_icon(1000, False)
        assert icon == "sun"
        assert animation == "rays"

    def test_clear_night(self):
        icon, animation = code_to_icon(1000, True)
        assert icon == "moon"
        assert animation == "moon_rays"

    def test_partly_cloudy_day(self):
        icon, animation = code_to_icon(1003, False)
        assert icon == "cloud_sun"

    def test_partly_cloudy_night(self):
        icon, animation = code_to_icon(1003, True)
        assert icon == "cloud_moon"

    def test_rain(self):
        icon, animation = code_to_icon(1183, False)
        assert animation == "rain"

    def test_unknown_code_falls_back(self):
        icon, animation = code_to_icon(9999, True)
        assert icon is None
        assert animation is None


class TestCodeToWeather:
    def test_returns_icon_animation_intensity(self):
        icon, animation, intensity = code_to_weather(1000, False)
        assert icon == "sun"
        assert animation == "rays"
        assert intensity == 0

    def test_light_rain_intensity(self):
        _, _, intensity = code_to_weather(1063, False)
        assert intensity == 0

    def test_heavy_rain_intensity(self):
        _, _, intensity = code_to_weather(1192, False)
        assert intensity == 2

    def test_unknown_code_returns_defaults(self):
        icon, animation, intensity = code_to_weather(9999, False)
        assert icon is None
        assert animation is None
        assert intensity == 0


# ---------------------------------------------------------------------------
# _parse_hourly (condition codes)
# ---------------------------------------------------------------------------


class TestParseHourly:
    def _raw_hour(self, code=1000, temp=15.0, precip=0.0):
        return {
            "temp_c": temp,
            "precip_mm": precip,
            "condition": {"code": code},
        }

    def _raw_day(self, hours=24, code=1000):
        """Build a raw day with *hours* hours, all with the same code."""
        return {"hour": [self._raw_hour(code=code) for _ in range(hours)]}

    def test_returns_dicts(self):
        raw_days = [self._raw_day(hours=24)]
        result = _parse_hourly(raw_days)
        current_hour = datetime.now().hour
        assert len(result) == 24 - current_hour
        assert isinstance(result[0], dict)

    def test_includes_condition_code(self):
        raw_days = [self._raw_day(hours=24, code=1183)]
        result = _parse_hourly(raw_days)
        assert result[0]["condition_code"] == 1183

    def test_includes_temp_and_precip(self):
        raw_days = [{"hour": [self._raw_hour(temp=20.5, precip=1.2) for _ in range(24)]}]
        result = _parse_hourly(raw_days)
        assert result[0]["temp_c"] == 20.5
        assert result[0]["precip_mm"] == 1.2

    def test_multiple_hours_across_days(self):
        raw_days = [
            {"hour": [self._raw_hour(code=1000) for _ in range(24)]},
            {"hour": [self._raw_hour(code=1003) for _ in range(24)]},
        ]
        result = _parse_hourly(raw_days)
        current_hour = datetime.now().hour
        assert len(result) == 48 - current_hour
        # First day's remaining hours should have code 1000
        assert result[0]["condition_code"] == 1000
        # Second day's first hour should have code 1003
        assert result[24 - current_hour]["condition_code"] == 1003

    def test_missing_condition_defaults_to_zero(self):
        raw_days = [{"hour": [{"temp_c": 10.0, "precip_mm": 0.0} for _ in range(24)]}]
        result = _parse_hourly(raw_days)
        assert result[0]["condition_code"] == 0

    def test_empty_input(self):
        assert _parse_hourly([]) == []

    def test_day_with_no_hours(self):
        assert _parse_hourly([{"hour": []}]) == []

    def test_drops_elapsed_hours(self):
        """Hours before the current hour should be discarded."""
        raw_days = [self._raw_day(hours=24)]
        result = _parse_hourly(raw_days)
        current_hour = datetime.now().hour
        assert len(result) == 24 - current_hour
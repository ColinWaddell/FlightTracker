"""Tests for the forecast idle theme and weather icon helper."""

from datetime import datetime

from scenes.idle.themes.icons.weather.code_to_weather import weather_icon
from scenes.idle.themes.theme_utilities import _parse_hourly


# ---------------------------------------------------------------------------
# weather_icon helper
# ---------------------------------------------------------------------------


class TestWeatherIcon:
    def test_clear_day(self):
        assert weather_icon(1000, True) == "clear_day.png"

    def test_clear_night(self):
        assert weather_icon(1000, False) == "clear_night.png"

    def test_partly_cloudy_day(self):
        assert weather_icon(1003, True) == "partly_cloudy_day.png"

    def test_partly_cloudy_night(self):
        assert weather_icon(1003, False) == "partly_cloudy_night.png"

    def test_rain(self):
        assert weather_icon(1183, True) == "rain_1.png"

    def test_unknown_code_falls_back(self):
        result = weather_icon(9999, True)
        assert result == "cloudy.png"

    def test_unknown_code_night_falls_back(self):
        result = weather_icon(9999, False)
        assert result == "cloudy.png"


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

    def test_returns_dicts(self):
        raw_days = [{"hour": [self._raw_hour()]}]
        result = _parse_hourly(raw_days)
        assert len(result) == 1
        assert isinstance(result[0], dict)

    def test_includes_condition_code(self):
        raw_days = [{"hour": [self._raw_hour(code=1183)]}]
        result = _parse_hourly(raw_days)
        assert result[0]["condition_code"] == 1183

    def test_includes_temp_and_precip(self):
        raw_days = [{"hour": [self._raw_hour(temp=20.5, precip=1.2)]}]
        result = _parse_hourly(raw_days)
        assert result[0]["temp_c"] == 20.5
        assert result[0]["precip_mm"] == 1.2

    def test_multiple_hours_across_days(self):
        raw_days = [
            {"hour": [self._raw_hour(code=1000), self._raw_hour(code=1003)]},
            {"hour": [self._raw_hour(code=1183)]},
        ]
        result = _parse_hourly(raw_days)
        assert len(result) == 3
        assert result[0]["condition_code"] == 1000
        assert result[1]["condition_code"] == 1003
        assert result[2]["condition_code"] == 1183

    def test_missing_condition_defaults_to_zero(self):
        raw_days = [{"hour": [{"temp_c": 10.0, "precip_mm": 0.0}]}]
        result = _parse_hourly(raw_days)
        assert result[0]["condition_code"] == 0

    def test_empty_input(self):
        assert _parse_hourly([]) == []

    def test_day_with_no_hours(self):
        assert _parse_hourly([{"hour": []}]) == []
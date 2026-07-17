"""Tests for the codes.py weather condition mapping."""

from scenes.idle.themes.icons.weather.codes import code_to_icon, code_to_weather


# ---------------------------------------------------------------------------
# code_to_icon
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
        assert animation == "rays"

    def test_partly_cloudy_night(self):
        icon, animation = code_to_icon(1003, True)
        assert icon == "cloud_moon"
        assert animation == "moon_rays"

    def test_rain_day(self):
        icon, animation = code_to_icon(1183, False)
        assert icon == "cloud"
        assert animation == "rain"

    def test_rain_night(self):
        icon, animation = code_to_icon(1183, True)
        assert icon == "cloud_moon"
        assert animation == "rain"

    def test_no_icon_code(self):
        # Fog codes have None for icon
        icon, animation = code_to_icon(1135, False)
        assert icon is None
        assert animation == "fog"

    def test_no_animation_code(self):
        # Cloudy (1006) has no animation
        icon, animation = code_to_icon(1006, False)
        assert icon == "cloud"
        assert animation is None

    def test_unknown_code_returns_none(self):
        icon, animation = code_to_icon(9999, False)
        assert icon is None
        assert animation is None


# ---------------------------------------------------------------------------
# code_to_weather (includes intensity)
# ---------------------------------------------------------------------------


class TestCodeToWeather:
    def test_returns_three_values(self):
        result = code_to_weather(1000, False)
        assert len(result) == 3

    def test_clear_day(self):
        icon, animation, intensity = code_to_weather(1000, False)
        assert icon == "sun"
        assert animation == "rays"
        assert intensity == 0

    def test_light_rain_intensity(self):
        icon, animation, intensity = code_to_weather(1063, False)
        assert animation == "rain"
        assert intensity == 0

    def test_medium_rain_intensity(self):
        icon, animation, intensity = code_to_weather(1186, False)
        assert animation == "rain"
        assert intensity == 1

    def test_heavy_rain_intensity(self):
        icon, animation, intensity = code_to_weather(1192, False)
        assert animation == "rain"
        assert intensity == 2

    def test_night_variant(self):
        icon, animation, intensity = code_to_weather(1192, True)
        assert icon == "cloud_dark"
        assert animation == "rain"
        assert intensity == 2

    def test_unknown_code_returns_defaults(self):
        icon, animation, intensity = code_to_weather(9999, False)
        assert icon is None
        assert animation is None
        assert intensity == 0

    def test_no_icon_code(self):
        icon, animation, intensity = code_to_weather(1135, False)
        assert icon is None
        assert animation == "fog"
        assert intensity == 1

    def test_no_animation_code(self):
        icon, animation, intensity = code_to_weather(1006, False)
        assert icon == "cloud"
        assert animation is None
        assert intensity == 0
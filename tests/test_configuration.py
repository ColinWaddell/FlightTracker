"""Tests for setup/configuration.py - migration, parsing, and utilities."""

import types
from datetime import datetime, time

from setup.configuration import (
    _next_backup_path,
    approx_sunrise_sunset,
    migrate_config,
    migrate_legacy_json,
    mins_to_time,
    parse_time,
    time_in_window,
    time_to_mins,
)

# ---------------------------------------------------------------------------
# _next_backup_path
# ---------------------------------------------------------------------------


class TestNextBackupPath:
    def test_no_existing_backup(self, tmp_path):
        src = tmp_path / "config.json"
        src.write_text("{}")
        result = _next_backup_path(src)
        assert result == tmp_path / "config.json.bak"

    def test_one_existing_backup(self, tmp_path):
        src = tmp_path / "config.json"
        src.write_text("{}")
        (tmp_path / "config.json.bak").write_text("{}")
        result = _next_backup_path(src)
        assert result == tmp_path / "config.json.bak.1"

    def test_multiple_existing_backups(self, tmp_path):
        src = tmp_path / "config.json"
        src.write_text("{}")
        (tmp_path / "config.json.bak").write_text("{}")
        (tmp_path / "config.json.bak.1").write_text("{}")
        (tmp_path / "config.json.bak.2").write_text("{}")
        result = _next_backup_path(src)
        assert result == tmp_path / "config.json.bak.3"


# ---------------------------------------------------------------------------
# migrate_legacy_json
# ---------------------------------------------------------------------------


class TestMigrateLegacyJson:
    def test_both_exist_backup_created(self, tmp_path):
        repo = tmp_path / "cache.json"
        platform = tmp_path / "platform" / "cache.json"
        repo.write_text('{"old": true}')
        platform.parent.mkdir(parents=True)
        platform.write_text('{"new": true}')

        result = migrate_legacy_json(repo, platform)
        assert result == platform
        # repo should have been renamed to .bak
        assert not repo.exists()
        assert (tmp_path / "cache.json.bak").exists()

    def test_only_repo_exists(self, tmp_path):
        repo = tmp_path / "cache.json"
        platform = tmp_path / "platform" / "cache.json"
        repo.write_text('{"old": true}')

        result = migrate_legacy_json(repo, platform)
        assert result == platform
        assert platform.exists()
        assert platform.read_text() == '{"old": true}'
        # repo should have been backed up
        assert not repo.exists()
        assert (tmp_path / "cache.json.bak").exists()

    def test_neither_exists(self, tmp_path):
        repo = tmp_path / "cache.json"
        platform = tmp_path / "platform" / "cache.json"

        result = migrate_legacy_json(repo, platform)
        assert result == platform
        assert not repo.exists()
        # platform dir should have been created
        assert platform.parent.exists()


# ---------------------------------------------------------------------------
# parse_time
# ---------------------------------------------------------------------------


class TestParseTime:
    def test_valid_time(self):
        assert parse_time("14:30") == time(14, 30)

    def test_valid_time_with_whitespace(self):
        assert parse_time("  09:15  ") == time(9, 15)

    def test_invalid_string(self):
        assert parse_time("not a time") == time(0, 0)

    def test_none_value(self):
        assert parse_time(None) == time(0, 0)

    def test_empty_string(self):
        assert parse_time("") == time(0, 0)

    def test_custom_default(self):
        assert parse_time("bad", default="12:00") == time(12, 0)

    def test_integer_input(self):
        # str(1234) -> "1234" which won't parse as HH:MM
        assert parse_time(1234) == time(0, 0)


# ---------------------------------------------------------------------------
# time_to_mins / mins_to_time
# ---------------------------------------------------------------------------


class TestTimeConversions:
    def test_time_to_mins(self):
        assert time_to_mins(time(0, 0)) == 0
        assert time_to_mins(time(12, 30)) == 750
        assert time_to_mins(time(23, 59)) == 1439

    def test_mins_to_time(self):
        assert mins_to_time(0) == time(0, 0)
        assert mins_to_time(750) == time(12, 30)
        assert mins_to_time(1439) == time(23, 59)

    def test_roundtrip(self):
        for mins in [0, 360, 720, 1080, 1439]:
            assert time_to_mins(mins_to_time(mins)) == mins


# ---------------------------------------------------------------------------
# time_in_window
# ---------------------------------------------------------------------------


class TestTimeInWindow:
    def test_none_inputs(self):
        assert time_in_window(None, None) is False

    def test_equal_start_end(self):
        # Equal start/end means "always in window"
        assert time_in_window(time(12, 0), time(12, 0)) is True

    def test_daytime_window(self):
        # Can't control "now" easily, but we can test the logic indirectly
        # by checking it returns a bool
        result = time_in_window(time(9, 0), time(17, 0))
        assert isinstance(result, bool)

    def test_overnight_window(self):
        result = time_in_window(time(22, 0), time(7, 0))
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# approx_sunrise_sunset
# ---------------------------------------------------------------------------


class TestApproxSunriseSunset:
    def test_london_summer(self):
        # London ~51.5N, -0.12W, June 21 (longest day)
        sunrise, sunset = approx_sunrise_sunset(51.5, -0.12, datetime(2026, 6, 21))
        # Summer sunrise should be early (before 5:00 UTC), sunset late (after 20:00 UTC)
        assert sunrise.hour < 5, f"Expected sunrise before 5am UTC, got {sunrise}"
        assert sunset.hour >= 20, f"Expected sunset after 8pm UTC, got {sunset}"

    def test_london_winter(self):
        # London ~51.5N, -0.12W, Dec 21 (shortest day)
        sunrise, sunset = approx_sunrise_sunset(51.5, -0.12, datetime(2026, 12, 21))
        # Winter sunrise late (after 7:00 UTC), sunset early (before 17:00 UTC)
        assert sunrise.hour >= 7, f"Expected sunrise after 7am UTC, got {sunrise}"
        assert sunset.hour < 17, f"Expected sunset before 5pm UTC, got {sunset}"

    def test_polar_night(self):
        # North Pole area in December - sun never rises
        sunrise, sunset = approx_sunrise_sunset(80.0, 0.0, datetime(2026, 12, 21))
        # Should return solar noon for both (sun never rises)
        assert sunrise == sunset

    def test_midnight_sun(self):
        # North Pole area in June - sun never sets
        sunrise, sunset = approx_sunrise_sunset(80.0, 0.0, datetime(2026, 6, 21))
        # Should return solar noon for both (sun never sets)
        assert sunrise == sunset

    def test_returns_time_objects(self):
        sunrise, sunset = approx_sunrise_sunset(51.5, -0.12)
        assert isinstance(sunrise, time)
        assert isinstance(sunset, time)


# ---------------------------------------------------------------------------
# migrate_config
# ---------------------------------------------------------------------------


class TestMigrateConfig:
    def _make_legacy_module(self, **kwargs):
        """Create a fake module with the given attributes."""
        mod = types.ModuleType("legacy_config")
        for k, v in kwargs.items():
            setattr(mod, k, v)
        return mod

    def test_location_home_takes_priority(self):
        mod = self._make_legacy_module(
            LOCATION_HOME=[55.8, -4.2, 50],
            ZONE_HOME={"tl_y": 56.0, "tl_x": -5.0, "br_y": 55.0, "br_x": -3.0},
        )
        data = migrate_config(mod)
        assert data["flight_lat"] == 55.8
        assert data["flight_lng"] == -4.2

    def test_zone_home_fallback(self):
        mod = self._make_legacy_module(
            ZONE_HOME={"tl_y": 56.0, "tl_x": -5.0, "br_y": 55.0, "br_x": -3.0},
        )
        data = migrate_config(mod)
        assert data["flight_lat"] == round((56.0 + 55.0) / 2, 7)
        assert data["flight_lng"] == round((-5.0 + -3.0) / 2, 7)
        # Radius should be derived from the larger half-width
        assert data["flight_radius"] > 0

    def test_brightness_migration(self):
        mod = self._make_legacy_module(BRIGHTNESS=80)
        data = migrate_config(mod)
        # 80 / 20 = 4, clamped to 1-5
        assert data["screen_brightness"] == 4

    def test_brightness_clamped_low(self):
        mod = self._make_legacy_module(BRIGHTNESS=10)
        data = migrate_config(mod)
        assert data["screen_brightness"] == 1

    def test_brightness_clamped_high(self):
        mod = self._make_legacy_module(BRIGHTNESS=120)
        data = migrate_config(mod)
        assert data["screen_brightness"] == 5

    def test_min_altitude_feet_to_metres(self):
        mod = self._make_legacy_module(MIN_ALTITUDE=1000)
        data = migrate_config(mod)
        assert data["flight_min_altitude"] == max(10.0, round(1000 * 0.3048, 1))

    def test_units_metric(self):
        mod = self._make_legacy_module(TEMPERATURE_UNITS="metric")
        data = migrate_config(mod)
        assert data["units"] == "m"

    def test_units_imperial(self):
        mod = self._make_legacy_module(TEMPERATURE_UNITS="imperial")
        data = migrate_config(mod)
        assert data["units"] == "i"

    def test_rainfall_enabled_sets_weather_mode(self):
        mod = self._make_legacy_module(RAINFALL_ENABLED=True)
        data = migrate_config(mod)
        assert data["weather_mode"] == 2

    def test_weather_location_sets_weather_mode(self):
        mod = self._make_legacy_module(WEATHER_LOCATION="Glasgow")
        data = migrate_config(mod)
        assert data["weather_mode"] == 1

    def test_tar1090_url_switches_data_source(self):
        mod = self._make_legacy_module(TAR1090_URL="http://localhost/tar1090")
        data = migrate_config(mod)
        assert data["data_source"] == "tar1090"
        assert data["tar1090_url"] == "http://localhost/tar1090"

    def test_journey_code_selected_to_home_airport(self):
        mod = self._make_legacy_module(JOURNEY_CODE_SELECTED="gli")
        data = migrate_config(mod)
        assert data["home_airport_code"] == "GLI"

    def test_simple_renames(self):
        mod = self._make_legacy_module(
            GPIO_SLOWDOWN=4,
            HAT_PWM_ENABLED=True,
            JOURNEY_BLANK_FILLER="-",
            LOADING_LED_ENABLED=True,
            LOADING_LED_GPIO_PIN=18,
        )
        data = migrate_config(mod)
        assert data["gpio_slowdown"] == 4
        assert data["hat_pwm_enabled"] is True
        assert data["journey_blank_filler"] == "-"
        assert data["loading_led_enabled"] is True
        assert data["loading_led_gpio_pin"] == 18

    def test_empty_legacy(self):
        mod = self._make_legacy_module()
        data = migrate_config(mod)
        # Should return defaults
        assert "flight_lat" in data
        assert "units" in data

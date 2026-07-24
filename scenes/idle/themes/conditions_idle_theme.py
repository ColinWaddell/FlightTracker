"""
ConditionsIdleTheme - current weather conditions idle screen.

Displays the current weather at a glance:

  - Top row: day abbreviation, date, and time (mirrors the forecast
    theme's clock/date layout).
  - Far left: a weather sprite (icon + animation) for the current
    condition code, with day/night variant selected via
    ``utilities.sun_times.is_daytime()``.
  - Remaining space: current temperature, humidity, wind speed +
    direction, and sunrise/sunset times, drawn as text.

Redraw caching: each piece of text is stashed in a ``last_*`` field and
only redrawn when its value changes.  The sprite is rebuilt only when
the condition code or day/night state changes.  This avoids constant
flicker while the weather service refreshes every few minutes.
"""

from __future__ import annotations

import datetime

from scenes.idle.idle_scene import BaseIdleScene
from scenes.idle.themes.icons.weather.codes import code_to_weather
from scenes.idle.themes.icons.weather.forecast_sprite import (
    SPRITE_WIDTH,
    blank_area,
    create_animation,
)
from scenes.idle.themes.theme_utilities import font_text_width, temperature_to_colour
from setup import fonts, frames
from setup.configuration import Config
from setup.screen import WIDTH as SCREEN_WIDTH
from setup.themes import (
    TC,
    THEME_BG,
    THEME_CONDITIONS_DATE,
    THEME_CONDITIONS_DAY,
    THEME_CONDITIONS_HUMIDITY,
    THEME_CONDITIONS_SUNRISE,
    THEME_CONDITIONS_SUNSET,
    THEME_CONDITIONS_TIME,
    THEME_CONDITIONS_WIND,
)
from utilities.sun_times import is_daytime, parse_time

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

# Clock / date / day (top row) - mirrors the forecast theme.
CLOCK_FONT = fonts.small
CLOCK_POSITION = (0, 6)
DATE_FONT = CLOCK_FONT
DATE_POSITION_Y = CLOCK_POSITION[1]
_DAY_ABBREVS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
DATE_DAY_FIRST = {0: True, 1: True, 2: False}
DAY_DATE_SPACE_PX = 0

# Sprite - far left, below the top row.
SPRITE_POSITION = (0, 12)

# Text column - to the right of the sprite.
TEXT_X = SPRITE_WIDTH + 1  # one pixel gap after the sprite
TEXT_FONT = fonts.extrasmall  # 4x6
TEXT_LINE_HEIGHT = 6

# Row Y positions for the text lines (below the top row).
ROW_TEMP_Y = 12
ROW_HUMIDITY_Y = ROW_TEMP_Y + TEXT_LINE_HEIGHT
ROW_WIND_Y = ROW_HUMIDITY_Y + TEXT_LINE_HEIGHT
ROW_SUN_Y = ROW_WIND_Y + TEXT_LINE_HEIGHT


class ConditionsIdleTheme(BaseIdleScene):
    """Current-conditions idle layout - sprite + temperature/humidity/wind/sun."""

    # ------------------------------------------------------------------
    # Theme-specific state
    # ------------------------------------------------------------------

    def theme_init(self) -> None:
        self.last_time: str | None = None
        self.last_date: str | None = None
        self.last_temp_str: str | None = None
        self.last_humidity_str: str | None = None
        self.last_wind_str: str | None = None
        self.last_sun_str: str | None = None
        self.last_sprite_key: tuple | None = None
        self.animation = None
        self._anim_position: tuple[int, int] | None = None

    def theme_reset(self) -> None:
        self._destroy_animation()
        self.last_time = None
        self.last_date = None
        self.last_temp_str = None
        self.last_humidity_str = None
        self.last_wind_str = None
        self.last_sun_str = None
        self.last_sprite_key = None

    # ------------------------------------------------------------------
    # draw() - overridden for per-frame sprite animation
    # ------------------------------------------------------------------
    #
    # The base class throttles draw_content() to ~1 fps.  The sprite
    # animation needs per-frame ticks (~12.5 fps) but the data only
    # changes once per second (clock) or every few minutes (weather).
    # We tick the animation every frame and evaluate content once per
    # second, matching the forecast theme's approach.

    def draw(self) -> None:
        self.frame += 1

        if self.animation is not None:
            self.animation.tick()

        if self.frame % int(frames.PER_SECOND):
            return

        count = self.frame // int(frames.PER_SECOND)
        self.draw_content(count)

    # ------------------------------------------------------------------
    # draw_content - called once per second
    # ------------------------------------------------------------------

    def draw_content(self, count: int) -> None:
        self.draw_clock()
        self.draw_date()

        weather = self.weather.get()
        if weather is None:
            return

        self.draw_sprite(weather)
        self.draw_temperature(weather)
        self.draw_humidity(weather)
        self.draw_wind(weather)
        self.draw_sun(weather)

    # ------------------------------------------------------------------
    # Clock (top row, left)
    # ------------------------------------------------------------------

    def draw_clock(self) -> None:
        cfg = Config.instance()
        now = datetime.datetime.now()
        if cfg.clock_24hr:
            time_str = now.strftime("%H:%M")
        else:
            hour = int(now.strftime("%I"))
            time_str = f"{hour}:{now.strftime('%M')}"

        if self.last_time == time_str:
            return

        if self.last_time is not None:
            self.panel.draw_text(
                self.canvas,
                CLOCK_FONT,
                CLOCK_POSITION[0],
                CLOCK_POSITION[1],
                TC(THEME_BG),
                self.last_time,
            )

        self.last_time = time_str
        self.panel.draw_text(
            self.canvas,
            CLOCK_FONT,
            CLOCK_POSITION[0],
            CLOCK_POSITION[1],
            TC(THEME_CONDITIONS_TIME),
            time_str,
        )

    # ------------------------------------------------------------------
    # Date + day (top row, right-aligned)
    # ------------------------------------------------------------------

    def draw_date(self) -> None:
        cfg = Config.instance()
        now = datetime.datetime.now()

        day_name = _DAY_ABBREVS[now.weekday()].upper()
        day = now.day
        month = now.month

        day_first = DATE_DAY_FIRST.get(cfg.date_format, True)
        date_str = f"{day}/{month}" if day_first else f"{month}/{day}"

        current_date = day_name + " " + date_str
        if self.last_date == current_date:
            return

        date_width = font_text_width(DATE_FONT, date_str)
        date_x = SCREEN_WIDTH + 1 - date_width
        day_x = date_x - DAY_DATE_SPACE_PX - font_text_width(DATE_FONT, day_name)

        if self.last_date is not None:
            old_day_name = self.last_date[:3]
            old_date_str = self.last_date[4:]
            old_date_width = font_text_width(DATE_FONT, old_date_str)
            old_date_x = SCREEN_WIDTH + 1 - old_date_width
            old_day_x = (
                old_date_x
                - DAY_DATE_SPACE_PX
                - font_text_width(DATE_FONT, old_day_name)
            )
            self.panel.draw_text(
                self.canvas,
                DATE_FONT,
                old_day_x,
                DATE_POSITION_Y,
                TC(THEME_BG),
                old_day_name,
            )
            self.panel.draw_text(
                self.canvas,
                DATE_FONT,
                old_date_x,
                DATE_POSITION_Y,
                TC(THEME_BG),
                old_date_str,
            )

        self.last_date = current_date
        self.panel.draw_text(
            self.canvas,
            DATE_FONT,
            day_x,
            DATE_POSITION_Y,
            TC(THEME_CONDITIONS_DAY),
            day_name,
        )
        self.panel.draw_text(
            self.canvas,
            DATE_FONT,
            date_x,
            DATE_POSITION_Y,
            TC(THEME_CONDITIONS_DATE),
            date_str,
        )

    # ------------------------------------------------------------------
    # Weather sprite (far left)
    # ------------------------------------------------------------------

    def draw_sprite(self, weather: dict) -> None:
        cfg = Config.instance()
        condition_code = int(weather.get("condition_code", 0))
        is_day = is_daytime(cfg.observer_lat, cfg.observer_lng)
        sprite_key = (condition_code, is_day)

        if sprite_key == self.last_sprite_key:
            return

        self._destroy_animation()
        icon_name, animation_name, intensity = code_to_weather(
            condition_code, not is_day
        )

        anim = create_animation(
            panel=self.panel,
            canvas=self.canvas,
            x=SPRITE_POSITION[0],
            y=SPRITE_POSITION[1],
            icon_name=icon_name,
            animation_name=animation_name,
            intensity=intensity,
        )
        if anim is not None:
            self.animation = anim
            self._anim_position = SPRITE_POSITION

        self.last_sprite_key = sprite_key

    def _destroy_animation(self) -> None:
        if self._anim_position is not None:
            blank_area(self.panel, self.canvas, *self._anim_position)
        self.animation = None
        self._anim_position = None

    # ------------------------------------------------------------------
    # Temperature
    # ------------------------------------------------------------------

    def draw_temperature(self, weather: dict) -> None:
        cfg = Config.instance()
        temp_c = weather.get("temp_c")
        if temp_c is None:
            return

        display_temp = temp_c * 9.0 / 5.0 + 32 if cfg.units == "i" else temp_c
        unit_char = "F" if cfg.units == "i" else "C"
        temp_str = f"{round(display_temp)}{unit_char}"

        if temp_str == self.last_temp_str:
            return

        if self.last_temp_str is not None:
            self.panel.draw_text(
                self.canvas,
                TEXT_FONT,
                TEXT_X,
                ROW_TEMP_Y,
                TC(THEME_BG),
                self.last_temp_str,
            )

        self.last_temp_str = temp_str
        self.panel.draw_text(
            self.canvas,
            TEXT_FONT,
            TEXT_X,
            ROW_TEMP_Y,
            temperature_to_colour(temp_c),
            temp_str,
        )

    # ------------------------------------------------------------------
    # Humidity
    # ------------------------------------------------------------------

    def draw_humidity(self, weather: dict) -> None:
        humidity = weather.get("humidity")
        if humidity is None:
            return

        humidity_str = f"H{int(humidity)}%"

        if humidity_str == self.last_humidity_str:
            return

        if self.last_humidity_str is not None:
            self.panel.draw_text(
                self.canvas,
                TEXT_FONT,
                TEXT_X,
                ROW_HUMIDITY_Y,
                TC(THEME_BG),
                self.last_humidity_str,
            )

        self.last_humidity_str = humidity_str
        self.panel.draw_text(
            self.canvas,
            TEXT_FONT,
            TEXT_X,
            ROW_HUMIDITY_Y,
            TC(THEME_CONDITIONS_HUMIDITY),
            humidity_str,
        )

    # ------------------------------------------------------------------
    # Wind speed + direction
    # ------------------------------------------------------------------

    def draw_wind(self, weather: dict) -> None:
        cfg = Config.instance()
        wind_kph = weather.get("wind_kph")
        wind_dir = weather.get("wind_dir", "")
        if wind_kph is None:
            return

        if cfg.units == "i":
            wind_val = wind_kph * 0.621371
            wind_unit = "m"
        else:
            wind_val = wind_kph
            wind_unit = "k"
        wind_str = f"{round(wind_val)}{wind_unit} {wind_dir}"

        if wind_str == self.last_wind_str:
            return

        if self.last_wind_str is not None:
            self.panel.draw_text(
                self.canvas,
                TEXT_FONT,
                TEXT_X,
                ROW_WIND_Y,
                TC(THEME_BG),
                self.last_wind_str,
            )

        self.last_wind_str = wind_str
        self.panel.draw_text(
            self.canvas,
            TEXT_FONT,
            TEXT_X,
            ROW_WIND_Y,
            TC(THEME_CONDITIONS_WIND),
            wind_str,
        )

    # ------------------------------------------------------------------
    # Sunrise / sunset
    # ------------------------------------------------------------------

    def draw_sun(self, weather: dict) -> None:
        astro = weather.get("astro", {})
        sunrise_str = astro.get("sunrise", "")
        sunset_str = astro.get("sunset", "")
        if not sunrise_str and not sunset_str:
            return

        # WeatherAPI returns "06:30 AM" / "07:45 PM"; parse to HH:MM.
        sunrise = parse_time(sunrise_str) if sunrise_str else None
        sunset = parse_time(sunset_str) if sunset_str else None

        # Show the next event: sunset during the day, sunrise at night.
        cfg = Config.instance()
        is_day = is_daytime(cfg.observer_lat, cfg.observer_lng)
        if is_day and sunset is not None:
            label = "SS"
            t = sunset
            colour_key = THEME_CONDITIONS_SUNSET
        elif sunrise is not None:
            label = "SR"
            t = sunrise
            colour_key = THEME_CONDITIONS_SUNRISE
        else:
            return

        time_str = t.strftime("%H:%M") if cfg.clock_24hr else self._format_12h(t)
        sun_str = f"{label} {time_str}"

        if sun_str == self.last_sun_str:
            return

        if self.last_sun_str is not None:
            self.panel.draw_text(
                self.canvas,
                TEXT_FONT,
                TEXT_X,
                ROW_SUN_Y,
                TC(THEME_BG),
                self.last_sun_str,
            )

        self.last_sun_str = sun_str
        self.panel.draw_text(
            self.canvas,
            TEXT_FONT,
            TEXT_X,
            ROW_SUN_Y,
            TC(colour_key),
            sun_str,
        )

    @staticmethod
    def _format_12h(t: datetime.time) -> str:
        """Format a time as 12-hour with no leading zero (e.g. '7:30')."""
        hour = t.hour % 12
        if hour == 0:
            hour = 12
        return f"{hour}:{t.strftime('%M')}"

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
    _load_icon,
    blank_area,
    create_animation,
)
from scenes.idle.themes.theme_utilities import font_text_width, temperature_to_colour
from setup import fonts, frames
from setup.configuration import Config
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
from utilities.sun_times import is_daytime

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

# Clock / date / day (bottom bar).
CLOCK_FONT = fonts.small
CLOCK_POSITION = (0, 6)
DAY_GAP_PX = 2  # gap between time and abbreviated day name
DATE_FONT = fonts.extrasmall  # 4x6 - smaller font for full date
DATE_POSITION_Y = CLOCK_POSITION[1] + 8  # line below clock
_DAY_ABBREVS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
# 0 = YYYY-MM-DD, 1 = DD-MM-YYYY, 2 = MM-DD-YYYY
DATE_FORMATS = {
    0: lambda y, m, d: f"{y}-{m:02d}-{d:02d}",
    1: lambda y, m, d: f"{d:02d}-{m:02d}-{y}",
    2: lambda y, m, d: f"{m:02d}-{d:02d}-{y}",
}

# Sprite - top left.
SPRITE_POSITION = (63 - 15, 0)

# Text column - to the right of the sprite.
TEXT_X = SPRITE_WIDTH + 1  # one pixel gap after the sprite
TEXT_FONT = fonts.extrasmall  # 4x6
TEXT_LINE_HEIGHT = 6

# Row Y positions for the text lines (top section, right of sprite).
ROW_TEMP_Y = 6
ROW_HUMIDITY_Y = ROW_TEMP_Y + TEXT_LINE_HEIGHT
ROW_WIND_Y = ROW_HUMIDITY_Y + TEXT_LINE_HEIGHT

# Sunrise / sunset - very bottom of the display.
SUN_ROW_Y = 32  # baseline for 4x6 font at the bottom of 32px panel
SUN_ICON_WIDTH = 5  # width of the sunrise/sunset PNG sprites
SUN_ICON_HEIGHT = 5  # height of the sunrise/sunset PNG sprites
SUN_ICON_GAP = 1  # gap between icon and text
SUN_GAP = 2  # gap between sunrise and sunset segments


class ConditionsIdleTheme(BaseIdleScene):
    """Current-conditions idle layout - sprite + temperature/humidity/wind/sun."""

    # ------------------------------------------------------------------
    # Theme-specific state
    # ------------------------------------------------------------------

    def theme_init(self) -> None:
        self.last_time: str | None = None
        self.last_day: str | None = None
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
        self.last_day = None
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
        self.draw_day()
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
    # Clock (bottom bar, left)
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
    # Day abbreviation (beside clock, 2px gap)
    # ------------------------------------------------------------------

    def draw_day(self) -> None:
        now = datetime.datetime.now()
        day_name = _DAY_ABBREVS[now.weekday()].upper()

        if self.last_day == day_name:
            return

        day_x = (
            CLOCK_POSITION[0]
            + font_text_width(CLOCK_FONT, self.last_time or "")
            + DAY_GAP_PX
        )

        if self.last_day is not None:
            self.panel.draw_text(
                self.canvas,
                CLOCK_FONT,
                day_x,
                CLOCK_POSITION[1],
                TC(THEME_BG),
                self.last_day,
            )

        self.last_day = day_name
        self.panel.draw_text(
            self.canvas,
            CLOCK_FONT,
            day_x,
            CLOCK_POSITION[1],
            TC(THEME_CONDITIONS_DAY),
            day_name,
        )

    # ------------------------------------------------------------------
    # Date (stacked below clock, left-aligned)
    # ------------------------------------------------------------------

    def draw_date(self) -> None:
        cfg = Config.instance()
        now = datetime.datetime.now()

        day = now.day
        month = now.month
        year = now.year

        date_str = DATE_FORMATS.get(cfg.date_format, DATE_FORMATS[0])(year, month, day)

        if self.last_date == date_str:
            return

        if self.last_date is not None:
            self.panel.draw_text(
                self.canvas,
                DATE_FONT,
                0,
                DATE_POSITION_Y,
                TC(THEME_BG),
                self.last_date,
            )

        self.last_date = date_str
        self.panel.draw_text(
            self.canvas,
            DATE_FONT,
            0,
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

        # WeatherAPI returns "05:07 AM" / "07:45 PM" (12-hour with AM/PM).
        sunrise = self._parse_astro_time(sunrise_str) if sunrise_str else None
        sunset = self._parse_astro_time(sunset_str) if sunset_str else None

        cfg = Config.instance()
        fmt = "%H:%M" if cfg.clock_24hr else None

        # Build segments: (time_text, theme_key, icon_name).
        parts: list[tuple[str, object, str]] = []
        if sunrise is not None:
            t_str = sunrise.strftime(fmt) if fmt else self._format_12h(sunrise)
            parts.append((t_str, THEME_CONDITIONS_SUNRISE, "sunrise"))
        if sunset is not None:
            t_str = sunset.strftime(fmt) if fmt else self._format_12h(sunset)
            parts.append((t_str, THEME_CONDITIONS_SUNSET, "sunset"))

        if not parts:
            return

        # Cache the combined string for redraw avoidance.
        sun_str = " ".join(seg[0] for seg in parts)

        if sun_str == self.last_sun_str:
            return

        if self.last_sun_str is not None:
            self._undraw_sun_row(self.last_sun_str, len(parts))

        self.last_sun_str = sun_str

        # Draw new content at the bottom, left-aligned.
        # Icon is vertically centred against the 4x6 text row.
        icon_y = SUN_ROW_Y - 5 + (6 - SUN_ICON_HEIGHT) // 2
        x = 0
        for i, (t_str, seg_key, icon_name) in enumerate(parts):
            if i > 0:
                x += SUN_GAP
            # Draw icon sprite to the left of the text.
            icon_image = _load_icon(icon_name)
            if icon_image is not None:
                self.panel.draw_image(self.canvas, x, icon_y, icon_image)
            x += SUN_ICON_WIDTH + SUN_ICON_GAP
            # Draw text.
            self.panel.draw_text(
                self.canvas,
                TEXT_FONT,
                x,
                SUN_ROW_Y,
                TC(seg_key),
                t_str,
            )
            x += font_text_width(TEXT_FONT, t_str)

    def _undraw_sun_row(self, old_str: str, num_parts: int) -> None:
        """Erase old sunrise/sunset text and icons in background colour."""
        bg = TC(THEME_BG)
        segments = old_str.split(" ")
        icon_y = SUN_ROW_Y - 5 + (6 - SUN_ICON_HEIGHT) // 2
        x = 0
        for i in range(num_parts):
            if i > 0:
                x += SUN_GAP
            # Erase icon area (SUN_ICON_WIDTH x SUN_ICON_HEIGHT).
            for ty in range(icon_y, icon_y + SUN_ICON_HEIGHT):
                for tx in range(x, x + SUN_ICON_WIDTH):
                    self.panel.set_pixel(self.canvas, tx, ty, bg.red, bg.green, bg.blue)
            x += SUN_ICON_WIDTH + SUN_ICON_GAP
            # Erase text.
            seg_text = segments[i] if i < len(segments) else ""
            self.panel.draw_text(
                self.canvas,
                TEXT_FONT,
                x,
                SUN_ROW_Y,
                bg,
                seg_text,
            )
            x += font_text_width(TEXT_FONT, seg_text)

    @staticmethod
    def _parse_astro_time(value: str) -> datetime.time | None:
        """Parse a WeatherAPI astro time string (e.g. "05:07 AM").

        WeatherAPI returns 12-hour times with an AM/PM suffix, which the
        shared ``parse_time`` helper (expecting plain ``HH:MM``) cannot
        handle.  Returns ``None`` on failure.
        """
        try:
            return datetime.datetime.strptime(value.strip(), "%I:%M %p").time()
        except (ValueError, AttributeError, TypeError):
            return None

    @staticmethod
    def _format_12h(t: datetime.time) -> str:
        """Format a time as 12-hour with no leading zero (e.g. '7:30')."""
        hour = t.hour % 12
        if hour == 0:
            hour = 12
        return f"{hour}:{t.strftime('%M')}"

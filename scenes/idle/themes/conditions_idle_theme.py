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
import math
from enum import Enum, auto
from pathlib import Path

from PIL import Image

from scenes.idle.idle_scene import BaseIdleScene
from scenes.idle.themes.icons.weather.codes import code_to_weather
from scenes.idle.themes.icons.weather.forecast_sprite import (
    _load_icon,
    blank_area,
    create_animation,
)
from scenes.idle.themes.theme_utilities import (
    ClockDateBar,
    font_text_width,
    temperature_to_colour,
)
from setup import fonts, frames
from setup.configuration import Config
from setup.screen import WIDTH as SCREEN_WIDTH
from setup.themes import (
    TC,
    THEME_BG,
    THEME_CONDITIONS_DESCRIPTION,
    THEME_CONDITIONS_HUMIDITY,
    THEME_CONDITIONS_SUNRISE,
    THEME_CONDITIONS_SUNSET,
    THEME_CONDITIONS_TIME,
    THEME_CONDITIONS_WIND,
)
from utilities.sun_times import is_daytime

_DIRECTIONS_DIR = Path(__file__).parent / "icons" / "directions"
_direction_cache: dict[str, Image.Image] = {}

# 8 cardinal directions indexed by 45-degree sectors.
_CARDINAL_DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")


def _load_direction_icon(name: str) -> Image.Image | None:
    """Load a direction icon PNG from icons/directions/, cached for reuse."""
    if not name:
        return None
    if name not in _direction_cache:
        path = _DIRECTIONS_DIR / f"{name}.png"
        if not path.exists():
            return None
        with Image.open(path) as img:
            _direction_cache[name] = img.convert("RGBA")
    return _direction_cache[name]


# Moon phase icon loading (module-level cache).
_MOON_DIR = Path(__file__).parent / "icons" / "moon"
_moon_cache: dict[str, Image.Image] = {}

# Maps WeatherAPI moon_phase strings to icon filenames.
_MOON_PHASE_ICONS = {
    "New Moon": "new",
    "Waxing Crescent": "waxing_crescent",
    "First Quarter": "first_quarter",
    "Waxing Gibbous": "waxing_gibbous",
    "Full Moon": "full",
    "Waning Gibbous": "waning_gibbous",
    "Last Quarter": "last_quarter",
    "Waning Crescent": "waning_crescent",
}


def _load_moon_icon(name: str) -> Image.Image | None:
    """Load a moon phase icon PNG from icons/moon/, cached for reuse."""
    if not name:
        return None
    if name not in _moon_cache:
        path = _MOON_DIR / f"{name}.png"
        if not path.exists():
            return None
        with Image.open(path) as img:
            _moon_cache[name] = img.convert("RGBA")
    return _moon_cache[name]


# ---------------------------------------------------------------------------
# Description scroller (bouncing text for long descriptions)
# ---------------------------------------------------------------------------

# Easing pattern for smooth scrolling (same as flight_scene.py).
_EASING_STEPS = (1, 0, 0, 1, 1, 0, 1, 1, 1)

_DESC_INITIAL_TICKS = 12 * 8  # hold before scrolling
_DESC_PAUSE_TICKS = 12 * 3  # hold at each end


def _easing_offset(tick: int) -> int:
    return 1 if tick >= len(_EASING_STEPS) else _EASING_STEPS[tick]


class _ScrollState(Enum):
    INITIAL = auto()
    REVEAL = auto()
    PAUSE = auto()
    RETRACT = auto()


class DescriptionScroller:
    """Bounce-scroll text that's too wide for the display.

    Simplified version of flight_scene.LineScroller - no loop-done
    signalling, just bounces back and forth indefinitely when the
    text exceeds the available width.
    """

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.state: _ScrollState = _ScrollState.INITIAL
        self.timer: int = 0
        self.position: int = 0
        self.scroll_max: int = 0

    def tick(self) -> int:
        st = self.state

        if st == _ScrollState.REVEAL:
            self.position -= _easing_offset(self.timer)
        elif st == _ScrollState.RETRACT:
            self.position += _easing_offset(self.timer)

        if st == _ScrollState.INITIAL:
            if self.scroll_max > 0 and self.timer >= _DESC_INITIAL_TICKS:
                self.state = _ScrollState.REVEAL
                self.timer = 0
        elif st == _ScrollState.REVEAL:
            if self.position <= -self.scroll_max:
                self.position = -self.scroll_max
                self.state = _ScrollState.PAUSE
                self.timer = 0
        elif st == _ScrollState.PAUSE:
            if self.timer >= _DESC_PAUSE_TICKS:
                self.state = (
                    _ScrollState.RETRACT
                    if self.position <= -self.scroll_max
                    else _ScrollState.INITIAL
                )
                self.timer = 0
        elif st == _ScrollState.RETRACT and self.position >= 0:
            self.position = 0
            self.state = _ScrollState.PAUSE
            self.timer = 0

        self.timer += 1
        return self.position


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

# Background image drawn once on scene entry.
CONDITIONS_BG_POS = (15, 6)

# Sprite - top left.
SPRITE_POSITION = (0, 6)

# Text positions for the weather data fields.
TEXT_FONT = fonts.small
TEMPERATURE_POSITION = [48, 13]
HUMIDITY_POSITION = [23, 20]
WIND_POSITION = [23, 13]
WIND_ARROW_POSITION = [16, 7]

# Moon phase icon.
MOON_X = 56  # hardcoded x position for the moon icon
MOON_Y = 14  # y position for the moon icon (below the temperature string)

# UV index triangle (drawn to the left of the moon icon).
# Hardcoded three vertices of the triangle (height 7px). Tweak to fit.

UV_TRIANGLE = ((48, 20), (54, 20), (51, 15))


# UV index -> colour mapping (via theme keys resolved at draw time).
# 0 = grey, 1-2 = green, 3-5 = yellow, 6+ = red.
def _uv_colour(uv: float):
    # Use raw RGB via the Colour helper so we don't depend on extra theme keys.
    from display.rgbpanel import Colour

    if uv >= 6:
        return Colour(255, 0, 0)  # red
    if uv >= 3:
        return Colour(255, 255, 0)  # yellow
    if uv >= 1:
        return Colour(0, 255, 0)  # green
    return Colour(128, 128, 128)  # grey


# Sunrise / sunset - very bottom of the display.
SUN_FONT = fonts.extrasmall
SUN_ROW_Y = 32  # baseline for 4x6 font at the bottom of 32px panel
DESCRIPTION_FONT = fonts.extrasmall
DESCRIPTION_Y = SUN_ROW_Y - 6  # baseline for description text, directly above sun row
SUN_ICON_WIDTH = 5  # width of the sunrise/sunset PNG sprites
SUN_ICON_HEIGHT = 5  # height of the sunrise/sunset PNG sprites
SUN_ICON_GAP = 1  # gap between icon and text
SUN_GAP = 1  # gap between sunrise and sunset segments


class ConditionsIdleTheme(BaseIdleScene):
    """Current-conditions idle layout - sprite + temperature/humidity/wind/sun."""

    # ------------------------------------------------------------------
    # Theme-specific state
    # ------------------------------------------------------------------

    def theme_init(self) -> None:
        self.bar = ClockDateBar(self.panel, self.canvas, THEME_CONDITIONS_TIME)
        self.last_temp_str: str | None = None
        self.last_humidity_str: str | None = None
        self.last_wind_str: str | None = None
        self.last_wind_dir: str | None = None
        self.last_description: str | None = None
        self.description_scroller = DescriptionScroller()
        self.last_moon_phase: str | None = None
        self.last_uv: float | None = None
        self.last_sun_str: str | None = None
        self.last_sprite_key: tuple | None = None
        self.animation = None
        self._anim_position: tuple[int, int] | None = None

    def theme_reset(self) -> None:
        self._destroy_animation()
        self.bar.reset()
        self.last_temp_str = None
        self.last_humidity_str = None
        self.last_wind_str = None
        self.last_wind_dir = None
        self.last_description = None
        self.description_scroller.reset()
        self.last_moon_phase = None
        self.last_uv = None
        self.last_sun_str = None
        self.last_sprite_key = None

    def on_enter(self) -> None:
        """Called on scene transition. Clear, draw background image, then reset."""
        self.panel.clear(self.canvas)
        bg_image = _load_icon("conditions")
        if bg_image is not None:
            self.panel.draw_image(self.canvas, *CONDITIONS_BG_POS, bg_image)
        self.reset()

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

        # Tick the description scroller every frame for smooth scrolling.
        self.draw_description_scroll()

        if self.frame % int(frames.PER_SECOND):
            return

        count = self.frame // int(frames.PER_SECOND)
        self.draw_content(count)

    # ------------------------------------------------------------------
    # draw_content - called once per second
    # ------------------------------------------------------------------

    def draw_content(self, count: int) -> None:
        self.bar.draw()

        weather = self.weather.get()
        if weather is None:
            return

        self.draw_sprite(weather)
        self.draw_temperature(weather)
        self.draw_humidity(weather)
        self.draw_wind(weather)
        self.draw_moon(weather)
        self.draw_uv(weather)
        self.draw_description(weather)
        self.draw_sun(weather)

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

        if cfg.temperature_unit == "f":
            display_temp = temp_c * 9.0 / 5.0 + 32
            unit_char = "F"
        elif cfg.temperature_unit == "k":
            display_temp = temp_c + 273.15
            unit_char = "K"
        else:
            display_temp = temp_c
            unit_char = "C"
        rounded_temp = round(display_temp)
        # Only show the unit suffix when the temperature is two
        # characters wide (i.e. -9..99); drop it for longer values so
        # three-digit (or "-10" and below) readings still fit.
        if -10 < rounded_temp < 100:
            temp_str = f"{rounded_temp}{unit_char}"
        else:
            temp_str = f"{rounded_temp}"

        if temp_str == self.last_temp_str:
            return

        temp_x = 64 - font_text_width(TEXT_FONT, temp_str)

        if self.last_temp_str is not None:
            old_x = 64 - font_text_width(TEXT_FONT, self.last_temp_str)
            self.panel.draw_text(
                self.canvas,
                TEXT_FONT,
                old_x,
                TEMPERATURE_POSITION[1],
                TC(THEME_BG),
                self.last_temp_str,
            )

        self.last_temp_str = temp_str
        self.panel.draw_text(
            self.canvas,
            TEXT_FONT,
            temp_x,
            TEMPERATURE_POSITION[1],
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

        humidity_str = f"{int(humidity)}%"

        if humidity_str == self.last_humidity_str:
            return

        if self.last_humidity_str is not None:
            self.panel.draw_text(
                self.canvas,
                TEXT_FONT,
                HUMIDITY_POSITION[0],
                HUMIDITY_POSITION[1],
                TC(THEME_BG),
                self.last_humidity_str,
            )

        self.last_humidity_str = humidity_str
        self.panel.draw_text(
            self.canvas,
            TEXT_FONT,
            HUMIDITY_POSITION[0],
            HUMIDITY_POSITION[1],
            TC(THEME_CONDITIONS_HUMIDITY),
            humidity_str,
        )

    # ------------------------------------------------------------------
    # Wind speed + direction
    # ------------------------------------------------------------------

    def draw_wind(self, weather: dict) -> None:
        cfg = Config.instance()
        wind_kph = weather.get("wind_kph")
        if wind_kph is None:
            return

        if cfg.speed_unit == "mph":
            wind_val = wind_kph * 0.621371
            wind_unit = "m"
        elif cfg.speed_unit == "kts":
            wind_val = wind_kph * 0.539957
            wind_unit = "k"
        else:
            wind_val = wind_kph
            wind_unit = "k"
        wind_str = f"{round(wind_val)}{wind_unit}"

        # Determine cardinal direction from wind_degrees.
        wind_degrees = weather.get("wind_degree")
        cardinal = (
            self._degrees_to_cardinal(wind_degrees)
            if wind_degrees is not None
            else None
        )

        if wind_str == self.last_wind_str and cardinal == self.last_wind_dir:
            return

        # Undraw old wind text.
        if self.last_wind_str is not None and wind_str != self.last_wind_str:
            self.panel.draw_text(
                self.canvas,
                TEXT_FONT,
                WIND_POSITION[0],
                WIND_POSITION[1],
                TC(THEME_BG),
                self.last_wind_str,
            )

        # Undraw old wind direction icon.
        if self.last_wind_dir is not None and cardinal != self.last_wind_dir:
            old_icon = _load_direction_icon(self.last_wind_dir)
            if old_icon is not None:
                self._erase_image(old_icon, WIND_ARROW_POSITION)

        self.last_wind_str = wind_str
        self.last_wind_dir = cardinal

        # Draw wind text.
        self.panel.draw_text(
            self.canvas,
            TEXT_FONT,
            WIND_POSITION[0],
            WIND_POSITION[1],
            TC(THEME_CONDITIONS_WIND),
            wind_str,
        )

        # Draw wind direction icon.
        if cardinal is not None:
            icon = _load_direction_icon(cardinal)
            if icon is not None:
                self.panel.draw_image(
                    self.canvas,
                    WIND_ARROW_POSITION[0],
                    WIND_ARROW_POSITION[1],
                    icon,
                )

    @staticmethod
    def _degrees_to_cardinal(degrees: float) -> str:
        """Convert a wind bearing in degrees to one of 8 cardinal directions."""
        # Use floor(x + 0.5) instead of round() because Python's round()
        # uses banker's rounding (round half to even), which gives wrong
        # results at the .5 boundaries (e.g. 22.5° should be NE, not N).
        index = int(math.floor(degrees / 45.0 + 0.5)) % 8
        return _CARDINAL_DIRECTIONS[index]

    def _erase_image(self, image, position: list[int]) -> None:
        """Erase a previously drawn image by setting its pixels to background."""
        bg = TC(THEME_BG)
        x, y = position
        for py in range(image.height):
            for px in range(image.width):
                if image.getpixel((px, py))[3] > 0:
                    self.panel.set_pixel(
                        self.canvas, x + px, y + py, bg.red, bg.green, bg.blue
                    )

    # ------------------------------------------------------------------
    # Moon phase
    # ------------------------------------------------------------------

    def draw_moon(self, weather: dict) -> None:
        astro = weather.get("astro", {})
        moon_phase = astro.get("moon_phase", "")
        if not moon_phase:
            return

        if moon_phase == self.last_moon_phase:
            return

        icon_name = _MOON_PHASE_ICONS.get(moon_phase)

        # Undraw old moon icon.
        if self.last_moon_phase is not None:
            old_icon_name = _MOON_PHASE_ICONS.get(self.last_moon_phase)
            if old_icon_name is not None:
                old_icon = _load_moon_icon(old_icon_name)
                if old_icon is not None:
                    self._erase_image(old_icon, [MOON_X, MOON_Y])

        self.last_moon_phase = moon_phase

        # Draw new moon icon at the hardcoded position.
        if icon_name is not None:
            icon = _load_moon_icon(icon_name)
            if icon is not None:
                self.panel.draw_image(self.canvas, MOON_X, MOON_Y, icon)

    # ------------------------------------------------------------------
    # UV index triangle (left of the moon icon)
    # ------------------------------------------------------------------

    def draw_uv(self, weather: dict) -> None:
        uv = weather.get("uv")
        if uv is None:
            return

        try:
            uv = float(uv)
        except (TypeError, ValueError):
            return

        if uv == self.last_uv:
            return

        # Erase the previous triangle by filling its bounding box with bg.
        if self.last_uv is not None:
            self._erase_triangle()

        self.last_uv = uv
        self._fill_triangle(UV_TRIANGLE, _uv_colour(uv))

    def _erase_triangle(self) -> None:
        """Erase the UV triangle area by filling its bounding box with bg."""
        bg = TC(THEME_BG)
        xs = [p[0] for p in UV_TRIANGLE]
        ys = [p[1] for p in UV_TRIANGLE]
        x0, x1 = min(xs), max(xs)
        y0, y1 = min(ys), max(ys)
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                self.panel.set_pixel(self.canvas, x, y, bg.red, bg.green, bg.blue)

    def _fill_triangle(self, points: tuple, colour) -> None:
        """Draw a filled triangle via horizontal scanlines."""
        (ax, ay), (bx, by), (cx, cy) = points
        # Sort vertices by y.
        if ay > by:
            ax, ay, bx, by = bx, by, ax, ay
        if ay > cy:
            ax, ay, cx, cy = cx, cy, ax, ay
        if by > cy:
            bx, by, cx, cy = cx, cy, bx, by

        total_h = cy - ay
        if total_h <= 0:
            return

        for y in range(ay, cy + 1):
            # Current segment is ay..by, then by..cy.
            if y < by:
                alpha_a = (y - ay) / (by - ay) if by != ay else 0.0
                alpha_b = (y - ay) / (cy - ay) if cy != ay else 0.0
                lx = ax + (bx - ax) * alpha_a
                rx = ax + (cx - ax) * alpha_b
            else:
                alpha_a = (y - by) / (cy - by) if cy != by else 0.0
                alpha_b = (y - ay) / (cy - ay) if cy != ay else 0.0
                lx = bx + (cx - bx) * alpha_a
                rx = ax + (cx - ax) * alpha_b
            if lx > rx:
                lx, rx = rx, lx
            for x in range(int(round(lx)), int(round(rx)) + 1):
                self.panel.set_pixel(
                    self.canvas, x, y, colour.red, colour.green, colour.blue
                )

    # ------------------------------------------------------------------

    def draw_description(self, weather: dict) -> None:
        description = weather.get("description")
        if not description:
            return

        # If the description text changed, reset the scroller.
        if description != self.last_description:
            if self.last_description is not None:
                self.panel.draw_text(
                    self.canvas,
                    DESCRIPTION_FONT,
                    0,
                    DESCRIPTION_Y,
                    TC(THEME_BG),
                    self.last_description,
                )
            self.last_description = description
            self.description_scroller.reset()
            text_width = font_text_width(DESCRIPTION_FONT, description)
            self.description_scroller.scroll_max = max(0, text_width - SCREEN_WIDTH)
            # Draw the text at the initial position immediately.
            self.panel.draw_text(
                self.canvas,
                DESCRIPTION_FONT,
                0,
                DESCRIPTION_Y,
                TC(THEME_CONDITIONS_DESCRIPTION),
                description,
            )

    def draw_description_scroll(self) -> None:
        """Tick the description scroller every frame and redraw if moved.

        Called from draw() at full frame rate (~12.5 fps), not from
        draw_content() which is throttled to ~1 fps.
        """
        if self.last_description is None:
            return

        prev_pos = self.description_scroller.position
        new_pos = self.description_scroller.tick()

        if prev_pos != new_pos or self.description_scroller.state in (
            _ScrollState.REVEAL,
            _ScrollState.RETRACT,
        ):
            # Erase old text at previous position.
            self.panel.draw_text(
                self.canvas,
                DESCRIPTION_FONT,
                prev_pos,
                DESCRIPTION_Y,
                TC(THEME_BG),
                self.last_description,
            )
            # Draw new text at the scrolled position.
            self.panel.draw_text(
                self.canvas,
                DESCRIPTION_FONT,
                new_pos,
                DESCRIPTION_Y,
                TC(THEME_CONDITIONS_DESCRIPTION),
                self.last_description,
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
                SUN_FONT,
                x,
                SUN_ROW_Y,
                TC(seg_key),
                t_str,
            )
            x += font_text_width(SUN_FONT, t_str)

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
                SUN_FONT,
                x,
                SUN_ROW_Y,
                bg,
                seg_text,
            )
            x += font_text_width(SUN_FONT, seg_text)

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

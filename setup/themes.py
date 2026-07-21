"""
Theme system - mirrors the DotboxClient C++ themes.

Usage:
    from setup.themes import theme_colour, theme_set, TC
    from setup.themes import (
        THEME_BG, THEME_PLANE, THEME_FLIGHT_NUMERIC, ...
    )

    colour = TC(THEME_PLANE)        # shorthand, matches the C++ TC() macro
    theme_set(1)                     # switch to Monochrome
"""

from setup import colours

# ---------------------------------------------------------------------------
# Semantic colour key constants
# ---------------------------------------------------------------------------

THEME_BG = "BG"
THEME_TEXT = "TEXT"

# Flight scene
THEME_PLANE = "PLANE"
THEME_FLIGHT_NUMERIC = "FLIGHT_NUMERIC"
THEME_FLIGHT_ALPHA = "FLIGHT_ALPHA"
THEME_DIVIDING_BAR = "DIVIDING_BAR"
THEME_DATA_INDEX = "DATA_INDEX"
THEME_ARROW = "ARROW"
THEME_PLANE_TLM = "PLANE_TLM"
THEME_PLANE_TLM_UNITS = "PLANE_TLM_UNITS"

# Clock / date scene
THEME_TIME = "TIME"
THEME_TIME_AMPM = "TIME_AMPM"
THEME_CURRENT_DAY = "CURRENT_DAY"
THEME_CURRENT_DATE = "CURRENT_DATE"

# Location widget
THEME_LOCATION_ORIGIN = "LOCATION_ORIGIN"
THEME_LOCATION_DESTINATION = "LOCATION_DESTINATION"
THEME_LOCATION_ORIGIN_FULL = "LOCATION_ORIGIN_FULL"
THEME_LOCATION_DESTINATION_FULL = "LOCATION_DESTINATION_FULL"
THEME_LOCATION_ORIGIN_ARROW = "LOCATION_ORIGIN_ARROW"
THEME_LOCATION_DESTINATION_ARROW = "LOCATION_DESTINATION_ARROW"

# Weather temperature gradient
THEME_WEATHER_00C = "WEATHER_00C"
THEME_WEATHER_01C = "WEATHER_01C"
THEME_WEATHER_10C = "WEATHER_10C"
THEME_WEATHER_15C = "WEATHER_15C"
THEME_WEATHER_20C = "WEATHER_20C"
THEME_WEATHER_25C = "WEATHER_25C"
THEME_WEATHER_35C = "WEATHER_35C"

# Forecast theme
THEME_FORECAST_TOP_TEXT = "FORECAST_TOP_TEXT"

# ---------------------------------------------------------------------------
# Theme definitions
# ---------------------------------------------------------------------------

THEME_DEFAULT = {
    THEME_BG: colours.BLACK,
    THEME_TEXT: colours.WHITE,
    THEME_PLANE: colours.PURPLE,
    THEME_FLIGHT_NUMERIC: colours.BLUE_LIGHT,
    THEME_FLIGHT_ALPHA: colours.BLUE_CALM,
    THEME_DIVIDING_BAR: colours.GREEN,
    THEME_DATA_INDEX: colours.GREY,
    THEME_ARROW: colours.ORANGE,
    THEME_PLANE_TLM: colours.PURPLE,
    THEME_PLANE_TLM_UNITS: colours.PALE_PINK,
    THEME_TIME: colours.DARK_BLUE,
    THEME_TIME_AMPM: colours.DARKER_BLUE,
    THEME_CURRENT_DAY: colours.DARK_PINK,
    THEME_CURRENT_DATE: colours.DARKER_PINK,
    THEME_LOCATION_ORIGIN: colours.GOLD,
    THEME_LOCATION_DESTINATION: colours.YELLOW,
    THEME_LOCATION_ORIGIN_FULL: colours.MOSS,
    THEME_LOCATION_DESTINATION_FULL: colours.PEACH,
    THEME_LOCATION_ORIGIN_ARROW: colours.LIME_GREEN,
    THEME_LOCATION_DESTINATION_ARROW: colours.ORANGE_RED,
    THEME_WEATHER_00C: colours.LIGHT_CYAN,
    THEME_WEATHER_01C: colours.SAPPHIRE,
    THEME_WEATHER_10C: colours.LIGHT_METHYL_BLUE,
    THEME_WEATHER_15C: colours.WAX_YELLOW,
    THEME_WEATHER_20C: colours.PEACH_SOFT,
    THEME_WEATHER_25C: colours.PEACH_RED,
    THEME_WEATHER_35C: colours.SCARLET_RED,
    THEME_FORECAST_TOP_TEXT: colours.PALE_TURQUOISE,
}

THEME_MONOCHROME = {
    THEME_BG: colours.BLACK,
    THEME_TEXT: colours.WHITE,
    THEME_PLANE: colours.WHITE_SMOKE,
    THEME_FLIGHT_NUMERIC: colours.WHITE,
    THEME_FLIGHT_ALPHA: colours.GHOST_WHITE,
    THEME_DIVIDING_BAR: colours.ANTIQUE_WHITE,
    THEME_DATA_INDEX: colours.NAVAJO_WHITE,
    THEME_ARROW: colours.FLORAL_WHITE,
    THEME_PLANE_TLM: colours.WHITE_SMOKE,
    THEME_PLANE_TLM_UNITS: colours.NAVAJO_WHITE,
    THEME_TIME: colours.WHITE,
    THEME_TIME_AMPM: colours.WHITE_SMOKE,
    THEME_CURRENT_DAY: colours.FLORAL_WHITE,
    THEME_CURRENT_DATE: colours.GHOST_WHITE,
    THEME_LOCATION_ORIGIN: colours.WHITE,
    THEME_LOCATION_DESTINATION: colours.WHITE,
    THEME_LOCATION_ORIGIN_FULL: colours.WHITE_SMOKE,
    THEME_LOCATION_DESTINATION_FULL: colours.WHITE_SMOKE,
    THEME_LOCATION_ORIGIN_ARROW: colours.NAVAJO_WHITE,
    THEME_LOCATION_DESTINATION_ARROW: colours.NAVAJO_WHITE,
    THEME_WEATHER_00C: colours.GHOST_WHITE,
    THEME_WEATHER_01C: colours.WHITE_SMOKE,
    THEME_WEATHER_10C: colours.FLORAL_WHITE,
    THEME_WEATHER_15C: colours.ANTIQUE_WHITE,
    THEME_WEATHER_20C: colours.NAVAJO_WHITE,
    THEME_WEATHER_25C: colours.WHITE,
    THEME_WEATHER_35C: colours.WHITE_SMOKE,
    THEME_FORECAST_TOP_TEXT: colours.WHITE,
}

THEME_PASTEL = {
    THEME_BG: colours.BLACK,
    THEME_TEXT: colours.LAVENDER_BLUSH,
    THEME_PLANE: colours.HOT_PINK,
    THEME_FLIGHT_NUMERIC: colours.LIGHT_SKY_BLUE,
    THEME_FLIGHT_ALPHA: colours.THISTLE,
    THEME_DIVIDING_BAR: colours.PALE_TURQUOISE,
    THEME_DATA_INDEX: colours.MISTY_ROSE,
    THEME_ARROW: colours.LIGHT_SALMON,
    THEME_PLANE_TLM: colours.AQUAMARINE,
    THEME_PLANE_TLM_UNITS: colours.LEMON_CHIFFON,
    THEME_TIME: colours.PINK,
    THEME_TIME_AMPM: colours.THISTLE,
    THEME_CURRENT_DAY: colours.LIGHT_CYAN,
    THEME_CURRENT_DATE: colours.LEMON_CHIFFON,
    THEME_LOCATION_ORIGIN: colours.PEACH_PUFF,
    THEME_LOCATION_DESTINATION: colours.LIGHT_CYAN,
    THEME_LOCATION_ORIGIN_FULL: colours.HONEYDEW,
    THEME_LOCATION_DESTINATION_FULL: colours.LAVENDER,
    THEME_LOCATION_ORIGIN_ARROW: colours.LIGHT_GREEN,
    THEME_LOCATION_DESTINATION_ARROW: colours.LIGHT_SALMON,
    THEME_WEATHER_00C: colours.ALICE_BLUE,
    THEME_WEATHER_01C: colours.POWDER_BLUE,
    THEME_WEATHER_10C: colours.LIGHT_SKY_BLUE,
    THEME_WEATHER_15C: colours.LEMON_CHIFFON,
    THEME_WEATHER_20C: colours.PEACH_SOFT,
    THEME_WEATHER_25C: colours.PEACH_PUFF,
    THEME_WEATHER_35C: colours.HOT_PINK,
    THEME_FORECAST_TOP_TEXT: colours.PALE_TURQUOISE,
}

THEME_CLASSIC = {
    THEME_BG: colours.BLACK,
    THEME_TEXT: colours.WHITE,
    THEME_PLANE: colours.PURPLE,
    THEME_FLIGHT_NUMERIC: colours.BLUE_LIGHT,
    THEME_FLIGHT_ALPHA: colours.BLUE,
    THEME_DIVIDING_BAR: colours.GREEN,
    THEME_DATA_INDEX: colours.GREY,
    THEME_ARROW: colours.ORANGE,
    THEME_PLANE_TLM: colours.PINK,
    THEME_PLANE_TLM_UNITS: colours.PINK,
    THEME_TIME: colours.BLUE_DARK,
    THEME_TIME_AMPM: colours.BLUE_DARK,
    THEME_CURRENT_DAY: colours.PINK_DARK,
    THEME_CURRENT_DATE: colours.PINK_DARKER,
    THEME_LOCATION_ORIGIN: colours.YELLOW,
    THEME_LOCATION_DESTINATION: colours.YELLOW,
    THEME_LOCATION_ORIGIN_FULL: colours.YELLOW,
    THEME_LOCATION_DESTINATION_FULL: colours.YELLOW,
    THEME_LOCATION_ORIGIN_ARROW: colours.ORANGE,
    THEME_LOCATION_DESTINATION_ARROW: colours.ORANGE,
    THEME_WEATHER_00C: colours.WHITE,
    THEME_WEATHER_01C: colours.BLUE_LIGHT,
    THEME_WEATHER_10C: colours.PINK_DARK,
    THEME_WEATHER_15C: colours.YELLOW,
    THEME_WEATHER_20C: colours.YELLOW,
    THEME_WEATHER_25C: colours.ORANGE,
    THEME_WEATHER_35C: colours.RED,
    THEME_FORECAST_TOP_TEXT: colours.PALE_TURQUOISE,
}

THEMES = [THEME_DEFAULT, THEME_MONOCHROME, THEME_PASTEL, THEME_CLASSIC]
THEME_NAMES = ["Default", "Monochrome", "Pastel", "Classic (v1)"]

# ---------------------------------------------------------------------------
# Active theme state
# ---------------------------------------------------------------------------

current_theme = THEME_DEFAULT
current_theme_id = 0


def theme_set(theme_id: int):
    global current_theme, current_theme_id
    if theme_id < 0 or theme_id >= len(THEMES):
        theme_id = 0
    current_theme = THEMES[theme_id]
    current_theme_id = theme_id


def theme_get() -> int:
    return current_theme_id


def theme_colour(key: str):
    """Return the active theme's colour for the given key.
    Falls back to WHITE if the key is not found."""
    return current_theme.get(key, colours.WHITE)


def theme_count() -> int:
    return len(THEMES)


# Convenience shorthand - matches the TC() macro in C++
TC = theme_colour

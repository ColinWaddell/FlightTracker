"""
Sunrise / sunset and time-window helpers.

Extracted from ``setup/configuration.py`` so that both the brightness
schedule and the forecast theme (day/night icon selection) can share
the same solar-position calculation without depending on the Config
singleton.
"""

from __future__ import annotations

import math
from datetime import datetime, time
from typing import Any


# ---------------------------------------------------------------------------
# Time conversion helpers
# ---------------------------------------------------------------------------


def mins_to_time(m: float) -> time:
    """Convert minutes-from-midnight (0-1440) into a ``datetime.time``."""
    m = int(round(m)) % 1440
    return time(hour=m // 60, minute=m % 60)


def time_to_mins(t: time) -> int:
    """Convert a ``datetime.time`` to minutes from midnight."""
    return t.hour * 60 + t.minute


def parse_time(value: Any, default: str = "00:00") -> time:
    """Parse an ``HH:MM`` string (or anything str()-able) into a ``datetime.time``.

    Falls back to *default* on failure. Used at the JSON-storage boundary.
    """
    try:
        return datetime.strptime(str(value).strip(), "%H:%M").time()
    except (ValueError, AttributeError, TypeError):
        return datetime.strptime(default, "%H:%M").time()


def time_in_window(start: time, end: time) -> bool:
    """Check if *now* falls inside a time window defined by two ``time`` objects.

    Handles overnight windows (e.g. 22:00 -> 07:00) where start > end.
    """
    if start is None or end is None:
        return False

    now_mins = datetime.now().hour * 60 + datetime.now().minute
    start_mins = time_to_mins(start)
    end_mins = time_to_mins(end)

    if start_mins == end_mins:
        return True
    if start_mins < end_mins:
        return start_mins <= now_mins < end_mins

    # Overnight window
    return now_mins >= start_mins or now_mins < end_mins


# ---------------------------------------------------------------------------
# Sunrise / sunset
# ---------------------------------------------------------------------------


def approx_sunrise_sunset(lat: float, lng: float, date=None) -> tuple[time, time]:
    """Approximate sunrise/sunset times for a given lat/lng and date.

    Uses a simplified solar position algorithm (NOAA approximation).
    Returns (sunrise, sunset) as ``datetime.time`` objects.
    """

    if date is None:
        date = datetime.now()

    day_of_year = date.timetuple().tm_yday

    # Solar declination (degrees)
    decl = 23.45 * math.sin(math.radians(360 / 365 * (day_of_year - 81)))

    # Approximate equation of time in minutes
    b = math.radians(360 / 365 * (day_of_year - 81))
    eot = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)

    # Solar noon in UTC (minutes from midnight)
    solar_noon_utc = 720 - 4 * lng - eot

    # Hour angle at sunrise/sunset (using 90° + 50' = -0.833° elevation)
    lat_rad = math.radians(lat)
    decl_rad = math.radians(decl)
    cos_h = (
        math.sin(math.radians(-0.833)) - math.sin(lat_rad) * math.sin(decl_rad)
    ) / (math.cos(lat_rad) * math.cos(decl_rad))

    # Polar night / midnight sun - clamp to 0 or 1440 minutes
    if cos_h > 1:
        # Sun never rises
        noon = mins_to_time(720)
        return noon, noon
    if cos_h < -1:
        # Sun never sets
        noon = mins_to_time(720)
        return noon, noon

    ha = math.degrees(math.acos(cos_h))  # degrees
    ha_minutes = ha * 4  # 1° = 4 minutes

    sunrise = solar_noon_utc - ha_minutes
    sunset = solar_noon_utc + ha_minutes

    # Wrap into 0-1440
    sunrise = sunrise % 1440
    sunset = sunset % 1440

    return mins_to_time(sunrise), mins_to_time(sunset)


def is_daytime(lat: float, lng: float, date=None) -> bool:
    """Return True if *date* falls between sunrise and sunset at *lat*/*lng*.

    If *date* is None, the current time is used.  In polar regions where the
    sun never rises (polar night) this returns False; where it never sets
    (midnight sun) it returns True.
    """
    if date is None:
        date = datetime.now()

    sunrise, sunset = approx_sunrise_sunset(lat, lng, date)

    # Polar night or midnight sun: sunrise == sunset
    if sunrise == sunset:
        # Determine which by checking the declination sign vs latitude.
        # If cos_h > 1 (sun never rises) -> not daytime.
        # If cos_h < -1 (sun never sets) -> daytime.
        day_of_year = date.timetuple().tm_yday
        decl = 23.45 * math.sin(math.radians(360 / 365 * (day_of_year - 81)))
        lat_rad = math.radians(lat)
        decl_rad = math.radians(decl)
        cos_h = (
            math.sin(math.radians(-0.833))
            - math.sin(lat_rad) * math.sin(decl_rad)
        ) / (math.cos(lat_rad) * math.cos(decl_rad))
        return cos_h < -1

    now_mins = date.hour * 60 + date.minute
    sunrise_mins = time_to_mins(sunrise)
    sunset_mins = time_to_mins(sunset)

    if sunrise_mins <= sunset_mins:
        return sunrise_mins <= now_mins < sunset_mins

    # Sunrise/sunset straddle midnight (rare but possible near poles)
    return now_mins >= sunrise_mins or now_mins < sunset_mins
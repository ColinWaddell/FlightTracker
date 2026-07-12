"""
Shared helpers for the overhead data-source libraries (fr24, tar1090, osn).

Consolidates:
  - Constants (EARTH_RADIUS_KM, BLANK_FIELDS)
  - Unit conversions (metres→feet, m/s→knots, m/s→fpm)
  - Geometry (in_zone, distance_from_home)
  - Field cleaning (clean_field)
  - Airport info lookup (bundled airports.json)
"""

import json
import logging
import math
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EARTH_RADIUS_KM = 6371
BLANK_FIELDS = {"", "N/A", "NONE"}

# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------


def metres_to_feet(m) -> float:
    """Convert metres to feet, returning 0.0 on invalid input."""
    try:
        return float(m) * 3.28084
    except (TypeError, ValueError):
        return 0.0


def ms_to_knots(ms) -> int:
    """Convert metres/second to knots, returning 0 on invalid input."""
    try:
        return int(float(ms) * 1.94384)
    except (TypeError, ValueError):
        return 0


def ms_to_fpm(ms) -> int:
    """Convert metres/second to feet/minute, returning 0 on invalid input."""
    try:
        return int(float(ms) * 196.85)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def in_zone(lat, lon, zone) -> bool:
    """Return True if (lat, lon) falls inside the bounding box *zone*.

    *zone* is a dict with keys ``tl_y``, ``tl_x`` (top-left) and
    ``br_y``, ``br_x`` (bottom-right).
    """
    return zone["br_y"] <= lat <= zone["tl_y"] and zone["tl_x"] <= lon <= zone["br_x"]


def distance_from_home(lat, lon, alt_ft, home) -> float:
    """Great-circle-plus-altitude distance from a point to *home*.

    Parameters
    ----------
    lat, lon : float
        Position of the aircraft in decimal degrees.
    alt_ft : float
        Altitude in feet.
    home : sequence of [lat, lon, radius_km]
        Observer location (radius_km is typically EARTH_RADIUS_KM).

    Returns
    -------
    float
        Straight-line distance in km.  Returns 1e6 on invalid input so
        sorting always works.
    """

    def polar_to_cartesian(lat, lon, alt):
        deg2rad = math.pi / 180
        return [
            alt * math.cos(deg2rad * lat) * math.sin(deg2rad * lon),
            alt * math.sin(deg2rad * lat),
            alt * math.cos(deg2rad * lat) * math.cos(deg2rad * lon),
        ]

    altitude_km = 0.0003048 * alt_ft + EARTH_RADIUS_KM
    try:
        x0, y0, z0 = polar_to_cartesian(lat, lon, altitude_km)
        x1, y1, z1 = polar_to_cartesian(*home)
        return math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2)
    except (TypeError, ValueError):
        return 1e6


# ---------------------------------------------------------------------------
# Field cleaning
# ---------------------------------------------------------------------------


def clean_field(value) -> str:
    """Strip whitespace and return '' for blank/None/sentinel values."""
    if value is None:
        return ""
    try:
        value = value.strip()
    except AttributeError:
        value = str(value).strip()
    return "" if value.upper() in BLANK_FIELDS else value


# ---------------------------------------------------------------------------
# Airport info lookup (bundled airports.json)
# ---------------------------------------------------------------------------

_airports_cache: dict[str, dict] = {}
_airports_loaded = False


def _load_airports():
    global _airports_cache, _airports_loaded
    if _airports_loaded:
        return
    _airports_loaded = True
    path = Path(__file__).parent.parent / "assets" / "airports.json"
    if path.exists():
        try:
            with open(path) as fh:
                _airports_cache = json.load(fh)
        except Exception:
            _airports_cache = {}


def airport_info(iata: str) -> dict:
    """Return the full airport dict {name, municipality, country_name} or {}."""
    _load_airports()
    return _airports_cache.get(iata.upper(), {})


def airport_name(iata: str) -> str:
    """Return the airport name for *iata*, or '' if unknown."""
    return airport_info(iata).get("name", "")

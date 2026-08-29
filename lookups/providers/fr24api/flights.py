"""Live flight positions from the official FlightRadar24 API.

GET /api/live/flight-positions/full?bounds=N,S,W,E - the full variant
carries origin/destination airports and the operating airline ICAO code
alongside telemetry, which rides along as pre-filled enrichment.  The
API bills per returned record, so the zone bounding box is exact and the
altitude band is requested server-side via ``altitude_ranges``.
"""

from __future__ import annotations

import logging

from lookups.providers.fr24api.client import (
    api_key,
    api_unavailable,
    data_of,
    is_transport_error,
)
from lookups.results import FlightObservation, FlightQuery, LookupResult
from utilities.overhead_utilities import distance_from_home, in_zone

logger = logging.getLogger(__name__)


def _bounds(zone: dict) -> str:
    """FR24 bounds string - north, south, west, east."""
    north = float(zone.get("tl_y", 0.0))
    south = float(zone.get("br_y", 0.0))
    west = float(zone.get("tl_x", 0.0))
    east = float(zone.get("br_x", 0.0))
    return f"{north},{south},{west},{east}"


def _to_observation(record: dict) -> FlightObservation | None:
    """Map one FR24 API position record to an observation."""
    from utilities.overhead_utilities import clean_field

    icao = (record.get("hex") or "").strip().lower()
    lat = record.get("lat")
    lng = record.get("lon")
    alt = record.get("alt")
    if not icao or not isinstance(lat, (int, float)):
        return None

    return FlightObservation(
        icao=icao,
        callsign=clean_field(record.get("callsign")),
        flight_number=clean_field(record.get("flight")),
        latitude=lat,
        longitude=lng,
        altitude_ft=alt if isinstance(alt, (int, float)) else 0,
        ground_speed_kt=_as_int(record.get("gspeed")),
        heading_deg=_as_int(record.get("track")),
        vertical_speed_fpm=_as_int(record.get("vspeed")),
        # Enrichment that rides free with the /full variant:
        origin=clean_field(record.get("orig_iata")),
        destination=clean_field(record.get("dest_iata")),
        airline_icao=clean_field(record.get("painted_as")),
    )


def _as_int(value, default: int = 0) -> int:
    return int(value) if isinstance(value, (int, float)) else default


class FlightProvider:
    """FR24 API flight-position capability (requires a paid token)."""

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}
        self._api_key = api_key(self._settings)

    def fetch(self, query: FlightQuery) -> LookupResult:
        if not self._api_key:
            return LookupResult.unavailable("FR24 API token not configured")

        from lookups.providers.fr24api.client import get

        params = {"bounds": _bounds(query.zone)}
        # Ask the API to do the altitude filtering - fewer records, fewer
        # credits.  The API's range format is two altitudes in feet.
        params["altitude_ranges"] = _altitude_range(query)

        try:
            resp = get("/api/live/flight-positions/full", self._api_key, params)
        except Exception as e:  # requests raises its own transport types
            if is_transport_error(e):
                logger.warning("FR24 API zone fetch failed: %s", e)
                return LookupResult.unavailable(f"FR24 API unreachable: {e}")
            raise

        if resp.status_code != 200:
            reason = api_unavailable(resp)
            logger.debug("FR24 API flights: %s", reason)
            return LookupResult.unavailable(reason)

        home = query.home
        candidates = []
        for record in data_of(resp):
            obs = _to_observation(record)
            if obs is None:
                continue
            alt_ft = obs.altitude_ft or 0
            if not query.min_altitude_m / 0.3048 < alt_ft < query.max_altitude_m / 0.3048:
                continue
            if not in_zone(obs.latitude, obs.longitude, query.zone):
                continue
            candidates.append(obs)

        candidates.sort(
            key=lambda obs: distance_from_home(
                home, obs.latitude or 0.0, obs.longitude or 0.0, obs.altitude_ft or 0
            )
        )
        return LookupResult.found(candidates[: query.max_results])


def _altitude_range(query: FlightQuery) -> str:
    """The query's altitude band as the API's "MIN-MAX" feet range."""
    min_ft = int(query.min_altitude_m / 0.3048)
    max_ft = int(query.max_altitude_m / 0.3048)
    return f"{min_ft}-{max_ft}"


def startup_check(settings: dict | None = None) -> bool:
    """Cheap reachability probe for the startup screen (status-agnostic)."""
    import requests

    try:
        requests.get(
            "https://fr24api.flightradar24.com/api/live/flight-positions/full",
            timeout=5,
        )
        return True
    except Exception:
        return False

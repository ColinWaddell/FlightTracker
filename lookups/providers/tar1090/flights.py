"""tar1090 / dump1090 live flight observations (local receiver)."""

from __future__ import annotations

import logging

import requests
from requests.exceptions import RequestException

from lookups.results import FlightObservation, FlightQuery, LookupResult
from utilities.overhead_utilities import (
    clean_field,
    distance_from_home,
    in_zone,
)

logger = logging.getLogger(__name__)

# Request timeout for the receiver's JSON endpoint (seconds).
TAR1090_TIMEOUT = 10


class FlightProvider:
    """Fetches live aircraft.json data from a local tar1090/dump1090 receiver.

    Accepts both readsb/tar1090-style field names (``alt_baro``, ``gs``,
    ``baro_rate``) and dump1090-style names (``altitude``, ``speed``,
    ``vert_rate``) so the parser works with either fork.

    The receiver's own aircraft-type database (``desc``, populated by
    tar1090-db) rides along as pre-filled enrichment - it is local and
    instant, so it outranks remote lookups.
    """

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}
        self.url = (self._settings.get("url") or "").strip()
        self._session = requests.Session()

    def fetch(self, query: FlightQuery) -> LookupResult:
        """Return observations for aircraft in *query* seen by the receiver."""
        if not self.url:
            return LookupResult.unavailable("tar1090 URL not configured")

        try:
            response = self._session.get(self.url, timeout=TAR1090_TIMEOUT)
            response.raise_for_status()
            aircraft_list = response.json().get("aircraft", [])
        except (RequestException, ValueError) as e:
            logger.warning("tar1090 fetch failed: %s", e)
            return LookupResult.unavailable(f"tar1090 unreachable: {e}")

        min_alt_ft = query.min_altitude_m / 0.3048
        max_alt_ft = query.max_altitude_m / 0.3048
        zone = query.zone
        home = query.home

        candidates = []
        for ac in aircraft_list:
            lat = ac.get("lat")
            lon = ac.get("lon")
            # readsb/tar1090 uses alt_baro; dump1090 (and older forks) uses
            # altitude.  Accept either field name.
            alt = ac.get("alt_baro")
            if alt is None:
                alt = ac.get("altitude")

            if lat is None or lon is None:
                continue
            if not isinstance(alt, (int, float)):
                continue
            if not (min_alt_ft < alt < max_alt_ft):
                continue
            if not in_zone(lat, lon, zone):
                continue
            candidates.append(ac)

        candidates.sort(
            key=lambda ac: distance_from_home(
                ac["lat"], ac["lon"], ac.get("alt_baro") or ac.get("altitude"), home
            )
        )

        observations = []
        for ac in candidates[: query.max_results]:
            observations.append(_to_observation(ac))

        logger.debug(
            "tar1090 fetch complete - %d flight(s) in zone", len(observations)
        )
        return LookupResult.found(observations)


def _to_observation(ac: dict) -> FlightObservation:
    """Build an observation from one tar1090 aircraft record.

    Live telemetry comes straight from the record; ``desc`` (the local
    tar1090-db aircraft type, when the receiver runs with ``--db-file-lt``)
    rides along as pre-filled enrichment so it outranks remote lookups.
    """

    alt = ac.get("alt_baro")
    if alt is None:
        alt = ac.get("altitude")
    alt_ft = alt if isinstance(alt, (int, float)) else 0

    try:
        ground_speed = int(ac.get("gs") or ac.get("speed") or 0)
    except (TypeError, ValueError):
        ground_speed = 0

    try:
        heading = int(ac.get("track", 0) or 0)
    except (TypeError, ValueError):
        heading = 0

    # baro_rate/vert_rate may be None when the transponder doesn't report
    # vertical rate; default to 0 to keep vertical_speed_fpm an int.
    vertical_speed = ac.get("baro_rate") or ac.get("vert_rate") or 0
    if not isinstance(vertical_speed, (int, float)):
        vertical_speed = 0

    return FlightObservation(
        icao=(ac.get("hex") or "").strip().lower(),
        callsign=clean_field(ac.get("flight")),
        latitude=ac.get("lat"),
        longitude=ac.get("lon"),
        altitude_ft=alt_ft,
        ground_speed_kt=ground_speed,
        heading_deg=int(heading),
        vertical_speed_fpm=int(vertical_speed),
        # Local receiver's own aircraft-type database (instant, wins over
        # remote lookups) and, when the receiver supplies it, the
        # registration.
        plane=clean_field(ac.get("desc")),
        registration=clean_field(ac.get("r")),
    )


def startup_check(url: str) -> bool:
    """Reachability probe for the startup screen (status-agnostic)."""
    if not url:
        return False
    try:
        requests.get(url, timeout=5)
        return True
    except Exception:
        return False

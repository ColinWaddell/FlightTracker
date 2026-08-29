"""
Shared adapter plumbing for community ADS-B aggregators.

adsb.fi, ADSB.lol and airplanes.live (plus local tar1090 receivers) all
publish aircraft in the "readsb" JSON dialect: positional records with
``hex`` / ``flight`` / ``r`` / ``alt_baro`` / ``gs`` / ``track`` keys,
wrapped in an envelope that differs per host (``aircraft`` on tar1090 and
adsb.fi, ``ac`` on ADSB.lol and airplanes.live).

This module owns the record -> :class:`FlightObservation` mapping once,
so each provider package is just its endpoint configuration.
"""

from __future__ import annotations

import logging
import math

from lookups.results import FlightObservation, LookupResult
from utilities.overhead_utilities import clean_field

logger = logging.getLogger(__name__)


def _as_int(value, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def observation_from_record(ac: dict) -> FlightObservation:
    """Map one readsb-format aircraft record to an observation.

    Accepts both readsb/tar1090-style field names (``alt_baro``, ``gs``,
    ``baro_rate``) and dump1090-style names (``altitude``, ``speed``,
    ``vert_rate``) so the parser works with every dialect in the family.
    """
    # readsb reports the string "ground" for alt_baro on ground traffic;
    # dump1090 forks (and some aggregators) use the "altitude" key.
    # Accept either field name, and only numeric values.
    alt = ac.get("alt_baro")
    if not isinstance(alt, (int, float)):
        alt = ac.get("altitude")
    if not isinstance(alt, (int, float)):
        alt = None

    vertical_rate = _as_int(
        ac.get("baro_rate") or ac.get("geom_rate") or ac.get("vert_rate") or 0
    )

    return FlightObservation(
        icao=(ac.get("hex") or "").strip().lower(),
        callsign=clean_field(ac.get("flight")),
        latitude=ac.get("lat"),
        longitude=ac.get("lon"),
        altitude_ft=_as_int(alt, 0),
        ground_speed_kt=_as_int(ac.get("gs") or ac.get("speed"), 0),
        heading_deg=_as_int(ac.get("track", 0), 0),
        vertical_speed_fpm=vertical_rate,
        # tar1090's desc is its local aircraft-database entry; the public
        # aggregators carry the same field.  It rides along as pre-filled
        # enrichment, so it outranks remote lookups.
        plane=clean_field(ac.get("desc")),
        registration=clean_field(ac.get("r")),
    )


def zone_radius_nm(zone: dict) -> float | None:
    """Half-diagonal of *zone* in nautical miles, padded 25%, capped at 250.

    The aggregators all accept a point + radius (NM) and reject radii
    above 250, so the bounding box is expressed as its centre-to-corner
    distance, padded 25% to keep edge aircraft inside the answer.
    """
    try:
        lat_c = (zone["tl_y"] + zone["br_y"]) / 2
        lng_c = (zone["tl_x"] + zone["br_x"]) / 2
        half_lat_km = abs(zone["tl_y"] - lat_c) * 111.0
        half_lng_km = abs(zone["tl_x"] - lng_c) * 111.0 * math.cos(math.radians(lat_c))
    except (KeyError, TypeError):
        return None

    radius_km = (half_lat_km**2 + half_lng_km**2) ** 0.5
    radius_nm = radius_km / 1.852
    return min(250.0, max(10.0, round(radius_nm * 1.25, 1)))


class AggregatorFlightProvider:
    """Base adapter for remote aggregators speaking the readsb dialect.

    Subclasses provide :attr:`endpoint` (a template taking ``{lat}``,
    ``{lon}`` and ``{radius}`` - the radius in nautical miles).  The
    response envelope differs per host (``aircraft`` on tar1090/adsb.fi,
    ``ac`` on ADSB.lol/airplanes.live) - both are accepted, in that order.
    """

    endpoint = ""
    timeout_seconds = 10
    envelope_keys = ("aircraft", "ac")

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}
        import requests

        self._session = requests.Session()

    def _records(self, payload: dict):
        for key in self.envelope_keys:
            records = payload.get(key)
            if records:
                return records
        return []

    def fetch(self, query):
        from utilities.overhead_utilities import distance_from_home, in_zone

        radius_nm = zone_radius_nm(query.zone)
        if radius_nm is None:
            return LookupResult.unavailable("flight zone is unusable")

        lat = (query.zone["tl_y"] + query.zone["br_y"]) / 2
        lon = (query.zone["tl_x"] + query.zone["br_x"]) / 2
        url = self.endpoint.format(lat=lat, lon=lon, radius=radius_nm)

        try:
            response = self._session.get(url, timeout=self.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except Exception as e:
            logger.warning("%s fetch failed: %s", type(self).__name__, e)
            return LookupResult.unavailable(f"aggregator unreachable: {e}")

        min_alt_ft = query.min_altitude_m / 0.3048
        max_alt_ft = query.max_altitude_m / 0.3048

        candidates = []
        for record in self._records(payload):
            lat = record.get("lat")
            lon = record.get("lon")
            alt = record.get("alt_baro")
            if lat is None or lon is None or not isinstance(alt, (int, float)):
                continue
            if not (min_alt_ft < alt < max_alt_ft):
                continue
            if not in_zone(lat, lon, query.zone):
                continue
            candidates.append(record)

        candidates.sort(
            key=lambda record: distance_from_home(
                record.get("lat"),
                record.get("lon"),
                record.get("alt_baro") or 0,
                query.home,
            )
        )
        observations = [
            observation_from_record(record)
            for record in candidates[: query.max_results]
        ]
        logger.debug(
            "%s fetch complete - %d flight(s)", type(self).__name__, len(observations)
        )
        return LookupResult.found(observations)

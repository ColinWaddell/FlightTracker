"""
Route and aircraft lookup via adsbdb.com - shared by overhead_tar1090 and overhead_osn.

Two independent adsbdb endpoints are used:

  Route     GET /v0/callsign/{callsign}
              -> origin, destination and full airport objects
              Cached by callsign with a 24-hour TTL.

  Aircraft  GET /v0/aircraft/{mode_s}
              -> aircraft manufacturer + type string
              Cached by mode_s (ICAO 24-bit hex) with a 24-hour TTL.

We do NOT use the combined /aircraft/{mode_s}?callsign= endpoint because
adsbdb only links the callsign to the flightroute when it can verify the
association with that specific airframe.  When it cannot (which happens
often), it returns 200 with just the aircraft object and no flightroute,
giving us empty origin/destination even when the callsign endpoint has the
data fine.

Each lookup is independently cached so a caller that only has a callsign
(overhead_tar1090) pays one request; a caller with both (overhead_osn) pays
two on the first encounter then hits cache on every subsequent poll.
"""

import logging

import requests
from requests.exceptions import RequestException

from utilities import routes_cache

logger = logging.getLogger(__name__)

ADSBDB_BASE = "https://api.adsbdb.com/v0"

# Module-level session - keeps the urllib3 connection pool alive across calls,
# avoiding Python 3.13 dummy-thread GC noise.
_session = requests.Session()

EMPTY_RESULT: dict = {
    "origin": "",
    "destination": "",
    "plane": "",
    "origin_name": "",
    "origin_municipality": "",
    "origin_country": "",
    "destination_name": "",
    "destination_municipality": "",
    "destination_country": "",
}

# ---------------------------------------------------------------------------
# Response parsers
# ---------------------------------------------------------------------------


def _parse_airport(ap: dict | None) -> dict:
    """Extract the fields we need from an adsbdb airport object."""
    if not ap or not isinstance(ap, dict):
        return {}
    iata = (ap.get("iata_code") or "").strip()
    if not iata or iata.upper() in ("", "N/A", "NONE"):
        return {}
    return {
        "iata": iata,
        "name": (ap.get("name") or "").strip(),
        "municipality": (ap.get("municipality") or "").strip(),
        "country_name": (ap.get("country_name") or "").strip(),
    }


def _parse_aircraft_type(ac: dict | None) -> str:
    """Return 'Manufacturer Type' string from an adsbdb aircraft object."""
    if not ac or not isinstance(ac, dict):
        return ""
    manufacturer = (ac.get("manufacturer") or "").strip()
    type_ = (ac.get("type") or "").strip()
    if manufacturer and type_:
        return f"{manufacturer} {type_}"
    return type_ or manufacturer


# ---------------------------------------------------------------------------
# Individual lookups (each with their own cache key)
# ---------------------------------------------------------------------------


def _lookup_route(callsign: str) -> dict:
    """Return route fields for *callsign* via GET /v0/callsign/{callsign}.

    Cached by callsign.  Returns a dict with origin/destination fields only
    (plane is always "" here — aircraft type is looked up separately).
    Never raises.
    """
    cached = routes_cache.get(callsign)
    if cached is not None:
        # Skip stale entries that have no useful data (e.g. from a previous
        # backend that cached empty results, or a failed lookup)
        if cached.get("origin") or cached.get("destination"):
            return {**EMPTY_RESULT, **cached, "plane": ""}

    route = {k: "" for k in EMPTY_RESULT if k != "plane"}
    try:
        resp = _session.get(f"{ADSBDB_BASE}/callsign/{callsign}", timeout=10)
        if resp.status_code == 404:
            logger.debug("adsbdb: unknown callsign %r", callsign)
            return {**EMPTY_RESULT, "plane": ""}
        resp.raise_for_status()

        flightroute = resp.json().get("response", {}).get("flightroute", {})
        if flightroute:
            origin = _parse_airport(flightroute.get("origin"))
            dest = _parse_airport(flightroute.get("destination"))
            route["origin"] = origin.get("iata", "")
            route["origin_name"] = origin.get("name", "")
            route["origin_municipality"] = origin.get("municipality", "")
            route["origin_country"] = origin.get("country_name", "")
            route["destination"] = dest.get("iata", "")
            route["destination_name"] = dest.get("name", "")
            route["destination_municipality"] = dest.get("municipality", "")
            route["destination_country"] = dest.get("country_name", "")

    except (RequestException, ValueError, KeyError, AttributeError, TypeError) as e:
        logger.debug("adsbdb callsign lookup failed for %r: %s", callsign, e)

    if route.get("origin") or route.get("destination"):
        routes_cache.put(callsign, {"plane": "", **route})

    return {**EMPTY_RESULT, "plane": "", **route}


def _lookup_aircraft(mode_s: str) -> str:
    """Return aircraft type string for *mode_s* via GET /v0/aircraft/{mode_s}.

    Cached by mode_s.  Returns "" when not found or on any error.
    Never raises.
    """
    cached = routes_cache.get(mode_s)
    if cached is not None:
        return cached.get("plane", "")

    plane = ""
    try:
        resp = _session.get(f"{ADSBDB_BASE}/aircraft/{mode_s.lower()}", timeout=10)
        if resp.status_code == 404:
            logger.debug("adsbdb: unknown aircraft %r", mode_s)
            # Cache a blank entry so we don't keep hitting on every poll
            routes_cache.put(mode_s, {"plane": ""})
            return ""
        resp.raise_for_status()
        aircraft = resp.json().get("response", {}).get("aircraft")
        plane = _parse_aircraft_type(aircraft)

    except (RequestException, ValueError, KeyError, AttributeError, TypeError) as e:
        logger.debug("adsbdb aircraft lookup failed for %r: %s", mode_s, e)

    routes_cache.put(mode_s, {"plane": plane})
    return plane


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def get_route(callsign: str, mode_s: str | None = None) -> dict:
    """Return a combined route + aircraft dict.

    Runs up to two independent adsbdb lookups (route by callsign, aircraft
    type by mode_s) and merges the results.  Each is independently cached
    with a 24-hour TTL, so repeat calls within that window are free.

    Returns a dict with keys:
        origin, destination, plane,
        origin_name, origin_municipality, origin_country,
        destination_name, destination_municipality, destination_country

    All values are strings; unknown fields are "".  Never raises.
    """
    result = dict(EMPTY_RESULT)

    if callsign:
        route = _lookup_route(callsign)
        result.update(route)

    if mode_s and not result["plane"]:
        result["plane"] = _lookup_aircraft(mode_s)

    return result

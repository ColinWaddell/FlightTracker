"""
Route and aircraft lookup via hexdb.io - shared by overhead_tar1090 and overhead_osn.

Three hexdb.io endpoints are used:

  Aircraft   GET /api/v1/aircraft/{hex}
               -> manufacturer, type code, registration, operator
               Cached by mode_s (ICAO 24-bit hex) with a 24-hour TTL.

  Route      GET /api/v1/route/icao/{callsign}
               -> "EGPF-LEMG" (ICAO airport codes, hyphen-separated)
               Cached by callsign with a 24-hour TTL.

  Airport    GET /api/v1/airport/icao/{icao}
               -> iata code, airport name, country code, region
               Fetched on demand and cached for the process lifetime.

ICAO-to-IATA conversion uses a bundled lookup table (assets/icao_to_iata.json)
so we can convert route codes without an extra API call.  Airport name,
municipality and country are resolved from the bundled airports.json (keyed
by IATA code) - the same file used by the FR24 backend.

Each lookup is independently cached so a caller that only has a callsign
(overhead_tar1090) pays one request; a caller with both (overhead_osn) pays
two on the first encounter then hits cache on every subsequent poll.

FR24 fallback
--------------
When hexdb.io returns no origin/destination for a callsign, the lookup
falls back to FlightRadar24 via the FlightRadarAPI library.  The FR24
real-time feed (feed.js) includes origin/destination IATA codes directly
in the flight list, so only one lightweight request is needed (filtered
by airline ICAO code).  This keeps FR24 usage minimal - only on hexdb
misses - and avoids hitting FR24 rate limits.

The FR24 fallback code is intentionally duplicated here (rather than
imported from overhead_fr24.py) to keep route_lookup self-contained.
"""

import json
import logging
from pathlib import Path

import requests
from requests.exceptions import RequestException

from utilities import routes_cache
from utilities.flight import RouteInfo

logger = logging.getLogger(__name__)

HEXDB_BASE = "https://hexdb.io/api/v1"

# Module-level session - keeps the urllib3 connection pool alive across calls,
# avoiding Python 3.13 dummy-thread GC noise.
_session = requests.Session()

# FR24 fallback timeout (seconds).  Kept short - this is a last-resort lookup.
FR24_TIMEOUT = 30

# ---------------------------------------------------------------------------
# Bundled ICAO→IATA lookup table
# ---------------------------------------------------------------------------

_icao_to_iata: dict[str, str] = {}
_icao_to_iata_loaded = False


def _load_icao_to_iata() -> None:
    """Load the ICAO-to-IATA mapping from assets/icao_to_iata.json."""
    global _icao_to_iata, _icao_to_iata_loaded
    if _icao_to_iata_loaded:
        return
    _icao_to_iata_loaded = True
    path = Path(__file__).parent.parent / "assets" / "icao_to_iata.json"
    if path.exists():
        try:
            with open(path) as fh:
                _icao_to_iata = json.load(fh)
        except Exception:
            _icao_to_iata = {}


def _icao_to_iata_code(icao: str) -> str:
    """Convert an ICAO airport code to IATA using the bundled table.

    Falls back to the hexdb.io airport endpoint if the code is not in the
    local table, then caches the result.  Returns "" if unknown.
    """
    icao = (icao or "").strip().upper()
    if not icao:
        return ""

    _load_icao_to_iata()
    if icao in _icao_to_iata:
        return _icao_to_iata[icao]

    # Not in the local table - try the hexdb airport endpoint as a fallback
    info = _lookup_airport_icao(icao)
    iata = info.get("iata", "")
    if iata:
        # Cache for future lookups
        _icao_to_iata[icao] = iata
    return iata


# ---------------------------------------------------------------------------
# Airport info cache (process-lifetime)
# ---------------------------------------------------------------------------

_airport_cache: dict[str, dict] = {}


def _lookup_airport_icao(icao: str) -> dict:
    """Fetch airport details from hexdb.io by ICAO code.

    Results are cached for the process lifetime.  Returns {} on any error.
    """
    icao = icao.strip().upper()
    if not icao:
        return {}

    if icao in _airport_cache:
        return _airport_cache[icao]

    info: dict = {}
    try:
        resp = _session.get(f"{HEXDB_BASE}/airport/icao/{icao}", timeout=10)
        if resp.status_code == 404:
            logger.debug("hexdb: unknown airport %r", icao)
            _airport_cache[icao] = {}
            return {}
        resp.raise_for_status()
        data = resp.json()
        info = {
            "iata": (data.get("iata") or "").strip(),
            "name": (data.get("airport") or "").strip(),
            "country_code": (data.get("country_code") or "").strip(),
            "region_name": (data.get("region_name") or "").strip(),
            "icao": icao,
        }

    except (RequestException, ValueError, KeyError, AttributeError, TypeError) as e:
        logger.debug("hexdb airport lookup failed for %r: %s", icao, e)

    _airport_cache[icao] = info
    return info


# ---------------------------------------------------------------------------
# Bundled airports.json (IATA-keyed, for name/municipality/country)
# ---------------------------------------------------------------------------

_airports_cache: dict[str, dict] = {}
_airports_loaded = False


def _load_airports() -> None:
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


def _airport_details(iata: str) -> dict:
    """Return {name, municipality, country_name} from bundled airports.json.

    Falls back to hexdb.io airport data (by IATA) if not in the local file.
    """
    _load_airports()
    info = _airports_cache.get(iata.upper(), {})
    if info:
        return info

    # Not in airports.json - try hexdb by IATA
    try:
        resp = _session.get(f"{HEXDB_BASE}/airport/iata/{iata}", timeout=10)
        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        data = resp.json()
        return {
            "name": (data.get("airport") or "").strip(),
            "municipality": (data.get("region_name") or "").strip(),
            "country_name": (data.get("country_code") or "").strip(),
        }
    except (RequestException, ValueError, KeyError, AttributeError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# Route parser
# ---------------------------------------------------------------------------


def _parse_route(route_str: str) -> tuple[str, str]:
    """Parse a hexdb route string "EGPF-LEMG" into (origin_icao, dest_icao)."""
    parts = route_str.split("-", 1)
    if len(parts) != 2:
        return "", ""
    return parts[0].strip().upper(), parts[1].strip().upper()


# ---------------------------------------------------------------------------
# Aircraft type parser
# ---------------------------------------------------------------------------


def _parse_aircraft_type(data: dict) -> str:
    """Build a 'Manufacturer Type' string from a hexdb aircraft response."""
    manufacturer = (data.get("Manufacturer") or "").strip()
    type_code = (data.get("ICAOTypeCode") or "").strip()
    if manufacturer and type_code:
        return f"{manufacturer} {type_code}"
    return type_code or manufacturer


# ---------------------------------------------------------------------------
# Individual lookups (each with their own cache key)
# ---------------------------------------------------------------------------


def _fr24_route_fallback(callsign: str) -> RouteInfo:
    """Fallback route lookup via FlightRadar24 when hexdb.io has no data.

    Uses the FlightRadarAPI library (same as overhead_fr24.py) to query the
    FR24 real-time feed, filtering by the airline ICAO code (first 3 chars of
    the callsign) and then scanning for a matching callsign.

    The feed.js response includes origin/destination IATA codes directly in
    the flight list, so no call to the clickhandler details endpoint is
    needed - this keeps the FR24 usage minimal.

    Returns a :class:`RouteInfo` with origin/destination fields populated
    from the FR24 flight list.  ``plane`` is always "" (aircraft type is
    not fetched here).  Never raises.
    """
    if not callsign or len(callsign) < 3:
        return RouteInfo()

    # Lazy import - FlightRadarAPI drags in curl_cffi + brotli (~4.7s on Pi).
    # Only pay that cost when a fallback is actually needed.
    try:
        from FlightRadar24.api import FlightRadar24API
    except ImportError:
        try:
            from FlightRadarAPI import FlightRadar24API
        except ImportError:
            logger.debug("FR24 fallback: FlightRadarAPI not installed")
            return RouteInfo()

    # Cloudflare may block stale cookies, so create a fresh API instance each
    # time.  This is a rare fallback path, so the overhead is acceptable.
    try:
        api = FlightRadar24API(timeout=FR24_TIMEOUT)

        # Exclude ground traffic to reduce result size
        tracker = api.get_flight_tracker_config()
        tracker.gnd = 0
        api.set_flight_tracker_config(tracker)

        airline_icao = callsign[:3].upper()
        flights = api.get_flights(airline=airline_icao)

        for flight in flights:
            if (flight.callsign or "").strip().upper() == callsign.upper():
                origin = (flight.origin_airport_iata or "").strip()
                destination = (flight.destination_airport_iata or "").strip()
                if not origin and not destination:
                    continue

                route = RouteInfo(origin=origin, destination=destination)

                if origin:
                    details = _airport_details(origin)
                    route.origin_name = details.get("name", "")
                    route.origin_municipality = details.get("municipality", "")
                    route.origin_country = details.get("country_name", "")

                if destination:
                    details = _airport_details(destination)
                    route.destination_name = details.get("name", "")
                    route.destination_municipality = details.get("municipality", "")
                    route.destination_country = details.get("country_name", "")

                logger.debug(
                    "FR24 fallback found route for %r: %s->%s",
                    callsign,
                    origin,
                    destination,
                )
                return route

        logger.debug("FR24 fallback: no matching flight for %r", callsign)

    except Exception as e:
        logger.debug("FR24 fallback failed for %r: %s", callsign, e)

    return RouteInfo()


def _lookup_route(callsign: str) -> RouteInfo:
    """Return route fields for *callsign* via GET /api/v1/route/icao/{callsign}.

    Cached by callsign.  Returns a RouteInfo with origin/destination fields
    (plane is always "" here - aircraft type is looked up separately).
    Falls back to FR24 when hexdb returns no origin/destination.
    Never raises.
    """
    cached = routes_cache.get(callsign)
    # Skip stale entries that have no useful data (e.g. from a previous
    # backend that cached empty results, or a failed lookup)
    if cached is not None and (cached.get("origin") or cached.get("destination")):
        ri = RouteInfo.from_dict(cached)
        ri.plane = ""
        return ri

    route = RouteInfo()
    try:
        resp = _session.get(f"{HEXDB_BASE}/route/icao/{callsign}", timeout=10)
        if resp.status_code == 404:
            logger.debug("hexdb: unknown callsign %r", callsign)
        else:
            resp.raise_for_status()

            data = resp.json()
            route_str = data.get("route", "")
            origin_icao, dest_icao = _parse_route(route_str)

            if origin_icao:
                origin_iata = _icao_to_iata_code(origin_icao)
                route.origin = origin_iata
                if origin_iata:
                    details = _airport_details(origin_iata)
                    route.origin_name = details.get("name", "")
                    route.origin_municipality = details.get("municipality", "")
                    route.origin_country = details.get("country_name", "")

            if dest_icao:
                dest_iata = _icao_to_iata_code(dest_icao)
                route.destination = dest_iata
                if dest_iata:
                    details = _airport_details(dest_iata)
                    route.destination_name = details.get("name", "")
                    route.destination_municipality = details.get("municipality", "")
                    route.destination_country = details.get("country_name", "")

    except (RequestException, ValueError, KeyError, AttributeError, TypeError) as e:
        logger.debug("hexdb route lookup failed for %r: %s", callsign, e)

    # ── FR24 fallback ────────────────────────────────────────────────
    # If hexdb gave us nothing useful, try FR24 before giving up.
    if not route.origin and not route.destination:
        logger.debug("hexdb had no route for %r - trying FR24 fallback", callsign)
        fr24_route = _fr24_route_fallback(callsign)
        if fr24_route.origin or fr24_route.destination:
            route = fr24_route

    if route.origin or route.destination:
        routes_cache.put(callsign, route.to_dict())

    return route


def _lookup_aircraft(mode_s: str) -> str:
    """Return aircraft type string for *mode_s* via GET /api/v1/aircraft/{hex}.

    Cached by mode_s.  Returns "" when not found or on any error.
    Never raises.
    """
    cached = routes_cache.get(mode_s)
    if cached is not None:
        return cached.get("plane", "")

    plane = ""
    try:
        resp = _session.get(f"{HEXDB_BASE}/aircraft/{mode_s.lower()}", timeout=10)
        if resp.status_code == 404:
            logger.debug("hexdb: unknown aircraft %r", mode_s)
            # Cache a blank entry so we don't keep hitting on every poll
            routes_cache.put(mode_s, {"plane": ""})
            return ""
        resp.raise_for_status()
        data = resp.json()
        plane = _parse_aircraft_type(data)

    except (RequestException, ValueError, KeyError, AttributeError, TypeError) as e:
        logger.debug("hexdb aircraft lookup failed for %r: %s", mode_s, e)

    routes_cache.put(mode_s, {"plane": plane})
    return plane


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def get_route(callsign: str, mode_s: str | None = None) -> RouteInfo:
    """Return a combined route + aircraft info.

    Runs up to two independent hexdb.io lookups (route by callsign, aircraft
    type by mode_s) and merges the results.  Each is independently cached
    with a 24-hour TTL, so repeat calls within that window are free.

    Returns a :class:`RouteInfo` with all fields as strings; unknown
    fields are "".  Never raises.
    """
    result = RouteInfo()

    if callsign:
        route = _lookup_route(callsign)
        result = route

    if mode_s and not result.plane:
        result.plane = _lookup_aircraft(mode_s)

    return result

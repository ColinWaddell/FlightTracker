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
When hexdb.io returns no origin/destination for a callsign, OR no aircraft
type for a mode_s, the lookup falls back to FlightRadar24 via the
FlightRadarAPI library.  The FR24 real-time feed (feed.js) is queried by
**aircraft registration** (the only FR24 filter that works reliably),
which is obtained from the hexdb aircraft lookup.  If hexdb yields no
registration, the FR24 fallback cannot fire - there is nothing to query
on - and the missing fields stay blank.

The fallback is **unified**: a single ``get_flights(registration=...)``
call is run at the end of :func:`get_route` after both hexdb lookups, and
fills whatever hexdb missed - route and/or aircraft type - from the one
matched flight.  This guarantees at most one ``get_flights`` call and
at most one ``get_flight_details`` (clickhandler) call per
``get_route`` invocation, so FR24 is never hit more than necessary.

Aircraft type is fetched the same way as ``overhead_fr24.py``: via
``get_flight_details`` -> ``details["aircraft"]["model"]["text"]`` (the
full model name, e.g. "Boeing 737-800").  If that call fails or returns no
model text, the free ``flight.aircraft_code`` (ICAO type code, e.g.
"B737") from the feed list is used instead so the plane field is not
left blank.

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
from utilities.overhead_utilities import clean_field

logger = logging.getLogger(__name__)

HEXDB_BASE = "https://hexdb.io/api/v1"

# Module-level session - keeps the urllib3 connection pool alive across calls,
# avoiding Python 3.13 dummy-thread GC noise.
_session = requests.Session()

# FR24 fallback timeout (seconds).  Matches overhead_fr24.py - the default 30
# is too short for Pi on slow networks, and the clickhandler details call is
# the slow one.
FR24_TIMEOUT = 60

# FR24 clickhandler (get_flight_details) retry behaviour - mirrors
# overhead_fr24.py.  The details call is rate-limited, so we retry a few times
# with a short delay before giving up and falling back to aircraft_code.
FR24_DETAIL_RETRIES = 3
FR24_DETAIL_DELAY = 1  # seconds, slept before each attempt

try:
    from curl_cffi.requests.exceptions import Timeout as _CurlTimeout
except ImportError:
    _CurlTimeout = None

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


def _parse_aircraft_registration(data: dict) -> str:
    registration = (data.get("Registration") or "").strip()
    return registration


# ---------------------------------------------------------------------------
# Individual lookups (each with their own cache key)
# ---------------------------------------------------------------------------


def _fr24_fallback(registration: str, want_plane: bool = False) -> RouteInfo:
    """Unified FR24 fallback for route and/or aircraft details.

    Uses the FlightRadarAPI library (same as overhead_fr24.py) to query the
    FR24 real-time feed, filtering by **aircraft registration** (the only
    FR24 filter that works reliably).  The registration uniquely identifies
    the aircraft, so the first flight returned is the match.

    The feed.js response includes origin/destination IATA codes directly in
    the flight list, so route fields are populated for free.  When
    ``want_plane`` is True, the aircraft type is fetched via
    ``get_flight_details`` -> ``details["aircraft"]["model"]["text"]`` (the
    full model name, e.g. "Boeing 737-800"), mirroring overhead_fr24.py.
    If that call fails or returns no model text, the free
    ``flight.aircraft_code`` (ICAO type code, e.g. "B737") from the feed list
    is used instead so the plane field is not left blank.

    Returns a :class:`RouteInfo` with whatever fields could be resolved.
    Never raises.
    """
    if not registration or len(registration) < 3:
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

        flights = api.get_flights(registration=registration)

        for flight in flights:
            origin = (flight.origin_airport_iata or "").strip()
            destination = (flight.destination_airport_iata or "").strip()

            route = RouteInfo()

            # ── Route (free from the feed list) ───────────────────────
            if origin or destination:
                route.origin = origin
                route.destination = destination

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

            # ── Aircraft type (only when requested) ──────────────────
            # The clickhandler details call is rate-limited, so only make it
            # when the caller actually needs a plane.  Mirrors
            # overhead_fr24.py:152-163 (retry loop + model text extraction).
            if want_plane:
                route.plane = _fr24_aircraft_type(api, flight)

            if route.origin or route.destination or route.plane:
                logger.debug(
                    "FR24 fallback found data for %r: %s->%s plane=%r",
                    registration,
                    route.origin,
                    route.destination,
                    route.plane,
                )
                return route

        logger.debug("FR24 fallback: no matching flight for %r", registration)

    except Exception as e:
        logger.debug("FR24 fallback failed for %r: %s", registration, e)

    return RouteInfo()


def _fr24_aircraft_type(api, flight) -> str:
    """Return the aircraft type string for *flight* via FR24.

    Tries the clickhandler details endpoint (``get_flight_details``) for the
    full model name (e.g. "Boeing 737-800"), mirroring overhead_fr24.py with
    up to ``FR24_DETAIL_RETRIES`` attempts and a ``FR24_DETAIL_DELAY`` second
    sleep before each.  If that fails or yields no model text, falls back to
    the free ``flight.aircraft_code`` (ICAO type code, e.g. "B737") from the
    feed list so the plane field is not left blank.

    Never raises; returns "" if nothing could be determined.
    """
    retries = FR24_DETAIL_RETRIES
    details = None
    while retries:
        try:
            details = api.get_flight_details(flight)
            break
        except (KeyError, AttributeError, TypeError, Exception) as e:
            if _CurlTimeout and isinstance(e, _CurlTimeout):
                logger.debug(
                    "FR24 flight detail timeout, retrying (%d left)",
                    retries - 1,
                )
            elif isinstance(e, (KeyError, AttributeError, TypeError)):
                pass
            else:
                logger.debug("FR24 flight detail error: %s", e)
            retries -= 1

    if details is not None:
        try:
            plane = clean_field(details["aircraft"]["model"]["text"])
            if plane:
                return plane
        except (KeyError, TypeError):
            pass

    # Details call failed or had no model text - fall back to the free ICAO
    # type code from the feed list (no extra HTTP call).
    return clean_field(getattr(flight, "aircraft_code", ""))


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

    return route


def _lookup_aircraft(mode_s: str) -> tuple[str, str]:
    """Return aircraft type and registration for *mode_s*.

    Fetches via GET /api/v1/aircraft/{hex} and returns a ``(plane,
    registration)`` tuple.  Cached by mode_s.  Returns ``("", "")`` when not
    found or on any error.  Never raises.
    """
    cached = routes_cache.get(mode_s)
    if cached is not None:
        return cached.get("plane", ""), cached.get("registration", "")

    plane = ""
    registration = ""
    try:
        resp = _session.get(f"{HEXDB_BASE}/aircraft/{mode_s.lower()}", timeout=10)
        if resp.status_code == 404:
            logger.debug("hexdb: unknown aircraft %r", mode_s)
            # Cache a blank entry so we don't keep hitting on every poll
            routes_cache.put(mode_s, {"plane": "", "registration": ""})
            return "", ""
        resp.raise_for_status()
        data = resp.json()
        plane = _parse_aircraft_type(data)
        registration = _parse_aircraft_registration(data)

    except (RequestException, ValueError, KeyError, AttributeError, TypeError) as e:
        logger.debug("hexdb aircraft lookup failed for %r: %s", mode_s, e)

    routes_cache.put(mode_s, {"plane": plane, "registration": registration})
    return plane, registration


# ---------------------------------------------------------------------------
# Public interface
# ---------------------------------------------------------------------------


def get_route(callsign: str, mode_s: str | None = None) -> RouteInfo:
    """Return a combined route + aircraft info.

    Runs up to two independent hexdb.io lookups (route by callsign, aircraft
    type + registration by mode_s) and merges the results.  Each is
    independently cached with a 24-hour TTL, so repeat calls within that
    window are free.

    If hexdb left the route OR the aircraft type blank, a single unified
    FR24 fallback is run, keyed on the aircraft **registration** (the only
    FR24 filter that works reliably).  This fills whatever is missing -
    route and/or aircraft type - from one matched flight.  If hexdb yielded
    no registration, the FR24 fallback cannot fire and the missing fields
    stay blank.  This guarantees at most one ``get_flights`` call and at
    most one ``get_flight_details`` call per invocation, so FR24 is never
    hit more than necessary.

    Returns a :class:`RouteInfo` with all fields as strings; unknown
    fields are "".  Never raises.
    """
    result = RouteInfo()

    if callsign:
        result = _lookup_route(callsign)

    if mode_s and not result.plane:
        result.plane, result.registration = _lookup_aircraft(mode_s)

    # ── Unified FR24 fallback ─────────────────────────────────────
    # Run a single FR24 lookup (keyed on registration) when hexdb left the
    # route OR the plane blank.  The clickhandler details call (rate-limited)
    # is only requested when the plane is still missing, so it is skipped
    # whenever hexdb already gave a plane (even if the route was missing and
    # we only need the free origin/destination from the feed list).
    # If there's no registration, FR24 cannot be queried - give up gracefully.
    route_missing = not result.origin and not result.destination
    plane_missing = not result.plane
    if result.registration and (route_missing or plane_missing):
        logger.debug(
            "hexdb left gaps for %r (route_missing=%s, plane_missing=%s) - "
            "trying unified FR24 fallback keyed on registration %r",
            callsign,
            route_missing,
            plane_missing,
            result.registration,
        )
        fr24 = _fr24_fallback(result.registration, want_plane=plane_missing)

        if route_missing:
            result.origin = fr24.origin
            result.origin_name = fr24.origin_name
            result.origin_municipality = fr24.origin_municipality
            result.origin_country = fr24.origin_country
            result.destination = fr24.destination
            result.destination_name = fr24.destination_name
            result.destination_municipality = fr24.destination_municipality
            result.destination_country = fr24.destination_country

        if plane_missing and fr24.plane:
            result.plane = fr24.plane
            # Cache the plane under the mode_s key too (mirrors
            # _lookup_aircraft's pattern) so subsequent polls hit cache and
            # skip FR24 entirely - even when no route was found.  Preserve
            # the registration (from hexdb) in the cache entry.
            if mode_s:
                routes_cache.put(
                    mode_s,
                    {"plane": result.plane, "registration": result.registration},
                )

    if callsign and (result.origin or result.destination):
        routes_cache.put(callsign, result.to_dict())

    return result

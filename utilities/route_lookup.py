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
municipality and country are resolved from the bundled airports.json (via
overhead_utilities.airport_info) - the same file used by the FR24 backend.

Each lookup is independently cached so a caller that only has a callsign
(overhead_tar1090) pays one request; a caller with both (overhead_osn) pays
two on the first encounter then hits cache on every subsequent poll.

Miss caching
------------
When hexdb returns 404 for a callsign, the result is cached with a 1-hour TTL
using the ``miss`` flag so the same HTTP request isn't repeated on every poll.
After 1 hour the entry expires and hexdb is retried.

When hexdb has no aircraft type for a mode_s, an empty entry is cached for
24 hours (same as a positive hit) so mode_s 404s are also not repeated.

FR24 fallback
--------------
When hexdb.io returns no origin/destination for a callsign, OR no aircraft
type for a mode_s, the lookup falls back to FlightRadar24 via the
FlightRadarAPI library.  The FR24 real-time feed (feed.js) is queried using a
**bounding box** around the aircraft's live position (built via
``api.get_bounds_by_point``), sized by the aircraft's ground speed to allow
for FR24 feed staleness.  The matching flight within that box is identified
by **callsign** - the disambiguator within the bubble.  If the callsign is
blank, the fallback cannot disambiguate and bails.

FR24 miss caching (in-memory)
------------------------------
When the FR24 fallback also finds nothing, the callsign is recorded in an
in-memory dict with a 1-hour TTL.  Subsequent polls skip the FR24 HTTP call
entirely for that callsign until the TTL expires.  This state is ephemeral
(lost on process restart) so a restart always retries FR24.

The fallback is **unified**: a single ``get_flights(bounds=...)`` call is run
at the end of :func:`get_route` after both hexdb lookups, and fills whatever
hexdb missed - route and/or aircraft type - from the one matched flight.
This guarantees at most one ``get_flights`` call and at most one
``get_flight_details`` (clickhandler) call per ``get_route`` invocation.

Aircraft type is fetched the same way as ``overhead_fr24.py``: via
``get_flight_details`` -> ``details["aircraft"]["model"]["text"]`` (the
full model name, e.g. "Boeing 737-800").  If that call fails or returns no
model text, the free ``flight.aircraft_code`` (ICAO type code, e.g.
"B737") from the feed list is used instead so the plane field is not
left blank.

The FR24 fallback code is intentionally kept here (rather than imported from
overhead_fr24.py) to keep route_lookup self-contained.
"""

import contextlib
import json
import logging
import threading
import time
from pathlib import Path

import requests
from requests.exceptions import RequestException

from utilities import routes_cache
from utilities.flight import RouteInfo
from utilities.overhead_utilities import airport_info as _bundled_airport_info, clean_field

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
# overhead_fr24.py.  Sleep only happens *between* retries (not before the
# first attempt) so a single successful call has zero added latency.
FR24_DETAIL_RETRIES = 3
FR24_DETAIL_DELAY = 1  # seconds, slept between failed attempts

# FR24 bounds-bubble sizing for the position+callsign fallback.  The bubble
# is built around the aircraft's live lat/lng and scaled by ground speed to
# allow for FR24 feed staleness: radius_m = min(CAP, max(BASELINE, speed*WINDOW)).
FR24_BOUNDS_BASELINE_M = 1000  # minimum radius (covers slow/stationary + GPS jitter)
FR24_BOUNDS_WINDOW_S = 30  # assumed FR24 feed staleness window (seconds)
FR24_BOUNDS_CAP_M = 20000  # sanity cap so a speed anomaly can't blow the box out

# TTL for miss entries - shorter than the 24-hour positive TTL so transient
# hexdb/FR24 gaps don't suppress data for too long.
HEXDB_MISS_TTL = routes_cache.CACHE_TTL_MISS   # 1 hour
FR24_MISS_TTL = routes_cache.CACHE_TTL_MISS    # 1 hour

# ---------------------------------------------------------------------------
# In-memory FR24 miss tracking
# ---------------------------------------------------------------------------
# Persistent miss entries (in routes_cache) cover hexdb misses.  FR24 misses
# are tracked in-memory only: FR24 availability can vary (rate limits,
# Cloudflare blocks) so we want retries after a process restart.

_fr24_miss: dict[str, float] = {}   # callsign -> timestamp of last FR24 miss
_fr24_miss_lock = threading.Lock()


def _is_fr24_miss(callsign: str) -> bool:
    """Return True if FR24 found nothing for *callsign* within FR24_MISS_TTL."""
    with _fr24_miss_lock:
        ts = _fr24_miss.get(callsign)
        if ts is None:
            return False
        if time.monotonic() - ts > FR24_MISS_TTL:
            del _fr24_miss[callsign]
            return False
        return True


def _record_fr24_miss(callsign: str) -> None:
    """Record that FR24 returned nothing for *callsign*."""
    with _fr24_miss_lock:
        _fr24_miss[callsign] = time.monotonic()


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
# Airport info cache (process-lifetime, keyed by ICAO)
# ---------------------------------------------------------------------------

_airport_icao_cache: dict[str, dict] = {}


def _lookup_airport_icao(icao: str) -> dict:
    """Fetch airport details from hexdb.io by ICAO code.

    Results are cached for the process lifetime.  Returns {} on any error.
    """
    icao = icao.strip().upper()
    if not icao:
        return {}

    if icao in _airport_icao_cache:
        return _airport_icao_cache[icao]

    info: dict = {}
    try:
        resp = _session.get(f"{HEXDB_BASE}/airport/icao/{icao}", timeout=10)
        if resp.status_code == 404:
            logger.debug("hexdb: unknown airport %r", icao)
            _airport_icao_cache[icao] = {}
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

    _airport_icao_cache[icao] = info
    return info


# ---------------------------------------------------------------------------
# Airport details (IATA-keyed, for name/municipality/country)
# ---------------------------------------------------------------------------


def _airport_details(iata: str) -> dict:
    """Return {name, municipality, country_name} for *iata*.

    Primary source: bundled airports.json (shared with overhead_utilities,
    loaded once into a single in-memory dict).
    Fallback: hexdb.io airport-by-IATA endpoint when not in the local file.

    Note: the hexdb fallback returns ``region_name`` as municipality (closest
    available proxy; may be a region rather than a city) and cannot supply a
    full country name, so ``country_name`` is left blank in that path.
    """
    iata = (iata or "").strip().upper()
    if not iata:
        return {}

    # Try bundled airports.json first (shared loader, no duplicate memory).
    info = _bundled_airport_info(iata)
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
            # hexdb region_name is the best available proxy for municipality
            # (e.g. "Greater London" for LHR).  It may be a region, not a city.
            "municipality": (data.get("region_name") or "").strip(),
            # hexdb only supplies a 2-letter ISO country code; we have no
            # bundled code→name mapping so we leave country_name blank to avoid
            # displaying "GB" where "United Kingdom" is expected.
            "country_name": "",
        }
    except (RequestException, ValueError, KeyError, AttributeError, TypeError):
        return {}


# ---------------------------------------------------------------------------
# Route parser
# ---------------------------------------------------------------------------


def _parse_route(route_str: str) -> tuple[str, str]:
    """Parse a hexdb route string into (origin_icao, dest_icao).

    Handles simple two-leg routes ("EGPF-LEMG") and multi-leg routes
    ("EGPF-VTSP-LEMG") by taking the first segment as origin and the last
    as destination.  Returns ("", "") for unparseable strings.
    """
    parts = [p.strip().upper() for p in route_str.split("-") if p.strip()]
    if len(parts) < 2:
        return "", ""
    return parts[0], parts[-1]


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
# Name enrichment helper
# ---------------------------------------------------------------------------


def _enrich_route_names(ri: RouteInfo) -> bool:
    """Fill blank name/municipality/country fields from airports.json / hexdb.

    Modifies *ri* in-place.  Returns True if any field was populated so the
    caller knows whether to update the persistent cache.
    """
    changed = False

    if ri.origin and not ri.origin_name:
        details = _airport_details(ri.origin)
        new_name = details.get("name", "")
        new_muni = details.get("municipality", "")
        new_country = details.get("country_name", "")
        if new_name or new_muni or new_country:
            ri.origin_name = new_name
            ri.origin_municipality = new_muni
            ri.origin_country = new_country
            changed = True

    if ri.destination and not ri.destination_name:
        details = _airport_details(ri.destination)
        new_name = details.get("name", "")
        new_muni = details.get("municipality", "")
        new_country = details.get("country_name", "")
        if new_name or new_muni or new_country:
            ri.destination_name = new_name
            ri.destination_municipality = new_muni
            ri.destination_country = new_country
            changed = True

    return changed


# ---------------------------------------------------------------------------
# Individual lookups (each with their own cache key)
# ---------------------------------------------------------------------------


def _fr24_fallback(
    callsign: str,
    lat: float | None,
    lng: float | None,
    ground_speed_mps: float | None,
    want_plane: bool = False,
) -> RouteInfo:
    """Unified FR24 fallback for route and/or aircraft details.

    Uses the FlightRadarAPI library (same as overhead_fr24.py) to query the
    FR24 real-time feed within a **bounding box** around the aircraft's live
    position.  The box is sized by ground speed to allow for FR24 feed
    staleness, and the matching flight is identified by **callsign** (the
    disambiguator within the bubble).

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
    # Can't disambiguate within the bubble without a callsign, and can't
    # build a bubble without a position.
    if not callsign or lat is None or lng is None:
        return RouteInfo()

    speed = ground_speed_mps if ground_speed_mps is not None else 0.0
    radius_m = min(
        FR24_BOUNDS_CAP_M,
        max(FR24_BOUNDS_BASELINE_M, speed * FR24_BOUNDS_WINDOW_S),
    )

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

        # Clear cookies before each fetch to avoid FR24 rate-limiting
        # on subsequent calls (stale cookies cause empty results)
        with contextlib.suppress(Exception):
            api._FlightRadar24API__client.clear_cookies()

        # Exclude ground traffic to reduce result size
        tracker = api.get_flight_tracker_config()
        tracker.gnd = 0
        api.set_flight_tracker_config(tracker)

        bounds = api.get_bounds_by_point(lat, lng, radius_m)
        flights = api.get_flights(bounds=bounds)

        for flight in flights:
            # Disambiguate within the bubble by callsign.
            flight_callsign = (getattr(flight, "callsign", "") or "").strip()
            if flight_callsign != callsign:
                continue

            origin = (flight.origin_airport_iata or "").strip()
            destination = (flight.destination_airport_iata or "").strip()

            route = RouteInfo()

            # -- Route (free from the feed list) -----------------------
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

            # -- Aircraft type (only when requested) ------------------
            # The clickhandler details call is rate-limited, so only make it
            # when the caller actually needs a plane.  Mirrors
            # overhead_fr24.py (retry loop + model text extraction).
            if want_plane:
                route.plane = _fr24_aircraft_type(api, flight)

            # -- Operating carrier ICAO (for logo lookup) --------------
            route.airline_icao = (getattr(flight, "airline_icao", "") or "").strip()

            if route.origin or route.destination or route.plane:
                logger.debug(
                    "FR24 fallback found data for %r: %s->%s plane=%r",
                    callsign,
                    route.origin,
                    route.destination,
                    route.plane,
                )
                return route

        logger.debug("FR24 fallback: no matching flight for %r", callsign)

    except Exception as e:
        logger.debug("FR24 fallback failed for %r: %s", callsign, e)

    return RouteInfo()


def _fr24_aircraft_type(api, flight) -> str:
    """Return the aircraft type string for *flight* via FR24.

    Tries the clickhandler details endpoint (``get_flight_details``) for the
    full model name (e.g. "Boeing 737-800"), mirroring overhead_fr24.py with
    up to ``FR24_DETAIL_RETRIES`` attempts.  Sleep of ``FR24_DETAIL_DELAY``
    seconds is inserted **between** retries only (not before the first attempt)
    so a successful first call has no added latency.

    If the details call fails or yields no model text, falls back to the free
    ``flight.aircraft_code`` (ICAO type code, e.g. "B737") from the feed list
    so the plane field is not left blank.

    Never raises; returns "" if nothing could be determined.
    """
    details = None
    for attempt in range(FR24_DETAIL_RETRIES):
        if attempt > 0:
            time.sleep(FR24_DETAIL_DELAY)
        try:
            details = api.get_flight_details(flight)
            break
        except Exception as e:
            if _CurlTimeout and isinstance(e, _CurlTimeout):
                logger.debug(
                    "FR24 flight detail timeout, retrying (%d left)",
                    FR24_DETAIL_RETRIES - attempt - 1,
                )
            elif not isinstance(e, (KeyError, AttributeError, TypeError)):
                logger.debug("FR24 flight detail error: %s", e)

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

    Checks the persistent route cache first:
    - Entries with ``miss=True`` (hexdb 404) are returned as empty RouteInfo
      without hitting hexdb again; the caller may still try the FR24 fallback.
    - Entries with origin/destination are returned directly; any blank name
      fields are enriched from the bundled airports.json before returning.

    On a hexdb 404, the callsign is cached with ``miss=True`` and a 1-hour
    TTL so repeated polls skip the HTTP call.

    Transient HTTP errors are not cached so the next poll retries hexdb.

    Never raises.
    """
    # 1. Persistent cache check
    cached = routes_cache.get(callsign)
    if cached is not None:
        if cached.get("miss"):
            # hexdb previously returned nothing for this callsign.
            # The caller (get_route) may still try the FR24 fallback.
            return RouteInfo()
        if cached.get("origin") or cached.get("destination"):
            ri = RouteInfo.from_dict(cached)
            # Re-enrich blank name fields.  This transparently upgrades
            # partial entries written by overhead_fr24 (which previously
            # omitted name/municipality/country) and any old cache entries.
            if _enrich_route_names(ri):
                routes_cache.put(callsign, ri.to_dict())
            return ri

    # 2. hexdb lookup
    route = RouteInfo()
    try:
        resp = _session.get(f"{HEXDB_BASE}/route/icao/{callsign}", timeout=10)
        if resp.status_code == 404:
            logger.debug("hexdb: unknown callsign %r", callsign)
            routes_cache.put(callsign, {"miss": True}, ttl=HEXDB_MISS_TTL)
            return RouteInfo()

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

        if not route.origin and not route.destination:
            # hexdb responded but the route string was empty or ICAO codes
            # couldn't be converted to IATA.  Treat as a miss.
            logger.debug("hexdb: empty/unconvertible route for %r (%r)", callsign, route_str)
            routes_cache.put(callsign, {"miss": True}, ttl=HEXDB_MISS_TTL)

    except (RequestException, ValueError, KeyError, AttributeError, TypeError) as e:
        logger.debug("hexdb route lookup failed for %r: %s", callsign, e)
        # Don't cache transient errors - retry on next poll

    return route


def _lookup_aircraft(mode_s: str) -> tuple[str, str]:
    """Return aircraft type and registration for *mode_s*.

    Fetches via GET /api/v1/aircraft/{hex} and returns a ``(plane,
    registration)`` tuple.  Cached by mode_s (24-hour TTL, including blank
    entries for hexdb 404s so 404s aren't repeated on every poll).
    Returns ``("", "")`` on any error.  Never raises.
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


def get_route(
    callsign: str,
    mode_s: str | None = None,
    lat: float | None = None,
    lng: float | None = None,
    ground_speed_mps: float | None = None,
) -> RouteInfo:
    """Return a combined route + aircraft info.

    Lookup order
    ------------
    1. Route by callsign via hexdb.io (cached; miss entries skip hexdb for 1 h).
    2. Aircraft type + registration by mode_s via hexdb.io (cached).
    3. Unified FR24 fallback when hexdb left the route **or** the plane blank
       - keyed on the aircraft's live position + callsign.
       - ``want_plane`` is only set when hexdb also returned no aircraft type,
         so the expensive ``get_flight_details`` call is skipped when only
         the route is missing.
       - If FR24 also returns nothing, the callsign is recorded in an
         in-memory miss dict (1-hour TTL) so the FR24 HTTP call is not
         repeated on every subsequent poll.

    ``lat``, ``lng`` and ``ground_speed_mps`` are optional; without them the
    FR24 fallback cannot fire.

    Returns a :class:`RouteInfo` with all fields as strings; unknown fields
    are "".  Never raises.
    """
    result = RouteInfo()

    if callsign:
        result = _lookup_route(callsign)

    if mode_s and not result.plane:
        result.plane, result.registration = _lookup_aircraft(mode_s)

    # -- Unified FR24 fallback -------------------------------------
    # Run when hexdb left the route OR the plane blank.  The FR24 miss guard
    # prevents hammering FR24 for callsigns it consistently can't find.
    route_missing = not result.origin and not result.destination
    plane_missing = not result.plane

    if (
        callsign
        and lat is not None
        and lng is not None
        and (route_missing or plane_missing)
        and not _is_fr24_miss(callsign)
    ):
        logger.debug(
            "hexdb left gaps for %r (route_missing=%s, plane_missing=%s) - "
            "trying unified FR24 fallback at lat=%s lng=%s",
            callsign,
            route_missing,
            plane_missing,
            lat,
            lng,
        )
        fr24 = _fr24_fallback(
            callsign, lat, lng, ground_speed_mps, want_plane=plane_missing
        )

        if fr24.origin or fr24.destination or fr24.plane:
            # FR24 found something - apply it
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
                # Cache the plane under the mode_s key too so subsequent polls
                # hit cache and skip FR24 entirely.  Preserve the registration
                # (from hexdb) in the cache entry.
                if mode_s:
                    routes_cache.put(
                        mode_s,
                        {"plane": result.plane, "registration": result.registration},
                    )

            if fr24.airline_icao:
                result.airline_icao = fr24.airline_icao

        else:
            # FR24 also found nothing - record a miss so we don't retry on
            # every subsequent poll until the TTL expires.
            logger.debug("FR24 fallback found nothing for %r - recording miss", callsign)
            _record_fr24_miss(callsign)

    # Persist a positive route result under the callsign key.
    # This also overwrites any stale miss entry from a previous lookup.
    if callsign and (result.origin or result.destination):
        routes_cache.put(callsign, result.to_dict())

    return result

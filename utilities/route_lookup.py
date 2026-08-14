"""
Route and aircraft lookup with multi-provider failover - shared by
overhead_tar1090 and overhead_osn.

The actual HTTP calls to lookup providers (hexdb.io, adsbdb.com,
aerodatabox.com) live in :mod:`utilities.route_providers`.  This module
wraps them with persistent caching, miss-tracking, and the FR24 fallback.

Cache layout
------------
Two kinds of entries in routes_cache.json, distinguished by key:

  callsign keys  (e.g. "BAW123")
      plane, origin, destination, origin_name, origin_municipality,
      origin_country, destination_name, destination_municipality,
      destination_country, registration, airline_icao

  mode_s keys    (e.g. "400f5a")
      plane, registration, operator_icao, owner

Both key types use a 24-hour TTL by default.  Miss entries use a 1-hour TTL.

``operator_icao`` and ``owner`` are deliberately stored **only** under the
mode_s key, never under a callsign key: they describe the airframe, not the
flight.  Caching them per-callsign would let one day's airframe decide
tomorrow's logo when a different aircraft operates the same flight number.

Miss caching
------------
When every provider returns 404 for a callsign, the result is cached with a
1-hour TTL using the ``miss`` flag so the same HTTP request isn't repeated on
every poll.  After 1 hour the entry expires and providers are retried.

When every provider has no aircraft type for a mode_s, an empty entry is
cached for 24 hours (same as a positive hit) so mode_s 404s are also not
repeated.

FR24 fallback
--------------
When all lookup providers return no origin/destination for a callsign, OR no
aircraft type for a mode_s, the lookup falls back to FlightRadar24 via the
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
at the end of :func:`get_route` after the provider lookups, and fills
whatever the providers missed - route and/or aircraft type - from the one
matched flight.  This guarantees at most one ``get_flights`` call and at most
one ``get_flight_details`` (clickhandler) call per ``get_route`` invocation.

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
import logging
import threading
import time

from utilities import route_providers, routes_cache
from utilities.flight import AircraftInfo, RouteInfo
from utilities.overhead_utilities import clean_field

logger = logging.getLogger(__name__)

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
# provider/FR24 gaps don't suppress data for too long.
PROVIDER_MISS_TTL = routes_cache.CACHE_TTL_MISS  # 1 hour
FR24_MISS_TTL = routes_cache.CACHE_TTL_MISS  # 1 hour

# ---------------------------------------------------------------------------
# In-memory FR24 miss tracking
# ---------------------------------------------------------------------------
# Persistent miss entries (in routes_cache) cover provider misses.  FR24 misses
# are tracked in-memory only: FR24 availability can vary (rate limits,
# Cloudflare blocks) so we want retries after a process restart.

_fr24_miss: dict[str, float] = {}  # callsign -> timestamp of last FR24 miss
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
# Name enrichment helper
# ---------------------------------------------------------------------------


def _enrich_route_names(ri: RouteInfo) -> bool:
    """Fill blank name/municipality/country fields from airports.json.

    Modifies *ri* in-place.  Returns True if any field was populated so the
    caller knows whether to update the persistent cache.
    """
    from utilities.overhead_utilities import airport_info as _bundled_airport_info

    changed = False

    if ri.origin and not ri.origin_name:
        details = _bundled_airport_info(ri.origin)
        new_name = details.get("name", "")
        new_muni = details.get("municipality", "")
        new_country = details.get("country_name", "")
        if new_name or new_muni or new_country:
            ri.origin_name = new_name
            ri.origin_municipality = new_muni
            ri.origin_country = new_country
            changed = True

    if ri.destination and not ri.destination_name:
        details = _bundled_airport_info(ri.destination)
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
# FR24 fallback
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
                    details = _enrich_route_names_helper(origin)
                    route.origin_name = details.get("name", "")
                    route.origin_municipality = details.get("municipality", "")
                    route.origin_country = details.get("country_name", "")

                if destination:
                    details = _enrich_route_names_helper(destination)
                    route.destination_name = details.get("name", "")
                    route.destination_municipality = details.get("municipality", "")
                    route.destination_country = details.get("country_name", "")

            # -- Aircraft type (only when requested) ------------------
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


def _enrich_route_names_helper(iata: str) -> dict:
    """Return airport details for *iata* from bundled airports.json."""
    from utilities.overhead_utilities import airport_info as _bundled_airport_info

    return _bundled_airport_info(iata) or {}


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


# ---------------------------------------------------------------------------
# Individual lookups (delegated to route_providers, with caching)
# ---------------------------------------------------------------------------


def _lookup_route(callsign: str) -> RouteInfo:
    """Return route fields for *callsign* via the provider chain.

    Checks the persistent route cache first:
    - Entries with ``miss=True`` are returned as empty RouteInfo without
      hitting providers; the caller may still try the FR24 fallback.
    - Entries with origin/destination are returned directly; any blank name
      fields are enriched from the bundled airports.json before returning.

    On a provider miss (all providers return 404), the callsign is cached
    with ``miss=True`` and a 1-hour TTL so repeated polls skip HTTP calls.

    Transient HTTP errors are not cached so the next poll retries.

    Never raises.
    """
    # 1. Persistent cache check
    cached = routes_cache.get(callsign)
    if cached is not None:
        if cached.get("miss"):
            return RouteInfo()
        if cached.get("origin") or cached.get("destination"):
            ri = RouteInfo.from_dict(cached)
            if _enrich_route_names(ri):
                routes_cache.put(callsign, ri.to_dict())
            return ri

    # 2. Provider chain lookup
    route = route_providers.lookup_route(callsign)

    if not route.origin and not route.destination:
        # All providers returned nothing.  Try the stale fallback: if we
        # have a recently-expired positive entry (within 7 days), re-cache
        # it with the timestamp advanced by 4 h and return it so the screen
        # shows real data instead of "Unknown".  Providers will be retried
        # every 4 h while they keep failing.
        stale = routes_cache.get_stale(callsign)
        if stale is not None and (stale.get("origin") or stale.get("destination")):
            ri = RouteInfo.from_dict(stale)
            if _enrich_route_names(ri):
                routes_cache.put(
                    callsign,
                    ri.to_dict(),
                    ts=stale["_ts"] + routes_cache.STALE_RECACHE_ADVANCE,
                )
            else:
                routes_cache.put(
                    callsign,
                    ri.to_dict(),
                    ts=stale["_ts"] + routes_cache.STALE_RECACHE_ADVANCE,
                )
            logger.debug(
                "Providers returned nothing for %r - reusing stale cached "
                "route (age %.1fh)",
                callsign,
                (time.time() - stale["_ts"]) / 3600,
            )
            return ri

        # No stale fallback available - cache as miss.
        routes_cache.put(callsign, {"miss": True}, ttl=PROVIDER_MISS_TTL)
        return RouteInfo()

    # Enrich blank name fields from bundled airports.json
    _enrich_route_names(route)
    return route


def _aircraft_cache_entry(info: AircraftInfo) -> dict:
    """Serialise an :class:`AircraftInfo` for the mode_s cache key."""
    return {
        "plane": info.plane,
        "registration": info.registration,
        "operator_icao": info.operator_icao,
        "owner": info.owner,
    }


def _lookup_aircraft(mode_s: str) -> AircraftInfo:
    """Return aircraft info for *mode_s* via the provider chain.

    Fetches via the provider chain and returns an :class:`AircraftInfo`
    carrying the aircraft type, registration, and the airframe's registered
    operator ICAO code.  Cached by mode_s (24-hour TTL, including blank
    entries for 404s so they aren't repeated on every poll).

    Cache entries written before ``operator_icao`` existed simply have no
    such key; ``.get()`` yields ``""`` and the entry refreshes naturally
    when its 24-hour TTL expires.

    Returns an empty ``AircraftInfo`` on any error.  Never raises.
    """
    cached = routes_cache.get(mode_s)
    if cached is not None:
        return AircraftInfo(
            plane=cached.get("plane", ""),
            registration=cached.get("registration", ""),
            operator_icao=cached.get("operator_icao", ""),
            owner=cached.get("owner", ""),
        )

    info = route_providers.lookup_aircraft(mode_s)

    if not info.plane and not info.registration:
        # Providers returned nothing.  Try the stale fallback: if we have a
        # recently-expired entry (within 7 days), re-cache it with the
        # timestamp advanced by 4 h and return it so the screen shows real
        # data instead of blank aircraft info.
        stale = routes_cache.get_stale(mode_s)
        if stale is not None and (stale.get("plane") or stale.get("registration")):
            stale_info = AircraftInfo(
                plane=stale.get("plane", ""),
                registration=stale.get("registration", ""),
                # A freshly-resolved identity beats a stale one.
                operator_icao=info.operator_icao or stale.get("operator_icao", ""),
                owner=info.owner or stale.get("owner", ""),
            )
            routes_cache.put(
                mode_s,
                _aircraft_cache_entry(stale_info),
                ts=stale["_ts"] + routes_cache.STALE_RECACHE_ADVANCE,
            )
            logger.debug(
                "Providers returned nothing for mode_s %r - reusing stale "
                "aircraft info (age %.1fh)",
                mode_s,
                (time.time() - stale["_ts"]) / 3600,
            )
            return stale_info

    routes_cache.put(mode_s, _aircraft_cache_entry(info))
    return info


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
    1. Route by callsign via provider chain (hexdb -> adsbdb -> aerodatabox).
       Cached; miss entries skip providers for 1 h.
    2. Aircraft type, registration, and registered-operator ICAO code by
       mode_s via provider chain (cached).  This runs whenever the plane
       **or** the airline is still unknown, because the mode_s lookup is the
       only per-airframe signal available: it resolves ICAO designator
       collisions that a callsign prefix cannot.
    3. Unified FR24 fallback when providers left the route **or** the plane
       blank - keyed on the aircraft's live position + callsign.
       - ``want_plane`` is only set when providers also returned no aircraft
         type, so the expensive ``get_flight_details`` call is skipped when
         only the route is missing.
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

    # The mode_s lookup fills two independent gaps: the aircraft type, and the
    # airframe's registered operator (used for logo resolution when no
    # flight-level airline_icao is available).  Run it when either is missing.
    if mode_s and (not result.plane or not result.airline_icao):
        aircraft = _lookup_aircraft(mode_s)
        if not result.plane:
            result.plane = aircraft.plane
        if not result.registration:
            result.registration = aircraft.registration
        result.operator_icao = aircraft.operator_icao
        result.owner = aircraft.owner

    # -- Unified FR24 fallback -------------------------------------
    # Run when providers left the route OR the plane blank.  The FR24 miss
    # guard prevents hammering FR24 for callsigns it consistently can't find.
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
            "Providers left gaps for %r (route_missing=%s, plane_missing=%s) - "
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
                # (from providers) in the cache entry.
                if mode_s:
                    routes_cache.put(
                        mode_s,
                        _aircraft_cache_entry(
                            AircraftInfo(
                                plane=result.plane,
                                registration=result.registration,
                                operator_icao=result.operator_icao,
                                owner=result.owner,
                            )
                        ),
                    )

            if fr24.airline_icao:
                result.airline_icao = fr24.airline_icao

        else:
            # FR24 also found nothing - record a miss so we don't retry on
            # every subsequent poll until the TTL expires.
            logger.debug(
                "FR24 fallback found nothing for %r - recording miss", callsign
            )
            _record_fr24_miss(callsign)

    # Persist a positive route result under the callsign key.
    # This also overwrites any stale miss entry from a previous lookup.
    #
    # operator_icao and owner are stripped: they belong to the airframe
    # (mode_s key), not the flight.  Storing them here would pin the logo to
    # whichever aircraft happened to fly this callsign first.
    if callsign and (result.origin or result.destination):
        entry = result.to_dict()
        entry.pop("operator_icao", None)
        entry.pop("owner", None)
        routes_cache.put(callsign, entry)

    return result

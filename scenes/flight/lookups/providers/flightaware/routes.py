"""FlightAware AeroAPI route lookup (optional paid-tier provider).

Resolves a callsign or aircraft registration to its origin/destination
airports via AeroAPI v4's flights-by-ident endpoint.  Requests are billed
per result set, so this provider makes exactly one call per lookup: the
endpoint answers with a single page of recent flights (roughly the past
11 days through 2 days ahead) by default.

The endpoint accepts an ident, a registration, or an fa_flight_id.  The
documented ``ident_type`` parameter disambiguates which kind was passed:
it is sent explicitly when the ident is recognisably a callsign
(``designator``) or a tail number (``registration``), and omitted
otherwise so the API applies its default interpretation.  Only documented
parameters are ever sent - AeroAPI rejects unknown query arguments with a
400 ("Invalid argument 'max_results' supplied", #101).

An unknown ident is signalled by a 200 response with an empty ``flights``
list, not a 404; flights without route data (position-only records) are
skipped.  A 400 means the request itself was unparseable - an unsupported
parameter or malformed ident - not that the provider is failing: the
response body is logged and the lookup reads as not-found so the pipeline
walks to the next provider (#101).  Auth and quota problems
(401/403/429) still read as UNAVAILABLE so the provider is held off
rather than treated as a dead callsign.
"""

from __future__ import annotations

import logging
import re
import urllib.parse

import requests
from requests.exceptions import RequestException

from scenes.flight.lookups.providers.common.airports import (
    fill_airport_details,
    icao_to_iata_code,
)
from scenes.flight.lookups.results import LookupResult, RouteInfo

logger = logging.getLogger(__name__)

BASE = "https://aeroapi.flightaware.com/aeroapi"

# Request timeout (seconds).
PROVIDER_TIMEOUT = 10

# ICAO operator code + flight number (e.g. AAY430, UAL4, RYR215K).
_DESIGNATOR_RE = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9]{0,3}$")
# US registration (N40726) or hyphenated registration (G-XWBA, VH-XYZ).
_REGISTRATION_RE = re.compile(r"^(N[0-9]{1,5}[A-Z]{0,3}|[A-Z0-9]{1,2}-[A-Z]{1,4})$")


def _ident_type(callsign: str) -> str | None:
    """Pick the documented ident_type for *callsign*, or None.

    None lets AeroAPI apply its default interpretation, which handles
    anything ambiguous (IATA-style idents, hex addresses, unknown
    shapes).  Sending a wrong explicit type is worse than omitting it.
    """
    if _DESIGNATOR_RE.match(callsign):
        return "designator"
    if _REGISTRATION_RE.match(callsign):
        return "registration"
    return None


def _error_detail(resp) -> str:
    """Extract a message from an AeroAPI error body ({title, reason, detail})."""
    try:
        body = resp.json() or {}
    except ValueError:
        return (resp.text or "").strip()[:200]
    if isinstance(body, dict):
        return str(body.get("detail") or body.get("title") or body)[:200]
    return str(body)[:200]


class RouteProvider:
    """FlightAware AeroAPI route capability (requires an API key)."""

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}
        self.api_key = (self._settings.get("api_key") or "").strip()

    def lookup_route(self, ctx) -> LookupResult:
        callsign = (ctx.callsign or "").strip()
        if not callsign:
            return LookupResult.not_found("no callsign")
        if not self.api_key:
            return LookupResult.unavailable("aeroapi key not configured")

        try:
            resp = self._fetch(callsign, ident_type=_ident_type(callsign))
        except (RequestException, OSError) as e:
            logger.debug("aeroapi route lookup failed for %r: %s", callsign, e)
            return LookupResult.unavailable(f"aeroapi unreachable: {e}")

        # Auth and quota problems must read as UNAVAILABLE so the provider
        # is held off rather than treated as a dead callsign.
        if resp.status_code in (401, 403, 429):
            return LookupResult.unavailable(
                f"aeroapi rejected the request (HTTP {resp.status_code})"
            )
        if resp.status_code == 404:
            logger.debug("aeroapi: unknown flight %r", callsign)
            return LookupResult.not_found("aeroapi has no flight for this callsign")
        if resp.status_code == 400:
            # AeroAPI 400s when the request itself is unparseable - an
            # unsupported query parameter or a malformed ident.  That is a
            # mis-shaped request, not a provider failure: log the body (it
            # names the offending argument) and read as not-found so the
            # pipeline walks to the next provider.  (#101)
            logger.debug(
                "aeroapi rejected the request for %r (HTTP 400): %s",
                callsign,
                _error_detail(resp),
            )
            return LookupResult.not_found("aeroapi: invalid request")
        if resp.status_code >= 400:
            return LookupResult.unavailable(f"aeroapi HTTP {resp.status_code}")

        try:
            flights = (resp.json() or {}).get("flights") or []
        except ValueError as e:
            logger.debug("aeroapi response unparseable: %s", e)
            return LookupResult.unavailable(f"aeroapi returned a bad response: {e}")

        for flight in flights:
            route = _flight_to_route(flight)
            if route is not None:
                return LookupResult.found(route)
        return LookupResult.not_found("aeroapi flight has no route")

    def ping(self) -> bool:
        """Cheap reachability probe (status-agnostic) for the startup screen."""
        try:
            resp = requests.get(BASE, params={"max_pages": 1}, timeout=5)
            return resp is not None
        except Exception:
            return False

    def _fetch(self, ident: str, ident_type: str | None = None):
        """Call the flights-by-ident endpoint for *ident* (single page)."""
        params = {"ident_type": ident_type} if ident_type else {}
        return requests.get(
            f"{BASE}/flights/{urllib.parse.quote(ident, safe='')}",
            params=params,
            headers={"x-apikey": self.api_key},
            timeout=PROVIDER_TIMEOUT,
        )


def _flight_to_route(flight: dict) -> RouteInfo | None:
    """Build a RouteInfo from one AeroAPI flight object, or None.

    AeroAPI answers with ICAO-coded airports; the bundled ICAO->IATA
    table restores the display format (falling back to the raw code).
    The lookup walks the returned flights until one carries both ends -
    flights without an origin/destination (position-only records like
    N40726's) are skipped.
    """
    origin_code = (flight.get("origin") or {}).get("code", "")
    destination_code = (flight.get("destination") or {}).get("code", "")
    if not origin_code or not destination_code:
        return None

    route = RouteInfo()
    route.origin = icao_to_iata_code(origin_code) or origin_code
    route.destination = icao_to_iata_code(destination_code) or destination_code
    fill_airport_details(route, "origin")
    fill_airport_details(route, "destination")
    return route

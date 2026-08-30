"""FlightAware AeroAPI route lookup (optional paid-tier provider).

Resolves a callsign to its origin/destination airports via AeroAPI v4's
flights-by-ident endpoint.  Requests are billed per result set, so this
provider is best suited to per-new-callsign lookups (the lookup caches
suppress repeats) rather than position polling.
"""

from __future__ import annotations

import logging

import requests
from requests.exceptions import RequestException

from lookups.providers.common.airports import fill_airport_details, icao_to_iata_code
from lookups.results import LookupResult, RouteInfo

logger = logging.getLogger(__name__)

BASE = "https://aeroapi.flightaware.com/aeroapi"

# Request timeout (seconds).
PROVIDER_TIMEOUT = 10


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
            resp = requests.get(
                f"{BASE}/flights/{callsign}",
                params={"max_results": 5},
                headers={"x-apikey": self.api_key},
                timeout=PROVIDER_TIMEOUT,
            )
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
            # AeroAPI 400s when the ident isn't in fa_flight_id format - the
            # request was mis-shaped for this endpoint, not the provider
            # failing.  Treat it as a valid "no answer" and let the
            # pipeline walk to the next provider.
            logger.debug(
                "aeroapi rejected ident %r (HTTP 400) - treating as not found",
                callsign,
            )
            return LookupResult.not_found(
                "aeroapi: ident is not in fa_flight_id format"
            )
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


def _flight_to_route(flight: dict) -> RouteInfo | None:
    """Build a RouteInfo from one AeroAPI flight object, or None.

    AeroAPI answers with ICAO-coded airports; the bundled ICAO->IATA
    table restores the display format (falling back to the raw code).
    The lookup walks the returned flights until one carries both ends.
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

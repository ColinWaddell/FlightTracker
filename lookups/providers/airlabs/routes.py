"""AirLabs route lookup (requires a free API key).

Resolves a callsign to its scheduled airport pair via the AirLabs
routes database (``/v9/routes``).  AirLabs' data is schedule-based -
one flight number can map to several airport pairs across the season -
so it belongs late in the route chain.

The free plan covers 1,000 lookups per month; an API key from
airlabs.co is required.
"""

from __future__ import annotations

import logging

import requests
from requests.exceptions import RequestException

from lookups.results import LookupResult, RouteInfo
from utilities.overhead_utilities import clean_field

logger = logging.getLogger(__name__)

BASE = "https://airlabs.co/api/v9"
PROVIDER_TIMEOUT = 10


class RouteProvider:
    """AirLabs route capability (requires an AirLabs API key)."""

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}
        self.api_key = (self._settings.get("api_key") or "").strip()

    def lookup_route(self, ctx) -> LookupResult:
        callsign = (ctx.callsign or "").strip()
        if not callsign:
            return LookupResult.not_found("no callsign")
        if not self.api_key:
            return LookupResult.unavailable("airlabs API key not configured")

        try:
            resp = requests.get(
                f"{BASE}/routes",
                params={"api_key": self.api_key, "flight_icao": callsign},
                timeout=PROVIDER_TIMEOUT,
            )
        except (RequestException, OSError) as e:
            logger.debug("airlabs route lookup failed for %r: %s", callsign, e)
            return LookupResult.unavailable(f"airlabs unreachable: {e}")

        # Quota/auth problems must translate to UNAVAILABLE so the
        # provider is held off rather than treated as a dead callsign.
        if resp.status_code in (401, 403, 429):
            return LookupResult.unavailable(
                f"airlabs rejected the request (HTTP {resp.status_code})"
            )
        if resp.status_code in (400, 404):
            # A rejected/unknown ident is "no answer" for this query, not a
            # provider failure - must not quarantine.  (#101 family)
            logger.debug(
                "airlabs: no route for %r (HTTP %d)", callsign, resp.status_code
            )
            return LookupResult.not_found("airlabs has no answer for this callsign")
        if resp.status_code >= 400:
            return LookupResult.unavailable(f"airlabs HTTP {resp.status_code}")
        try:
            rows = (resp.json() or {}).get("response") or []
        except ValueError as e:
            return LookupResult.unavailable(f"airlabs returned a bad response: {e}")

        for row in rows:
            route = _row_to_route(row)
            if route is not None:
                return LookupResult.found(route)
        return LookupResult.not_found("airlabs has no usable route for this callsign")

    def ping(self) -> bool:
        """Cheap reachability probe (status-agnostic)."""
        try:
            requests.head("https://airlabs.co", timeout=5)
            return True
        except Exception:
            return False


def _row_to_route(row: dict) -> RouteInfo | None:
    """Build a RouteInfo from an AirLabs row; None when it lacks airports."""
    from lookups.providers.common.airports import fill_airport_details

    origin = (row.get("dep_iata") or row.get("dep_icao") or "").strip()
    destination = (row.get("arr_iata") or row.get("arr_icao") or "").strip()
    if not origin and not destination:
        return None

    route = RouteInfo()
    route.origin = origin
    route.destination = destination
    route.airline_icao = clean_field(row.get("airline_icao"))
    fill_airport_details(route, "origin")
    fill_airport_details(route, "destination")
    return route

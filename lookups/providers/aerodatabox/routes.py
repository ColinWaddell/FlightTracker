"""AeroDataBox route lookup (RapidAPI, key required).

Queries the AeroDataBox flight-by-callsign endpoint.  RapidAPI quota
exhaustion is common on free tiers, so it is detected explicitly - via the
HTTP status (429/403) and via 200-with-error-body gateway responses - and
reported as ``UNAVAILABLE`` so the service layer quarantines the provider
instead of burning the remaining quota on every aircraft.
"""

from __future__ import annotations

import logging

from lookups.providers.aerodatabox.client import (
    RATE_LIMIT_CODES,
    aerodatabox_get,
    is_error_response,
)
from lookups.results import LookupResult, RouteInfo

logger = logging.getLogger(__name__)


class RouteProvider:
    """AeroDataBox route capability (requires a RapidAPI key)."""

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}
        self.api_key = (self._settings.get("api_key") or "").strip()

    def ping(self) -> bool:
        """Cheap reachability probe for the startup screen (checks quota)."""
        if not self.api_key:
            return False
        try:
            from lookups.providers.aerodatabox.client import aerodatabox_get

            resp, _ = aerodatabox_get("/subscriptions/balance", self.api_key, timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def lookup_route(self, ctx) -> LookupResult:
        callsign = (ctx.callsign or "").strip()
        if not callsign:
            return LookupResult.not_found("no callsign")
        if not self.api_key:
            return LookupResult.unavailable("aerodatabox API key not configured")

        try:
            resp, data = aerodatabox_get(
                f"/flights/callsign/{callsign}", self.api_key
            )
        except Exception as e:
            logger.debug("aerodatabox route lookup failed for %r: %s", callsign, e)
            return LookupResult.unavailable(f"aerodatabox unreachable: {e}")

        if resp.status_code == 404:
            logger.debug("aerodatabox: unknown callsign %r", callsign)
            return LookupResult.not_found("aerodatabox has no route for this callsign")

        if resp.status_code in RATE_LIMIT_CODES:
            logger.warning(
                "aerodatabox: rate limit / quota exceeded (HTTP %d) for %r",
                resp.status_code,
                callsign,
            )
            return LookupResult.unavailable(
                f"aerodatabox rate limited (HTTP {resp.status_code})"
            )

        if resp.status_code >= 400:
            return LookupResult.unavailable(
                f"aerodatabox HTTP {resp.status_code}"
            )

        # Some gateways return HTTP 200 with an error body when
        # rate-limited (e.g. {"message": "You exceeded your monthly quota"}).
        # Detect this and report UNAVAILABLE rather than treating it as a
        # genuine miss (which would poison the miss cache).
        if is_error_response(data):
            msg = ""
            if isinstance(data, dict):
                for k in ERROR_BODY_KEYS:
                    if k in data:
                        msg = str(data[k])[:200]
                        break
            logger.warning("aerodatabox: error response for %r (%s)", callsign, msg)
            return LookupResult.unavailable(f"aerodatabox error response: {msg}")

        flights = data if isinstance(data, list) else [data]
        if not flights:
            return LookupResult.not_found("aerodatabox returned no flights")

        route = parse_route(flights[0])
        if route is None or not (route.origin or route.destination):
            return LookupResult.not_found("aerodatabox flight has no route")

        return LookupResult.found(route)


# ---------------------------------------------------------------------------
# Parsing helpers (module-level so tests can exercise them directly)
# ---------------------------------------------------------------------------

# Body keys that signal an error response rather than flight data.
ERROR_BODY_KEYS = frozenset({"message", "error", "errors"})


def parse_route(flight: dict) -> RouteInfo | None:
    """Build a RouteInfo from an AeroDataBox flight object."""
    route = RouteInfo()

    dep = flight.get("departure", {}) or {}
    arr = flight.get("arrival", {}) or {}

    if dep:
        airport = dep.get("airport", {}) or {}
        iata = (airport.get("iata") or "").strip()
        icao = (airport.get("icao") or "").strip()
        route.origin = iata or icao
        _fill_airport_details(route, "origin")

    if arr:
        airport = arr.get("airport", {}) or {}
        iata = (airport.get("iata") or "").strip()
        icao = (airport.get("icao") or "").strip()
        route.destination = iata or icao
        _fill_airport_details(route, "destination")

    airline = flight.get("airline", {}) or {}
    route.airline_icao = (airline.get("icao") or "").strip()

    return route


def _fill_airport_details(route: RouteInfo, which: str) -> None:
    """Populate name/municipality/country from the bundled airports.json.

    The bundled airports database is the single source of truth for
    airport location fields; provider-supplied names are ignored.
    """
    code = getattr(route, which, "")
    if not code:
        return
    from utilities.overhead_utilities import airport_info as bundled

    details = bundled(code) or {}
    if which == "origin":
        route.origin_name = details.get("name", "")
        route.origin_municipality = details.get("municipality", "")
        route.origin_country = details.get("country_name", "")
    else:
        route.destination_name = details.get("name", "")
        route.destination_municipality = details.get("municipality", "")
        route.destination_country = details.get("country_name", "")

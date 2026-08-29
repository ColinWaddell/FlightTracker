"""adsbdb.com route lookup (origin/destination by callsign)."""

from __future__ import annotations

import logging

import requests
from requests.exceptions import RequestException

from lookups.providers.common.operators import clean_operator_code
from lookups.results import LookupResult, RouteInfo
from utilities.overhead_utilities import airport_info as bundled_airport_info

logger = logging.getLogger(__name__)

BASE = "https://api.adsbdb.com/v0"

# Request timeout (seconds).
PROVIDER_TIMEOUT = 10


def _get(url: str, timeout: int = PROVIDER_TIMEOUT):
    """GET *url* with the provider timeout.  Raises on connection errors."""
    return requests.get(url, timeout=timeout)


class RouteProvider:
    """adsbdb.com - free, no API key.

    ``GET {BASE}/callsign/{callsign}`` answers with
    ``{"response": {"flightroute": {...origin, destination, airline...}}}``;
    unknown callsigns come back as ``{"response": "unknown callsign"}``
    without a ``flightroute`` key.
    """

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}

    def ping(self) -> bool:
        """Cheap reachability probe (status-agnostic) for the startup screen."""
        try:
            resp = _get(f"{BASE}/aircraft/random", timeout=5)
            return resp is not None
        except Exception:
            return False

    def lookup_route(self, ctx) -> LookupResult:
        callsign = (ctx.callsign or "").strip()
        if not callsign:
            return LookupResult.not_found("no callsign")

        try:
            resp = _get(f"{BASE}/callsign/{callsign}")
        except (RequestException, OSError) as e:
            logger.debug("adsbdb route lookup failed for %r: %s", callsign, e)
            return LookupResult.unavailable(f"adsbdb unreachable: {e}")

        if resp.status_code == 404:
            logger.debug("adsbdb: unknown callsign %r", callsign)
            return LookupResult.not_found("adsbdb has no route for this callsign")
        try:
            resp.raise_for_status()
            data = resp.json()
        except (RequestException, ValueError) as e:
            logger.debug("adsbdb route lookup failed for %r: %s", callsign, e)
            return LookupResult.unavailable(f"adsbdb returned a bad response: {e}")

        route = parse_route(data)
        if route is None:
            return LookupResult.not_found("adsbdb has no flightroute")

        if route.origin or route.destination:
            return LookupResult.found(route)
        return LookupResult.not_found("adsbdb flightroute has no airports")


# ---------------------------------------------------------------------------
# Response parsing (module-level so tests can exercise them directly)
# ---------------------------------------------------------------------------


def parse_route(data: dict) -> RouteInfo | None:
    """Build a RouteInfo from an adsbdb callsign response.

    Returns None when the response carries no usable flightroute.
    """
    fr = (data.get("response") or {}).get("flightroute") or {}
    if not fr:
        return None

    route = RouteInfo()
    origin = fr.get("origin", {}) or {}
    dest = fr.get("destination", {}) or {}

    if origin:
        # Prefer IATA; fall back to ICAO.
        route.origin = (
            origin.get("iata_code") or origin.get("icao_code") or ""
        ).strip()
        _fill_airport_details(route, "origin")
    if dest:
        route.destination = (dest.get("iata_code") or dest.get("icao_code") or "").strip()
        _fill_airport_details(route, "destination")

    # Airline ICAO from the airline block
    airline = fr.get("airline", {}) or {}
    route.airline_icao = (airline.get("icao") or "").strip()

    return route


def _fill_airport_details(route: RouteInfo, which: str) -> None:
    """Populate name/municipality/country for one end of *route*.

    The bundled airports.json is the single source of truth for airport
    location fields (the provider API's own names are ignored, matching
    the historical behaviour).
    """
    code = getattr(route, which, "") or ""
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
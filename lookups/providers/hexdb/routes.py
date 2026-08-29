"""HexDB route lookup (origin/destination by callsign).

Queries the free hexdb.io database for an aircraft's scheduled route given
its callsign.  hexdb answers with an airport-pair string (``"EGPH-EGLL"``
or the longer ``" Callsign - ORIG - DEST"`` style), using ICAO identifiers;
they are converted to the IATA codes the display expects using the bundled
airport table, with airport names/municipalities enriched from the bundled
airports database.
"""

from __future__ import annotations

import logging

import requests
from requests.exceptions import RequestException

from lookups.providers.common.airports import icao_to_iata_code
from lookups.providers.common.operators import clean_operator_code
from lookups.results import LookupResult, RouteInfo
from utilities.overhead_utilities import airport_info as bundled_airport_info

logger = logging.getLogger(__name__)

BASE = "https://hexdb.io/api/v1"

# Request timeout (seconds).
PROVIDER_TIMEOUT = 10


def _get(url: str, timeout: int = PROVIDER_TIMEOUT):
    """GET *url* with the provider timeout.  Raises on connection errors."""
    return requests.get(url, timeout=timeout)


class RouteProvider:
    """hexdb.io - free, no API key.  The legacy default route provider."""

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}

    def ping(self) -> bool:
        """Cheap reachability probe (status-agnostic) for the startup screen."""
        try:
            resp = _get("https://hexdb.io", timeout=5)
            return resp is not None
        except Exception:
            return False

    def lookup_route(self, ctx) -> LookupResult:
        callsign = (ctx.callsign or "").strip()
        if not callsign:
            return LookupResult.not_found("no callsign")

        try:
            resp = _get(f"{BASE}/route/icao/{callsign}")
        except (RequestException, OSError) as e:
            logger.debug("hexdb route lookup failed for %r: %s", callsign, e)
            return LookupResult.unavailable(f"hexdb unreachable: {e}")

        if resp.status_code == 404:
            logger.debug("hexdb: no route for callsign %r", callsign)
            return LookupResult.not_found("hexdb has no route for this callsign")
        try:
            resp.raise_for_status()
            data = resp.json()
        except (RequestException, ValueError) as e:
            logger.debug("hexdb route lookup failed for %r: %s", callsign, e)
            return LookupResult.unavailable(f"hexdb returned a bad response: {e}")

        route_str = data.get("route", "") or ""
        origin_icao, dest_icao = parse_route(route_str)
        if not origin_icao or not dest_icao:
            logger.debug(
                "hexdb: empty/unparseable route for %r (%r)", callsign, route_str
            )
            return LookupResult.not_found("hexdb has no usable route")

        origin_iata = icao_to_iata_code(origin_icao)
        dest_iata = icao_to_iata_code(dest_icao)

        if not origin_iata and not dest_iata:
            logger.debug(
                "hexdb: route ICAO codes unconvertible for %r (%r)",
                callsign,
                route_str,
            )
            return LookupResult.not_found("route ICAO codes unconvertible")

        route = RouteInfo()
        if origin_iata:
            route.origin = origin_iata
            _fill_airport_details(route, "origin", origin_iata)
        if dest_iata:
            route.destination = dest_iata
            _fill_airport_details(route, "destination", dest_iata)

        return LookupResult.found(route)


# ---------------------------------------------------------------------------
# Parsing helpers (kept module-level so tests can exercise them directly)
# ---------------------------------------------------------------------------


def parse_route(route_str: str) -> tuple[str, str]:
    """Parse a hexdb route string into ``(origin_icao, dest_icao)``.

    hexdb returns airport pairs like ``"EGPH-EGLL"``.  Longer strings
    (a callsign followed by the pair) take the first and last elements.
    """
    parts = [p.strip().upper() for p in (route_str or "").split("-") if p.strip()]
    if len(parts) < 2:
        return "", ""
    return parts[0], parts[-1]


def parse_aircraft_type(data: dict) -> str:
    """Build a 'Manufacturer Type' string from a hexdb aircraft response."""
    manufacturer = (data.get("Manufacturer") or "").strip()
    type_code = (data.get("ICAOTypeCode") or "").strip()
    if manufacturer and type_code:
        return f"{manufacturer} {type_code}"
    return type_code or manufacturer


def parse_registration(data: dict) -> str:
    return (data.get("Registration") or "").strip()


def parse_operator_icao(data: dict) -> str:
    """Return the registered operator's ICAO code from a hexdb response.

    hexdb exposes this as ``OperatorFlagCode`` - for airline aircraft this
    is the 3-letter ICAO airline designator (e.g. ``EIN``, ``BAW``).
    """
    return clean_operator_code(data.get("OperatorFlagCode"))


def parse_owner(data: dict) -> str:
    return (data.get("RegisteredOwners") or "").strip()


def _fill_airport_details(route: RouteInfo, which: str, iata: str) -> None:
    """Populate name/municipality/country for one end of *route*.

    *which* is ``"origin"`` or ``"destination"``; the airport's location
    fields are enriched from the bundled airports database, keyed by the
    IATA code stored on the route.
    """
    if not iata:
        return
    details = bundled_airport_info(icao) or {}
    if which == "origin":
        route.origin_name = details.get("name", "")
        route.origin_municipality = details.get("municipality", "")
        route.origin_country = details.get("country_name", "")
    else:
        route.destination_name = details.get("name", "")
        route.destination_municipality = details.get("municipality", "")
        route.destination_country = details.get("country_name", "")
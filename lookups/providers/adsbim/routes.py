"""ADSB.im community route lookup (the standing-data service tar1090 uses).

POSTs the aircraft's callsign + live position to the adsb.im route
service, which answers with candidate airport pairs weighed against the
aircraft's movement (a ``plausible`` flag) plus the operating airline's
ICAO code and flight number.  Free, no key required.  IATA codes are
preferred for display; the service's ICAO pair is the fallback.
"""

from __future__ import annotations

import logging

import requests
from requests.exceptions import RequestException

from lookups.providers.common.airports import (
    fill_airport_details,
    icao_to_iata_code,
)
from lookups.results import LookupResult, RouteInfo

logger = logging.getLogger(__name__)

ROUTESET_URL = "https://adsb.im/api/0/routeset"

# Request timeout (seconds).
PROVIDER_TIMEOUT = 10


def _pair_codes(codes: str) -> tuple[str, str]:
    """Split a "XXX-YYY" airport-pair string; ("", "") when unparseable."""
    parts = [part.strip().upper() for part in (codes or "").split("-") if part.strip()]
    if len(parts) != 2:
        return "", ""
    return parts[0], parts[1]


class RouteProvider:
    """adsb.im community route lookup (requires callsign + live position)."""

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}

    def lookup_route(self, ctx) -> LookupResult:
        callsign = (ctx.callsign or "").strip()
        if not callsign:
            return LookupResult.not_found("no callsign")
        if ctx.lat is None or ctx.lng is None:
            # The service weighs routes against the aircraft's movement,
            # so it cannot answer without a position.
            return LookupResult.not_found("no position for adsb.im route")

        try:
            resp = requests.post(
                ROUTESET_URL,
                json={"planes": [{"callsign": callsign, "lat": ctx.lat, "lng": ctx.lng}]},
                timeout=PROVIDER_TIMEOUT,
            )
        except (RequestException, OSError) as e:
            logger.debug("adsb.im route lookup failed for %r: %s", callsign, e)
            return LookupResult.unavailable(f"adsb.im unreachable: {e}")

        if resp.status_code != 200:
            return LookupResult.unavailable(f"adsb.im HTTP {resp.status_code}")
        try:
            entries = resp.json()
        except ValueError as e:
            logger.debug("adsb.im route response unparseable: %s", e)
            return LookupResult.unavailable(f"adsb.im returned a bad response: {e}")

        entry = _match_entry(entries, callsign)
        route = _entry_to_route(entry) if entry else None
        if route is None:
            return LookupResult.not_found("adsb.im has no plausible route")

        return LookupResult.found(route)


def _match_entry(entries, callsign):
    """The routeset entry for *callsign* (the request lists one plane)."""
    for entry in entries:
        if (entry.get("callsign") or "").strip().upper() == callsign.upper():
            return entry
    return entries[0] if entries else None


def _entry_to_route(entry: dict) -> RouteInfo | None:
    """Build a RouteInfo from one routeset entry, or None when unusable.

    Routes the service marks "unknown" or not ``plausible`` count as
    no-data: an implausible pair would confidently draw the wrong line.
    IATA codes are preferred (the display format), with the ICAO pair
    converted via the bundled airport table as fallback.
    """
    codes = (entry.get("airport_codes") or "").strip()
    if not codes or codes.lower() == "unknown":
        return None
    if entry.get("plausible") is False:
        return None

    icao_origin, icao_dest = _pair_codes(entry.get("airport_codes", ""))
    iata_origin, iata_dest = _pair_codes(entry.get("_airport_codes_iata", ""))

    route = RouteInfo()
    route.origin = iata_origin or icao_to_iata_code(icao_origin)
    route.destination = iata_dest or icao_to_iata_code(icao_dest)
    route.airline_icao = (entry.get("airline_code") or "").strip()

    if not route.origin and not route.destination:
        return None

    fill_airport_details(route, "origin")
    fill_airport_details(route, "destination")
    return route

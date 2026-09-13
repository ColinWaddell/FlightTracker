"""FlightRadar24 route lookup via the live feed (position bubble + callsign).

The FR24 real-time feed list includes origin/destination IATA codes and the
airline ICAO code for free, so a single ``get_flights`` call inside a bubble
around the aircraft's live position is enough to resolve routing for
aircraft that other providers missed.  The bubble is sized by the
aircraft's ground speed to allow for feed staleness, and the match is
identified by callsign (the disambiguator within the bubble).

Lookups require a live position; without one the provider answers
``NOT_FOUND`` rather than pretending to have no data.
"""

from __future__ import annotations

import logging

from utilities.lookups.providers.common.airports import (
    fill_airport_details,
    icao_to_iata_code,
)
from utilities.lookups.providers.fr24.client import get_client
from utilities.lookups.results import LookupResult, RouteInfo

logger = logging.getLogger(__name__)

# FR24 fills the IATA slot with a "QQQ" placeholder when an airport has no
# IATA code (e.g. Indianapolis Regional, KMQJ).  Treat it as "no IATA data":
# fall back to the ICAO side of FR24's flight details, or blank the slot so
# the display falls back to ``journey_blank_filler``.
Q_FILLER = "QQQ"


class RouteProvider:
    """FR24 route capability: live-position bubble lookup keyed by callsign."""

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}

    def lookup_route(self, ctx) -> LookupResult:
        callsign = (ctx.callsign or "").strip()
        if not callsign or ctx.lat is None or ctx.lng is None:
            return LookupResult.not_found("no callsign/position for FR24 route")

        client = get_client()
        if client.recently_missed(callsign):
            return LookupResult.not_found("recent FR24 live-feed miss")

        try:
            flight = client.match_in_bubble(
                callsign, ctx.lat, ctx.lng, ctx.ground_speed_mps
            )
        except Exception as e:
            logger.warning("FR24 route lookup failed for %r: %s", callsign, e)
            return LookupResult.unavailable(f"FR24 feed unavailable: {e}")

        if flight is None:
            # The feed answered but has no such flight near this position
            # right now - a live-data miss, memoised to avoid hammering the
            # feed on every poll.
            client.record_feed_miss(callsign)
            return LookupResult.not_found("no matching FR24 flight")

        origin = (getattr(flight, "origin_airport_iata", "") or "").strip()
        destination = (getattr(flight, "destination_airport_iata", "") or "").strip()

        origin, destination = _resolve_q_fillers(client, flight, origin, destination)

        if not origin and not destination:
            return LookupResult.not_found("FR24 flight has no route data")

        route = RouteInfo()
        route.origin = origin
        route.destination = destination
        fill_airport_details(route, "origin")
        fill_airport_details(route, "destination")
        route.airline_icao = (getattr(flight, "airline_icao", "") or "").strip()

        client.clear_feed_miss(callsign)
        logger.debug(
            "FR24 route for %r: %s->%s", callsign, route.origin, route.destination
        )
        return LookupResult.found(route)


# ---------------------------------------------------------------------------
# QQQ filler handling
# ---------------------------------------------------------------------------


def _is_q_filler(code: str) -> bool:
    """True when FR24 used its "airport has no IATA code" filler."""
    return (code or "").strip().upper() == Q_FILLER


def _resolve_q_fillers(client, flight, origin: str, destination: str):
    """Replace QQQ filler codes with resolvable fallbacks, else blank them.

    FR24 stamps "QQQ" into the IATA slot for airports without an IATA
    code.  Its clickhandler details still know the airport's ICAO code,
    which converts through the bundled ICAO->IATA table when possible and
    is otherwise used as-is when the bundled airports database can name
    it.  Anything unresolvable is blanked so the display falls back to
    ``journey_blank_filler``.  Flights with no filler codes never touch
    the details API.
    """
    if not (_is_q_filler(origin) or _is_q_filler(destination)):
        return origin, destination

    details = client.flight_details(flight)
    return _replace_filler(details, "origin", origin), _replace_filler(
        details, "destination", destination
    )


def _replace_filler(details, side: str, code: str) -> str:
    """A non-filler code passes through; a filler becomes its fallback."""
    if not _is_q_filler(code):
        return code
    return _fallback_code(details, side)


def _fallback_code(details, side: str) -> str:
    """ICAO-based fallback for one QQQ filler slot, or "" when unresolvable."""
    if not isinstance(details, dict):
        return ""
    airport = details.get("airport") or {}
    block = airport.get(side) or {}
    code_block = block.get("code") or {}
    # A real IATA from the details beats the feed's filler.
    iata_field = (code_block.get("iata") or "").strip().upper()
    if iata_field and not _is_q_filler(iata_field):
        return iata_field
    icao = (code_block.get("icao") or "").strip().upper()
    if not icao:
        return ""
    iata = icao_to_iata_code(icao)
    if iata:
        return iata
    from utilities.overhead_utilities import airport_info

    # Keep the ICAO only when the bundled database can name it (a bare
    # K-stripped FAA LID is NOT safe: MQJ is Moma Airport, Russia).
    return icao if airport_info(icao) else ""

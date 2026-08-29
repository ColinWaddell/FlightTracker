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

from lookups.providers.fr24.client import get_client
from lookups.results import LookupResult, RouteInfo

logger = logging.getLogger(__name__)


def _enrich_names(route: RouteInfo) -> None:
    """Fill blank airport name/municipality/country from bundled airports.json."""
    from utilities.overhead_utilities import airport_info as bundled

    if route.origin and not route.origin_name:
        d = bundled(route.origin) or {}
        route.origin_name = d.get("name", "")
        route.origin_municipality = d.get("municipality", "")
        route.origin_country = d.get("country_name", "")
    if route.destination and not route.destination_name:
        d = bundled(route.destination) or {}
        route.destination_name = d.get("name", "")
        route.destination_municipality = d.get("municipality", "")
        route.destination_country = d.get("country_name", "")


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

        if not origin and not destination:
            return LookupResult.not_found("FR24 flight has no route data")

        route = RouteInfo()
        route.origin = origin
        route.destination = destination
        _enrich_names(route)
        route.airline_icao = (getattr(flight, "airline_icao", "") or "").strip()

        client.clear_feed_miss(callsign)
        logger.debug(
            "FR24 route for %r: %s->%s", callsign, route.origin, route.destination
        )
        return LookupResult.found(route)

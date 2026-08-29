"""FlightRadar24 aircraft lookup via the live feed (bubble + clickhandler).

Resolves the aircraft type for an aircraft when no hex-based provider could,
by matching the callsign inside a bubble around the aircraft's live position
and fetching the clickhandler details endpoint for the full model name
(e.g. "Boeing 737-800").  The free ``aircraft_code`` ICAO type code from the
feed list is the fallback so the plane field isn't left blank.

The bubble fetch is memoised by the shared client, so when the route
pipeline already queried the same bubble during this enrichment pass the
feed is not hit twice.
"""

from __future__ import annotations

import logging

from lookups.providers.fr24.client import get_client
from lookups.results import AircraftInfo, LookupResult

logger = logging.getLogger(__name__)


class AircraftProvider:
    """FR24 aircraft capability: resolve the type from feed + details."""

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}

    def lookup_aircraft(self, ctx) -> LookupResult:
        callsign = (ctx.callsign or "").strip()
        if not callsign or ctx.lat is None or ctx.lng is None:
            return LookupResult.not_found("no callsign/position for FR24 aircraft")

        client = get_client()
        if client.recently_missed(callsign):
            return LookupResult.not_found("recent FR24 live-feed miss")

        try:
            flight = client.match_in_bubble(
                callsign, ctx.lat, ctx.lng, ctx.ground_speed_mps
            )
        except Exception as e:
            logger.warning("FR24 aircraft lookup failed for %r: %s", callsign, e)
            return LookupResult.unavailable(f"FR24 feed unavailable: {e}")

        if flight is None:
            client.record_feed_miss(callsign)
            return LookupResult.not_found("no matching FR24 flight")

        plane = client.aircraft_model_text(flight)
        if not plane:
            return LookupResult.not_found("FR24 has no aircraft type")

        info = AircraftInfo(plane=plane)
        registration = (getattr(flight, "registration", "") or "").strip()
        if registration:
            info.registration = registration

        client.clear_feed_miss(callsign)
        logger.debug("FR24 aircraft for %r: %r", callsign, plane)
        return LookupResult.found(info)
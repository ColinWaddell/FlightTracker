"""FlightRadar24 live flight observations."""

from __future__ import annotations

import logging

from utilities.lookups.providers.fr24.client import FR24_TIMEOUT, get_client
from utilities.lookups.results import (
    FlightObservation,
    FlightQuery,
    LookupResult,
)
from utilities.overhead_utilities import distance_from_home

logger = logging.getLogger(__name__)


class FlightProvider:
    """Fetches live flight observations for the configured zone from FR24.

    The FR24 feed list supplies origin/destination IATA codes, the airline
    ICAO code and the Mode-S hex for free; those ride along as pre-filled
    enrichment.  Telemetry is always live.
    """

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}
        self.timeout = FR24_TIMEOUT

    def _client(self):
        return get_client()

    def fetch(self, query: FlightQuery) -> LookupResult:
        """Return observations for flights inside *query* (by distance).

        ``FOUND`` with an empty list is a legitimate observation: quiet sky.
        Any transport-level failure yields ``UNAVAILABLE``.
        """
        client = get_client()
        try:
            client.clear_cookies()
            bounds = client.get_zone_bounds(query.zone)
            flights = client.get_flights_in_bounds(bounds)
        except Exception as e:
            # Broad catch - curl_cffi raises its own Timeout/ConnectionError
            # types that don't inherit from requests.exceptions.
            logger.warning("FR24 zone fetch failed: %s", e)
            return LookupResult.unavailable(f"FR24 feed unavailable: {e}")

        min_alt_ft = query.min_altitude_m / 0.3048
        max_alt_ft = query.max_altitude_m / 0.3048
        home = query.home

        flights = [
            f
            for f in flights
            if isinstance(getattr(f, "altitude", None), (int, float))
            and min_alt_ft < f.altitude < max_alt_ft
        ]
        flights.sort(
            key=lambda f: distance_from_home(
                f.latitude or 0.0, f.longitude or 0.0, f.altitude or 0, home
            )
        )

        observations = []
        for flight in flights[: query.max_results]:
            try:
                obs = _to_observation(flight)
            except (AttributeError, TypeError, ValueError):
                logger.debug("FR24: skipping malformed flight entry")
                continue
            if obs is not None:
                observations.append(obs)

        logger.debug("FR24 fetch complete - %d flight(s) in zone", len(observations))
        return LookupResult.found(observations)


def _to_observation(flight) -> FlightObservation | None:
    """Map a FlightRadar24API Flight to a FlightObservation."""
    from utilities.overhead_utilities import clean_field

    icao = clean_field(getattr(flight, "icao_24bit", ""))
    if icao:
        icao = str(icao).lower()
    callsign = clean_field(flight.callsign)

    latitude = flight.latitude if isinstance(flight.latitude, (int, float)) else None
    longitude = flight.longitude if isinstance(flight.longitude, (int, float)) else None

    try:
        ground_speed = int(flight.ground_speed)
    except (TypeError, ValueError):
        ground_speed = 0

    try:
        heading = int(flight.heading)
    except (TypeError, ValueError):
        heading = 0

    vertical_speed = (
        int(flight.vertical_speed)
        if isinstance(flight.vertical_speed, (int, float))
        else 0
    )

    return FlightObservation(
        icao=icao,
        callsign=callsign,
        flight_number=clean_field(getattr(flight, "number", "")),
        latitude=latitude,
        longitude=longitude,
        altitude_ft=flight.altitude or 0,
        ground_speed_kt=ground_speed,
        heading_deg=heading,
        vertical_speed_fpm=vertical_speed,
        # Free enrichment from the feed list:
        origin=clean_field(flight.origin_airport_iata),
        destination=clean_field(flight.destination_airport_iata),
        airline_icao=clean_field(flight.airline_icao),
        # FlightRadarAPI already parses Flight.squawk from the feed.
        # getattr defensive: the attribute exists from 1.5.1 onward.
        squawk=clean_field(getattr(flight, "squawk", "")),
    )


def startup_check(settings: dict | None = None) -> bool:
    """Cheap reachability probe for the startup screen (status-agnostic)."""
    import requests

    try:
        requests.get(
            "https://data-cloud.flightradar24.com/zones/fcgi/feed.js", timeout=5
        )
        return True
    except Exception:
        return False

"""
Flight data class for FlightTracker.

``Flight`` is the display-facing aircraft object passed between the
overhead data source (``utilities.overhead``) and the flight scene.

``RouteInfo``/``AircraftInfo`` (the lookup result types) live in
``lookups.results`` and are re-exported here for convenience.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

# ---------------------------------------------------------------------------
# AircraftInfo / RouteInfo - single source of truth in lookups.results
# ---------------------------------------------------------------------------
# The lookup result types moved into the lookups package when the provider
# layer was decoupled; they are re-exported here so scenes and the web app
# keep importing from utilities.flight.
from scenes.flight.lookups.results import AircraftInfo, RouteInfo  # noqa: E402,F401

# ---------------------------------------------------------------------------
# Flight - a single tracked aircraft
# ---------------------------------------------------------------------------

# Telemetry fields compared by telemetry_changed()
TELEMETRY_FIELDS = ("altitude", "ground_speed", "heading")


@dataclass
class Flight:
    """A single tracked aircraft with route info and live telemetry.

    Created by the overhead data-source modules and consumed by
    ``FlightScene`` for display.
    """

    # Identity
    callsign: str = ""
    icao_callsign: str = ""
    airline_icao: str = ""  # operating carrier ICAO code for logo lookup
    operator_icao: str = ""  # registered operator of the airframe (from Mode S hex)
    owner: str = ""  # registered owner's name (GA aircraft have no airline)

    # Route info
    plane: str = ""
    registration: str = ""
    origin: str = ""
    destination: str = ""
    origin_name: str = ""
    destination_name: str = ""
    origin_municipality: str = ""
    destination_municipality: str = ""
    origin_country: str = ""
    destination_country: str = ""

    # Live telemetry
    altitude: float = 0
    ground_speed: int = 0
    heading: int = 0
    vertical_speed: int = 0

    # -- Identity -----------------------------------------------------------

    @property
    def flight_id(self) -> str:
        """Stable identity key - ICAO callsign preferred, display callsign fallback."""
        return self.icao_callsign or self.callsign

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Flight):
            return NotImplemented
        return self.flight_id == other.flight_id

    def __hash__(self) -> int:
        return hash(self.flight_id)

    # -- Factory ------------------------------------------------------------

    @classmethod
    def from_route(cls, route: RouteInfo, **telemetry) -> Flight:
        """Build a Flight from a RouteInfo plus telemetry/identity kwargs.

        Telemetry kwargs override the corresponding route fields (e.g.
        ``plane`` from a local tar1090 database takes priority over the
        hexdb lookup result).
        """
        route_fields = {f.name: getattr(route, f.name) for f in fields(route)}
        route_fields.update(telemetry)
        return cls(**route_fields)

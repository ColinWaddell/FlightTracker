"""
Flight and RouteInfo data classes for FlightTracker.

``Flight`` replaces the ad-hoc flight dictionaries that were passed between
the overhead data-source modules (fr24, tar1090, osn) and the flight scene.

``RouteInfo`` replaces the route-dict returned by ``route_lookup.get_route()``
and stored in the route cache.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

# ---------------------------------------------------------------------------
# AircraftInfo - per-airframe lookup result (keyed by Mode S hex)
# ---------------------------------------------------------------------------


@dataclass
class AircraftInfo:
    """Result of a Mode S hex (``icao24``) aircraft lookup.

    Returned by :func:`utilities.route_providers.lookup_aircraft` and
    :func:`utilities.route_lookup._lookup_aircraft`.

    ``operator_icao`` is the *registered operator* of the airframe, taken
    from the provider's operator-flag field (hexdb ``OperatorFlagCode``,
    adsbdb ``registered_owner_operator_flag_code``).  Unlike a callsign
    prefix it is unique per airframe, so it disambiguates ICAO designator
    collisions - two operators sharing a 3-letter code still have distinct
    hex addresses.  It is a weaker signal than a flight-level
    ``airline_icao`` from a route provider, because a wet-leased airframe
    reports its owner rather than the brand it is flying for.
    """

    plane: str = ""
    registration: str = ""
    operator_icao: str = ""

    def __bool__(self) -> bool:
        """True when any field was resolved."""
        return bool(self.plane or self.registration or self.operator_icao)


# ---------------------------------------------------------------------------
# RouteInfo - origin/destination/aircraft lookup result
# ---------------------------------------------------------------------------


@dataclass
class RouteInfo:
    """Result of a route + aircraft lookup via hexdb.io or airports.json.

    Returned by :func:`utilities.route_lookup.get_route`.
    """

    plane: str = ""
    registration: str = ""
    airline_icao: str = ""  # operating carrier ICAO code for logo lookup
    operator_icao: str = ""  # registered operator of the airframe (from Mode S hex)
    origin: str = ""
    destination: str = ""
    origin_name: str = ""
    destination_name: str = ""
    origin_municipality: str = ""
    destination_municipality: str = ""
    origin_country: str = ""
    destination_country: str = ""

    # -- Cache serialisation ------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise to a plain dict for routes_cache."""
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, d: dict) -> RouteInfo:
        """Construct from a cache dict, ignoring unknown keys."""
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


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

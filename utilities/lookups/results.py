"""
Provider-independent lookup result types and data models.

This module is the shared vocabulary of the lookup architecture:

* :class:`LookupStatus` / :class:`LookupResult` - explicit outcome types used
  by every provider and understood by the caching / fallback / quarantine
  layers.  A provider that cannot currently answer (timeout, rate limit,
  network failure, malformed response) reports ``UNAVAILABLE``; a provider
  that answered but has no data reports ``NOT_FOUND``.  The distinction
  drives negative caching and quarantine behaviour.

* :class:`RouteInfo` / :class:`AircraftInfo` - provider-independent enrichment
  metadata.  Providers translate their service responses into these;

* :class:`FlightObservation` - a live flight position produced by a flight
  provider.  Observations are live data and are never cached.

* :class:`LookupContext` - per-aircraft context passed to enrichment
  providers (callsign, mode-s hex, live position) so that providers that
  need a live-position hint (e.g. FlightRadar24's bounds lookup) can use it.

Provider interfaces (duck-typed, implemented by ``lookups.providers.*``):

    FlightProvider.fetch(query)    -> LookupResult[list[FlightObservation]]
    RouteProvider.lookup_route(cx) -> LookupResult[RouteInfo]
    AircraftProvider.lookup_ac(ctx)-> LookupResult[AircraftInfo]
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from enum import Enum, auto
from typing import Generic, TypeVar

__all__ = [
    "AircraftInfo",
    "FlightObservation",
    "FlightQuery",
    "LookupContext",
    "LookupResult",
    "LookupStatus",
    "RouteInfo",
]


# ---------------------------------------------------------------------------
# Result envelope
# ---------------------------------------------------------------------------


class LookupStatus(Enum):
    """Outcome of a single provider lookup.

    ``FOUND``       - the provider returned useful information.
    ``NOT_FOUND``   - the provider answered successfully but has no
                      information for this item (eligible for miss caching).
    ``UNAVAILABLE`` - the provider could not currently answer (timeout,
                      network failure, auth failure, rate limit, malformed
                      response, ...).  Never negative-cached.
    """

    FOUND = auto()
    NOT_FOUND = auto()
    UNAVAILABLE = auto()


T = TypeVar("T")


@dataclass(frozen=True)
class LookupResult(Generic[T]):
    """A provider's answer to one lookup, plus *why* it failed.

    ``value``      - the payload when ``status`` is ``FOUND``.
    ``reason``     - short human-readable explanation for ``UNAVAILABLE``
                     (logged by the orchestrator, shown on the live-data page).
    """

    status: LookupStatus
    value: T | None = None
    reason: str = ""

    @classmethod
    def found(cls, value: T) -> LookupResult[T]:
        return cls(status=LookupStatus.FOUND, value=value)

    @classmethod
    def not_found(cls, reason: str = "") -> LookupResult[T]:
        return cls(status=LookupStatus.NOT_FOUND, reason=reason)

    @classmethod
    def unavailable(cls, reason: str = "") -> LookupResult[T]:
        return cls(status=LookupStatus.UNAVAILABLE, reason=reason)

    @property
    def is_found(self) -> bool:
        return self.status is LookupStatus.FOUND

    @property
    def is_unavailable(self) -> bool:
        return self.status is LookupStatus.UNAVAILABLE

    @property
    def is_not_found(self) -> bool:
        return self.status is LookupStatus.NOT_FOUND


# ---------------------------------------------------------------------------
# Enrichment models (provider-independent)
# ---------------------------------------------------------------------------


@dataclass
class AircraftInfo:
    """Metadata about a specific airframe, keyed by Mode S hex.

    Returned by aircraft-capable providers and cached by the lookup layer
    under the mode-s key (the airframe's identity, not the flight's).

    ``operator_icao`` is the *registered operator* of the airframe, taken
    from the provider's operator-flag field (hexdb ``OperatorFlagCode``,
    adsbdb ``registered_owner_operator_flag_code``).  Unlike a callsign
    prefix it is unique per airframe, so it disambiguates ICAO designator
    collisions.  It is a weaker signal than a flight-level
    ``airline_icao`` from a route provider, because a wet-leased airframe
    reports its owner rather than the brand it is flying for.

    ``owner`` is the registered owner's *name* (hexdb ``RegisteredOwners``,
    adsbdb ``registered_owner``) - free text, not a code.  Most general
    aviation aircraft have an owner but no ICAO designator and no logo,
    so this is the only identity available for them.
    """

    plane: str = ""
    registration: str = ""
    operator_icao: str = ""  # registered operator ICAO code (from Mode S hex)
    owner: str = ""  # registered owner's name (GA aircraft have no airline)

    def __bool__(self) -> bool:
        """True when any field was resolved."""
        return bool(self.plane or self.registration or self.operator_icao or self.owner)

    def is_complete(self) -> bool:
        """True when every enrichable field has been filled."""
        return bool(self.plane and self.registration and self.operator_icao)

    def merge_missing(self, update: AircraftInfo) -> None:
        """Fill blank fields from *update* without overwriting existing values."""
        for f in fields(self):
            if not getattr(self, f.name):
                value = getattr(update, f.name, "")
                if value:
                    setattr(self, f.name, value)

    # -- Cache serialisation ------------------------------------------------

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, d: dict) -> AircraftInfo:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class RouteInfo:
    """Route and associated metadata for one flight (keyed by callsign).

    Returned by route providers and merged by the route lookup pipeline.
    ``operator_icao`` / ``owner`` describe the *airframe* and are stripped
    before the result is written under a callsign cache key (see
    ``lookups.enrichment``), because caching them per-callsign would let
    one day's airframe decide tomorrow's logo for a different aircraft.
    """

    plane: str = ""
    registration: str = ""
    airline_icao: str = ""  # operating carrier ICAO code for logo lookup
    operator_icao: str = ""  # registered operator of the airframe (Mode S)
    owner: str = ""  # registered owner's name (GA aircraft have no airline)
    origin: str = ""
    destination: str = ""
    origin_name: str = ""
    destination_name: str = ""
    origin_municipality: str = ""
    destination_municipality: str = ""
    origin_country: str = ""
    destination_country: str = ""

    def is_complete(self) -> bool:
        """True when the flight-level route data is fully known.

        The route pipeline stops once this is True.  The bar covers only
        what describes the *flight* (its callsign): the airport pair and
        the operating carrier.  Airframe identity (``plane`` /
        ``registration``) is deliberately excluded - it belongs to the
        mode-s aircraft pipeline, which caches it per airframe, so route
        providers are never re-queried just to fill airframe fields.
        Airport names/municipalities/countries come from the bundled
        airports.json rather than by providers, so only the codes and
        identity fields count as "enrichable pipeline fields".
        """
        return bool(self.origin and self.destination and self.airline_icao)

    def merge_missing(self, update: RouteInfo) -> None:
        """Fill blank fields from *update* without overwriting existing values."""
        for f in fields(self):
            if not getattr(self, f.name):
                value = getattr(update, f.name, "")
                if value:
                    setattr(self, f.name, value)

    # -- Cache serialisation ------------------------------------------------

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}

    @classmethod
    def from_dict(cls, d: dict) -> RouteInfo:
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# Live flight observation (never cached)
# ---------------------------------------------------------------------------


@dataclass
class FlightObservation:
    """One live aircraft position observed by a flight data provider.

    Observations are live data - they are never cached.  A provider may
    additionally supply fields it gets for free from its live feed
    (FR24 supplies origin/destination IATA codes; tar1090 supplies the
    local aircraft-type database description).  The enrichment pipeline
    treats those as already-known, highest-priority values and only fills
    what is missing.
    """

    # Identity
    icao: str = ""  # Mode-S hex, lowercase, when the feed provides it
    callsign: str = ""  # ICAO callsign (always the route-cache key)
    flight_number: str = ""  # IATA flight number, when the feed supplies it
    latitude: float | None = None
    longitude: float | None = None

    # Live telemetry
    altitude_ft: float = 0.0
    ground_speed_kt: int = 0
    heading_deg: int = 0
    vertical_speed_fpm: int = 0

    # Pre-filled enrichment (from the live feed itself, highest priority)
    plane: str = ""
    registration: str = ""
    origin: str = ""
    destination: str = ""
    airline_icao: str = ""


@dataclass
class FlightQuery:
    """Parameters for a live flight-position query.

    Altitudes reach providers in metres; each provider converts to its
    native units (FR24/tar1090 report feet, OpenSky reports metres).
    """

    zone: dict  # {"tl_y","tl_x","br_y","br_x"} bounding box
    home: list  # [lat, lng, radius_km] observer position
    min_altitude_m: float = 100.0
    max_altitude_m: float = 10000.0
    max_results: int = 5


@dataclass
class LookupContext:
    """Per-aircraft context for the enrichment pipelines.

    Route providers use the callsign; aircraft providers are keyed by
    mode-s hex.  The live position and speed are optional hints that let
    position-based providers (FR24's bubble lookup) disambiguate.
    """

    callsign: str = ""
    mode_s: str = ""
    lat: float | None = None
    lng: float | None = None
    ground_speed_mps: float | None = None
    # Set by the enrichment service: True when the aircraft type is still
    # unknown and a provider that pays extra for it should fetch it.
    want_plane: bool = False

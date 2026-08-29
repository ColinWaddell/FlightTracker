"""
Enrichment pipeline: turns a live :class:`FlightObservation` into a fully
resolved :class:`RouteInfo`.

The observation itself carries the highest-priority answers (a provider's
live feed often supplies origin/destination IATA codes, the operating
airline, even the aircraft type for free).  The route and aircraft
pipelines then fill whatever remains:

1.  Build a prefill :class:`RouteInfo` from the observation fields.
2.  Route pipeline (callsign-keyed): persistent cache, then the configured
    route providers.  ``merge_missing`` semantics mean the prefill can
    never be overwritten - providers only fill blanks.
3.  Aircraft pipeline (mode-s-keyed): runs whenever plane/registration/
    airline identity is still missing (the airframe's registered operator
    is the only per-airframe signal and resolves ICAO designator
    collisions).  Operator/owner from the mode-s lookup *replace* any
    flight-level answer - the airframe's registered operator is stronger
    evidence for logo resolution than a callsign-prefix guess.
4.  Position-gated providers (FR24's live-feed bubble) only participate
    when the context carries a position; the aircraft pipeline requests
    the expensive type lookup (``want_plane``) only while the type is
    still unknown.
"""

from __future__ import annotations

import logging

from lookups.results import FlightObservation, LookupContext, RouteInfo

logger = logging.getLogger(__name__)

# knots -> m/s
_KT_TO_MPS = 0.514444


def build_context(observation: FlightObservation) -> LookupContext:
    """Build the per-aircraft lookup context from a live observation."""
    return LookupContext(
        callsign=(observation.callsign or "").strip(),
        mode_s=(observation.icao or "").strip().lower(),
        lat=observation.latitude,
        lng=observation.longitude,
        ground_speed_mps=(observation.ground_speed_kt or 0) * _KT_TO_MPS,
        want_plane=not observation.plane,
    )


def build_prefill(observation: FlightObservation) -> RouteInfo:
    """Route-seeded values from the observation's own prefill fields."""
    return RouteInfo(
        plane=observation.plane,
        registration=observation.registration,
        airline_icao=observation.airline_icao,
        origin=observation.origin,
        destination=observation.destination,
    )


def enrich(observation: FlightObservation) -> RouteInfo:
    """Fully resolve *observation* into a :class:`RouteInfo`.

    Never raises.  See module docstring for the pipeline order.
    """
    from lookups import aircraft as aircraft_service
    from lookups import routes as route_service

    result = route_service.lookup_route(
        build_context(observation),
        prefill=build_prefill(observation),
    )

    ctx = build_context(observation)
    if ctx.mode_s and not result.is_complete():
        # The mode-s lookup fills two independent gaps: the aircraft type
        # and the airframe's registered operator (the only per-airframe
        # identity signal).  Its operator/owner answers are authoritative
        # for the airframe, so they replace rather than merge.
        info = aircraft_service.lookup_aircraft(ctx)
        if not result.plane:
            result.plane = info.plane
        if not result.registration:
            result.registration = info.registration
        result.operator_icao = info.operator_icao
        result.owner = info.owner

    return result
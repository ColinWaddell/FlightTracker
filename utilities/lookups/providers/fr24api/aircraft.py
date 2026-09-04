"""Aircraft details via the official FlightRadar24 API.

The API has no mode-S hex filter, but callsign-filtered live positions
answer with the airframe's registration, ICAO type and operating
airline - everything the aircraft panel needs.  Lookups therefore key
off the callsign; without one the provider answers NOT_FOUND.
"""

from __future__ import annotations

import logging

from utilities.lookups.providers.common.operators import clean_operator_code
from utilities.lookups.providers.fr24api.client import (
    api_key,
    api_unavailable,
    callsign_position,
    data_of,
    is_transport_error,
)
from utilities.lookups.results import AircraftInfo, LookupResult

logger = logging.getLogger(__name__)


class AircraftProvider:
    """FR24 API aircraft capability (requires a paid token)."""

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}
        self._api_key = api_key(self._settings)

    def lookup_aircraft(self, ctx) -> LookupResult:
        callsign = (ctx.callsign or "").strip()
        if not callsign:
            return LookupResult.not_found("no callsign for FR24 API aircraft")
        if not self._api_key:
            return LookupResult.unavailable("FR24 API token not configured")

        try:
            # Shared with the route capability: both capabilities need
            # the identical callsign request, and every call is billed.
            resp = callsign_position(self._api_key, callsign)
        except Exception as e:
            if is_transport_error(e):
                logger.debug("FR24 API aircraft lookup failed for %r: %s", callsign, e)
                return LookupResult.unavailable(f"FR24 API unreachable: {e}")
            raise

        if resp.status_code in (400, 404):
            # Ident rejected or unknown: "no answer for this callsign",
            # not a provider failure - must not quarantine.  (#101 family)
            logger.debug(
                "FR24 API rejected ident %r (HTTP %d)",
                callsign,
                resp.status_code,
            )
            return LookupResult.not_found("FR24 API rejected the ident format")

        if resp.status_code != 200:
            reason = api_unavailable(resp)
            logger.debug("FR24 API aircraft for %r: %s", callsign, reason)
            return LookupResult.unavailable(reason)

        data = data_of(resp)
        if not data:
            return LookupResult.not_found("no FR24 API flight for this callsign")

        record = data[0]
        info = _to_aircraft(record)
        if info is None:
            return LookupResult.not_found("FR24 API flight has no aircraft data")
        fields = (info.plane, info.registration, info.operator_icao)
        identity = " ".join(part for part in fields if part)
        logger.debug("FR24 API aircraft for %r: %s", callsign, identity)
        return LookupResult.found(info)


def _to_aircraft(record: dict) -> AircraftInfo | None:
    """Build AircraftInfo from one FR24 API position record."""
    from utilities.overhead_utilities import clean_field

    registration = clean_field(record.get("reg"))
    plane = clean_field(record.get("type"))  # ICAO type code, e.g. A20N
    operator = clean_operator_code(record.get("painted_as"))
    if not (registration or plane or operator):
        return None
    return AircraftInfo(
        plane=plane,
        registration=registration,
        operator_icao=operator,
    )

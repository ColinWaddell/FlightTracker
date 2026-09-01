"""HexDB aircraft lookup (type/registration/operator/owner by mode-s hex)."""

from __future__ import annotations

import logging

from requests.exceptions import RequestException

from scenes.flight.lookups.providers.common.operators import clean_operator_code
from scenes.flight.lookups.providers.hexdb.routes import BASE, _get
from scenes.flight.lookups.results import AircraftInfo, LookupResult

logger = logging.getLogger(__name__)


class AircraftProvider:
    """hexdb.io aircraft capability (free, no API key)."""

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}

    def lookup_aircraft(self, ctx) -> LookupResult:
        mode_s = (ctx.mode_s or "").strip().lower()
        if not mode_s:
            return LookupResult.not_found("no mode_s for hexdb aircraft")

        try:
            resp = _get(f"{BASE}/aircraft/{mode_s}")
        except (RequestException, OSError) as e:
            logger.debug("hexdb aircraft lookup failed for %r: %s", mode_s, e)
            return LookupResult.unavailable(f"hexdb unreachable: {e}")

        if resp.status_code == 404:
            logger.debug("hexdb: unknown aircraft %r", mode_s)
            return LookupResult.not_found("hexdb has no aircraft for this hex")
        try:
            resp.raise_for_status()
            data = resp.json()
        except (RequestException, ValueError) as e:
            logger.debug("hexdb aircraft lookup failed for %r: %s", mode_s, e)
            return LookupResult.unavailable(f"hexdb returned a bad response: {e}")

        info = AircraftInfo(
            plane=parse_aircraft_type(data),
            registration=parse_registration(data),
            operator_icao=parse_operator_icao(data),
            owner=parse_owner(data),
        )
        fields = (info.plane, info.registration, info.operator_icao or info.owner)
        identity = " ".join(part for part in fields if part)
        logger.debug("hexdb aircraft for %r: %s", mode_s, identity)
        return LookupResult.found(info)


# ---------------------------------------------------------------------------
# Response parsing (module-level for direct testing)
# ---------------------------------------------------------------------------


def parse_aircraft_type(data: dict) -> str:
    """Build a 'Manufacturer Type' string from a hexdb aircraft response."""
    manufacturer = (data.get("Manufacturer") or "").strip()
    type_code = (data.get("ICAOTypeCode") or "").strip()
    if manufacturer and type_code:
        return f"{manufacturer} {type_code}"
    return type_code or manufacturer


def parse_registration(data: dict) -> str:
    return (data.get("Registration") or "").strip()


def parse_operator_icao(data: dict) -> str:
    """Return the registered operator's ICAO code from a hexdb response.

    hexdb exposes this as ``OperatorFlagCode`` - for airline aircraft this
    is the 3-letter ICAO airline designator (e.g. ``EIN``, ``BAW``).
    """
    return clean_operator_code(data.get("OperatorFlagCode"))


def parse_owner(data: dict) -> str:
    return (data.get("RegisteredOwners") or "").strip()

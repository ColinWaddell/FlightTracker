"""adsbdb.com aircraft lookup (type/registration/operator/owner by mode-s hex)."""

from __future__ import annotations

import logging

from lookups.providers.adsbdb.routes import BASE, _get
from lookups.providers.common.operators import clean_operator_code
from lookups.results import AircraftInfo, LookupResult
from requests.exceptions import RequestException

logger = logging.getLogger(__name__)


class AircraftProvider:
    """adsbdb.com aircraft capability (free, no API key)."""

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}

    def lookup_aircraft(self, ctx) -> LookupResult:
        mode_s = (ctx.mode_s or "").strip().lower()
        if not mode_s:
            return LookupResult.not_found("no mode_s for adsbdb aircraft")

        try:
            resp = _get(f"{BASE}/aircraft/{mode_s}")
        except (RequestException, OSError) as e:
            logger.debug("adsbdb aircraft lookup failed for %r: %s", mode_s, e)
            return LookupResult.unavailable(f"adsbdb unreachable: {e}")

        if resp.status_code == 404:
            logger.debug("adsbdb: unknown aircraft %r", mode_s)
            return LookupResult.not_found("adsbdb has no aircraft for this hex")
        try:
            resp.raise_for_status()
            data = resp.json()
        except (RequestException, ValueError) as e:
            logger.debug("adsbdb aircraft lookup failed for %r: %s", mode_s, e)
            return LookupResult.unavailable(f"adsbdb returned a bad response: {e}")

        info = parse_aircraft(data)
        if info is None:
            return LookupResult.not_found("adsbdb has no aircraft data")

        if not (
            info.plane
            or info.registration
            or info.operator_icao
            or info.owner
        ):
            return LookupResult.not_found("adsbdb aircraft record empty")

        return LookupResult.found(info)


# ---------------------------------------------------------------------------
# Response parsing (module-level for direct testing)
# ---------------------------------------------------------------------------


def parse_aircraft(data: dict) -> AircraftInfo | None:
    """Build an :class:`AircraftInfo` from an adsbdb aircraft response.

    Returns None when the response has no aircraft block.
    """
    ac = (data.get("response") or {}).get("aircraft") or {}
    if not ac:
        return None

    manufacturer = (ac.get("manufacturer") or "").strip()
    type_full = (ac.get("type") or "").strip()
    icao_type = (ac.get("icao_type") or "").strip()
    registration = (ac.get("registration") or "").strip()

    # Build a "Manufacturer TypeCode" string to match hexdb format.
    # Prefer icao_type for the type code (e.g. "A320"); use type_full as
    # the full model name (e.g. "A320 214") when icao_type is missing.
    if manufacturer and icao_type:
        plane = f"{manufacturer} {icao_type}"
    elif type_full:
        plane = type_full
    else:
        plane = icao_type or manufacturer

    # adsbdb's equivalents of hexdb's OperatorFlagCode / RegisteredOwners.
    return AircraftInfo(
        plane=plane,
        registration=registration,
        operator_icao=clean_operator_code(
            ac.get("registered_owner_operator_flag_code")
        ),
        owner=(ac.get("registered_owner") or "").strip(),
    )
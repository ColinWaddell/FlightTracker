"""AeroDataBox aircraft lookup (RapidAPI, key required).

Rate-limit responses (429/403 and 200-with-error-body) are reported as
``UNAVAILABLE`` so the service layer quarantines the provider rather than
burning remaining quota on every aircraft.
"""

from __future__ import annotations

import logging

from requests.exceptions import RequestException

from lookups.providers.aerodatabox.client import (
    RATE_LIMIT_CODES,
    aerodatabox_get,
    is_error_response,
)
from lookups.providers.common.operators import clean_operator_code
from lookups.results import AircraftInfo, LookupResult

logger = logging.getLogger(__name__)


class AircraftProvider:
    """AeroDataBox aircraft capability (requires a RapidAPI key)."""

    def __init__(self, settings: dict | None = None):
        self._settings = settings or {}
        self.api_key = (self._settings.get("api_key") or "").strip()

    def lookup_aircraft(self, ctx) -> LookupResult:
        mode_s = (ctx.mode_s or "").strip().lower()
        if not mode_s:
            return LookupResult.not_found("no mode_s for aerodatabox aircraft")
        if not self.api_key:
            return LookupResult.unavailable("aerodatabox API key not configured")

        try:
            resp, data = aerodatabox_get(f"/aircrafts/icao24/{mode_s}", self.api_key)
        except (RequestException, OSError) as e:
            logger.debug("aerodatabox aircraft lookup failed for %r: %s", mode_s, e)
            return LookupResult.unavailable(f"aerodatabox unreachable: {e}")

        if resp.status_code == 404:
            logger.debug("aerodatabox: unknown aircraft %r", mode_s)
            return LookupResult.not_found("aerodatabox has no aircraft for this hex")

        if resp.status_code in RATE_LIMIT_CODES:
            logger.warning(
                "aerodatabox: rate limit / quota exceeded (HTTP %d) for %r",
                resp.status_code,
                mode_s,
            )
            return LookupResult.unavailable(
                f"aerodatabox rate limited (HTTP {resp.status_code})"
            )

        if resp.status_code >= 400:
            return LookupResult.unavailable(f"aerodatabox HTTP {resp.status_code}")

        # Detect 200-with-error-body rate-limit responses.
        if is_error_response(data):
            msg = ""
            for k in ("message", "error", "errors"):
                if k in data:
                    msg = str(data[k])[:200]
                    break
            logger.warning("aerodatabox: error response for %r (%s)", mode_s, msg)
            return LookupResult.unavailable(f"aerodatabox error response: {msg}")

        # Response may be a list or a single object.
        ac_list = data if isinstance(data, list) else [data]
        if not ac_list:
            return LookupResult.not_found("aerodatabox returned no aircraft")

        info = parse_aircraft(ac_list[0])
        if info is None or not (
            info.plane or info.registration or info.operator_icao or info.owner
        ):
            return LookupResult.not_found("aerodatabox aircraft record empty")

        return LookupResult.found(info)


# ---------------------------------------------------------------------------
# Response parsing (module-level for direct testing)
# ---------------------------------------------------------------------------


def parse_aircraft(ac: dict) -> AircraftInfo:
    """Build an :class:`AircraftInfo` from an AeroDataBox aircraft object."""
    plane = (ac.get("typeName") or ac.get("productionLine") or "").strip()
    registration = (ac.get("reg") or "").strip()

    # AeroDataBox nests the operator under an "airline" object when known.
    airline = ac.get("airline") or {}
    is_airline_dict = isinstance(airline, dict)

    operator_icao = clean_operator_code(
        airline.get("icao") if is_airline_dict else None
    )
    owner = (
        (airline.get("name") if is_airline_dict else None)
        or ac.get("airlineName")
        or ""
    ).strip()

    return AircraftInfo(
        plane=plane,
        registration=registration,
        operator_icao=operator_icao,
        owner=owner,
    )

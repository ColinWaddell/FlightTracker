"""OpenSky Network live flight observations (OAuth2 client credentials).

Uses the OpenSky REST API to fetch live aircraft state vectors within the
configured bounding box.  OAuth2 tokens are requested with the client
credentials grant and cached until shortly before expiry.
"""

from __future__ import annotations

import logging
import time as time_mod
from threading import Lock

import requests

from utilities.lookups.results import FlightObservation, FlightQuery, LookupResult
from utilities.overhead_utilities import (
    clean_field,
    distance_from_home,
    in_zone,
    metres_to_feet,
    ms_to_fpm,
    ms_to_knots,
)

logger = logging.getLogger(__name__)

OSN_TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network"
    "/protocol/openid-connect/token"
)
OSN_STATES_URL = "https://opensky-network.org/api/states/all"

# Request timeout for both the token and states endpoints (seconds).
OSN_TIMEOUT = 15

# Refresh the token this many seconds before it actually expires to avoid
# races at the boundary.
TOKEN_EXPIRY_BUFFER = 60


class FlightProvider:
    """Fetches live state vectors from the OpenSky Network.

    OpenSky state vector field order (indices):
      0 icao24, 1 callsign, 5 longitude, 6 latitude, 7 baro_altitude (m),
      8 on_ground, 9 velocity (m/s), 10 true_track, 11 vertical_rate (m/s).
    """

    def __init__(self, settings: dict | None = None):
        settings = settings or {}
        self.client_id = (settings.get("client_id") or "").strip()
        self.client_secret = (settings.get("client_secret") or "").strip()

        # Persistent session - keeps the urllib3 connection pool alive
        # across polling cycles.
        self._session = requests.Session()

        # OAuth2 token state
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = Lock()

    # ------------------------------------------------------------------
    # OAuth2 token management
    # ------------------------------------------------------------------

    def _refresh_token(self) -> None:
        """Fetch a fresh OAuth2 access token using client credentials.

        Raises requests.exceptions.RequestException on failure.
        """
        with self._token_lock:
            # Double-checked: another thread may have refreshed while waiting
            if self._token and time_mod.time() < self._token_expires_at:
                return

            resp = self._session.post(
                OSN_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=OSN_TIMEOUT,
            )
            resp.raise_for_status()
            payload = resp.json()
            self._token = payload["access_token"]
            expires_in = int(payload.get("expires_in", 300))
            self._token_expires_at = time_mod.time() + expires_in - TOKEN_EXPIRY_BUFFER
            logger.debug("OSN token refreshed, expires in %ds", expires_in)

    def _auth_headers(self) -> dict:
        """Return Authorization headers, refreshing the token if needed."""
        if not self._token or time_mod.time() >= self._token_expires_at:
            self._refresh_token()
        return {"Authorization": f"Bearer {self._token}"}

    def _get_states(self, query: FlightQuery) -> list:
        """Return raw state-vector candidates inside the query zone."""
        zone = query.zone
        params = {
            "lamin": zone["br_y"],
            "lomin": zone["tl_x"],
            "lamax": zone["tl_y"],
            "lomax": zone["br_x"],
        }

        resp = self._session.get(
            OSN_STATES_URL,
            params=params,
            headers=self._auth_headers(),
            timeout=OSN_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()

        states = payload.get("states") or []

        min_alt_ft = query.min_altitude_m / 0.3048
        max_alt_ft = query.max_altitude_m / 0.3048

        candidates = []
        for sv in states:
            # sv is a list; guard against malformed entries
            if not isinstance(sv, list) or len(sv) < 12:
                continue

            if sv[8]:  # on_ground
                continue

            lat = sv[6]
            lon = sv[5]
            baro_alt_m = sv[7]

            if lat is None or lon is None or baro_alt_m is None:
                continue

            alt_ft = metres_to_feet(baro_alt_m)
            if not (min_alt_ft < alt_ft < max_alt_ft):
                continue

            if not in_zone(lat, lon, zone):
                continue

            candidates.append(sv)

        return candidates

    def fetch(self, query: FlightQuery) -> LookupResult:
        """Return observations for aircraft inside *query* from OpenSky."""
        try:
            candidates = self._get_states(query)
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status in (401, 403):
                return LookupResult.unavailable(
                    "OpenSky authentication failed - check client credentials"
                )
            return LookupResult.unavailable(f"OpenSky request failed: {e}")
        except requests.exceptions.RequestException as e:
            logger.warning("OSN fetch failed: %s", e)
            return LookupResult.unavailable(f"OpenSky unreachable: {e}")

        candidates.sort(
            key=lambda sv: distance_from_home(
                sv[6], sv[5], metres_to_feet(sv[7]), query.home
            )
        )

        observations = []
        for sv in candidates[: query.max_results]:
            observations.append(_sv_to_observation(sv))

        logger.debug("OSN fetch complete - %d flight(s) tracked", len(observations))
        return LookupResult.found(observations)


def _sv_to_observation(sv: list) -> FlightObservation:
    """Map one OpenSky state vector to an observation.

    Malformed numeric fields degrade to 0 rather than dropping the
    aircraft - the feed occasionally yields partial vectors.
    """
    heading = 0
    if sv[10] is not None:
        try:
            heading = int(float(sv[10]))
        except (TypeError, ValueError):
            heading = 0

    return FlightObservation(
        icao=(sv[0] or "").strip().lower(),
        callsign=clean_field(sv[1]),
        latitude=sv[6],
        longitude=sv[5],
        altitude_ft=metres_to_feet(sv[7]) if sv[7] is not None else 0.0,
        ground_speed_kt=ms_to_knots(sv[9]),
        heading_deg=heading,
        vertical_speed_fpm=ms_to_fpm(sv[11]),
    )


def startup_check(settings: dict | None = None) -> bool:
    """Reachability probe for the startup screen (status-agnostic)."""
    try:
        requests.get(OSN_STATES_URL, timeout=5)
        return True
    except Exception:
        return False

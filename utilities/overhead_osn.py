"""
OpenSky Network data source for FlightTracker.

Uses the OpenSky Network REST API to fetch live aircraft state vectors within
the configured bounding box.  Authenticates via OAuth2 client credentials
(client_id + client_secret obtained from opensky-network.org account settings).

Route lookup (origin/destination) and aircraft type are both handled via
route_lookup.get_route(), which uses two independent hexdb.io endpoints:
  Route    GET /api/v1/route/icao/{callsign}  -> cached by callsign
  Aircraft GET /api/v1/aircraft/{hex}        -> cached by mode_s
See utilities/route_lookup.py for details.

OpenSky state vector field order (indices):
  0  icao24          unique 24-bit ICAO transponder address (hex string)
  1  callsign        8-char callsign, may have trailing spaces
  5  longitude       WGS-84 decimal degrees
  6  latitude        WGS-84 decimal degrees
  7  baro_altitude   barometric altitude in metres (may be None)
  8  on_ground       bool
  9  velocity        ground speed in m/s (may be None)
  10 true_track      track angle clockwise from north in degrees (may be None)
  11 vertical_rate   vertical rate in m/s (may be None)
"""

import logging
import time as time_mod
from threading import Event, Lock, Thread

import requests

from utilities import route_lookup
from utilities.flight import Flight
from utilities.overhead_utilities import (
    clean_field,
    distance_from_home,
    in_zone,
    metres_to_feet,
    ms_to_fpm,
    ms_to_knots,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OSN_TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network"
    "/protocol/openid-connect/token"
)
OSN_STATES_URL = "https://opensky-network.org/api/states/all"

# Refresh token this many seconds before it actually expires to avoid races
TOKEN_EXPIRY_BUFFER = 60


# ---------------------------------------------------------------------------
# Placeholder flight for credential errors
# ---------------------------------------------------------------------------


def _key_error_flight() -> Flight:
    """Return a fake flight entry displayed when OSN credentials are invalid."""
    return Flight(
        plane="Check OSN credentials",
        callsign="KEY ERROR",
        icao_callsign="KEY ERROR",
    )


# ---------------------------------------------------------------------------
# Overhead class
# ---------------------------------------------------------------------------


class Overhead:
    def __init__(self):
        from setup.configuration import Config

        cfg = Config.instance()
        self.zone_home = cfg.zone_home
        self.min_altitude = cfg.flight_min_altitude
        self.max_altitude = cfg.flight_max_altitude
        self.location_home = cfg.location_home
        self.max_flight_lookup = cfg.max_flight_lookup
        self.client_id = cfg.osn_client_id
        self.client_secret = cfg.osn_client_secret

        # Persistent session - keeps the urllib3 connection pool alive across
        # polling cycles, avoiding Python 3.13 dummy-thread GC noise.
        self._session = requests.Session()

        # OAuth2 token state
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._token_lock = Lock()

        self.lock = Lock()
        self.done = Event()

        self.thread = None
        self.data_store = []
        self.new_data_store = False
        self.processing_store = False
        self.error_store = None

    # ------------------------------------------------------------------
    # OAuth2 token management
    # ------------------------------------------------------------------

    def _refresh_token(self):
        """Fetch a fresh OAuth2 access token using client credentials.

        Updates self._token and self._token_expires_at.
        Raises requests.exceptions.RequestException on failure.
        """
        with self._token_lock:
            # Double-checked: another thread may have refreshed while we waited
            if self._token and time_mod.time() < self._token_expires_at:
                return

            resp = self._session.post(
                OSN_TOKEN_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                timeout=15,
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

    def _get_states(self, zone: dict) -> list:
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
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()

        states = payload.get("states") or []

        min_alt_ft = self.min_altitude / 0.3048
        max_alt_ft = self.max_altitude / 0.3048

        # Filter and collect candidates
        candidates = []
        for sv in states:
            # sv is a list; guard against malformed entries
            if not isinstance(sv, list) or len(sv) < 12:
                continue

            on_ground = sv[8]
            if on_ground:
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

    # ------------------------------------------------------------------
    # Threading interface
    # ------------------------------------------------------------------

    def grab_data(self) -> bool:
        with self.lock:
            if self.processing_store:
                return False
            self.processing_store = True
            self.new_data_store = False
            self.error_store = None
            self.done.clear()
            self.thread = Thread(
                target=self.grab_data_impl, name="overhead-osn-grabber"
            )
        self.thread.start()
        return True

    def refresh(self) -> bool:
        with self.lock:
            if self.processing_store:
                return False
            self.processing_store = True
            self.new_data_store = False
            self.error_store = None
            self.done.clear()
        self.grab_data_impl()
        return True

    def wait(self, timeout=None) -> bool:
        finished = self.done.wait(timeout)
        if finished and self.thread is not None:
            self.thread.join()
        return finished

    # ------------------------------------------------------------------
    # Data fetch
    # ------------------------------------------------------------------

    def grab_data_impl(self):
        data = []

        try:
            zone = self.zone_home
            candidates = self._get_states(zone)

            # Sort by distance from observer
            candidates.sort(
                key=lambda sv: distance_from_home(
                    sv[6], sv[5], metres_to_feet(sv[7]), self.location_home
                )
            )

            for sv in candidates[: self.max_flight_lookup]:
                try:
                    icao24 = (sv[0] or "").strip().lower()
                    callsign = clean_field(sv[1])

                    alt_ft = metres_to_feet(sv[7])
                    ground_speed = ms_to_knots(sv[9])
                    heading = int(float(sv[10])) if sv[10] is not None else 0
                    vertical_speed = ms_to_fpm(sv[11])

                    # Two independent hexdb lookups: route by callsign,
                    # aircraft type by mode_s.  Each is cached under its own
                    # key so repeat polls are free.
                    route = route_lookup.get_route(callsign, mode_s=icao24)

                    data.append(
                        Flight.from_route(
                            route,
                            callsign=callsign,
                            icao_callsign=callsign,
                            altitude=alt_ft,
                            ground_speed=ground_speed,
                            heading=heading,
                            vertical_speed=vertical_speed,
                        )
                    )

                except (IndexError, TypeError, ValueError, AttributeError):
                    continue

            with self.lock:
                self.data_store = data
                self.new_data_store = True
                self.error_store = None
            logger.debug("OSN fetch complete - %d flight(s) tracked", len(data))

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status in (401, 403):
                # Bad or missing credentials - surface a visible placeholder so
                # the display shows something useful rather than going idle.
                logger.warning(
                    "OSN authentication failed (HTTP %s) - check client credentials",
                    status,
                )
                with self.lock:
                    self.data_store = [_key_error_flight()]
                    self.new_data_store = True
                    self.error_store = None
            else:
                with self.lock:
                    self.new_data_store = False
                    self.error_store = e
                logger.warning("OSN fetch failed: %s", e)

        except Exception as e:
            with self.lock:
                self.new_data_store = False
                self.error_store = e
            logger.warning("OSN fetch failed: %s", e)

        finally:
            with self.lock:
                self.processing_store = False
            self.done.set()

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def new_data(self) -> bool:
        with self.lock:
            return self.new_data_store

    @property
    def processing(self) -> bool:
        with self.lock:
            return self.processing_store

    @property
    def error(self):
        with self.lock:
            return self.error_store

    @property
    def data(self) -> list:
        with self.lock:
            self.new_data_store = False
            return list(self.data_store)

    @property
    def data_is_empty(self) -> bool:
        with self.lock:
            return len(self.data_store) == 0


if __name__ == "__main__":
    o = Overhead()
    o.refresh()
    if o.error is not None:
        print(f"failed: {o.error}")
    else:
        print(o.data)

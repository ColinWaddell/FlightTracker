"""
OpenSky Network data source for FlightTracker.

Uses the OpenSky Network REST API to fetch live aircraft state vectors within
the configured bounding box.  Authenticates via OAuth2 client credentials
(client_id + client_secret obtained from opensky-network.org account settings).

Route lookup (origin/destination) and aircraft type are both handled via
route_lookup.get_route(), which uses two independent adsbdb.com endpoints:
  Route    GET /v0/callsign/{callsign}     -> cached by callsign
  Aircraft GET /v0/aircraft/{icao24}       -> cached by mode_s
See utilities/route_lookup.py for details on why we avoid the combined
endpoint.

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
import math
import time as time_mod
from threading import Event, Lock, Thread

import requests

from utilities import route_lookup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EARTH_RADIUS_KM = 6371
BLANK_FIELDS = {"", "N/A", "NONE"}

OSN_TOKEN_URL = (
    "https://auth.opensky-network.org/auth/realms/opensky-network"
    "/protocol/openid-connect/token"
)
OSN_STATES_URL = "https://opensky-network.org/api/states/all"

# Refresh token this many seconds before it actually expires to avoid races
TOKEN_EXPIRY_BUFFER = 60

# ---------------------------------------------------------------------------
# Unit conversion helpers
# ---------------------------------------------------------------------------


def _metres_to_feet(m) -> float:
    try:
        return float(m) * 3.28084
    except (TypeError, ValueError):
        return 0.0


def _ms_to_knots(ms) -> int:
    try:
        return int(float(ms) * 1.94384)
    except (TypeError, ValueError):
        return 0


def _ms_to_fpm(ms) -> int:
    try:
        return int(float(ms) * 196.85)
    except (TypeError, ValueError):
        return 0


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------


def _in_zone(lat, lon, zone) -> bool:
    return zone["br_y"] <= lat <= zone["tl_y"] and zone["tl_x"] <= lon <= zone["br_x"]


def _distance_from_home(lat, lon, alt_ft, home) -> float:
    def polar_to_cartesian(lat, lon, alt):
        deg2rad = math.pi / 180
        return [
            alt * math.cos(deg2rad * lat) * math.sin(deg2rad * lon),
            alt * math.sin(deg2rad * lat),
            alt * math.cos(deg2rad * lat) * math.cos(deg2rad * lon),
        ]

    altitude_km = 0.0003048 * alt_ft + EARTH_RADIUS_KM
    try:
        x0, y0, z0 = polar_to_cartesian(lat, lon, altitude_km)
        x1, y1, z1 = polar_to_cartesian(*home)
        return math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2)
    except (TypeError, ValueError):
        return 1e6


# ---------------------------------------------------------------------------
# Placeholder flight for credential errors
# ---------------------------------------------------------------------------


def _key_error_flight() -> dict:
    """Return a fake flight entry displayed when OSN credentials are invalid."""
    return {
        "plane": "Check OSN credentials",
        "origin": "",
        "destination": "",
        "origin_name": "",
        "destination_name": "",
        "origin_municipality": "",
        "destination_municipality": "",
        "origin_country": "",
        "destination_country": "",
        "altitude": 0,
        "ground_speed": 0,
        "heading": 0,
        "vertical_speed": 0,
        "callsign": "KEY ERROR",
        "icao_callsign": "KEY ERROR",
    }


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
            home = self.location_home

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

                alt_ft = _metres_to_feet(baro_alt_m)
                if not (min_alt_ft < alt_ft < max_alt_ft):
                    continue

                if not _in_zone(lat, lon, zone):
                    continue

                candidates.append(sv)

            # Sort by distance from observer
            candidates.sort(
                key=lambda sv: _distance_from_home(
                    sv[6], sv[5], _metres_to_feet(sv[7]), home
                )
            )

            for sv in candidates[: self.max_flight_lookup]:
                try:
                    icao24 = (sv[0] or "").strip().lower()
                    callsign = (sv[1] or "").strip()
                    if callsign.upper() in BLANK_FIELDS:
                        callsign = ""

                    lat = sv[6]
                    lon = sv[5]
                    alt_ft = _metres_to_feet(sv[7])
                    ground_speed = _ms_to_knots(sv[9])
                    heading = int(float(sv[10])) if sv[10] is not None else 0
                    vertical_speed = _ms_to_fpm(sv[11])

                    # Two independent adsbdb lookups: route by callsign,
                    # aircraft type by mode_s.  Each is cached under its own
                    # key so repeat polls are free.
                    route = route_lookup.get_route(callsign, mode_s=icao24)

                    data.append(
                        {
                            "plane": route["plane"],
                            "origin": route["origin"],
                            "destination": route["destination"],
                            "origin_name": route["origin_name"],
                            "destination_name": route["destination_name"],
                            "origin_municipality": route["origin_municipality"],
                            "destination_municipality": route[
                                "destination_municipality"
                            ],
                            "origin_country": route["origin_country"],
                            "destination_country": route["destination_country"],
                            "altitude": alt_ft,
                            "ground_speed": ground_speed,
                            "heading": heading,
                            "vertical_speed": vertical_speed,
                            "callsign": callsign,
                            "icao_callsign": callsign,
                        }
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

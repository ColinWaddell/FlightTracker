import logging
import math
from threading import Event, Lock, Thread

import requests
from requests.exceptions import RequestException

from utilities import route_lookup

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371
BLANK_FIELDS = ["", "N/A", "NONE"]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def in_zone(lat, lon, zone):
    return zone["br_y"] <= lat <= zone["tl_y"] and zone["tl_x"] <= lon <= zone["br_x"]


def distance_from_home(lat, lon, alt_ft, home):
    def polar_to_cartesian(lat, lon, alt):
        deg2rad = math.pi / 180

        return [
            alt * math.cos(deg2rad * lat) * math.sin(deg2rad * lon),
            alt * math.sin(deg2rad * lat),
            alt * math.cos(deg2rad * lat) * math.cos(deg2rad * lon),
        ]

    altitude_km = 0.0003048 * alt_ft + EARTH_RADIUS_KM
    x0, y0, z0 = polar_to_cartesian(lat, lon, altitude_km)
    x1, y1, z1 = polar_to_cartesian(*home)

    return math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2)


# ---------------------------------------------------------------------------
# Overhead class
# ---------------------------------------------------------------------------


class Overhead:
    def __init__(self):
        from setup.configuration import Config

        cfg = Config.instance()
        self.tar1090_url = cfg.tar1090_url
        self.zone_home = cfg.zone_home
        self.min_altitude = cfg.flight_min_altitude
        self.max_altitude = cfg.flight_max_altitude
        self.location_home = cfg.location_home
        self.max_flight_lookup = cfg.max_flight_lookup
        self._session = requests.Session()
        self.lock = Lock()
        self.done = Event()

        self.thread = None
        self.data_store = []
        self.new_data_store = False
        self.processing_store = False
        self.error_store = None

    def grab_data(self):
        with self.lock:
            if self.processing_store:
                return False

            self.processing_store = True
            self.new_data_store = False
            self.error_store = None
            self.done.clear()
            self.thread = Thread(
                target=self.grab_data_impl, name="overhead-tar1090-grabber"
            )

        self.thread.start()
        return True

    def refresh(self):
        with self.lock:
            if self.processing_store:
                return False

            self.processing_store = True
            self.new_data_store = False
            self.error_store = None
            self.done.clear()

        self.grab_data_impl()
        return True

    def wait(self, timeout=None):
        finished = self.done.wait(timeout)
        if finished and self.thread is not None:
            self.thread.join()

        return finished

    def grab_data_impl(self):
        data = []

        try:
            response = self._session.get(self.tar1090_url, timeout=10)
            response.raise_for_status()

            aircraft_list = response.json().get("aircraft", [])

            min_alt_ft = self.min_altitude / 0.3048
            max_alt_ft = self.max_altitude / 0.3048
            zone = self.zone_home
            home = self.location_home

            candidates = []
            for ac in aircraft_list:
                lat = ac.get("lat")
                lon = ac.get("lon")
                alt = ac.get("alt_baro")

                if lat is None or lon is None:
                    continue
                if not isinstance(alt, (int, float)):
                    continue
                if not (min_alt_ft < alt < max_alt_ft):
                    continue
                if not in_zone(lat, lon, zone):
                    continue

                candidates.append(ac)

            candidates.sort(
                key=lambda ac: distance_from_home(
                    ac["lat"], ac["lon"], ac["alt_baro"], home
                )
            )

            for ac in candidates[: self.max_flight_lookup]:
                try:
                    callsign = (ac.get("flight") or "").strip()
                    if callsign.upper() in BLANK_FIELDS:
                        callsign = ""

                    # tar1090 provides aircraft type directly from its local DB
                    # (tar1090-db enrichment). We keep this as the primary source
                    # since it's local and instant. adsbdb may fill it in if blank.
                    plane = (ac.get("desc") or "").strip()
                    if plane.upper() in BLANK_FIELDS:
                        plane = ""

                    # mode_s (hex) enables the combined adsbdb endpoint which
                    # returns richer airport info (name, municipality, country)
                    # directly - no airports.json lookup needed for known routes.
                    mode_s = (ac.get("hex") or "").strip().lower() or None
                    route = route_lookup.get_route(callsign, mode_s=mode_s)

                    # Prefer local tar1090 plane type; fall back to adsbdb
                    if not plane:
                        plane = route["plane"]

                    # Telemetry
                    try:
                        ground_speed = int(ac.get("gs", 0) or 0)
                    except (TypeError, ValueError):
                        ground_speed = 0

                    try:
                        heading = int(ac.get("track", 0) or 0)
                    except (TypeError, ValueError):
                        heading = 0

                    data.append(
                        {
                            "plane": plane,
                            "origin": route["origin"],
                            "destination": route["destination"],
                            "origin_name": route["origin_name"],
                            "destination_name": route["destination_name"],
                            "origin_municipality": route["origin_municipality"],
                            "destination_municipality": route["destination_municipality"],
                            "origin_country": route["origin_country"],
                            "destination_country": route["destination_country"],
                            "vertical_speed": ac.get("baro_rate", 0),
                            "altitude": ac.get("alt_baro", 0),
                            "ground_speed": ground_speed,
                            "heading": heading,
                            "callsign": callsign,
                            "icao_callsign": callsign,
                        }
                    )

                except (KeyError, AttributeError, TypeError):
                    continue

            with self.lock:
                self.data_store = data
                self.new_data_store = True
                self.error_store = None
            logger.debug("tar1090 fetch complete - %d flight(s) tracked", len(data))

        except (RequestException, ValueError, KeyError, AttributeError, TypeError) as e:
            with self.lock:
                self.new_data_store = False
                self.error_store = e
            logger.warning("tar1090 fetch failed: %s", e)

        finally:
            with self.lock:
                self.processing_store = False
            self.done.set()

    @property
    def new_data(self):
        with self.lock:
            return self.new_data_store

    @property
    def processing(self):
        with self.lock:
            return self.processing_store

    @property
    def error(self):
        with self.lock:
            return self.error_store

    @property
    def data(self):
        with self.lock:
            self.new_data_store = False
            return list(self.data_store)

    @property
    def data_is_empty(self):
        with self.lock:
            return len(self.data_store) == 0

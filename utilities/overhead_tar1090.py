import math
import requests
from threading import Thread, Lock
from time import sleep, time

from requests.exceptions import ConnectionError
from urllib3.exceptions import NewConnectionError, MaxRetryError

try:
    from config import MIN_ALTITUDE
except (ModuleNotFoundError, NameError, ImportError):
    MIN_ALTITUDE = 0  # feet

try:
    from config import ZONE_HOME, LOCATION_HOME

    ZONE_DEFAULT = ZONE_HOME
    LOCATION_DEFAULT = LOCATION_HOME
except (ModuleNotFoundError, NameError, ImportError):
    ZONE_DEFAULT = {"tl_y": 62.61, "tl_x": -13.07, "br_y": 49.71, "br_x": 3.46}
    LOCATION_DEFAULT = [51.509865, -0.118092, 6371]

try:
    from config import TAR1090_URL
except (ModuleNotFoundError, NameError, ImportError):
    TAR1090_URL = "http://garagepi.local:8080//data/aircraft.json"

ROUTE_CACHE_TTL = 28800  # 8 hours
MAX_FLIGHT_LOOKUP = 5
MAX_ALTITUDE = 10000  # feet
EARTH_RADIUS_KM = 6371
BLANK_FIELDS = ["", "N/A", "NONE"]


def get_route(callsign):
    """
    Look up origin and destination IATA codes for a given callsign.
    Returns a tuple (origin, destination), each an IATA code string or "".
    """
    ADSBDB_BASE_URL = "https://api.adsbdb.com/v0"
    if not callsign or callsign.upper() in BLANK_FIELDS:
        return "", ""

    try:
        response = requests.get(
            f"{ADSBDB_BASE_URL}/callsign/{callsign}",
            timeout=5,
        )
        data = response.json()

        flightroute = data.get("response", {}).get("flightroute", {})
        if not flightroute:
            return "", ""

        origin = flightroute.get("origin", {}).get("iata_code", "") or ""
        destination = flightroute.get("destination", {}).get("iata_code", "") or ""

        if origin.upper() in BLANK_FIELDS:
            origin = ""
        if destination.upper() in BLANK_FIELDS:
            destination = ""

        return origin, destination

    except (ConnectionError, NewConnectionError, MaxRetryError, ValueError, KeyError):
        return "", ""


def _in_zone(lat, lon, zone):
    return zone["br_y"] <= lat <= zone["tl_y"] and zone["tl_x"] <= lon <= zone["br_x"]


def _distance_from_home(lat, lon, alt_ft, home=LOCATION_DEFAULT):
    def polar_to_cartesian(lat, lon, alt):
        DEG2RAD = math.pi / 180
        return [
            alt * math.cos(DEG2RAD * lat) * math.sin(DEG2RAD * lon),
            alt * math.sin(DEG2RAD * lat),
            alt * math.cos(DEG2RAD * lat) * math.cos(DEG2RAD * lon),
        ]

    altitude_km = 0.0003048 * alt_ft + EARTH_RADIUS_KM
    x0, y0, z0 = polar_to_cartesian(lat, lon, altitude_km)
    x1, y1, z1 = polar_to_cartesian(*home)
    return math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2)


class Overhead:
    def __init__(self):
        self._route_cache = {}  # callsign -> (origin, dest, timestamp)
        self._lock = Lock()
        self._data = []
        self._new_data = False
        self._processing = False

    def _get_route(self, callsign):
        if callsign in self._route_cache:
            origin, dest, ts = self._route_cache[callsign]
            if time() - ts < ROUTE_CACHE_TTL:
                return origin, dest

        origin, dest = get_route(callsign)
        self._route_cache[callsign] = (origin, dest, time())
        return origin, dest

    def grab_data(self):
        Thread(target=self._grab_data).start()

    def _grab_data(self):
        with self._lock:
            self._new_data = False
            self._processing = True

        data = []

        try:
            response = requests.get(TAR1090_URL, timeout=10)
            aircraft_list = response.json().get("aircraft", [])

            # Filter to aircraft with a current position, numeric altitude, within bounds
            candidates = []
            for ac in aircraft_list:
                lat = ac.get("lat")
                lon = ac.get("lon")
                alt = ac.get("alt_baro")

                if lat is None or lon is None:
                    continue
                if not isinstance(alt, (int, float)):
                    continue
                if not (MIN_ALTITUDE < alt < MAX_ALTITUDE):
                    continue
                if not _in_zone(lat, lon, ZONE_DEFAULT):
                    continue

                candidates.append(ac)

            # Sort by distance from home
            candidates.sort(
                key=lambda ac: _distance_from_home(ac["lat"], ac["lon"], ac["alt_baro"])
            )

            for ac in candidates[:MAX_FLIGHT_LOOKUP]:
                try:
                    callsign = ac.get("flight", "").strip()
                    if callsign.upper() in BLANK_FIELDS:
                        callsign = ""

                    plane = ac.get("desc", "").strip()
                    if plane.upper() in BLANK_FIELDS:
                        plane = ""

                    origin, destination = (
                        self._get_route(callsign) if callsign else ("", "")
                    )

                    data.append(
                        {
                            "plane": plane,
                            "origin": origin,
                            "destination": destination,
                            "vertical_speed": ac.get("baro_rate", 0),
                            "altitude": ac.get("alt_baro", 0),
                            "callsign": callsign,
                        }
                    )
                except (KeyError, AttributeError):
                    pass

            with self._lock:
                self._new_data = True
                self._processing = False
                self._data = data

        except (ConnectionError, NewConnectionError, MaxRetryError):
            self._new_data = False
            self._processing = False

    @property
    def new_data(self):
        with self._lock:
            return self._new_data

    @property
    def processing(self):
        with self._lock:
            return self._processing

    @property
    def data(self):
        with self._lock:
            self._new_data = False
            return self._data

    @property
    def data_is_empty(self):
        return len(self._data) == 0


# Main function
if __name__ == "__main__":
    o = Overhead()
    o.grab_data()
    while not o.new_data:
        print("processing...")
        sleep(1)

    print(o.data)

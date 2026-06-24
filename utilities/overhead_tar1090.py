import math
import requests

from threading import Thread, Lock, Event
from time import time

from requests.exceptions import RequestException

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
    TAR1090_URL = "http://garagepi.local:8080/data/aircraft.json"


ROUTE_CACHE_TTL = 28800  # 8 hours
MAX_FLIGHT_LOOKUP = 5
MAX_ALTITUDE = 10000  # feet
EARTH_RADIUS_KM = 6371
BLANK_FIELDS = ["", "N/A", "NONE"]


def get_route(callsign):
    """
    Look up origin and destination IATA codes for a given callsign.

    Returns:
        (origin, destination)
    """
    ADSBDB_BASE_URL = "https://api.adsbdb.com/v0"

    if not callsign or callsign.upper() in BLANK_FIELDS:
        return "", ""

    try:
        response = requests.get(
            f"{ADSBDB_BASE_URL}/callsign/{callsign}",
            timeout=5,
        )
        response.raise_for_status()

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

    except (RequestException, ValueError, KeyError, AttributeError):
        return "", ""


def _in_zone(lat, lon, zone):
    return zone["br_y"] <= lat <= zone["tl_y"] and zone["tl_x"] <= lon <= zone["br_x"]


def _distance_from_home(lat, lon, alt_ft, home=LOCATION_DEFAULT):
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


class Overhead:
    def __init__(self):
        self._route_cache = {}
        self._lock = Lock()
        self._done = Event()

        self._thread = None
        self._data = []
        self._new_data = False
        self._processing = False
        self._error = None

    def grab_data(self):
        """
        Start a background data grab.

        Returns:
            True if a new worker was started.
            False if one was already running.
        """
        with self._lock:
            if self._processing:
                return False

            self._processing = True
            self._new_data = False
            self._error = None
            self._done.clear()

            self._thread = Thread(
                target=self._grab_data,
                name="overhead-data-grabber",
            )

        self._thread.start()
        return True

    def wait(self, timeout=None):
        """
        Wait for the background task to finish.

        Returns:
            True if the worker finished.
            False if timeout expired.
        """
        finished = self._done.wait(timeout)

        if finished:
            thread = self._thread
            if thread is not None:
                thread.join()

        return finished

    def _get_route(self, callsign):
        now = time()

        with self._lock:
            cached = self._route_cache.get(callsign)

        if cached is not None:
            origin, dest, ts = cached
            if now - ts < ROUTE_CACHE_TTL:
                return origin, dest

        origin, dest = get_route(callsign)

        with self._lock:
            self._route_cache[callsign] = (origin, dest, time())

        return origin, dest

    def _grab_data(self):
        data = []

        try:
            response = requests.get(TAR1090_URL, timeout=10)
            response.raise_for_status()

            aircraft_list = response.json().get("aircraft", [])

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

            candidates.sort(
                key=lambda ac: _distance_from_home(
                    ac["lat"],
                    ac["lon"],
                    ac["alt_baro"],
                )
            )

            for ac in candidates[:MAX_FLIGHT_LOOKUP]:
                try:
                    callsign = ac.get("flight", "").strip()
                    if callsign.upper() in BLANK_FIELDS:
                        callsign = ""

                    plane = ac.get("desc", "").strip()
                    if plane.upper() in BLANK_FIELDS:
                        plane = ""

                    if callsign:
                        origin, destination = self._get_route(callsign)
                    else:
                        origin, destination = "", ""

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

                except (KeyError, AttributeError, TypeError):
                    continue

            with self._lock:
                self._data = data
                self._new_data = True
                self._error = None

        except (RequestException, ValueError, KeyError, AttributeError, TypeError) as e:
            with self._lock:
                self._new_data = False
                self._error = e

        finally:
            with self._lock:
                self._processing = False

            self._done.set()

    def refresh(self):
        """
        Run the data grab synchronously.
        """
        with self._lock:
            if self._processing:
                return False

            self._processing = True
            self._new_data = False
            self._error = None
            self._done.clear()

        self._grab_data()
        return True

    @property
    def new_data(self):
        with self._lock:
            return self._new_data

    @property
    def processing(self):
        with self._lock:
            return self._processing

    @property
    def error(self):
        with self._lock:
            return self._error

    @property
    def data(self):
        with self._lock:
            self._new_data = False
            return list(self._data)

    @property
    def data_is_empty(self):
        with self._lock:
            return len(self._data) == 0


if __name__ == "__main__":
    o = Overhead()
    o.refresh()

    if o.error is not None:
        print(f"failed: {o.error}")
    else:
        print(o.data)

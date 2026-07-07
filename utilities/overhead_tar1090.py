import json
import logging
import math
import requests

from threading import Thread, Lock, Event
from time import time
from pathlib import Path

from requests.exceptions import RequestException
from utilities import routes_cache

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371
BLANK_FIELDS = ["", "N/A", "NONE"import math
import requests

from threading import Thread, Lock, Event
from time import time

from requests.exceptions import RequestException

try:
    from config import MIN_ALTITUDE, MAX_ALTITUDE
except (ModuleNotFoundError, NameError, ImportError):
    MIN_ALTITUDE = 0  # feet
    MAX_ALTITUDE = 10000 # feet

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
EARTH_RADIUS_KM = 6371
BLANK_FIELDS = ["", "N/A", "NONE"]


def lookup_route(callsign: str, lat: float | None = None, lng: float | None = None) -> dict | None:
    """
    Look up flight route info from the adsb.im route API.

    Args:
        callsign: Aircraft callsign (e.g. "BAW123").
        lat:      Current latitude  (optional, improves disambiguation).
        lng:      Current longitude (optional, improves disambiguation).

    Returns:
        Dict with route data (callsign, _airports, plausible, ...) or None on failure.
    """
    payload = {"planes": [{"callsign": callsign, "lat": lat, "lng": lng}]}
    resp = requests.post(
        "https://adsb.im/api/0/routeset",
        json=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=15,
    )
    resp.raise_for_status()
    routes = resp.json()
    if not routes:
        return None
    return routes[0]


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

    def _get_route(self, callsign, lat=None, lng=None):
        now = time()

        with self._lock:
            cached = self._route_cache.get(callsign)

        if cached is not None:
            origin, dest, ts = cached
            if now - ts < ROUTE_CACHE_TTL:
                return origin, dest

        origin, dest = "", ""

        try:
            route = lookup_route(callsign, lat, lng)
            if route and route.get("_airports"):
                airports = route["_airports"]
                origin = airports[0].get("iata", "") or ""
                dest = airports[-1].get("iata", "") or ""

                if origin.upper() in BLANK_FIELDS:
                    origin = ""

                if dest.upper() in BLANK_FIELDS:
                    dest = ""
        except (RequestException, ValueError, KeyError, AttributeError, TypeError):
            pass

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
                        origin, destination = self._get_route(
                            callsign, ac.get("lat"), ac.get("lon")
                        )
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
    from time import sleep, strftime

    REFRESH_DELAY = 3

    def print_flights(flights):
        if not flights:
            print("  No aircraft currently visible.")
            return

        for index, flight in enumerate(flights, start=1):
            callsign = flight.get("callsign") or "unknown"
            plane = flight.get("plane") or "unknown aircraft"
            origin = flight.get("origin") or "?"
            destination = flight.get("destination") or "?"
            altitude = flight.get("altitude", 0)
            vertical_speed = flight.get("vertical_speed", 0)

            route = f"{origin} -> {destination}"

            print(f"  {index}. {callsign}")
            print(f"     Aircraft : {plane}")
            print(f"     Route    : {route}")
            print(f"     Altitude : {altitude} ft")
            print(f"     V/S      : {vertical_speed} ft/min")

    o = Overhead()

    print("Overhead aircraft test")
    print("Press Ctrl-C to quit.")
    print()

    try:
        while True:
            print(f"[{strftime('%H:%M:%S')}] Refreshing...")

            o.refresh()

            if o.error is not None:
                print(f"  Failed: {o.error}")
            else:
                print_flights(o.data)

            print()
            sleep(REFRESH_DELAY)

    except KeyboardInterrupt:
        print()
        print("Exiting.")
]

# ---------------------------------------------------------------------------
# Airport name lookup (bundled airports.json)
# ---------------------------------------------------------------------------

airports_cache: dict[str, str] = {}
airports_loaded = False


def load_airports():
    global airports_cache, airports_loaded

    if airports_loaded:
        return

    path = Path(__file__).parent.parent / "assets" / "airports.json"
    if path.exists():
        try:
            with open(path) as fh:
                airports_cache = json.load(fh)

        except Exception:
            airports_cache = {}

    airports_loaded = True


def airport_name(iata: str) -> str:
    load_airports()
    return airports_cache.get(iata.upper(), "")


# ---------------------------------------------------------------------------
# Route lookup (adsb.im)
# ---------------------------------------------------------------------------


def lookup_route(callsign: str, lat=None, lng=None) -> dict | None:
    payload = {"planes": [{"callsign": callsign, "lat": lat, "lng": lng}]}
    resp = requests.post(
        "https://adsb.im/api/0/routeset",
        json=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        timeout=15,
    )
    resp.raise_for_status()
    routes = resp.json()
    return routes[0] if routes else None


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

    def get_route(self, callsign, lat=None, lng=None):
        # Check persistent cache first (24h TTL)
        cached = routes_cache.get(callsign) if callsign else None
        if cached is not None:
            return cached.get("origin", ""), cached.get("destination", "")

        # Cache miss — fetch from adsb.im
        origin, dest = "", ""
        try:
            route = lookup_route(callsign, lat, lng)

            if route and route.get("_airports"):
                airports = route["_airports"]
                origin = airports[0].get("iata", "") or ""
                dest = airports[-1].get("iata", "") or ""

                if origin.upper() in BLANK_FIELDS:
                    origin = ""

                if dest.upper() in BLANK_FIELDS:
                    dest = ""

        except (RequestException, ValueError, KeyError, AttributeError, TypeError):
            pass

        # Cache the route info for 24 hours
        if callsign and (origin or dest):
            routes_cache.put(callsign, {
                "plane": "",
                "origin": origin,
                "destination": dest,
                "origin_name": "",
                "destination_name": "",
            })

        return origin, dest

    def grab_data_impl(self):
        data = []

        try:
            response = requests.get(self.tar1090_url, timeout=10)
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

                    plane = (ac.get("desc") or "").strip()
                    if plane.upper() in BLANK_FIELDS:
                        plane = ""

                    if callsign:
                        origin, destination = self.get_route(
                            callsign, ac.get("lat"), ac.get("lon")
                        )
                    else:
                        origin, destination = "", ""

                    # Full names from bundled airport database
                    origin_name = airport_name(origin) if origin else ""
                    destination_name = airport_name(destination) if destination else ""

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
                            "origin": origin,
                            "destination": destination,
                            "origin_name": origin_name,
                            "destination_name": destination_name,
                            "vertical_speed": ac.get("baro_rate", 0),
                            "altitude": ac.get("alt_baro", 0),
                            "ground_speed": ground_speed,
                            "heading": heading,
                            "callsign": callsign,
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

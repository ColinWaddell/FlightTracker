from FlightRadar24.api import FlightRadar24API

from threading import Thread, Lock, Event
from time import sleep
import math

from requests.exceptions import RequestException, ConnectionError
from urllib3.exceptions import NewConnectionError, MaxRetryError

try:
    from config import MIN_ALTITUDE
except (ModuleNotFoundError, NameError, ImportError):
    MIN_ALTITUDE = 0  # feet


RETRIES = 3
RATE_LIMIT_DELAY = 1
MAX_FLIGHT_LOOKUP = 5
MAX_ALTITUDE = 10000  # feet
EARTH_RADIUS_KM = 6371
BLANK_FIELDS = ["", "N/A", "NONE"]


try:
    from config import ZONE_HOME, LOCATION_HOME

    ZONE_DEFAULT = ZONE_HOME
    LOCATION_DEFAULT = LOCATION_HOME
except (ModuleNotFoundError, NameError, ImportError):
    ZONE_DEFAULT = {"tl_y": 62.61, "tl_x": -13.07, "br_y": 49.71, "br_x": 3.46}
    LOCATION_DEFAULT = [51.509865, -0.118092, EARTH_RADIUS_KM]


def _clean_field(value):
    if value is None:
        return ""

    try:
        value = value.strip()
    except AttributeError:
        value = str(value).strip()

    if value.upper() in BLANK_FIELDS:
        return ""

    return value


def distance_from_flight_to_home(flight, home=LOCATION_DEFAULT):
    def polar_to_cartesian(lat, lon, alt):
        deg2rad = math.pi / 180

        return [
            alt * math.cos(deg2rad * lat) * math.sin(deg2rad * lon),
            alt * math.sin(deg2rad * lat),
            alt * math.cos(deg2rad * lat) * math.cos(deg2rad * lon),
        ]

    def feet_to_km_plus_earth(altitude_ft):
        altitude_km = 0.0003048 * altitude_ft
        return altitude_km + EARTH_RADIUS_KM

    try:
        x0, y0, z0 = polar_to_cartesian(
            flight.latitude,
            flight.longitude,
            feet_to_km_plus_earth(flight.altitude),
        )

        x1, y1, z1 = polar_to_cartesian(*home)

        return math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2)

    except (AttributeError, TypeError, ValueError):
        return 1e6


class Overhead:
    def __init__(self):
        self._api = FlightRadar24API()
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
                name="overhead-flightradar24-grabber",
            )

        self._thread.start()
        return True

    def refresh(self):
        """
        Run the data grab synchronously.

        Returns:
            True if the refresh was started.
            False if one was already running.
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

    def _grab_data(self):
        data = []

        try:
            bounds = self._api.get_bounds(ZONE_DEFAULT)
            flights = self._api.get_flights(bounds=bounds)

            flights = [
                flight
                for flight in flights
                if isinstance(flight.altitude, (int, float))
                and MIN_ALTITUDE < flight.altitude < MAX_ALTITUDE
            ]

            flights = sorted(flights, key=distance_from_flight_to_home)

            for flight in flights[:MAX_FLIGHT_LOOKUP]:
                retries = RETRIES

                while retries:
                    sleep(RATE_LIMIT_DELAY)

                    try:
                        details = self._api.get_flight_details(flight)

                        try:
                            plane = details["aircraft"]["model"]["text"]
                        except (KeyError, TypeError):
                            plane = ""

                        plane = _clean_field(plane)
                        origin = _clean_field(flight.origin_airport_iata)
                        destination = _clean_field(flight.destination_airport_iata)
                        callsign = _clean_field(flight.callsign)

                        data.append(
                            {
                                "plane": plane,
                                "origin": origin,
                                "destination": destination,
                                "vertical_speed": flight.vertical_speed,
                                "altitude": flight.altitude,
                                "callsign": callsign,
                            }
                        )

                        break

                    except (KeyError, AttributeError, TypeError):
                        retries -= 1

            with self._lock:
                self._data = data
                self._new_data = True
                self._error = None

        except (
            RequestException,
            ConnectionError,
            NewConnectionError,
            MaxRetryError,
            KeyError,
            AttributeError,
            TypeError,
            ValueError,
        ) as e:
            with self._lock:
                self._new_data = False
                self._error = e

        finally:
            with self._lock:
                self._processing = False

            self._done.set()

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

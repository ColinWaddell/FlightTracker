from FlightRadar24.api import FlightRadar24API

from threading import Thread, Lock, Event
from time import sleep

from requests.exceptions import RequestException, ConnectionError
from urllib3.exceptions import NewConnectionError, MaxRetryError

from setup.configuration import Config

RETRIES = 3
RATE_LIMIT_DELAY = 1
MAX_FLIGHT_LOOKUP = 5
EARTH_RADIUS_KM = 6371
BLANK_FIELDS = ["", "N/A", "NONE"]


def _clean_field(value):
    if value is None:
        return ""
    try:
        value = value.strip()
    except AttributeError:
        value = str(value).strip()
    return "" if value.upper() in BLANK_FIELDS else value


def distance_from_flight_to_home(flight, cfg: Config):
    import math

    def polar_to_cartesian(lat, lon, alt):
        deg2rad = math.pi / 180
        return [
            alt * math.cos(deg2rad * lat) * math.sin(deg2rad * lon),
            alt * math.sin(deg2rad * lat),
            alt * math.cos(deg2rad * lat) * math.cos(deg2rad * lon),
        ]

    def feet_to_km_plus_earth(altitude_ft):
        return 0.0003048 * altitude_ft + EARTH_RADIUS_KM

    home = cfg.location_home
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

        # Configure FR24 to exclude ground traffic
        flight_tracker = self._api.get_flight_tracker_config()
        flight_tracker.gnd = 0
        self._api.set_flight_tracker_config(flight_tracker)

    def grab_data(self):
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
        finished = self._done.wait(timeout)
        if finished and self._thread is not None:
            self._thread.join()
        return finished

    def _grab_data(self):
        data = []
        cfg = Config.instance()

        try:
            bounds = self._api.get_bounds(cfg.zone_home)
            flights = self._api.get_flights(bounds=bounds)

            min_alt_ft = cfg.flight_min_altitude / 0.3048
            max_alt_ft = cfg.flight_max_altitude / 0.3048

            flights = [
                f
                for f in flights
                if isinstance(f.altitude, (int, float))
                and min_alt_ft < f.altitude < max_alt_ft
            ]

            flights = sorted(
                flights, key=lambda f: distance_from_flight_to_home(f, cfg)
            )

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

                        # Full airport names from detail lookup
                        try:
                            origin_name = details["airport"]["origin"]["name"] or ""
                        except (KeyError, TypeError):
                            origin_name = ""

                        try:
                            destination_name = (
                                details["airport"]["destination"]["name"] or ""
                            )
                        except (KeyError, TypeError):
                            destination_name = ""

                        # Telemetry
                        try:
                            ground_speed = int(flight.ground_speed)
                        except (TypeError, ValueError):
                            ground_speed = 0

                        try:
                            heading = int(flight.heading)
                        except (TypeError, ValueError):
                            heading = 0

                        data.append(
                            {
                                "plane": plane,
                                "origin": origin,
                                "destination": destination,
                                "origin_name": origin_name[:80],
                                "destination_name": destination_name[:80],
                                "vertical_speed": flight.vertical_speed,
                                "altitude": flight.altitude,
                                "ground_speed": ground_speed,
                                "heading": heading,
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

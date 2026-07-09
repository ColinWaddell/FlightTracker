from threading import Thread, Lock, Event
from time import sleep
import logging

from requests.exceptions import RequestException, ConnectionError
from utilities import routes_cache
from urllib3.exceptions import NewConnectionError, MaxRetryError

try:
    from curl_cffi.requests.exceptions import Timeout as CurlTimeout
except ImportError:
    CurlTimeout = None

logger = logging.getLogger(__name__)

RETRIES = 3
RATE_LIMIT_DELAY = 1
FR24_TIMEOUT = 60  # seconds - default 30 is too short for Pi on slow networks
EARTH_RADIUS_KM = 6371
BLANK_FIELDS = ["", "N/A", "NONE"]


def clean_field(value):
    if value is None:
        return ""
    try:
        value = value.strip()
    except AttributeError:
        value = str(value).strip()
    return "" if value.upper() in BLANK_FIELDS else value


def distance_from_flight_to_home(flight, location_home):
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

    home = location_home
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
        # Lazy import - FlightRadar24API drags in curl_cffi + brotli (~4.7s on Pi)
        from FlightRadar24.api import FlightRadar24API

        from setup.configuration import Config

        cfg = Config.instance()
        self.zone_home = cfg.zone_home
        self.min_altitude = cfg.flight_min_altitude
        self.max_altitude = cfg.flight_max_altitude
        self.location_home = cfg.location_home
        self.max_flight_lookup = cfg.max_flight_lookup

        self.api = FlightRadar24API(timeout=FR24_TIMEOUT)
        self.lock = Lock()
        self.done = Event()

        self.thread = None
        self.data_store = []
        self.new_data_store = False
        self.processing_store = False
        self.error_store = None

        # Configure FR24 to exclude ground traffic
        flight_tracker = self.api.get_flight_tracker_config()
        flight_tracker.gnd = 0
        self.api.set_flight_tracker_config(flight_tracker)

    def grab_data(self):
        with self.lock:
            if self.processing_store:
                return False
            self.processing_store = True
            self.new_data_store = False
            self.error_store = None
            self.done.clear()
            self.thread = Thread(
                target=self.grab_data_impl,
                name="overhead-flightradar24-grabber",
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
            # Clear cookies before each fetch to avoid FR24 rate-limiting
            # on subsequent calls (stale cookies cause empty results)
            try:
                self.api._FlightRadar24API__client.clear_cookies()
            except Exception:
                pass

            bounds = self.api.get_bounds(self.zone_home)
            flights = self.api.get_flights(bounds=bounds)

            min_alt_ft = self.min_altitude / 0.3048
            max_alt_ft = self.max_altitude / 0.3048

            flights = [
                f
                for f in flights
                if isinstance(f.altitude, (int, float))
                and min_alt_ft < f.altitude < max_alt_ft
            ]

            flights = sorted(
                flights,
                key=lambda f: distance_from_flight_to_home(f, self.location_home),
            )

            for flight in flights[: self.max_flight_lookup]:
                callsign = clean_field(flight.callsign)

                #number = IATA
                #callsign = ICAO

                # Check route cache first - avoids expensive API lookups
                cached = routes_cache.get(callsign) if callsign else None

                if cached is not None:
                    plane = cached.get("plane", "")
                    origin = cached.get("origin", "")
                    destination = cached.get("destination", "")
                    origin_name = cached.get("origin_name", "")
                    destination_name = cached.get("destination_name", "")
                else:
                    # Cache miss - fetch details from FR24 API
                    retries = RETRIES
                    details = None
                    while retries:
                        sleep(RATE_LIMIT_DELAY)
                        try:
                            details = self.api.get_flight_details(flight)
                            break
                        except (KeyError, AttributeError, TypeError, Exception) as e:
                            if CurlTimeout and isinstance(e, CurlTimeout):
                                logger.debug(
                                    "FR24 flight detail timeout, retrying (%d left)",
                                    retries - 1,
                                )
                            elif isinstance(e, (KeyError, AttributeError, TypeError)):
                                pass
                            else:
                                logger.debug("FR24 flight detail error: %s", e)
                            retries -= 1

                    if details is not None:
                        try:
                            plane = details["aircraft"]["model"]["text"]
                        except (KeyError, TypeError):
                            plane = ""
                        plane = clean_field(plane)

                        origin = clean_field(flight.origin_airport_iata)
                        destination = clean_field(flight.destination_airport_iata)

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

                        # Cache the route info for 24 hours
                        if callsign:
                            routes_cache.put(
                                callsign,
                                {
                                    "plane": plane,
                                    "origin": origin,
                                    "destination": destination,
                                    "origin_name": origin_name[:80],
                                    "destination_name": destination_name[:80],
                                },
                            )
                    else:
                        # All retries failed - use what we have from the flight object
                        plane = ""
                        origin = clean_field(flight.origin_airport_iata)
                        destination = clean_field(flight.destination_airport_iata)
                        origin_name = ""
                        destination_name = ""

                # Telemetry (always from live flight object, not cached)
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

            with self.lock:
                self.data_store = data
                self.new_data_store = True
                self.error_store = None
            logger.debug("FR24 fetch complete - %d flight(s) tracked", len(data))

        except Exception as e:
            # Broad catch - curl_cffi raises its own Timeout/ConnectionError
            # types that don't inherit from requests.exceptions, so listing
            # them individually is fragile. Log and set error state gracefully.
            with self.lock:
                self.new_data_store = False
                self.error_store = e
            logger.warning("FR24 fetch failed: %s", e)

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


if __name__ == "__main__":
    o = Overhead()
    o.refresh()
    if o.error is not None:
        print(f"failed: {o.error}")
    else:
        print(o.data)

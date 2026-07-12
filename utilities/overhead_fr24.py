import contextlib
import logging
from threading import Event, Lock, Thread
from time import sleep

from utilities import routes_cache
from utilities.flight import Flight
from utilities.overhead_utilities import (
    airport_info,
    clean_field,
    distance_from_home,
)

try:
    from curl_cffi.requests.exceptions import Timeout as CurlTimeout
except ImportError:
    CurlTimeout = None

logger = logging.getLogger(__name__)

RETRIES = 3
RATE_LIMIT_DELAY = 1
FR24_TIMEOUT = 60  # seconds - default 30 is too short for Pi on slow networks


def distance_from_flight_to_home(flight, location_home):
    """Distance from a FR24 flight object to home.

    Thin adapter that extracts lat/lon/alt from the flight object and
    delegates to :func:`overhead_utilities.distance_from_home`.
    """
    try:
        return distance_from_home(
            flight.latitude, flight.longitude, flight.altitude, location_home
        )
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
        self.callsign_format = cfg.callsign_format

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
            with contextlib.suppress(Exception):
                self.api._FlightRadar24API__client.clear_cookies()

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
                # ICAO callsign is always used as the route-cache key.
                # The displayed identifier can be IATA (flight.number) or ICAO.
                icao_callsign = clean_field(flight.callsign)
                if self.callsign_format == "iata":
                    display_callsign = clean_field(flight.number) or icao_callsign
                else:
                    display_callsign = icao_callsign

                # Check route cache first - avoids expensive API lookups
                cached = routes_cache.get(icao_callsign) if icao_callsign else None

                if cached is not None:
                    plane = cached.get("plane", "")
                    origin = cached.get("origin", "")
                    destination = cached.get("destination", "")
                else:
                    # Cache miss - fetch details from FR24 API (for plane model only)
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

                        # Cache the route info for 24 hours
                        if icao_callsign:
                            routes_cache.put(
                                icao_callsign,
                                {
                                    "plane": plane,
                                    "origin": origin,
                                    "destination": destination,
                                },
                            )
                    else:
                        # All retries failed - use what we have from the flight object
                        plane = ""
                        origin = clean_field(flight.origin_airport_iata)
                        destination = clean_field(flight.destination_airport_iata)

                # Airport names / municipality / country from bundled airports.json
                origin_info = airport_info(origin) if origin else {}
                dest_info = airport_info(destination) if destination else {}

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
                    Flight(
                        plane=plane,
                        origin=origin,
                        destination=destination,
                        origin_name=origin_info.get("name", ""),
                        destination_name=dest_info.get("name", ""),
                        origin_municipality=origin_info.get("municipality", ""),
                        destination_municipality=dest_info.get("municipality", ""),
                        origin_country=origin_info.get("country_name", ""),
                        destination_country=dest_info.get("country_name", ""),
                        vertical_speed=flight.vertical_speed,
                        altitude=flight.altitude,
                        ground_speed=ground_speed,
                        heading=heading,
                        callsign=display_callsign,
                        icao_callsign=icao_callsign,
                    )
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

from FlightRadarAPI import FlightRadar24API
from pyadsbdb import Client as AdsbdbClient
from threading import Thread, Lock
from time import sleep, time
import math

from requests.exceptions import ConnectionError
from urllib3.exceptions import NewConnectionError
from urllib3.exceptions import MaxRetryError

try:
    # Attempt to load config data
    from config import MIN_ALTITUDE

except (ModuleNotFoundError, NameError, ImportError):
    # If there's no config data
    MIN_ALTITUDE = 0  # feet

RETRIES = 3
RATE_LIMIT_DELAY = 1
ROUTE_CACHE_TTL = 28800  # 8 hours
MAX_FLIGHT_LOOKUP = 5
MAX_ALTITUDE = 10000  # feet
EARTH_RADIUS_KM = 6371
BLANK_FIELDS = ["", "N/A", "NONE"]

try:
    # Attempt to load config data
    from config import ZONE_HOME, LOCATION_HOME

    ZONE_DEFAULT = ZONE_HOME
    LOCATION_DEFAULT = LOCATION_HOME

except (ModuleNotFoundError, NameError, ImportError):
    # If there's no config data
    ZONE_DEFAULT = {"tl_y": 62.61, "tl_x": -13.07, "br_y": 49.71, "br_x": 3.46}
    LOCATION_DEFAULT = [51.509865, -0.118092, EARTH_RADIUS_KM]


def distance_from_flight_to_home(flight, home=LOCATION_DEFAULT):
    def polar_to_cartesian(lat, long, alt):
        DEG2RAD = math.pi / 180
        return [
            alt * math.cos(DEG2RAD * lat) * math.sin(DEG2RAD * long),
            alt * math.sin(DEG2RAD * lat),
            alt * math.cos(DEG2RAD * lat) * math.cos(DEG2RAD * long),
        ]

    def feet_to_meters_plus_earth(altitude_ft):
        altitude_km = 0.0003048 * altitude_ft
        return altitude_km + EARTH_RADIUS_KM

    try:
        (x0, y0, z0) = polar_to_cartesian(
            flight.latitude,
            flight.longitude,
            feet_to_meters_plus_earth(flight.altitude),
        )

        (x1, y1, z1) = polar_to_cartesian(*home)

        dist = math.sqrt((x1 - x0) ** 2 + (y1 - y0) ** 2 + (z1 - z0) ** 2)

        return dist

    except AttributeError:
        # on error say it's far away
        return 1e6


class Overhead:
    def __init__(self):
        self._api = FlightRadar24API()
        self._adsbdb = AdsbdbClient()
        self._route_cache = {}    # callsign -> (origin, dest, timestamp)
        self._aircraft_cache = {} # mode_s -> plane type string
        self._lock = Lock()
        self._data = []
        self._new_data = False
        self._processing = False

    def _get_route(self, callsign):
        if callsign in self._route_cache:
            origin, dest, ts = self._route_cache[callsign]
            if time() - ts < ROUTE_CACHE_TTL:
                return origin, dest
        route_data = self._adsbdb.get_flight_route(callsign)
        if "error" not in route_data:
            flightroute = route_data.get("response", {}).get("flightroute", {})
            origin = flightroute.get("origin", {}).get("iata_code", "") or ""
            dest = flightroute.get("destination", {}).get("iata_code", "") or ""
            self._route_cache[callsign] = (origin, dest, time())
            return origin, dest
        return "", ""

    def _get_aircraft_type(self, mode_s):
        if mode_s in self._aircraft_cache:
            return self._aircraft_cache[mode_s]
        aircraft_data = self._adsbdb.get_aircraft_data(mode_s)
        if isinstance(aircraft_data, dict) and "error" not in aircraft_data:
            aircraft = aircraft_data.get("response", {}).get("aircraft", {})
            manufacturer = aircraft.get("manufacturer", "") or ""
            plane_type = aircraft.get("type", "") or ""
            if manufacturer.upper() in BLANK_FIELDS:
                manufacturer = ""
            if plane_type.upper() in BLANK_FIELDS:
                plane_type = ""
            plane = f"{manufacturer} {plane_type}".strip()
            self._aircraft_cache[mode_s] = plane
            return plane
        self._aircraft_cache[mode_s] = ""
        return ""

    def grab_data(self):
        Thread(target=self._grab_data).start()

    def _grab_data(self):
        # Mark data as old
        with self._lock:
            self._new_data = False
            self._processing = True

        data = []

        # Grab flight details
        try:
            bounds = self._api.get_bounds(ZONE_DEFAULT)
            flights = self._api.get_flights(bounds=bounds)

            # Sort flights by closest first
            flights = [
                f
                for f in flights
                if f.altitude < MAX_ALTITUDE and f.altitude > MIN_ALTITUDE
            ]
            flights = sorted(flights, key=lambda f: distance_from_flight_to_home(f))

            for flight in flights[:MAX_FLIGHT_LOOKUP]:
                # Rate limit protection
                sleep(RATE_LIMIT_DELAY)

                try:
                    callsign = (
                        flight.callsign
                        if not (flight.callsign.upper() in BLANK_FIELDS)
                        else ""
                    )

                    # Look up route (origin/destination) via adsbdb, fall back to FR24
                    origin, destination = self._get_route(callsign) if callsign else ("", "")
                    if not origin:
                        origin = (
                            flight.origin_airport_iata
                            if not (flight.origin_airport_iata.upper() in BLANK_FIELDS)
                            else ""
                        )
                    if not destination:
                        destination = (
                            flight.destination_airport_iata
                            if not (flight.destination_airport_iata.upper() in BLANK_FIELDS)
                            else ""
                        )

                    plane = self._get_aircraft_type(flight.registration) if flight.registration else ""

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

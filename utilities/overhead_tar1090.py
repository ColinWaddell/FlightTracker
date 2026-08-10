import logging
import time
from threading import Event, Lock, Thread

import requests
from requests.exceptions import RequestException

from assets.airlines.convert import icao_flight_to_iata
from utilities import route_lookup, routes_cache
from utilities.flight import Flight
from utilities.overhead_utilities import (
    clean_field,
    distance_from_home,
    in_zone,
)

logger = logging.getLogger(__name__)


def _url_error_flight() -> Flight:
    """Return a fake flight entry displayed when the tar1090 URL is unreachable."""
    return Flight(
        plane="Check tar1090 URL",
        callsign="URL ERROR",
        icao_callsign="URL ERROR",
    )


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
        self.callsign_format = cfg.callsign_format
        self._session = requests.Session()
        self.lock = Lock()
        self.done = Event()

        self.thread = None
        self.data_store = []
        self.new_data_store = False
        self.processing_store = False
        self.error_store = None
        self.last_updated = None

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

            # readsb/tar1090 uses alt_baro, gs, baro_rate, desc
            # dump1090 (and older forks) uses altitude, speed, vert_rate
            # Accept either field name so the parser works with both.
            candidates = []
            for ac in aircraft_list:
                lat = ac.get("lat")
                lon = ac.get("lon")
                alt = ac.get("alt_baro")
                if alt is None:
                    alt = ac.get("altitude")

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
                    ac["lat"], ac["lon"], ac.get("alt_baro") or ac.get("altitude"), home
                )
            )

            for ac in candidates[: self.max_flight_lookup]:
                try:
                    callsign = clean_field(ac.get("flight"))

                    # tar1090 provides aircraft type directly from its local DB
                    # (tar1090-db enrichment, requires --db-file-lt flag). We keep
                    # this as the primary source since it's local and instant.
                    # hexdb may fill it in if blank.
                    plane = clean_field(ac.get("desc"))

                    # mode_s (hex) enables the hexdb aircraft endpoint which
                    # returns the aircraft type, complementing the route lookup
                    # that returns origin/destination airport info.
                    mode_s = (ac.get("hex") or "").strip().lower() or None

                    # Live position + speed feed the FR24 bounds fallback when
                    # hexdb has no route/aircraft data.  tar1090 reports ground
                    # speed in knots; convert to m/s for get_route.
                    lat = ac.get("lat")
                    lng = ac.get("lon")
                    try:
                        gs_knots = float(ac.get("gs") or ac.get("speed") or 0)
                    except (TypeError, ValueError):
                        gs_knots = 0.0
                    ground_speed_mps = gs_knots * 0.514444

                    route = route_lookup.get_route(
                        callsign,
                        mode_s=mode_s,
                        lat=lat,
                        lng=lng,
                        ground_speed_mps=ground_speed_mps,
                    )

                    # Prefer local tar1090 plane type; fall back to hexdb
                    if not plane:
                        plane = route.plane

                    # The tar1090 feed only exposes the ICAO callsign.  When
                    # the user has selected the IATA display format, translate
                    # the ICAO callsign (e.g. BAW147) to its IATA form (BA147);
                    # fall back to the ICAO callsign if no mapping exists.
                    icao_callsign = callsign
                    if self.callsign_format == "iata":
                        display_callsign = icao_flight_to_iata(callsign) or callsign
                    else:
                        display_callsign = callsign

                    # Telemetry
                    try:
                        ground_speed = int(ac.get("gs") or ac.get("speed") or 0)
                    except (TypeError, ValueError):
                        ground_speed = 0

                    try:
                        heading = int(ac.get("track", 0) or 0)
                    except (TypeError, ValueError):
                        heading = 0

                    data.append(
                        Flight.from_route(
                            route,
                            plane=plane,
                            callsign=display_callsign,
                            icao_callsign=icao_callsign,
                            altitude=ac.get("alt_baro") or ac.get("altitude") or 0,
                            ground_speed=ground_speed,
                            heading=heading,
                            # baro_rate/vert_rate may be None when the
                            # transponder doesn't report vertical rate;
                            # default to 0 to keep the Flight.vertical_speed
                            # field an int, not None.
                            vertical_speed=ac.get("baro_rate")
                            or ac.get("vert_rate")
                            or 0,
                        )
                    )

                except (KeyError, AttributeError, TypeError):
                    continue

            with self.lock:
                self.data_store = data
                self.new_data_store = True
                self.error_store = None
                self.last_updated = time.time()
            logger.debug("tar1090 fetch complete - %d flight(s) tracked", len(data))

        except (RequestException, ValueError, KeyError, AttributeError, TypeError) as e:
            # Surface a visible placeholder so the display shows something useful
            # rather than going blank. Any exception here means the URL is wrong
            # or the receiver is unreachable.
            logger.warning("tar1090 fetch failed: %s", e)
            with self.lock:
                self.data_store = [_url_error_flight()]
                self.new_data_store = True
                self.error_store = None

        finally:
            with self.lock:
                self.processing_store = False
            self.done.set()
            # Flush the route cache once per poll cycle rather than on every
            # individual put() to reduce SD-card writes on Raspberry Pi.
            routes_cache.flush()

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

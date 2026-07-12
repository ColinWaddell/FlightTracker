import logging
from threading import Event, Lock, Thread

import requests
from requests.exceptions import RequestException

from utilities import route_lookup
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
                    callsign = clean_field(ac.get("flight"))

                    # tar1090 provides aircraft type directly from its local DB
                    # (tar1090-db enrichment). We keep this as the primary source
                    # since it's local and instant. adsbdb may fill it in if blank.
                    plane = clean_field(ac.get("desc"))

                    # mode_s (hex) enables the combined adsbdb endpoint which
                    # returns richer airport info (name, municipality, country)
                    # directly - no airports.json lookup needed for known routes.
                    mode_s = (ac.get("hex") or "").strip().lower() or None
                    route = route_lookup.get_route(callsign, mode_s=mode_s)

                    # Prefer local tar1090 plane type; fall back to adsbdb
                    if not plane:
                        plane = route.plane

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
                        Flight.from_route(
                            route,
                            plane=plane,
                            callsign=callsign,
                            icao_callsign=callsign,
                            altitude=ac.get("alt_baro", 0),
                            ground_speed=ground_speed,
                            heading=heading,
                            vertical_speed=ac.get("baro_rate", 0),
                        )
                    )

                except (KeyError, AttributeError, TypeError):
                    continue

            with self.lock:
                self.data_store = data
                self.new_data_store = True
                self.error_store = None
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

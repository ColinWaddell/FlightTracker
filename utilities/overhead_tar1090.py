import json
import math
import requests

from threading import Thread, Lock, Event
from time import time
from pathlib import Path

from requests.exceptions import RequestException

ROUTE_CACHE_TTL = 28800  # 8 hours
EARTH_RADIUS_KM = 6371
BLANK_FIELDS = ["", "N/A", "NONE"]

# ---------------------------------------------------------------------------
# Airport name lookup (bundled airports.json)
# ---------------------------------------------------------------------------

_airports: dict[str, str] = {}
_airports_loaded = False


def _load_airports():
    global _airports, _airports_loaded
    if _airports_loaded:
        return
    path = Path(__file__).parent.parent / "assets" / "airports.json"
    if path.exists():
        try:
            with open(path) as fh:
                _airports = json.load(fh)
        except Exception:
            _airports = {}
    _airports_loaded = True


def airport_name(iata: str) -> str:
    _load_airports()
    return _airports.get(iata.upper(), "")


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


def _in_zone(lat, lon, zone):
    return zone["br_y"] <= lat <= zone["tl_y"] and zone["tl_x"] <= lon <= zone["br_x"]


def _distance_from_home(lat, lon, alt_ft, home):
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

        _cfg = Config.instance()
        self._tar1090_url = _cfg.tar1090_url
        self._zone_home = _cfg.zone_home
        self._min_altitude = _cfg.flight_min_altitude
        self._max_altitude = _cfg.flight_max_altitude
        self._location_home = _cfg.location_home

        self._route_cache: dict[str, tuple] = {}
        self._lock = Lock()
        self._done = Event()

        self._thread = None
        self._data = []
        self._new_data = False
        self._processing = False
        self._error = None

    def grab_data(self):
        with self._lock:
            if self._processing:
                return False
            self._processing = True
            self._new_data = False
            self._error = None
            self._done.clear()
            self._thread = Thread(
                target=self._grab_data, name="overhead-tar1090-grabber"
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
            response = requests.get(self._tar1090_url, timeout=10)
            response.raise_for_status()

            aircraft_list = response.json().get("aircraft", [])

            min_alt_ft = self._min_altitude / 0.3048
            max_alt_ft = self._max_altitude / 0.3048
            zone = self._zone_home
            home = self._location_home

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
                if not _in_zone(lat, lon, zone):
                    continue
                candidates.append(ac)

            candidates.sort(
                key=lambda ac: _distance_from_home(
                    ac["lat"], ac["lon"], ac["alt_baro"], home
                )
            )

            for ac in candidates[:Config.instance().max_flight_lookup]:
                try:
                    callsign = (ac.get("flight") or "").strip()
                    if callsign.upper() in BLANK_FIELDS:
                        callsign = ""

                    plane = (ac.get("desc") or "").strip()
                    if plane.upper() in BLANK_FIELDS:
                        plane = ""

                    if callsign:
                        origin, destination = self._get_route(
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

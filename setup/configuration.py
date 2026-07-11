"""
Config singleton backed by config.json.

On first run, if config.json does not exist but config.py does, the legacy
file is imported and its variables are migrated automatically.
"""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import math
from datetime import datetime, time
from pathlib import Path
from typing import Any

try:
    import platformdirs
except ModuleNotFoundError:
    from pip._vendor import platformdirs

ROOT_PATH = Path(__file__).parent.parent
APP_NAME = "FlightTracker"
APP_AUTHOR = "FlightTracker"
PLATFORM_DATA_DIR = Path(
    platformdirs.user_data_dir(APP_NAME, APP_AUTHOR, ensure_exists=True)
)
CONFIG_PATH = PLATFORM_DATA_DIR / "config.json"
LEGACY_PATH = ROOT_PATH / "config.py"

# Sensible defaults - single source of truth for each config key.
# These constants are used both to populate DEFAULTS below and as the
# fallback in every Config @property, so the two never drift apart.
DEFAULT_PASSWORD = b"flighttracker"

# Location / flight zone
DEFAULT_FLIGHT_LOCATION_MODE = "simple"  # "simple" or "advanced"
DEFAULT_FLIGHT_LAT = 55.87
DEFAULT_FLIGHT_LNG = -4.25
DEFAULT_FLIGHT_RADIUS = 20.0  # km
DEFAULT_FLIGHT_MIN_ALTITUDE = 100.0  # metres
DEFAULT_FLIGHT_MAX_ALTITUDE = 10000.0  # metres
# Advanced mode: bounding-box corners (FR24/tar1090 search area)
DEFAULT_FLIGHT_ZONE_TL_Y = 55.87 + 0.18  # north
DEFAULT_FLIGHT_ZONE_TL_X = -4.25 - 0.32  # west
DEFAULT_FLIGHT_ZONE_BR_Y = 55.87 - 0.18  # south
DEFAULT_FLIGHT_ZONE_BR_X = -4.25 + 0.32  # east
# Advanced mode: observer position (weather + distance sorting)
DEFAULT_FLIGHT_OBSERVER_LAT = 55.87
DEFAULT_FLIGHT_OBSERVER_LNG = -4.25

# Airport display
DEFAULT_FULL_AIRPORT_NAME = False
DEFAULT_ABBREVIATE_NAME = False
DEFAULT_HOME_AIRPORT_CODE = ""
DEFAULT_JOURNEY_BLANK_FILLER = "???"

# Plane info row
DEFAULT_DETAILS = 0  # 0 = plane make/model, 1 = altitude/speed/heading

# Weather
DEFAULT_WEATHERAPI_KEY = ""  # empty = weather disabled
DEFAULT_WEATHER_MODE = 0  # 0 = off, 1 = temperature only, 2 = temperature + rainfall
DEFAULT_RAIN_SENSITIVITY = (
    1  # 0 = dry (Egypt/1mm), 1 = moderate (UK/3mm), 2 = wet (Singapore/9mm)
)
DEFAULT_UNITS = "m"  # 'm' = metric, 'i' = imperial

# Display
DEFAULT_THEME = 0  # 0 = Default, 1 = Monochrome, 2 = Pastel
DEFAULT_SCREEN_BRIGHTNESS = 3  # 1-5
DEFAULT_SCREEN_ROTATE = False
DEFAULT_DISPLAY_SPEED = "default"  # default / slower / faster

# Brightness schedule
DEFAULT_SCREEN_SCHEDULE_ENABLED = False
DEFAULT_SCREEN_SCHEDULE_AUTO = False
DEFAULT_SCREEN_SCHEDULE_START = "22:00"
DEFAULT_SCREEN_SCHEDULE_END = "07:00"
DEFAULT_SCREEN_SCHEDULE_BRIGHTNESS = 0

# Clock / date
DEFAULT_CLOCK_24HR = True
DEFAULT_DATE_FORMAT = 0  # 0 = YYYY-MM-DD, 1 = DD-MM-YYYY, 2 = MM-DD-YYYY

# Web interface
DEFAULT_WEB_INTERFACE_ENABLED = True
DEFAULT_WEB_PORT = 8584  # TCP port for the Flask config server
DEFAULT_WEB_PASSWORD_HASH = ""  # SHA-256 hex; empty = default password "flighttracker"

# Hardware
DEFAULT_GPIO_SLOWDOWN = 1
DEFAULT_HAT_PWM_ENABLED = True
DEFAULT_LOADING_LED_ENABLED = False
DEFAULT_LOADING_LED_GPIO_PIN = ""

# Data source
DEFAULT_DATA_SOURCE = "fr24"  # 'fr24' = FlightRadar24, 'tar1090' = local tar1090
DEFAULT_TAR1090_URL = ""  # only used when data_source == 'tar1090'
DEFAULT_MAX_FLIGHT_LOOKUP = 5  # how many nearby flights to track at once
DEFAULT_CALLSIGN_FORMAT = (
    "icao"  # 'icao' = callsign, 'iata' = flight number (FR24 only)
)

# Satellite tracking
DEFAULT_SATELLITE_TRACKING_ENABLED = True
DEFAULT_SATELLITE_NORAD_IDS = [25544]  # ISS (ZARYA) = 25544; celestrak.org for others
DEFAULT_SATELLITE_MIN_ELEVATION = 20  # degrees - passes peaking below this are ignored
DEFAULT_SATELLITE_MAX_COUNT = 5  # max simultaneous satellites to plot
DEFAULT_SATELLITE_TIMEOUT_ENABLED = False  # cap how long the scene is shown per pass
DEFAULT_SATELLITE_TIMEOUT_SECONDS = (
    30  # seconds from AOS before the scene yields to lower-priority scenes
)

# Logging
DEFAULT_LOG_LEVEL = "INFO"  # DEBUG / INFO / WARNING / ERROR / CRITICAL

DEFAULTS: dict[str, Any] = {
    # Location / flight zone
    "flight_location_mode": DEFAULT_FLIGHT_LOCATION_MODE,
    "flight_lat": DEFAULT_FLIGHT_LAT,
    "flight_lng": DEFAULT_FLIGHT_LNG,
    "flight_radius": DEFAULT_FLIGHT_RADIUS,
    "flight_min_altitude": DEFAULT_FLIGHT_MIN_ALTITUDE,
    "flight_max_altitude": DEFAULT_FLIGHT_MAX_ALTITUDE,
    # Advanced mode: bounding-box corners
    "flight_zone_tl_y": DEFAULT_FLIGHT_ZONE_TL_Y,
    "flight_zone_tl_x": DEFAULT_FLIGHT_ZONE_TL_X,
    "flight_zone_br_y": DEFAULT_FLIGHT_ZONE_BR_Y,
    "flight_zone_br_x": DEFAULT_FLIGHT_ZONE_BR_X,
    # Advanced mode: observer position
    "flight_observer_lat": DEFAULT_FLIGHT_OBSERVER_LAT,
    "flight_observer_lng": DEFAULT_FLIGHT_OBSERVER_LNG,
    # Airport display
    "full_airport_name": DEFAULT_FULL_AIRPORT_NAME,
    "abbreviate_name": DEFAULT_ABBREVIATE_NAME,
    "home_airport_code": DEFAULT_HOME_AIRPORT_CODE,
    "journey_blank_filler": DEFAULT_JOURNEY_BLANK_FILLER,
    # Plane info row
    "details": DEFAULT_DETAILS,
    # Weather
    "weatherapi_key": DEFAULT_WEATHERAPI_KEY,
    "weather_mode": DEFAULT_WEATHER_MODE,
    "rain_sensitivity": DEFAULT_RAIN_SENSITIVITY,
    "units": DEFAULT_UNITS,
    # Display
    "theme": DEFAULT_THEME,
    "screen_brightness": DEFAULT_SCREEN_BRIGHTNESS,
    "screen_rotate": DEFAULT_SCREEN_ROTATE,
    "display_speed": DEFAULT_DISPLAY_SPEED,
    # Brightness schedule
    "screen_schedule_enabled": DEFAULT_SCREEN_SCHEDULE_ENABLED,
    "screen_schedule_auto": DEFAULT_SCREEN_SCHEDULE_AUTO,
    "screen_schedule_start": DEFAULT_SCREEN_SCHEDULE_START,
    "screen_schedule_end": DEFAULT_SCREEN_SCHEDULE_END,
    "screen_schedule_brightness": DEFAULT_SCREEN_SCHEDULE_BRIGHTNESS,
    # Clock / date
    "clock_24hr": DEFAULT_CLOCK_24HR,
    "date_format": DEFAULT_DATE_FORMAT,
    # Web interface
    "web_interface_enabled": DEFAULT_WEB_INTERFACE_ENABLED,
    "web_port": DEFAULT_WEB_PORT,
    "web_password_hash": DEFAULT_WEB_PASSWORD_HASH,
    # Hardware
    "gpio_slowdown": DEFAULT_GPIO_SLOWDOWN,
    "hat_pwm_enabled": DEFAULT_HAT_PWM_ENABLED,
    "loading_led_enabled": DEFAULT_LOADING_LED_ENABLED,
    "loading_led_gpio_pin": DEFAULT_LOADING_LED_GPIO_PIN,
    # Data source
    "data_source": DEFAULT_DATA_SOURCE,
    "tar1090_url": DEFAULT_TAR1090_URL,
    "max_flight_lookup": DEFAULT_MAX_FLIGHT_LOOKUP,
    "callsign_format": DEFAULT_CALLSIGN_FORMAT,
    # Satellite tracking
    "satellite_tracking_enabled": DEFAULT_SATELLITE_TRACKING_ENABLED,
    "satellite_norad_ids": DEFAULT_SATELLITE_NORAD_IDS,
    "satellite_min_elevation": DEFAULT_SATELLITE_MIN_ELEVATION,
    "satellite_max_count": DEFAULT_SATELLITE_MAX_COUNT,
    "satellite_timeout_enabled": DEFAULT_SATELLITE_TIMEOUT_ENABLED,
    "satellite_timeout_seconds": DEFAULT_SATELLITE_TIMEOUT_SECONDS,
    # Logging
    "log_level": DEFAULT_LOG_LEVEL,
}


def mins_to_time(m: float) -> time:
    """Convert minutes-from-midnight (0-1440) into a ``datetime.time``."""
    m = int(round(m)) % 1440
    return time(hour=m // 60, minute=m % 60)


def time_to_mins(t: time) -> int:
    """Convert a ``datetime.time`` to minutes from midnight."""
    return t.hour * 60 + t.minute


def _next_backup_path(path: Path) -> Path:
    backup = path.with_suffix(path.suffix + ".bak")
    if not backup.exists():
        return backup

    for index in range(1, 100):
        candidate = path.with_name(f"{path.name}.bak.{index}")
        if not candidate.exists():
            return candidate

    raise FileExistsError(f"Unable to create backup for {path}")


def migrate_legacy_json(repo_path: Path, platform_path: Path) -> Path:
    platform_path.parent.mkdir(parents=True, exist_ok=True)
    repo_exists = repo_path.exists()
    platform_exists = platform_path.exists()

    if repo_exists and platform_exists:
        backup = _next_backup_path(repo_path)
        repo_path.rename(backup)
        return platform_path

    if repo_exists:
        shutil.copy2(repo_path, platform_path)
        backup = _next_backup_path(repo_path)
        repo_path.rename(backup)
        return platform_path

    return platform_path


def parse_time(value: Any, default: str = "00:00") -> time:
    """Parse an ``HH:MM`` string (or anything str()-able) into a ``datetime.time``.

    Falls back to *default* on failure. Used at the JSON-storage boundary.
    """
    try:
        return datetime.strptime(str(value).strip(), "%H:%M").time()
    except (ValueError, AttributeError, TypeError):
        return datetime.strptime(default, "%H:%M").time()


def time_in_window(start: time, end: time) -> bool:
    """Check if *now* falls inside a time window defined by two ``time`` objects.

    Handles overnight windows (e.g. 22:00 -> 07:00) where start > end.
    """
    if start is None or end is None:
        return False

    now_mins = datetime.now().hour * 60 + datetime.now().minute
    start_mins = time_to_mins(start)
    end_mins = time_to_mins(end)

    if start_mins == end_mins:
        return True
    if start_mins < end_mins:
        return start_mins <= now_mins < end_mins

    # Overnight window
    return now_mins >= start_mins or now_mins < end_mins


def approx_sunrise_sunset(lat: float, lng: float, date=None) -> tuple[time, time]:
    """Approximate sunrise/sunset times for a given lat/lng and date.

    Uses a simplified solar position algorithm (NOAA approximation).
    Returns (sunrise, sunset) as ``datetime.time`` objects.
    """

    if date is None:
        date = datetime.now()

    day_of_year = date.timetuple().tm_yday

    # Solar declination (degrees)
    decl = 23.45 * math.sin(math.radians(360 / 365 * (day_of_year - 81)))

    # Approximate equation of time in minutes
    b = math.radians(360 / 365 * (day_of_year - 81))
    eot = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)

    # Solar noon in UTC (minutes from midnight)
    solar_noon_utc = 720 - 4 * lng - eot

    # Hour angle at sunrise/sunset (using 90° + 50' = -0.833° elevation)
    lat_rad = math.radians(lat)
    decl_rad = math.radians(decl)
    cos_h = (
        math.sin(math.radians(-0.833)) - math.sin(lat_rad) * math.sin(decl_rad)
    ) / (math.cos(lat_rad) * math.cos(decl_rad))

    # Polar night / midnight sun - clamp to 0 or 1440 minutes
    if cos_h > 1:
        # Sun never rises
        noon = mins_to_time(720)
        return noon, noon
    if cos_h < -1:
        # Sun never sets
        noon = mins_to_time(720)
        return noon, noon

    ha = math.degrees(math.acos(cos_h))  # degrees
    ha_minutes = ha * 4  # 1° = 4 minutes

    sunrise = solar_noon_utc - ha_minutes
    sunset = solar_noon_utc + ha_minutes

    # Wrap into 0-1440
    sunrise = sunrise % 1440
    sunset = sunset % 1440

    return mins_to_time(sunrise), mins_to_time(sunset)


def import_legacy(path: Path):
    """Import a config.py file as a module without it needing to be on sys.path."""
    spec = importlib.util.spec_from_file_location("legacy_config", str(path))
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        print(
            f"[config] Warning: could not fully load legacy config.py: {exc}",
            file=sys.stderr,
        )
    return mod


def migrate_config(mod) -> dict[str, Any]:
    """Map legacy config.py variables onto the new JSON schema."""

    data: dict[str, Any] = dict(DEFAULTS)

    def get(name, default=None):
        return getattr(mod, name, default)

    # Location - prefer LOCATION_HOME [lat, lng, alt]; fall back to ZONE_HOME
    # bounding box centre if LOCATION_HOME is not present.
    location_home = get("LOCATION_HOME")
    if location_home and len(location_home) >= 2:
        data["flight_lat"] = float(location_home[0])
        data["flight_lng"] = float(location_home[1])
    else:
        zone = get("ZONE_HOME")
        if zone and all(k in zone for k in ("tl_y", "tl_x", "br_y", "br_x")):
            data["flight_lat"] = round(
                (float(zone["tl_y"]) + float(zone["br_y"])) / 2, 7
            )
            data["flight_lng"] = round(
                (float(zone["tl_x"]) + float(zone["br_x"])) / 2, 7
            )
            # Derive radius from the bounding box (km, using the larger half-width)
            lat_deg = abs(float(zone["tl_y"]) - float(zone["br_y"])) / 2
            lng_deg = abs(float(zone["tl_x"]) - float(zone["br_x"])) / 2
            lat_km = lat_deg * 111.0
            lng_km = lng_deg * 111.0 * math.cos(math.radians(data["flight_lat"]))
            data["flight_radius"] = round(max(lat_km, lng_km), 1)

    # Brightness: old scale 0-100 -> new scale 1-5
    brightness = get("BRIGHTNESS")
    if brightness is not None:
        data["screen_brightness"] = max(1, min(5, round(int(brightness) / 20)))

    # Min altitude: old value was in feet -> convert to metres
    min_alt = get("MIN_ALTITUDE")
    if min_alt is not None:
        data["flight_min_altitude"] = max(10.0, round(float(min_alt) * 0.3048, 1))

    # Units: old 'metric'/'imperial' -> new 'm'/'i'
    temp_units = get("TEMPERATURE_UNITS", "metric")
    data["units"] = "i" if str(temp_units).lower() == "imperial" else DEFAULT_UNITS

    # Migrate old RAINFALL_ENABLED -> weather_mode
    # (WEATHER_LOCATION / OPENWEATHER_API_KEY are dropped - weatherapi uses lat/lng)
    if get("RAINFALL_ENABLED"):
        data["weather_mode"] = 2
    elif get("WEATHER_LOCATION"):
        data["weather_mode"] = 1

    # Simple renames
    simple_map = {
        "GPIO_SLOWDOWN": "gpio_slowdown",
        "HAT_PWM_ENABLED": "hat_pwm_enabled",
        "JOURNEY_BLANK_FILLER": "journey_blank_filler",
        "TAR1090_URL": "tar1090_url",
        "LOADING_LED_ENABLED": "loading_led_enabled",
        "LOADING_LED_GPIO_PIN": "loading_led_gpio_pin",
    }
    for old, new in simple_map.items():
        val = get(old)
        if val is not None:
            data[new] = val

    # If a tar1090 URL was configured, switch data_source to tar1090
    if get("TAR1090_URL"):
        data["data_source"] = "tar1090"

    # JOURNEY_CODE_SELECTED -> home_airport_code
    jcs = get("JOURNEY_CODE_SELECTED")
    if jcs:
        data["home_airport_code"] = str(jcs).strip().upper()[:3]

    print("[config] Migrated legacy config.py -> config.json", file=sys.stderr)
    return data


class Config:
    """Singleton configuration object backed by config.json."""

    instance_cache: Config | None = None

    @classmethod
    def instance(cls) -> "Config":
        if cls.instance_cache is None:
            cls.instance_cache = cls()
        return cls.instance_cache

    @classmethod
    def reload(cls) -> "Config":
        """Discard the cached instance and reload from disk."""
        cls.instance_cache = None
        return cls.instance()

    def __init__(self):
        self.data_store: dict[str, Any] = {}
        self.load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def load(self):
        migrate_legacy_json(ROOT_PATH / "config.json", CONFIG_PATH)

        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH) as fh:
                    loaded = json.load(fh)
                # Merge over defaults so new keys always have a value
                self.data_store = {**DEFAULTS, **loaded}
                return
            except Exception as exc:
                print(f"[config] Failed to read config.json: {exc}", file=sys.stderr)

        if LEGACY_PATH.exists():
            mod = import_legacy(LEGACY_PATH)
            self.data_store = migrate_config(mod)
            self.save()
            return

        # Fresh install - write defaults
        self.data_store = dict(DEFAULTS)
        self.save()

    def save(self):
        try:
            tmp_path = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".tmp")
            with open(tmp_path, "w") as fh:
                json.dump(self.data_store, fh, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_path, CONFIG_PATH)
        except Exception as exc:
            print(f"[config] Failed to write config.json: {exc}", file=sys.stderr)

    @property
    def is_configured(self) -> bool:
        """False when the device has never been set up (no config.json existed)."""
        return CONFIG_PATH.exists()

    # ------------------------------------------------------------------
    # Raw access
    # ------------------------------------------------------------------

    def get(self, key: str, default=None):
        return self.data_store.get(key, default)

    def set(self, key: str, value):
        self.data_store[key] = value

    def update(self, data: dict):
        self.data_store.update(data)

    def as_dict(self) -> dict:
        return dict(self.data_store)

    # ------------------------------------------------------------------
    # Typed properties
    # ------------------------------------------------------------------

    @property
    def flight_location_mode(self) -> str:
        val = str(
            self.data_store.get("flight_location_mode", DEFAULT_FLIGHT_LOCATION_MODE)
        ).lower()
        return val if val in ("simple", "advanced") else DEFAULT_FLIGHT_LOCATION_MODE

    @property
    def flight_lat(self) -> float:
        return float(self.data_store.get("flight_lat", DEFAULT_FLIGHT_LAT))

    @property
    def flight_lng(self) -> float:
        return float(self.data_store.get("flight_lng", DEFAULT_FLIGHT_LNG))

    @property
    def flight_radius(self) -> float:
        return float(self.data_store.get("flight_radius", DEFAULT_FLIGHT_RADIUS))

    @property
    def flight_min_altitude(self) -> float:
        return float(
            self.data_store.get("flight_min_altitude", DEFAULT_FLIGHT_MIN_ALTITUDE)
        )

    @property
    def flight_max_altitude(self) -> float:
        return float(
            self.data_store.get("flight_max_altitude", DEFAULT_FLIGHT_MAX_ALTITUDE)
        )

    # -- Advanced mode: bounding-box corners -----------------------------

    @property
    def flight_zone_tl_y(self) -> float:
        return float(self.data_store.get("flight_zone_tl_y", DEFAULT_FLIGHT_ZONE_TL_Y))

    @property
    def flight_zone_tl_x(self) -> float:
        return float(self.data_store.get("flight_zone_tl_x", DEFAULT_FLIGHT_ZONE_TL_X))

    @property
    def flight_zone_br_y(self) -> float:
        return float(self.data_store.get("flight_zone_br_y", DEFAULT_FLIGHT_ZONE_BR_Y))

    @property
    def flight_zone_br_x(self) -> float:
        return float(self.data_store.get("flight_zone_br_x", DEFAULT_FLIGHT_ZONE_BR_X))

    # -- Advanced mode: observer position -------------------------------

    @property
    def flight_observer_lat(self) -> float:
        return float(
            self.data_store.get("flight_observer_lat", DEFAULT_FLIGHT_OBSERVER_LAT)
        )

    @property
    def flight_observer_lng(self) -> float:
        return float(
            self.data_store.get("flight_observer_lng", DEFAULT_FLIGHT_OBSERVER_LNG)
        )

    @property
    def full_airport_name(self) -> bool:
        return bool(self.data_store.get("full_airport_name", DEFAULT_FULL_AIRPORT_NAME))

    @property
    def abbreviate_name(self) -> bool:
        return bool(self.data_store.get("abbreviate_name", DEFAULT_ABBREVIATE_NAME))

    @property
    def home_airport_code(self) -> str:
        return str(
            self.data_store.get("home_airport_code", DEFAULT_HOME_AIRPORT_CODE)
        ).upper()

    @property
    def journey_blank_filler(self) -> str:
        return str(
            self.data_store.get("journey_blank_filler", DEFAULT_JOURNEY_BLANK_FILLER)
        )

    @property
    def details(self) -> int:
        return int(self.data_store.get("details", DEFAULT_DETAILS))

    @property
    def weatherapi_key(self) -> str:
        return str(self.data_store.get("weatherapi_key", DEFAULT_WEATHERAPI_KEY))

    @property
    def weather_mode(self) -> int:
        """0 = off, 1 = temperature only, 2 = temperature + rainfall graph."""
        return max(
            0, min(2, int(self.data_store.get("weather_mode", DEFAULT_WEATHER_MODE)))
        )

    @property
    def rain_sensitivity(self) -> int:
        """Graph full-scale mm/hr: 0 = 1mm (dry), 1 = 3mm (moderate), 2 = 9mm (wet)."""
        return max(
            0,
            min(
                2,
                int(self.data_store.get("rain_sensitivity", DEFAULT_RAIN_SENSITIVITY)),
            ),
        )

    @property
    def units(self) -> str:
        val = str(self.data_store.get("units", DEFAULT_UNITS))
        return val if val in ("m", "i") else DEFAULT_UNITS

    @property
    def theme(self) -> int:
        return int(self.data_store.get("theme", DEFAULT_THEME))

    @property
    def screen_brightness(self) -> int:
        return max(
            1,
            min(
                5,
                int(
                    self.data_store.get("screen_brightness", DEFAULT_SCREEN_BRIGHTNESS)
                ),
            ),
        )

    @property
    def brightness_percent(self) -> int:
        """Map 1-5 brightness setting to 0-100 percent for rgbmatrix."""
        return {1: 20, 2: 40, 3: 60, 4: 80, 5: 100}.get(self.screen_brightness, 60)

    @property
    def screen_rotate(self) -> bool:
        return bool(self.data_store.get("screen_rotate", DEFAULT_SCREEN_ROTATE))

    @property
    def display_speed(self) -> str:
        val = str(self.data_store.get("display_speed", DEFAULT_DISPLAY_SPEED)).lower()
        return val if val in ("default", "slower", "faster") else DEFAULT_DISPLAY_SPEED

    @property
    def display_speed_factor(self) -> float:
        return {"default": 1.0, "slower": 2.0, "faster": 0.75}.get(
            self.display_speed, 1.0
        )

    @property
    def screen_schedule_enabled(self) -> bool:
        return bool(
            self.data_store.get(
                "screen_schedule_enabled", DEFAULT_SCREEN_SCHEDULE_ENABLED
            )
        )

    @property
    def screen_schedule_auto(self) -> bool:
        return bool(
            self.data_store.get("screen_schedule_auto", DEFAULT_SCREEN_SCHEDULE_AUTO)
        )

    @property
    def screen_schedule_start(self) -> time:
        return parse_time(
            self.data_store.get("screen_schedule_start", DEFAULT_SCREEN_SCHEDULE_START)
        )

    @property
    def screen_schedule_end(self) -> time:
        return parse_time(
            self.data_store.get("screen_schedule_end", DEFAULT_SCREEN_SCHEDULE_END)
        )

    @property
    def screen_schedule_brightness(self) -> int:
        return max(
            0,
            min(
                5,
                int(
                    self.data_store.get(
                        "screen_schedule_brightness", DEFAULT_SCREEN_SCHEDULE_BRIGHTNESS
                    )
                ),
            ),
        )

    @property
    def schedule_brightness_percent(self) -> int:
        """Map 0-5 schedule brightness to 0-100 percent (0 = screen off)."""
        return {0: 0, 1: 20, 2: 40, 3: 60, 4: 80, 5: 100}.get(
            self.screen_schedule_brightness, 0
        )

    def is_in_brightness_schedule(self) -> bool:
        """True if the current time falls within the configured brightness schedule."""
        start, end = self.brightness_schedule_window
        return self.screen_schedule_enabled and time_in_window(start, end)

    @property
    def brightness_schedule_window(self) -> tuple[time, time]:
        """Return the (start, end) times for the active brightness schedule.

        The schedule dims the screen at night, so the window runs from the
        dim-start time to the brighten time.  In auto mode that is
        (sunset, sunrise); in manual mode it is the user-configured times.
        Returns (00:00, 00:00) when the schedule is disabled.
        """
        if self.screen_schedule_auto:
            sunrise, sunset = approx_sunrise_sunset(
                self.observer_lat, self.observer_lng
            )
            return sunset, sunrise
        return self.screen_schedule_start, self.screen_schedule_end

    @property
    def clock_24hr(self) -> bool:
        return bool(self.data_store.get("clock_24hr", DEFAULT_CLOCK_24HR))

    @property
    def date_format(self) -> int:
        return int(self.data_store.get("date_format", DEFAULT_DATE_FORMAT))

    @property
    def web_interface_enabled(self) -> bool:
        return bool(
            self.data_store.get("web_interface_enabled", DEFAULT_WEB_INTERFACE_ENABLED)
        )

    @property
    def web_port(self) -> int:
        try:
            return max(
                1024,
                min(65535, int(self.data_store.get("web_port", DEFAULT_WEB_PORT))),
            )
        except (TypeError, ValueError):
            return DEFAULT_WEB_PORT

    @property
    def web_password_hash(self) -> str:
        """SHA-256 hex digest of the web UI password.
        If not set, returns the hash of the default password 'flighttracker'."""
        import hashlib

        stored = str(
            self.data_store.get("web_password_hash", DEFAULT_WEB_PASSWORD_HASH)
        )
        if stored:
            return stored
        return hashlib.sha256(DEFAULT_PASSWORD).hexdigest()

    @property
    def gpio_slowdown(self) -> int:
        return int(self.data_store.get("gpio_slowdown", DEFAULT_GPIO_SLOWDOWN))

    @property
    def hat_pwm_enabled(self) -> bool:
        return bool(self.data_store.get("hat_pwm_enabled", DEFAULT_HAT_PWM_ENABLED))

    @property
    def loading_led_enabled(self) -> bool:
        return bool(
            self.data_store.get("loading_led_enabled", DEFAULT_LOADING_LED_ENABLED)
        )

    @property
    def loading_led_gpio_pin(self) -> int:
        return int(
            self.data_store.get("loading_led_gpio_pin", DEFAULT_LOADING_LED_GPIO_PIN)
        )

    @property
    def tar1090_url(self) -> str:
        return str(self.data_store.get("tar1090_url", DEFAULT_TAR1090_URL))

    @property
    def data_source(self) -> str:
        val = str(self.data_store.get("data_source", DEFAULT_DATA_SOURCE)).lower()
        return val if val in ("fr24", "tar1090") else DEFAULT_DATA_SOURCE

    @property
    def use_tar1090(self) -> bool:
        return self.data_source == "tar1090" and bool(self.tar1090_url)

    @property
    def max_flight_lookup(self) -> int:
        try:
            return max(
                1,
                int(
                    self.data_store.get("max_flight_lookup", DEFAULT_MAX_FLIGHT_LOOKUP)
                ),
            )
        except (TypeError, ValueError):
            return DEFAULT_MAX_FLIGHT_LOOKUP

    @property
    def callsign_format(self) -> str:
        val = str(
            self.data_store.get("callsign_format", DEFAULT_CALLSIGN_FORMAT)
        ).lower()
        return val if val in ("icao", "iata") else DEFAULT_CALLSIGN_FORMAT

    @property
    def satellite_tracking_enabled(self) -> bool:
        return bool(
            self.data_store.get(
                "satellite_tracking_enabled", DEFAULT_SATELLITE_TRACKING_ENABLED
            )
        )

    @property
    def satellite_norad_ids(self) -> list[int]:
        val = self.data_store.get("satellite_norad_ids", DEFAULT_SATELLITE_NORAD_IDS)
        if isinstance(val, list):
            ids = []
            for n in val:
                try:
                    ids.append(int(n))
                except (TypeError, ValueError):
                    pass
            return ids
        return list(DEFAULT_SATELLITE_NORAD_IDS)

    @property
    def satellite_min_elevation(self) -> int:
        try:
            return max(
                0,
                min(
                    90,
                    int(
                        self.data_store.get(
                            "satellite_min_elevation", DEFAULT_SATELLITE_MIN_ELEVATION
                        )
                    ),
                ),
            )
        except (TypeError, ValueError):
            return DEFAULT_SATELLITE_MIN_ELEVATION

    @property
    def satellite_max_count(self) -> int:
        try:
            return max(
                1,
                min(
                    10,
                    int(
                        self.data_store.get(
                            "satellite_max_count", DEFAULT_SATELLITE_MAX_COUNT
                        )
                    ),
                ),
            )
        except (TypeError, ValueError):
            return DEFAULT_SATELLITE_MAX_COUNT

    @property
    def satellite_timeout_enabled(self) -> bool:
        return bool(
            self.data_store.get(
                "satellite_timeout_enabled", DEFAULT_SATELLITE_TIMEOUT_ENABLED
            )
        )

    @property
    def satellite_timeout_seconds(self) -> int:
        try:
            return max(
                5,
                min(
                    3600,
                    int(
                        self.data_store.get(
                            "satellite_timeout_seconds",
                            DEFAULT_SATELLITE_TIMEOUT_SECONDS,
                        )
                    ),
                ),
            )
        except (TypeError, ValueError):
            return DEFAULT_SATELLITE_TIMEOUT_SECONDS

    @property
    def log_level(self) -> str:
        """Configured logging level name (DEBUG / INFO / WARNING / ERROR / CRITICAL).

        Stored as an uppercase string in config.json; coerced to one of the
        five valid names, falling back to the default on anything unknown.
        """
        import logging

        val = str(self.data_store.get("log_level", DEFAULT_LOG_LEVEL)).upper()
        valid = {
            logging.getLevelName(logging.DEBUG),
            logging.getLevelName(logging.INFO),
            logging.getLevelName(logging.WARNING),
            logging.getLevelName(logging.ERROR),
            logging.getLevelName(logging.CRITICAL),
        }
        return val if val in valid else DEFAULT_LOG_LEVEL

    # Derived: zone bounding box (same algorithm as DotboxServer)
    @property
    def zone_home(self) -> dict:
        """
        Bounding box for flight data queries.

        In *simple* mode the box is derived from lat/lng + radius.
        In *advanced* mode the box corners are stored directly.
        """
        if self.flight_location_mode == "advanced":
            return {
                "tl_y": self.flight_zone_tl_y,
                "tl_x": self.flight_zone_tl_x,
                "br_y": self.flight_zone_br_y,
                "br_x": self.flight_zone_br_x,
            }

        import math

        lat, lng, r = self.flight_lat, self.flight_lng, self.flight_radius
        lat_deg = r / 111.0
        lng_deg = r / (111.0 * math.cos(math.radians(lat)))
        return {
            "tl_y": lat + lat_deg,
            "tl_x": lng - lng_deg,
            "br_y": lat - lat_deg,
            "br_x": lng + lng_deg,
        }

    @property
    def location_home(self) -> list:
        """[lat, lng, altitude_km] compatible with the old LOCATION_HOME format.

        Uses the observer position in advanced mode, the centre point in simple mode.
        """
        if self.flight_location_mode == "advanced":
            return [self.flight_observer_lat, self.flight_observer_lng, 6371.0]
        return [self.flight_lat, self.flight_lng, 6371.0]

    @property
    def observer_lat(self) -> float:
        """Observer latitude — used for weather, sunrise/sunset, and satellite passes."""
        if self.flight_location_mode == "advanced":
            return self.flight_observer_lat
        return self.flight_lat

    @property
    def observer_lng(self) -> float:
        """Observer longitude — used for weather, sunrise/sunset, and satellite passes."""
        if self.flight_location_mode == "advanced":
            return self.flight_observer_lng
        return self.flight_lng

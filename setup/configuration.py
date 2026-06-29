"""
Config singleton backed by config.json.

On first run, if config.json does not exist but config.py does, the legacy
file is imported and its variables are migrated automatically.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


def _time_in_window(start_str: str, end_str: str) -> bool:
    """Check if *now* falls inside a time window defined by two HH:MM strings.

    Handles overnight windows (e.g. 22:00 → 07:00) where start > end.
    """
    try:
        now = datetime.now()
        start = datetime.strptime(start_str.strip(), "%H:%M")
        end = datetime.strptime(end_str.strip(), "%H:%M")
    except (ValueError, AttributeError):
        return False

    start_mins = start.hour * 60 + start.minute
    end_mins = end.hour * 60 + end.minute
    now_mins = now.hour * 60 + now.minute

    if start_mins == end_mins:
        return True
    if start_mins < end_mins:
        return start_mins <= now_mins < end_mins
    # Overnight window
    return now_mins >= start_mins or now_mins < end_mins


def _approx_sunrise_sunset(lat: float, lng: float, date=None):
    """Approximate sunrise/sunset times for a given lat/lng and date.

    Uses a simplified solar position algorithm (NOAA approximation).
    Returns (sunrise_str, sunset_str) as HH:MM strings.
    """
    import math

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
    cos_h = (math.sin(math.radians(-0.833)) - math.sin(lat_rad) * math.sin(decl_rad)) / (
        math.cos(lat_rad) * math.cos(decl_rad)
    )

    # Polar night / midnight sun — clamp to 0 or 1440 minutes
    if cos_h > 1:
        # Sun never rises
        return "12:00", "12:00"
    if cos_h < -1:
        # Sun never sets
        return "12:00", "12:00"

    ha = math.degrees(math.acos(cos_h))  # degrees
    ha_minutes = ha * 4  # 1° = 4 minutes

    sunrise = solar_noon_utc - ha_minutes
    sunset = solar_noon_utc + ha_minutes

    # Wrap into 0–1440
    sunrise = sunrise % 1440
    sunset = sunset % 1440

    def _mins_to_hhmm(m):
        m = int(round(m)) % 1440
        return f"{m // 60:02d}:{m % 60:02d}"

    return _mins_to_hhmm(sunrise), _mins_to_hhmm(sunset)


_ROOT = Path(__file__).parent.parent
CONFIG_PATH = _ROOT / "config.json"
LEGACY_PATH = _ROOT / "config.py"

# Sensible defaults — mirrors the Django Settings model for Dotbox
DEFAULTS: dict[str, Any] = {
    # Location / flight zone
    "flight_lat": 55.87,
    "flight_lng": -4.25,
    "flight_radius": 20.0,  # km
    "flight_min_altitude": 100.0,  # metres
    "flight_max_altitude": 10000.0,  # metres
    # Airport display
    "full_airport_name": False,
    "abbreviate_name": False,
    "home_airport_code": "",
    "journey_blank_filler": " ? ",
    # Plane info row
    "details": 0,  # 0 = plane make/model, 1 = altitude/speed/heading
    # Weather
    "weatherapi_key": "",  # weatherapi.com API key; empty = weather disabled
    "weather_mode": 0,  # 0 = off, 1 = temperature only, 2 = temperature + rainfall
    "units": "m",  # 'm' = metric, 'i' = imperial
    # Display
    "theme": 0,  # 0 = Default, 1 = Monochrome, 2 = Pastel
    "screen_brightness": 3,  # 1–5
    "screen_rotate": False,
    # Brightness schedule
    "screen_schedule_enabled": False,
    "screen_schedule_auto": False,
    "screen_schedule_start": "22:00",
    "screen_schedule_end": "07:00",
    "screen_schedule_brightness": 0,
    # Clock / date
    "clock_24hr": True,
    "date_format": 0,  # 0 = YYYY-MM-DD, 1 = DD-MM-YYYY, 2 = MM-DD-YYYY
    # Web interface
    "web_interface_enabled": True,
    "web_password_hash": "",  # SHA-256 hex; empty = default password "flighttracker"
    # Hardware
    "gpio_slowdown": 1,
    "hat_pwm_enabled": True,
    "loading_led_enabled": False,
    "loading_led_gpio_pin": 25,
    # Data source
    "data_source": "fr24",  # 'fr24' = FlightRadar24, 'tar1090' = local tar1090
    "tar1090_url": "",  # only used when data_source == 'tar1090'
}


def _import_legacy(path: Path):
    """Import a config.py file as a module without it needing to be on sys.path."""
    spec = importlib.util.spec_from_file_location("_legacy_config", str(path))
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as exc:
        print(
            f"[config] Warning: could not fully load legacy config.py: {exc}",
            file=sys.stderr,
        )
    return mod


def _migrate(mod) -> dict[str, Any]:
    """Map legacy config.py variables onto the new JSON schema."""
    data: dict[str, Any] = dict(DEFAULTS)

    def get(name, default=None):
        return getattr(mod, name, default)

    # Location
    location_home = get("LOCATION_HOME")
    if location_home and len(location_home) >= 2:
        data["flight_lat"] = float(location_home[0])
        data["flight_lng"] = float(location_home[1])

    # Brightness: old scale 0–100 → new scale 1–5
    brightness = get("BRIGHTNESS")
    if brightness is not None:
        data["screen_brightness"] = max(1, min(5, round(int(brightness) / 20)))

    # Min altitude: old value was in feet → convert to metres
    min_alt = get("MIN_ALTITUDE")
    if min_alt is not None:
        data["flight_min_altitude"] = max(10.0, round(float(min_alt) * 0.3048, 1))

    # Units: old 'metric'/'imperial' → new 'm'/'i'
    temp_units = get("TEMPERATURE_UNITS", "metric")
    data["units"] = "i" if str(temp_units).lower() == "imperial" else "m"

    # Migrate old RAINFALL_ENABLED → weather_mode
    # (WEATHER_LOCATION / OPENWEATHER_API_KEY are dropped — weatherapi uses lat/lng)
    if get("RAINFALL_ENABLED"):
        data["weather_mode"] = 2
    elif get("WEATHER_LOCATION"):
        data["weather_mode"] = 1

    # Simple renames
    _simple = {
        "GPIO_SLOWDOWN": "gpio_slowdown",
        "HAT_PWM_ENABLED": "hat_pwm_enabled",
        "JOURNEY_BLANK_FILLER": "journey_blank_filler",
        "TAR1090_URL": "tar1090_url",
        "LOADING_LED_ENABLED": "loading_led_enabled",
        "LOADING_LED_GPIO_PIN": "loading_led_gpio_pin",
    }
    for old, new in _simple.items():
        val = get(old)
        if val is not None:
            data[new] = val

    # JOURNEY_CODE_SELECTED → home_airport_code
    jcs = get("JOURNEY_CODE_SELECTED")
    if jcs:
        data["home_airport_code"] = str(jcs).strip().upper()[:3]

    print("[config] Migrated legacy config.py → config.json", file=sys.stderr)
    return data


class Config:
    """Singleton configuration object backed by config.json."""

    _instance: Config | None = None

    @classmethod
    def instance(cls) -> "Config":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reload(cls) -> "Config":
        """Discard the cached instance and reload from disk."""
        cls._instance = None
        return cls.instance()

    def __init__(self):
        self._data: dict[str, Any] = {}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH) as fh:
                    loaded = json.load(fh)
                # Merge over defaults so new keys always have a value
                self._data = {**DEFAULTS, **loaded}
                # One-time migration: old weather_graph/rainfall_enabled → weather_mode
                if "weather_mode" not in loaded:
                    if loaded.get("rainfall_enabled"):
                        self._data["weather_mode"] = 2
                    elif loaded.get("weather_graph"):
                        self._data["weather_mode"] = 1
                return
            except Exception as exc:
                print(f"[config] Failed to read config.json: {exc}", file=sys.stderr)

        if LEGACY_PATH.exists():
            mod = _import_legacy(LEGACY_PATH)
            self._data = _migrate(mod)
            self.save()
            return

        # Fresh install — write defaults
        self._data = dict(DEFAULTS)
        self.save()

    def save(self):
        try:
            tmp_path = CONFIG_PATH.with_suffix(CONFIG_PATH.suffix + ".tmp")
            with open(tmp_path, "w") as fh:
                json.dump(self._data, fh, indent=2)
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
        return self._data.get(key, default)

    def set(self, key: str, value):
        self._data[key] = value

    def update(self, data: dict):
        self._data.update(data)

    def as_dict(self) -> dict:
        return dict(self._data)

    # ------------------------------------------------------------------
    # Typed properties
    # ------------------------------------------------------------------

    @property
    def flight_lat(self) -> float:
        return float(self._data.get("flight_lat", DEFAULTS["flight_lat"]))

    @property
    def flight_lng(self) -> float:
        return float(self._data.get("flight_lng", DEFAULTS["flight_lng"]))

    @property
    def flight_radius(self) -> float:
        return float(self._data.get("flight_radius", DEFAULTS["flight_radius"]))

    @property
    def flight_min_altitude(self) -> float:
        return float(
            self._data.get("flight_min_altitude", DEFAULTS["flight_min_altitude"])
        )

    @property
    def flight_max_altitude(self) -> float:
        return float(
            self._data.get("flight_max_altitude", DEFAULTS["flight_max_altitude"])
        )

    @property
    def full_airport_name(self) -> bool:
        return bool(self._data.get("full_airport_name", False))

    @property
    def abbreviate_name(self) -> bool:
        return bool(self._data.get("abbreviate_name", False))

    @property
    def home_airport_code(self) -> str:
        return str(self._data.get("home_airport_code", "")).upper()

    @property
    def journey_blank_filler(self) -> str:
        return str(self._data.get("journey_blank_filler", " ? "))

    @property
    def details(self) -> int:
        return int(self._data.get("details", 0))

    @property
    def weatherapi_key(self) -> str:
        return str(self._data.get("weatherapi_key", ""))

    @property
    def weather_mode(self) -> int:
        """0 = off, 1 = temperature only, 2 = temperature + rainfall graph."""
        return max(0, min(2, int(self._data.get("weather_mode", 0))))

    @property
    def units(self) -> str:
        val = str(self._data.get("units", "m"))
        return val if val in ("m", "i") else "m"

    @property
    def theme(self) -> int:
        return int(self._data.get("theme", 0))

    @property
    def screen_brightness(self) -> int:
        return max(1, min(5, int(self._data.get("screen_brightness", 3))))

    @property
    def brightness_percent(self) -> int:
        """Map 1–5 brightness setting to 0–100 percent for rgbmatrix."""
        return {1: 20, 2: 40, 3: 60, 4: 80, 5: 100}.get(self.screen_brightness, 60)

    @property
    def screen_rotate(self) -> bool:
        return bool(self._data.get("screen_rotate", False))

    @property
    def screen_schedule_enabled(self) -> bool:
        return bool(self._data.get("screen_schedule_enabled", False))

    @property
    def screen_schedule_auto(self) -> bool:
        return bool(self._data.get("screen_schedule_auto", False))

    @property
    def screen_schedule_start(self) -> str:
        return str(self._data.get("screen_schedule_start", "22:00"))

    @property
    def screen_schedule_end(self) -> str:
        return str(self._data.get("screen_schedule_end", "07:00"))

    @property
    def screen_schedule_brightness(self) -> int:
        return max(0, min(5, int(self._data.get("screen_schedule_brightness", 0))))

    @property
    def schedule_brightness_percent(self) -> int:
        """Map 0–5 schedule brightness to 0–100 percent (0 = screen off)."""
        return {0: 0, 1: 20, 2: 40, 3: 60, 4: 80, 5: 100}.get(
            self.screen_schedule_brightness, 0
        )

    def is_in_brightness_schedule(self) -> bool:
        """True if the current time falls within the configured brightness schedule."""
        if not self.screen_schedule_enabled:
            return False
        if self.screen_schedule_auto:
            start, end = _approx_sunrise_sunset(self.flight_lat, self.flight_lng)
        else:
            start, end = self.screen_schedule_start, self.screen_schedule_end
        return _time_in_window(start, end)

    @property
    def clock_24hr(self) -> bool:
        return bool(self._data.get("clock_24hr", True))

    @property
    def date_format(self) -> int:
        return int(self._data.get("date_format", 0))

    @property
    def web_interface_enabled(self) -> bool:
        return bool(self._data.get("web_interface_enabled", True))

    @property
    def web_password_hash(self) -> str:
        """SHA-256 hex digest of the web UI password.
        If not set, returns the hash of the default password 'flighttracker'."""
        import hashlib

        stored = str(self._data.get("web_password_hash", ""))
        if stored:
            return stored
        return hashlib.sha256(b"flighttracker").hexdigest()

    @property
    def gpio_slowdown(self) -> int:
        return int(self._data.get("gpio_slowdown", 1))

    @property
    def hat_pwm_enabled(self) -> bool:
        return bool(self._data.get("hat_pwm_enabled", True))

    @property
    def loading_led_enabled(self) -> bool:
        return bool(self._data.get("loading_led_enabled", False))

    @property
    def loading_led_gpio_pin(self) -> int:
        return int(self._data.get("loading_led_gpio_pin", 25))

    @property
    def tar1090_url(self) -> str:
        return str(self._data.get("tar1090_url", ""))

    @property
    def data_source(self) -> str:
        val = str(self._data.get("data_source", "fr24")).lower()
        return val if val in ("fr24", "tar1090") else "fr24"

    @property
    def use_tar1090(self) -> bool:
        return self.data_source == "tar1090" and bool(self.tar1090_url)

    # Derived: zone bounding box (same algorithm as DotboxServer)
    @property
    def zone_home(self) -> dict:
        """
        Derive a bounding box from lat/lng + radius.
        1 degree latitude ≈ 111 km; longitude varies with cos(lat).
        """
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
        """[lat, lng, altitude_km] compatible with the old LOCATION_HOME format."""
        return [self.flight_lat, self.flight_lng, 6371.0]

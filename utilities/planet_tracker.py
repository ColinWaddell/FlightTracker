"""
PlanetTracker - computes positions of solar system bodies for the
astronomy idle theme.

Uses skyfield with a JPL ephemeris (de421.bsp) to calculate apparent
altitude/azimuth of the Sun, Moon, and naked-eye planets from the
observer's location.  Results are cached and refreshed every
REFRESH_INTERVAL_SECONDS so the frame loop never blocks on orbital math.

The ephemeris file (~17 MB) is downloaded once and cached in the
platform data directory.  Loading happens in a background thread so
the display can show a loading message during the initial download.
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REFRESH_INTERVAL_SECONDS = 60  # recompute every minute
EPHEMERIS_FILENAME = "de421.bsp"

# Bodies we can compute positions for, keyed by config name.
# Each maps to (skyfield ephemeris name, display name, theme colour key).
BODY_DEFINITIONS = {
    "sun":     ("SUN",                "SUN",     "ASTRO_SUN"),
    "moon":    ("MOON",               "MOON",    "ASTRO_MOON"),
    "mercury": ("MERCURY",            "MERCURY", "ASTRO_MERCURY"),
    "venus":   ("VENUS",              "VENUS",   "ASTRO_VENUS"),
    "mars":    ("MARS",               "MARS",    "ASTRO_MARS"),
    "jupiter": ("JUPITER BARYCENTER", "JUPITER", "ASTRO_JUPITER"),
    "saturn":  ("SATURN BARYCENTER",  "SATURN",  "ASTRO_SATURN"),
    "uranus":  ("URANUS BARYCENTER",  "URANUS",  "ASTRO_URANUS"),
}

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class BodyPosition:
    """Position of a celestial body as seen by the observer."""

    name: str           # display name (e.g. "JUPITER")
    config_key: str     # config key (e.g. "jupiter")
    az_deg: float       # azimuth: 0=N, 90=E, 180=S, 270=W
    el_deg: float       # elevation: 0=horizon, 90=zenith
    above_horizon: bool  # True if el_deg > 0
    illumination: float | None  # fraction illuminated (0..1), Moon only
    colour_key: str     # theme colour key for this body


# ---------------------------------------------------------------------------
# PlanetTracker - thread-safe cached position calculator
# ---------------------------------------------------------------------------


class PlanetTracker:
    """
    Thread-safe singleton that computes body positions from the observer's
    location.  Caches results and refreshes every REFRESH_INTERVAL_SECONDS.

    The ephemeris loads in a background thread; while loading, ``loading``
    is True and ``get_positions()`` returns an empty list.  The theme
    can check ``loading`` to show a message on the display.

    Usage::

        tracker = PlanetTracker.instance()
        if tracker.loading:
            # show loading message
        else:
            positions = tracker.get_positions(lat, lng, bodies)
    """

    _instance: PlanetTracker | None = None
    _instance_lock = threading.Lock()

    @classmethod
    def instance(cls) -> PlanetTracker:
        with cls._instance_lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Discard the singleton so the next call creates a fresh tracker.

        Used after cache-clear to force a re-download of the ephemeris.
        """
        with cls._instance_lock:
            cls._instance = None

    @staticmethod
    def ephemeris_path() -> str:
        """Return the expected path of the ephemeris file.

        Stored alongside the TLE cache and config in the platform data dir.
        """
        from setup.configuration import PLATFORM_DATA_DIR
        return os.path.join(str(PLATFORM_DATA_DIR), EPHEMERIS_FILENAME)

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._positions: list[BodyPosition] = []
        self._last_refresh: float = 0.0
        self._last_lat: float | None = None
        self._last_lng: float | None = None
        self._last_bodies: tuple[str, ...] = ()
        self._ephemeris = None
        self._timescale = None
        self._wgs84 = None
        self.loading = False
        self.load_error: str | None = None
        self._load_thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Lazy skyfield initialisation (background thread)
    # ------------------------------------------------------------------

    def _ensure_skyfield(self) -> None:
        """Start background ephemeris loading if not already started."""
        if self._ephemeris is not None or self.loading or self.load_error:
            return

        self.loading = True
        self._load_thread = threading.Thread(
            target=self._load_ephemeris, daemon=True, name="ephemeris-loader"
        )
        self._load_thread.start()

    def _load_ephemeris(self) -> None:
        """Download/load the ephemeris in a background thread."""
        try:
            from skyfield.api import load, wgs84
        except ImportError:
            logger.warning("skyfield not installed; PlanetTracker disabled")
            self.loading = False
            self.load_error = "skyfield not installed"
            return

        from setup.configuration import PLATFORM_DATA_DIR
        cache_dir = str(PLATFORM_DATA_DIR)

        ephemeris_path = os.path.join(cache_dir, EPHEMERIS_FILENAME)

        try:
            load.path = cache_dir
            self._ephemeris = load(EPHEMERIS_FILENAME)
            self._timescale = load.timescale()
            self._wgs84 = wgs84
            logger.info("PlanetTracker: ephemeris loaded from %s", ephemeris_path)
        except Exception as exc:
            logger.warning("Failed to load ephemeris: %s", exc)
            self.load_error = str(exc)
        finally:
            self.loading = False

    # ------------------------------------------------------------------
    # Position computation
    # ------------------------------------------------------------------

    def get_positions(
        self,
        lat: float,
        lng: float,
        bodies: list[str],
    ) -> list[BodyPosition]:
        """Return cached positions, refreshing if stale or parameters changed.

        Returns a list of BodyPosition for all requested bodies (including
        those below the horizon).  Returns an empty list if skyfield is
        unavailable or still loading.
        """
        self._ensure_skyfield()
        if self._ephemeris is None or self.loading:
            return []

        now = time.monotonic()
        bodies_tuple = tuple(bodies)

        with self._lock:
            stale = (
                now - self._last_refresh > REFRESH_INTERVAL_SECONDS
                or lat != self._last_lat
                or lng != self._last_lng
                or bodies_tuple != self._last_bodies
            )

            if stale:
                self._positions = self._compute(lat, lng, bodies)
                self._last_refresh = now
                self._last_lat = lat
                self._last_lng = lng
                self._last_bodies = bodies_tuple

            return list(self._positions)

    def _compute(
        self,
        lat: float,
        lng: float,
        body_keys: list[str],
    ) -> list[BodyPosition]:
        """Compute apparent alt/az for each requested body."""
        if self._ephemeris is None or self._timescale is None:
            return []

        earth = self._ephemeris["earth"]
        observer = self._wgs84.latlon(lat, lng)
        topocenter = earth + observer
        t = self._timescale.now()

        results: list[BodyPosition] = []

        for key in body_keys:
            if key not in BODY_DEFINITIONS:
                continue

            eph_name, display_name, colour_key = BODY_DEFINITIONS[key]

            try:
                body = self._ephemeris[eph_name]
            except KeyError:
                logger.warning("Body '%s' not in ephemeris", eph_name)
                continue

            try:
                astrometric = topocenter.at(t).observe(body)
                apparent = astrometric.apparent()
                alt, az, _distance = apparent.altaz()
                el_deg = alt.degrees
                az_deg = az.degrees
            except Exception as exc:
                logger.warning("Failed to compute position for %s: %s", key, exc)
                continue

            # Moon illumination
            illumination = None
            if key == "moon":
                try:
                    sun = self._ephemeris["sun"]
                    sun_app = topocenter.at(t).observe(sun).apparent()
                    moon_app = topocenter.at(t).observe(body).apparent()
                    phase_angle = sun_app.separation_from(moon_app).degrees
                    illumination = (1 + math.cos(math.radians(phase_angle))) / 2
                except Exception:
                    pass

            results.append(
                BodyPosition(
                    name=display_name,
                    config_key=key,
                    az_deg=az_deg,
                    el_deg=el_deg,
                    above_horizon=el_deg > 0.0,
                    illumination=illumination,
                    colour_key=colour_key,
                )
            )

        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def is_northern_hemisphere(lat: float) -> bool:
        """True if observer is in the northern hemisphere."""
        return lat >= 0.0

    @staticmethod
    def azimuth_to_strip_x(az_deg: float, lat: float, strip_width: int) -> int | None:
        """Map an azimuth to an x position on the horizon strip.

        Northern hemisphere: strip shows 90° (East) to 270° (West),
        centred on South (180°).  Left = East, right = West.

        Southern hemisphere: strip shows 270° (West) to 90° (East),
        centred on North (0°/360°).  Left = West, right = East.

        Returns None if the body is outside the 180° visible arc.
        """
        northern = PlanetTracker.is_northern_hemisphere(lat)

        if northern:
            # Visible arc: 90° to 270° (East through South to West)
            if az_deg < 90 or az_deg > 270:
                return None
            frac = (az_deg - 90) / 180.0
        else:
            # Visible arc: 270° to 360° then 0° to 90° (West through North to East)
            if az_deg > 90 and az_deg < 270:
                return None
            if az_deg >= 270:
                frac = (az_deg - 270) / 180.0
            else:
                frac = (az_deg + 90) / 180.0

        return int(round(frac * (strip_width - 1)))

    @staticmethod
    def elevation_to_strip_y(el_deg: float, strip_height: int, strip_y_origin: int) -> int:
        """Map an elevation to a y position within the horizon strip.

        el_deg=0 → bottom of strip (on horizon line)
        el_deg=90 → top of strip (at zenith)

        Clamped to strip bounds.
        """
        frac = max(0.0, min(1.0, el_deg / 90.0))
        # Higher elevation = higher on screen = lower y
        y = strip_y_origin + strip_height - 1 - int(round(frac * (strip_height - 1)))
        return y
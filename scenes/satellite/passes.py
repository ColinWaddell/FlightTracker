"""
Pass prediction for SatelliteScene.

Uses the sgp4 library (pure Python, no native deps) for orbital propagation.
Az/El and pass-finding are implemented directly here so there is no
dependency on pyorbital or pyproj.

Each PassWindow pre-bakes the full trajectory as a list of (az_deg, el_deg, t)
samples so draw() never has to do orbital math during the frame loop.
"""

from __future__ import annotations

import datetime
import logging
import math
from dataclasses import dataclass, field
from typing import List, Tuple

from sgp4.api import Satrec, jday as sgp4_jday

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

LOOKAHEAD_HOURS = 24
SAMPLE_INTERVAL_S = 10  # trajectory pre-bake resolution
SCAN_INTERVAL_S = 30  # coarser step used while hunting for pass windows
EARTH_R_KM = 6378.137

# ---------------------------------------------------------------------------
# Debug flag - flip to True to inject a fake always-active pass for testing.
# Remove once satellite scene has been validated on real hardware.
# ---------------------------------------------------------------------------
DEBUG_FAKE_PASS = False


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class PassWindow:
    """A single overhead pass for one satellite."""

    name: str
    tle_index: int
    aos: datetime.datetime
    los: datetime.datetime
    max_el: float
    trajectory: List[Tuple[float, float, float, datetime.datetime]] = field(
        default_factory=list
    )
    # Each entry: (azimuth_deg, elevation_deg, range_km, utc_time)


# ---------------------------------------------------------------------------
# Coordinate math (no external deps)
# ---------------------------------------------------------------------------


def jday_from_dt(dt: datetime.datetime) -> tuple[float, float]:
    """Convert a UTC datetime to (jd, fr) for sgp4."""
    return sgp4_jday(
        dt.year,
        dt.month,
        dt.day,
        dt.hour,
        dt.minute,
        dt.second + dt.microsecond * 1e-6,
    )


def gmst_rad(jd: float, fr: float) -> float:
    """Greenwich Mean Sidereal Time in radians."""
    t = (jd + fr - 2451545.0) / 36525.0
    deg = (
        280.46061837
        + 360.98564736629 * (jd + fr - 2451545.0)
        + t * t * (0.000387933 - t / 38710000.0)
    )
    return math.radians(deg % 360.0)


def teme_to_azel(
    r_teme: list[float],
    obs_lat_deg: float,
    obs_lon_deg: float,
    jd: float,
    fr: float,
) -> tuple[float, float]:
    """
    Convert a TEME position vector (km) to azimuth/elevation as seen from the
    observer at the given geodetic latitude and longitude (sea level).

    Returns (azimuth_deg, elevation_deg).
    Azimuth: 0° = North, increases clockwise.
    """
    # TEME -> ECEF via GMST rotation (sufficient accuracy for a 64x32 display)
    theta = gmst_rad(jd, fr)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    sx = r_teme[0] * cos_t + r_teme[1] * sin_t
    sy = -r_teme[0] * sin_t + r_teme[1] * cos_t
    sz = r_teme[2]

    # Observer ECEF (spherical Earth, altitude=0)
    lat = math.radians(obs_lat_deg)
    lon = math.radians(obs_lon_deg)
    ox = EARTH_R_KM * math.cos(lat) * math.cos(lon)
    oy = EARTH_R_KM * math.cos(lat) * math.sin(lon)
    oz = EARTH_R_KM * math.sin(lat)

    # Satellite relative to observer
    dx, dy, dz = sx - ox, sy - oy, sz - oz

    # Rotate into topocentric South-East-Zenith frame
    s = (
        math.sin(lat) * math.cos(lon) * dx
        + math.sin(lat) * math.sin(lon) * dy
        - math.cos(lat) * dz
    )
    e = -math.sin(lon) * dx + math.cos(lon) * dy
    z = (
        math.cos(lat) * math.cos(lon) * dx
        + math.cos(lat) * math.sin(lon) * dy
        + math.sin(lat) * dz
    )

    rng = math.sqrt(s * s + e * e + z * z)
    if rng < 1e-6:
        return 0.0, 90.0

    el = math.degrees(math.asin(z / rng))
    # atan2(e, -s) gives azimuth from North, clockwise
    az = math.degrees(math.atan2(e, -s)) % 360.0
    return az, el


def propagate(
    sat: Satrec, dt: datetime.datetime
) -> tuple[list[float], list[float]] | None:
    """Propagate sat to dt; returns (r_teme_km, v_teme_km_s) or None on error."""
    jd, fr = jday_from_dt(dt)
    err, r, v = sat.sgp4(jd, fr)
    if err != 0:
        return None
    return list(r), list(v)


def elevation_at(
    sat: Satrec,
    dt: datetime.datetime,
    lat: float,
    lng: float,
) -> float | None:
    """Return elevation in degrees at dt, or None on propagation error."""
    jd, fr = jday_from_dt(dt)
    err, r, _ = sat.sgp4(jd, fr)
    if err != 0:
        return None
    az, el = teme_to_azel(r, lat, lng, jd, fr)
    return el


# ---------------------------------------------------------------------------
# Debug helper
# ---------------------------------------------------------------------------


def fake_pass_window() -> PassWindow:
    """
    Synthetic pass for DEBUG_FAKE_PASS mode.
    Always active: AOS = 1 min ago, LOS = 5 min from now.
    Traces a south-east-to-north-east arc peaking at moderate elevation.

    Uses a sinusoidal azimuth profile so the angular rate is fastest near
    the peak (mimicking real orbital mechanics where the satellite is
    closest to the observer at max elevation).  This avoids the "seagull"
    artifact that a linear azimuth sweep produces on the polar plot.
    """
    now = datetime.datetime.utcnow()
    aos = now - datetime.timedelta(minutes=1)
    los = now + datetime.timedelta(minutes=5)
    total_seconds = int((los - aos).total_seconds())

    trajectory = []
    for i in range(0, total_seconds, SAMPLE_INTERVAL_S):
        frac = i / total_seconds
        t = aos + datetime.timedelta(seconds=i)

        # Azimuth: 160° -> 20° (SSE -> NNE), sinusoidal rate
        # sin(π·frac - π/2) maps [0,1] -> [-1,1], then scale to [0,1]
        az_frac = (math.sin(math.pi * frac - math.pi / 2) + 1.0) / 2.0
        az = 160.0 - az_frac * 140.0

        # Elevation: parabolic, peak at frac=0.5
        el = 55.0 * (1.0 - (2.0 * frac - 1.0) ** 2)

        trajectory.append((az, el, 408.0, t))

    return PassWindow(
        name="ISS (DEBUG)",
        tle_index=0,
        aos=aos,
        los=los,
        max_el=55.0,
        trajectory=trajectory,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_passes(
    tles: list[tuple[str, str, str]],
    lat: float,
    lng: float,
    min_elevation: float,
    max_count: int,
    lookahead_hours: int = LOOKAHEAD_HOURS,
) -> list[PassWindow]:
    """
    Compute upcoming passes for all TLEs from the observer position.

    Returns a list of PassWindows sorted by AOS.
    """
    if DEBUG_FAKE_PASS:
        return [fake_pass_window()]

    now = datetime.datetime.utcnow()
    end = now + datetime.timedelta(hours=lookahead_hours)
    windows: list[PassWindow] = []

    for idx, (name, line1, line2) in enumerate(tles):
        try:
            sat = Satrec.twoline2rv(line1, line2)
        except Exception as exc:
            logger.warning("TLE parse failed for '%s': %s", name, exc)
            continue

        # Scan at coarse resolution to find horizon crossings
        t = now
        step = datetime.timedelta(seconds=SCAN_INTERVAL_S)
        prev_el = elevation_at(sat, t, lat, lng)

        # If the satellite is already above the horizon right now, walk
        # backward to find the actual AOS so we don't miss in-progress passes.
        if prev_el is not None and prev_el > 0.0:
            back = now
            while back > now - datetime.timedelta(hours=6):
                back -= step
                el_back = elevation_at(sat, back, lat, lng)
                if el_back is not None and el_back <= 0.0:
                    # Found the rising edge; refine from here
                    window = refine_pass(
                        sat, name, idx, back, end, lat, lng, min_elevation
                    )
                    if window is not None:
                        windows.append(window)
                    break
            else:
                # No horizon crossing found in the past 6 hours - the sat may
                # have been above the horizon for a very long time.  Refine
                # from now anyway so we at least get the remainder of the pass.
                window = refine_pass(sat, name, idx, now, end, lat, lng, min_elevation)
                if window is not None:
                    windows.append(window)
            # Skip the forward scan - we already handled this satellite
            continue

        while t < end:
            t += step
            el = elevation_at(sat, t, lat, lng)
            if el is None or prev_el is None:
                prev_el = el
                continue

            # Rising edge: satellite crossed above horizon
            if prev_el <= 0.0 < el:
                aos_approx = t - step
                window = refine_pass(
                    sat, name, idx, aos_approx, end, lat, lng, min_elevation
                )
                if window is not None:
                    windows.append(window)
                    # Skip past the LOS of this pass to avoid duplicates
                    t = window.los + step

            prev_el = el

    windows.sort(key=lambda w: w.aos)
    return windows


def refine_pass(
    sat: Satrec,
    name: str,
    idx: int,
    aos_approx: datetime.datetime,
    end: datetime.datetime,
    lat: float,
    lng: float,
    min_elevation: float,
) -> PassWindow | None:
    """
    Given an approximate AOS, walk forward at fine resolution to find the
    exact AOS, LOS, and peak elevation, then pre-bake the trajectory.
    Returns None if the pass doesn't reach min_elevation.
    """
    fine = datetime.timedelta(seconds=SAMPLE_INTERVAL_S)

    # Find AOS (first moment elevation >= 0)
    t = aos_approx
    while t < end:
        el = elevation_at(sat, t, lat, lng)
        if el is not None and el >= 0.0:
            break
        t += fine
    else:
        return None
    aos = t

    # Walk forward collecting trajectory until elevation drops back below 0
    trajectory: list[tuple[float, float, float, datetime.datetime]] = []
    max_el = 0.0
    t = aos

    while t < end:
        jd, fr = jday_from_dt(t)
        err, r, _ = sat.sgp4(jd, fr)
        if err != 0:
            break
        az, el = teme_to_azel(r, lat, lng, jd, fr)
        if el < 0.0 and trajectory:
            break
        if el >= 0.0:
            rng = math.sqrt(r[0] ** 2 + r[1] ** 2 + r[2] ** 2) - EARTH_R_KM
            trajectory.append((az, el, rng, t))
            if el > max_el:
                max_el = el
        t += fine

    if not trajectory or max_el < min_elevation:
        return None

    los = trajectory[-1][3]
    return PassWindow(
        name=name,
        tle_index=idx,
        aos=aos,
        los=los,
        max_el=max_el,
        trajectory=trajectory,
    )


def current_passes(windows: list[PassWindow]) -> list[PassWindow]:
    """Return passes that are active right now (AOS <= now <= LOS)."""
    now = datetime.datetime.utcnow()
    return [w for w in windows if w.aos <= now <= w.los]


def current_position(window: PassWindow) -> tuple[float, float] | None:
    """
    Interpolate the current Az/El for an active pass.
    Returns (az_deg, el_deg) or None if trajectory is empty.
    """
    if not window.trajectory:
        return None

    now = datetime.datetime.utcnow()

    for i in range(len(window.trajectory) - 1):
        _, _, _, t0 = window.trajectory[i]
        _, _, _, t1 = window.trajectory[i + 1]
        if t0 <= now <= t1:
            az0, el0, _, _ = window.trajectory[i]
            az1, el1, _, _ = window.trajectory[i + 1]
            span = (t1 - t0).total_seconds()
            if span <= 0:
                return az0, el0
            frac = (now - t0).total_seconds() / span
            diff = ((az1 - az0 + 180) % 360) - 180
            az = (az0 + diff * frac) % 360
            el = el0 + (el1 - el0) * frac
            return az, el

    az, el, _, _ = window.trajectory[-1]
    return az, el

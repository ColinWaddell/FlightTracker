"""
Pass prediction for SatelliteScene.

Takes a list of (name, line1, line2) TLE tuples and an observer position,
and returns a list of PassWindow objects describing upcoming satellite passes
that meet the minimum elevation threshold.

Each PassWindow pre-bakes the full trajectory as a list of (az_deg, el_deg, t)
samples so draw() never has to call pyorbital during the frame loop.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import List, Tuple

from pyorbital.orbital import Orbital

# How far ahead to compute passes (hours)
LOOKAHEAD_HOURS = 24

# Trajectory sample interval (seconds)
SAMPLE_INTERVAL_S = 10


@dataclass
class PassWindow:
    """A single overhead pass for one satellite."""
    name: str           # Satellite display name
    tle_index: int      # Index into the TLE list (determines plot colour)
    aos: datetime.datetime   # Acquisition of Signal (rises above horizon)
    los: datetime.datetime   # Loss of Signal (drops below horizon)
    max_el: float            # Peak elevation in degrees
    trajectory: List[Tuple[float, float, datetime.datetime]] = field(default_factory=list)
    # Each trajectory entry: (azimuth_deg, elevation_deg, utc_time)


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

    Args:
        tles            : list of (name, line1, line2)
        lat, lng        : observer position in decimal degrees
        min_elevation   : minimum peak elevation in degrees; passes below
                          this threshold are discarded
        max_count       : cap on simultaneous satellites to include
        lookahead_hours : how far ahead to search

    Returns a list of PassWindows sorted by AOS, covering the next
    lookahead_hours from now.
    """
    now_utc = datetime.datetime.utcnow()
    windows: list[PassWindow] = []

    for idx, (name, line1, line2) in enumerate(tles):
        try:
            orb = Orbital(name, line1=line1, line2=line2)
            # get_next_passes returns [(rise_time, fall_time, max_el_time), ...]
            # horizon= is the minimum elevation at AOS/LOS
            raw_passes = orb.get_next_passes(
                now_utc,
                lookahead_hours,
                lng,   # pyorbital uses (lng, lat) order
                lat,
                0.0,   # observer altitude in km (sea level)
                horizon=0.0,  # find all passes that clear the horizon
            )
        except Exception as exc:
            print(f"[passes] prediction failed for '{name}': {exc}")
            continue

        for aos_t, los_t, max_el_t in raw_passes:
            # Sample the trajectory to find actual peak elevation
            try:
                _, peak_el = orb.get_observer_look(max_el_t, lng, lat, 0.0)
            except Exception:
                continue

            if peak_el < min_elevation:
                continue

            # Pre-bake the trajectory at SAMPLE_INTERVAL_S resolution
            trajectory: list[tuple[float, float, datetime.datetime]] = []
            t = aos_t
            dt = datetime.timedelta(seconds=SAMPLE_INTERVAL_S)
            while t <= los_t:
                try:
                    az, el = orb.get_observer_look(t, lng, lat, 0.0)
                    trajectory.append((az, el, t))
                except Exception:
                    pass
                t += dt

            if not trajectory:
                continue

            windows.append(
                PassWindow(
                    name=name,
                    tle_index=idx,
                    aos=aos_t,
                    los=los_t,
                    max_el=peak_el,
                    trajectory=trajectory,
                )
            )

    windows.sort(key=lambda w: w.aos)
    return windows


def current_passes(windows: list[PassWindow]) -> list[PassWindow]:
    """Return passes that are active right now (AOS <= now <= LOS)."""
    now = datetime.datetime.utcnow()
    return [w for w in windows if w.aos <= now <= w.los]


def current_position(window: PassWindow) -> tuple[float, float] | None:
    """
    Interpolate the current Az/El for a pass that is currently active.
    Returns (az_deg, el_deg) or None if the trajectory is empty.
    """
    if not window.trajectory:
        return None

    now = datetime.datetime.utcnow()

    # Find the two bracketing samples
    for i in range(len(window.trajectory) - 1):
        _, _, t0 = window.trajectory[i]
        _, _, t1 = window.trajectory[i + 1]
        if t0 <= now <= t1:
            az0, el0, _ = window.trajectory[i]
            az1, el1, _ = window.trajectory[i + 1]
            span = (t1 - t0).total_seconds()
            if span <= 0:
                return az0, el0
            frac = (now - t0).total_seconds() / span
            # Interpolate azimuth carefully across the 360→0 wrap
            diff = ((az1 - az0 + 180) % 360) - 180
            az = (az0 + diff * frac) % 360
            el = el0 + (el1 - el0) * frac
            return az, el

    # Past last sample — return the final position
    az, el, _ = window.trajectory[-1]
    return az, el

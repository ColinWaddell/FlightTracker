"""
SatelliteScene — Az-El polar plot for overhead satellite passes.

Shown when one or more tracked satellites are currently above the configured
minimum elevation.  Priority 2 (beats FlightScene at 1 and IdleScene at 0).

Display layout:
    Left  32×32  Az-El circular plot (horizon ring, north notch, trajectory
                 arcs, bright current-position dots).
    Right 32 col Cycling name + telemetry (speed / altitude), each satellite
                 rendered in its matching palette colour.

Data flow:
    TLEManager  →  passes.compute_passes()  →  list[PassWindow]
    poll() checks whether any PassWindow is active right now.
    draw() reads pre-baked trajectory data — no orbital math per frame.
"""

from __future__ import annotations

import datetime

from rgbmatrix import graphics

from setup import fonts, frames, screen
from setup.configuration import Config
from scenes.satellite import passes as passes_mod
from scenes.satellite import azel_plot

PRIORITY = 2

# How long (in seconds) to display each satellite's telemetry before cycling
CYCLE_INTERVAL_S = 4

# Right-column text positions
TEXT_COL_X = 33
NAME_Y = 8
SPEED_LABEL_Y = 18
SPEED_VALUE_Y = 24
ALT_LABEL_Y = 30  # bottom row

# Divider line x between plot and text area
DIVIDER_X = 31

_DIM_WHITE = graphics.Color(120, 120, 120)
_GREY = graphics.Color(60, 60, 60)


class SatelliteScene:
    """
    Priority-2 scene.  Shows overhead satellite passes on an Az-El polar plot
    with cycling name and telemetry in the right panel.
    """

    priority = PRIORITY

    def __init__(self, canvas, draw_square, tle_manager):
        self.canvas = canvas
        self.draw_square = draw_square
        self._tle_manager = tle_manager

        self._frame: int = 0
        self._pass_windows: list[passes_mod.PassWindow] = []
        self._windows_computed_at: float = 0.0

        # Which satellite's telemetry is currently shown in the right panel
        self._cycle_index: int = 0
        self._last_cycle_second: float = 0.0

        # Track drawn positions so we can erase them cleanly next frame
        self._last_positions: dict[str, tuple[int, int]] = {}  # name → (px, py)

        # Whether the ring has been drawn yet (drawn once on enter, redrawn on reset)
        self._ring_drawn: bool = False

    # ------------------------------------------------------------------
    # Scene protocol
    # ------------------------------------------------------------------

    def poll(self) -> None:
        """Refresh pass windows when stale; no-op otherwise."""
        cfg = Config.instance()
        now_ts = datetime.datetime.utcnow().timestamp()

        # Recompute if windows haven't been built yet or are all expired
        needs_refresh = (
            not self._pass_windows
            or all(w.los.timestamp() < now_ts for w in self._pass_windows)
        )

        if needs_refresh:
            self._recompute_passes(cfg)

    def has_data(self) -> bool:
        return bool(passes_mod.current_passes(self._pass_windows))

    def active(self) -> bool:
        return self.has_data()

    def on_enter(self) -> None:
        """Called by SceneManager on scene transition."""
        self.canvas.Clear()
        self.reset()

    def reset(self) -> None:
        self._frame = 0
        self._cycle_index = 0
        self._last_cycle_second = 0.0
        self._last_positions = {}
        self._ring_drawn = False

    def draw(self) -> None:
        self._frame += 1

        active = passes_mod.current_passes(self._pass_windows)
        if not active:
            return

        cfg = Config.instance()
        max_count = min(cfg.satellite_max_count, len(active))
        active = active[:max_count]

        # Draw ring once (persists across frames)
        if not self._ring_drawn:
            self._draw_divider()
            azel_plot.draw_horizon_ring(self.canvas)
            self._draw_trajectories(active)
            self._ring_drawn = True

        # Update current-position dots
        self._draw_positions(active)

        # Update right-panel text at ~1 fps
        if self._frame % int(frames.PER_SECOND) == 0:
            self._update_text_panel(active)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _recompute_passes(self, cfg) -> None:
        tles = self._tle_manager.get(timeout=5.0)
        if not tles:
            return
        try:
            self._pass_windows = passes_mod.compute_passes(
                tles,
                cfg.flight_lat,
                cfg.flight_lng,
                cfg.satellite_min_elevation,
                cfg.satellite_max_count,
            )
            self._windows_computed_at = datetime.datetime.utcnow().timestamp()
        except Exception as exc:
            print(f"[satellite] pass computation failed: {exc}")

    def _draw_divider(self) -> None:
        """Faint vertical line separating the plot from the text area."""
        for y in range(screen.HEIGHT):
            self.canvas.SetPixel(DIVIDER_X, y, _GREY.red, _GREY.green, _GREY.blue)

    def _draw_trajectories(self, active: list[passes_mod.PassWindow]) -> None:
        """Paint dim trajectory arcs for all currently active passes."""
        for window in active:
            traj_2d = [(az, el) for az, el, _ in window.trajectory]
            azel_plot.draw_trajectory(self.canvas, traj_2d, window.tle_index)

    def _draw_positions(self, active: list[passes_mod.PassWindow]) -> None:
        """Erase previous position dots and draw updated ones."""
        # Erase old dots
        for name, (px, py) in self._last_positions.items():
            self.canvas.SetPixel(px, py, 0, 0, 0)

        self._last_positions = {}
        for window in active:
            pos = passes_mod.current_position(window)
            if pos is None:
                continue
            az, el = pos
            azel_plot.draw_position(self.canvas, az, el, window.tle_index)
            px, py = azel_plot.azel_to_xy(az, el)
            self._last_positions[window.name] = (px, py)

        # Re-draw trajectories behind the dots (dots may have erased arc pixels)
        self._draw_trajectories(active)
        # Re-draw dots on top
        for window in active:
            pos = passes_mod.current_position(window)
            if pos is None:
                continue
            azel_plot.draw_position(self.canvas, pos[0], pos[1], window.tle_index)

    def _update_text_panel(self, active: list[passes_mod.PassWindow]) -> None:
        """
        Clear the right panel and render the currently cycled satellite's
        name and telemetry.
        """
        now_s = datetime.datetime.utcnow().timestamp()

        # Advance the cycle counter once per CYCLE_INTERVAL_S
        if now_s - self._last_cycle_second >= CYCLE_INTERVAL_S:
            self._cycle_index = (self._cycle_index + 1) % len(active)
            self._last_cycle_second = now_s

        window = active[self._cycle_index % len(active)]
        colour = azel_plot.sat_colour_bright(window.tle_index)

        # Clear text area
        self.draw_square(TEXT_COL_X, 0, screen.WIDTH, screen.HEIGHT, graphics.Color(0, 0, 0))

        # Satellite name (truncate to fit ~8 chars at small font)
        name = window.name[:10]
        graphics.DrawText(self.canvas, fonts.small, TEXT_COL_X, NAME_Y, colour, name)

        # Telemetry: speed and altitude from current position
        pos = passes_mod.current_position(window)
        if pos is not None:
            az, el = pos
            speed_kmh, alt_km = _compute_telemetry(window, az, el)

            cfg = Config.instance()
            if cfg.units == "i":
                speed_str = f"{int(speed_kmh * 0.621371)}mph"
                alt_str   = f"{int(alt_km * 3280.84)}ft"
            else:
                speed_str = f"{int(speed_kmh)}kph"
                alt_str   = f"{int(alt_km)}km"

            graphics.DrawText(
                self.canvas, fonts.extrasmall, TEXT_COL_X, SPEED_LABEL_Y,
                _DIM_WHITE, "spd"
            )
            graphics.DrawText(
                self.canvas, fonts.extrasmall, TEXT_COL_X, SPEED_VALUE_Y,
                colour, speed_str
            )
            graphics.DrawText(
                self.canvas, fonts.extrasmall, TEXT_COL_X, ALT_LABEL_Y,
                colour, alt_str
            )


# ---------------------------------------------------------------------------
# Telemetry helpers
# ---------------------------------------------------------------------------

def _compute_telemetry(
    window: passes_mod.PassWindow,
    az_deg: float,
    el_deg: float,
) -> tuple[float, float]:
    """
    Estimate orbital speed and altitude from the pass trajectory.

    Uses consecutive trajectory samples to derive instantaneous speed,
    and elevation angle + range geometry to estimate altitude.

    Returns (speed_kmh, altitude_km).
    """
    import math

    # Find the two trajectory samples that bracket the current time
    now = datetime.datetime.utcnow()
    traj = window.trajectory

    for i in range(len(traj) - 1):
        _, _, t0 = traj[i]
        _, _, t1 = traj[i + 1]
        if t0 <= now <= t1:
            az0, el0, _ = traj[i]
            az1, el1, _ = traj[i + 1]

            # Angular speed (degrees/second) in the sky → rough ground speed
            dt = (t1 - t0).total_seconds()
            if dt > 0:
                # Great-circle angle between the two Az/El positions
                daz = math.radians(az1 - az0)
                del_ = math.radians(el1 - el0)
                ang_speed_deg_s = math.sqrt(daz**2 + del_**2) * (180 / math.pi) / dt

                # Rough slant range via elevation angle (flat-Earth approx)
                # For LEO at ~400 km, range at el=0 ≈ 2300 km
                EARTH_R = 6371.0
                AVG_ALT = 400.0  # km, reasonable default
                el_rad = math.radians(max(1.0, el_deg))
                slant_km = (
                    -EARTH_R * math.sin(el_rad)
                    + math.sqrt(
                        (EARTH_R * math.sin(el_rad)) ** 2
                        + 2 * EARTH_R * AVG_ALT
                        + AVG_ALT ** 2
                    )
                )
                speed_kmh = math.radians(ang_speed_deg_s) * slant_km * 3600
                return speed_kmh, AVG_ALT

            break

    # Fallback: canonical ISS-like values
    return 27600.0, 408.0

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

        # Track drawn positions so we can update only when the pixel changes.
        # name → (px, py, tle_index)
        self._last_positions: dict[str, tuple[int, int, int]] = {}

        # Stash previous text draws so we can erase only what changed
        self._last_text: dict[str, tuple[str, int, int, graphics.Color]] = {}

        # Whether the ring has been drawn yet (drawn once on enter, redrawn on reset)
        self._ring_drawn: bool = False

    # ------------------------------------------------------------------
    # Scene protocol
    # ------------------------------------------------------------------

    def poll(self) -> None:
        """Refresh pass windows when stale; no-op otherwise."""
        cfg = Config.instance()
        now_ts = datetime.datetime.utcnow().timestamp()

        # Recompute if windows haven't been built yet, are all expired,
        # or are older than 1 hour (to catch new passes that overlap
        # with currently active ones).
        needs_refresh = (
            not self._pass_windows
            or all(w.los.timestamp() < now_ts for w in self._pass_windows)
            or (now_ts - self._windows_computed_at) > 3600
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
        self._last_text = {}
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
            # Clear plot area before redrawing ring + trajectories
            self.draw_square(0, 0, DIVIDER_X, screen.HEIGHT, graphics.Color(0, 0, 0))
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
            # Force redraw of ring + trajectories on next draw()
            self._ring_drawn = False
            self._last_positions = {}
        except Exception as exc:
            print(f"[satellite] pass computation failed: {exc}")

    def _draw_divider(self) -> None:
        """Faint vertical line separating the plot from the text area."""
        for y in range(screen.HEIGHT):
            self.canvas.SetPixel(DIVIDER_X, y, _GREY.red, _GREY.green, _GREY.blue)

    def _draw_trajectories(self, active: list[passes_mod.PassWindow]) -> None:
        """Paint dim trajectory arcs for all currently active passes."""
        for window in active:
            traj_2d = [(az, el) for az, el, _, _ in window.trajectory]
            azel_plot.draw_trajectory(self.canvas, traj_2d, window.tle_index)

    def _draw_positions(self, active: list[passes_mod.PassWindow]) -> None:
        """
        Update satellite position dots using a pixel-change-only strategy.

        On each frame the current Az/El is converted to a pixel.  If the
        pixel is the same as last frame nothing happens.  When the pixel
        *does* change:
          - the old pixel is repainted in the DIM (trail) colour
          - the new pixel is painted in the BRIGHT (current) colour

        This avoids redrawing the entire trajectory every frame and
        eliminates flicker.
        """
        new_positions: dict[str, tuple[int, int, int]] = {}

        for window in active:
            pos = passes_mod.current_position(window)
            if pos is None:
                continue
            az, el = pos
            px, py = azel_plot.azel_to_xy(az, el)
            new_positions[window.name] = (px, py, window.tle_index)

            old = self._last_positions.get(window.name)
            if old is None:
                # First frame for this satellite — just draw the bright dot
                azel_plot.draw_position(self.canvas, az, el, window.tle_index)
            else:
                old_px, old_py, old_idx = old
                if (px, py) != (old_px, old_py):
                    # Pixel changed: dim the old, brighten the new
                    azel_plot.draw_trail_pixel(self.canvas, old_px, old_py, old_idx)
                    azel_plot.draw_position(self.canvas, az, el, window.tle_index)

        # Dim any satellites that were active last frame but aren't now
        for name, (old_px, old_py, old_idx) in self._last_positions.items():
            if name not in new_positions:
                azel_plot.draw_trail_pixel(self.canvas, old_px, old_py, old_idx)

        self._last_positions = new_positions

    def _update_text_panel(self, active: list[passes_mod.PassWindow]) -> None:
        """
        Render the currently cycled satellite's name and telemetry in the
        right panel.  Uses a stash-and-erase strategy: old text is redrawn
        in black before new text is drawn on top, so only changed pixels
        are touched.
        """
        now_s = datetime.datetime.utcnow().timestamp()

        # Advance the cycle counter once per CYCLE_INTERVAL_S
        if now_s - self._last_cycle_second >= CYCLE_INTERVAL_S:
            self._cycle_index = (self._cycle_index + 1) % len(active)
            self._last_cycle_second = now_s

        window = active[self._cycle_index % len(active)]
        colour = azel_plot.sat_colour_bright(window.tle_index)

        # Satellite name (truncate to fit ~8 chars at small font)
        name = window.name[:10]

        # Telemetry: speed and altitude from current position
        pos = passes_mod.current_position(window)
        if pos is not None:
            az, el = pos
            telemetry = _compute_telemetry(window, az, el)

            cfg = Config.instance()
            if telemetry is not None:
                speed_kmh, alt_km = telemetry
                if cfg.units == "i":
                    speed_str = f"{int(speed_kmh * 0.621371)}mph"
                    alt_str   = f"{int(alt_km * 3280.84)}ft"
                else:
                    speed_str = f"{int(speed_kmh)}kph"
                    alt_str   = f"{int(alt_km)}km"
            else:
                speed_str = "--"
                alt_str = "--"
        else:
            speed_str = "--"
            alt_str = "--"

        # Build the set of text elements for this frame.
        # Each entry: (text, x, y, colour, font)
        new_texts: dict[str, tuple[str, int, int, graphics.Color, object]] = {
            "name":      (name,      TEXT_COL_X, NAME_Y,         colour,     fonts.small),
            "spd_label": ("spd",     TEXT_COL_X, SPEED_LABEL_Y,  _DIM_WHITE, fonts.extrasmall),
            "spd_value": (speed_str, TEXT_COL_X, SPEED_VALUE_Y,  colour,     fonts.extrasmall),
            "alt":       (alt_str,   TEXT_COL_X, ALT_LABEL_Y,    colour,     fonts.extrasmall),
        }

        black = graphics.Color(0, 0, 0)

        for key, (text, x, y, col, font) in new_texts.items():
            old = self._last_text.get(key)
            if old is not None:
                old_text, old_x, old_y, _, old_font = old
                # Only erase if something changed (text, position, or font)
                if (old_text, old_x, old_y, old_font) != (text, x, y, font):
                    graphics.DrawText(self.canvas, old_font, old_x, old_y, black, old_text)
            graphics.DrawText(self.canvas, font, x, y, col, text)

        self._last_text = new_texts


# ---------------------------------------------------------------------------
# Telemetry helpers
# ---------------------------------------------------------------------------

def _compute_telemetry(
    window: passes_mod.PassWindow,
    az_deg: float,
    el_deg: float,
) -> tuple[float, float] | None:
    """
    Estimate orbital speed and altitude from the pass trajectory.

    Uses consecutive trajectory samples to derive instantaneous speed,
    and reads altitude directly from pre-baked trajectory range data.

    Returns (speed_kmh, altitude_km), or None if unavailable.
    """
    import math

    # Find the two trajectory samples that bracket the current time
    now = datetime.datetime.utcnow()
    traj = window.trajectory

    for i in range(len(traj) - 1):
        _, _, _, t0 = traj[i]
        _, _, _, t1 = traj[i + 1]
        if t0 <= now <= t1:
            az0, el0, rng0, _ = traj[i]
            az1, el1, rng1, _ = traj[i + 1]

            dt = (t1 - t0).total_seconds()
            if dt > 0:
                # Azimuth delta with wrap-around handling
                daz = math.radians(((az1 - az0 + 180) % 360) - 180)
                del_ = math.radians(el1 - el0)
                # Approximate angular speed (small-angle approx, fine for 10 s steps)
                ang_speed_deg_s = math.sqrt(daz**2 + del_**2) * (180 / math.pi) / dt

                # Interpolate altitude at current time
                frac = (now - t0).total_seconds() / dt
                alt_km = rng0 + (rng1 - rng0) * frac

                # Slant range from observer: solve triangle Earth–observer–satellite
                EARTH_R = 6371.0
                el_rad = math.radians(max(1.0, (el0 + el1) / 2))
                slant_km = (
                    -EARTH_R * math.sin(el_rad)
                    + math.sqrt(
                        (EARTH_R * math.sin(el_rad)) ** 2
                        + 2 * EARTH_R * alt_km
                        + alt_km ** 2
                    )
                )

                speed_kmh = math.radians(ang_speed_deg_s) * slant_km * 3600
                return speed_kmh, alt_km

            break

    return None

"""
Az-El polar plot renderer for SatelliteScene.

Converts (azimuth, elevation) coordinates to pixel positions on a circular
polar plot and provides routines for drawing the circle, north notch,
trajectory arcs, and current-position dots.

Layout (within the left 32x32 region of the 64x32 canvas):
    Centre  : (PLOT_CX, PLOT_CY)
    Radius  : PLOT_RADIUS  (horizon ring)
    Azimuth : 0° = North = top of circle, increases clockwise
    Elevation: 0° = horizon (edge of circle), 90° = zenith (centre)
"""

from __future__ import annotations

import math

from display.rgbpanel import Colour

# ---------------------------------------------------------------------------
# Plot geometry
# ---------------------------------------------------------------------------

PLOT_CX = 48  # centre x within the canvas
PLOT_CY = 19  # centre y within the canvas
PLOT_RADIUS = 12  # pixels from centre to horizon ring

# ---------------------------------------------------------------------------
# Colour palette - one slot per satellite (index 0..4)
# Bright  = current-position dot
# Dim     = previous-position dot (trail)
# Dimmer  = predicted trajectory arc (light grey, uniform across satellites)
# ---------------------------------------------------------------------------

PALETTE_BRIGHT = [
    Colour(255, 220, 0),  # 0 amber
    Colour(0, 200, 255),  # 1 cyan
    Colour(180, 0, 255),  # 2 violet
    Colour(0, 255, 100),  # 3 green
    Colour(255, 60, 60),  # 4 red
]

PALETTE_DIM = [
    Colour(80, 60, 0),  # 0 amber dim
    Colour(0, 60, 80),  # 1 cyan dim
    Colour(55, 0, 80),  # 2 violet dim
    Colour(0, 80, 30),  # 3 green dim
    Colour(80, 20, 20),  # 4 red dim
]

PALETTE_DIMMER = [
    Colour(30, 25, 0),  # 0 amber dimmer
    Colour(0, 25, 30),  # 1 cyan dimmer
    Colour(20, 0, 30),  # 2 violet dimmer
    Colour(0, 30, 12),  # 3 green dimmer
    Colour(30, 8, 8),  # 4 red dimmer
]

RING_COLOUR = Colour(80, 80, 80)
NOTCH_COLOUR = Colour(200, 200, 200)


def sat_colour_bright(tle_index: int) -> Colour:
    return PALETTE_BRIGHT[tle_index % len(PALETTE_BRIGHT)]


def sat_colour_dim(tle_index: int) -> Colour:
    return PALETTE_DIM[tle_index % len(PALETTE_DIM)]


def sat_colour_dimmer(tle_index: int) -> Colour:
    return PALETTE_DIMMER[tle_index % len(PALETTE_DIMMER)]


# ---------------------------------------------------------------------------
# Coordinate conversion
# ---------------------------------------------------------------------------


def azel_to_xy(az_deg: float, el_deg: float) -> tuple[int, int]:
    """
    Convert (azimuth, elevation) to canvas pixel coordinates.

    Azimuth  0° = North (top of circle), increases clockwise.
    Elevation 0° = horizon (edge), 90° = zenith (centre).
    """
    # Distance from centre is proportional to (90° - elevation)
    r = PLOT_RADIUS * (90.0 - max(0.0, min(90.0, el_deg))) / 90.0
    # Azimuth: 0°=North=up means angle from +Y axis, clockwise
    angle_rad = math.radians(az_deg)
    px = PLOT_CX + round(r * math.sin(angle_rad))
    py = PLOT_CY - round(r * math.cos(angle_rad))
    return int(px), int(py)


# ---------------------------------------------------------------------------
# Drawing routines
# ---------------------------------------------------------------------------


def draw_horizon_ring(panel, canvas) -> None:
    panel.draw_circle(canvas, PLOT_CX, PLOT_CY, PLOT_RADIUS, RING_COLOUR)
    panel.draw_line(
        canvas,
        PLOT_CX,
        PLOT_CY - PLOT_RADIUS,
        PLOT_CX,
        PLOT_CY - PLOT_RADIUS - 1,
        NOTCH_COLOUR,
    )


def draw_trajectory(
    panel, canvas, trajectory: list[tuple[float, float]], tle_index: int
) -> None:
    """
    Paint the full pass trajectory as dimmer pixels (predicted path).

    Args:
        trajectory: list of (az_deg, el_deg) pairs for the pass
        tle_index : used to pick the dimmer palette colour
    """
    colour = sat_colour_dimmer(tle_index)
    for az, el in trajectory:
        x, y = azel_to_xy(az, el)
        panel.set_pixel(canvas, x, y, colour.red, colour.green, colour.blue)


def draw_trail(panel, canvas, az_deg: float, el_deg: float, tle_index: int) -> None:
    """Draw the previous-position pixel in the dim palette colour."""
    colour = sat_colour_dim(tle_index)
    x, y = azel_to_xy(az_deg, el_deg)
    panel.set_pixel(canvas, x, y, colour.red, colour.green, colour.blue)


def draw_trail_pixel(panel, canvas, px: int, py: int, tle_index: int) -> None:
    """Draw the previous-position pixel at given canvas coords in dim colour."""
    colour = sat_colour_dim(tle_index)
    panel.set_pixel(canvas, px, py, colour.red, colour.green, colour.blue)


def erase_trajectory(panel, canvas, trajectory: list[tuple[float, float]]) -> None:
    """Clear trajectory pixels (paint black)."""
    for az, el in trajectory:
        x, y = azel_to_xy(az, el)
        panel.set_pixel(canvas, x, y, 0, 0, 0)


def draw_position(panel, canvas, az_deg: float, el_deg: float, tle_index: int) -> None:
    """Draw the current-position dot in the bright palette colour."""
    colour = sat_colour_bright(tle_index)
    x, y = azel_to_xy(az_deg, el_deg)
    panel.set_pixel(canvas, x, y, colour.red, colour.green, colour.blue)

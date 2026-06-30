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

from rgbmatrix import graphics

# ---------------------------------------------------------------------------
# Plot geometry
# ---------------------------------------------------------------------------

PLOT_CX = 48  # centre x within the canvas
PLOT_CY = 19  # centre y within the canvas
PLOT_RADIUS = 12  # pixels from centre to horizon ring

# ---------------------------------------------------------------------------
# Colour palette — one slot per satellite (index 0..4)
# Bright  = current-position dot
# Dim     = previous-position dot (trail)
# Dimmer  = predicted trajectory arc (light grey, uniform across satellites)
# ---------------------------------------------------------------------------

PALETTE_BRIGHT = [
    graphics.Color(255, 220, 0),  # 0 amber
    graphics.Color(0, 200, 255),  # 1 cyan
    graphics.Color(180, 0, 255),  # 2 violet
    graphics.Color(0, 255, 100),  # 3 green
    graphics.Color(255, 60, 60),  # 4 red
]

PALETTE_DIM = [
    graphics.Color(80, 60, 0),  # 0 amber dim
    graphics.Color(0, 60, 80),  # 1 cyan dim
    graphics.Color(55, 0, 80),  # 2 violet dim
    graphics.Color(0, 80, 30),  # 3 green dim
    graphics.Color(80, 20, 20),  # 4 red dim
]

PALETTE_DIMMER = [
    graphics.Color(30, 25, 0),  # 0 amber dimmer
    graphics.Color(0, 25, 30),  # 1 cyan dimmer
    graphics.Color(20, 0, 30),  # 2 violet dimmer
    graphics.Color(0, 30, 12),  # 3 green dimmer
    graphics.Color(30, 8, 8),  # 4 red dimmer
]

RING_COLOUR = graphics.Color(80, 80, 80)
NOTCH_COLOUR = graphics.Color(200, 200, 200)


def sat_colour_bright(tle_index: int) -> graphics.Color:
    return PALETTE_BRIGHT[tle_index % len(PALETTE_BRIGHT)]


def sat_colour_dim(tle_index: int) -> graphics.Color:
    return PALETTE_DIM[tle_index % len(PALETTE_DIM)]


def sat_colour_dimmer(tle_index: int) -> graphics.Color:
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


def draw_horizon_ring(canvas) -> None:
    graphics.DrawCircle(canvas, PLOT_CX, PLOT_CY, PLOT_RADIUS, RING_COLOUR)
    graphics.DrawLine(
        canvas,
        PLOT_CX,
        PLOT_CY - PLOT_RADIUS,
        PLOT_CX,
        PLOT_CY - PLOT_RADIUS - 1,
        NOTCH_COLOUR,
    )


def draw_trajectory(
    canvas, trajectory: list[tuple[float, float]], tle_index: int
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
        canvas.SetPixel(x, y, colour.red, colour.green, colour.blue)


def draw_trail(canvas, az_deg: float, el_deg: float, tle_index: int) -> None:
    """Draw the previous-position pixel in the dim palette colour."""
    colour = sat_colour_dim(tle_index)
    x, y = azel_to_xy(az_deg, el_deg)
    canvas.SetPixel(x, y, colour.red, colour.green, colour.blue)


def draw_trail_pixel(canvas, px: int, py: int, tle_index: int) -> None:
    """Draw the previous-position pixel at given canvas coords in dim colour."""
    colour = sat_colour_dim(tle_index)
    canvas.SetPixel(px, py, colour.red, colour.green, colour.blue)


def erase_trajectory(canvas, trajectory: list[tuple[float, float]]) -> None:
    """Clear trajectory pixels (paint black)."""
    for az, el in trajectory:
        x, y = azel_to_xy(az, el)
        canvas.SetPixel(x, y, 0, 0, 0)


def draw_position(canvas, az_deg: float, el_deg: float, tle_index: int) -> None:
    """Draw the current-position dot in the bright palette colour."""
    colour = sat_colour_bright(tle_index)
    x, y = azel_to_xy(az_deg, el_deg)
    canvas.SetPixel(x, y, colour.red, colour.green, colour.blue)

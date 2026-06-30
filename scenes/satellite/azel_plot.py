"""
Az-El polar plot renderer for SatelliteScene.

Converts (azimuth, elevation) coordinates to pixel positions on a circular
polar plot and provides routines for drawing the circle, north notch,
trajectory arcs, and current-position dots.

Layout (within the left 32×32 region of the 64×32 canvas):
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

PLOT_CX = 15        # centre x within the canvas
PLOT_CY = 16        # centre y within the canvas
PLOT_RADIUS = 13    # pixels from centre to horizon ring

# North notch: a gap of ±NOTCH_HALF_DEG either side of 0° (North)
NOTCH_HALF_DEG = 12

# ---------------------------------------------------------------------------
# Colour palette — one slot per satellite (index 0..4)
# Bright versions for the current-position dot; dim for trajectory arcs.
# ---------------------------------------------------------------------------

_PALETTE_BRIGHT = [
    graphics.Color(255, 220,   0),   # 0 amber
    graphics.Color(  0, 200, 255),   # 1 cyan
    graphics.Color(180,   0, 255),   # 2 violet
    graphics.Color(  0, 255, 100),   # 3 green
    graphics.Color(255,  60,  60),   # 4 red
]

_PALETTE_DIM = [
    graphics.Color( 80,  60,   0),   # 0 amber dim
    graphics.Color(  0,  60,  80),   # 1 cyan dim
    graphics.Color( 55,   0,  80),   # 2 violet dim
    graphics.Color(  0,  80,  30),   # 3 green dim
    graphics.Color( 80,  20,  20),   # 4 red dim
]

_RING_COLOUR  = graphics.Color( 40,  40,  40)
_NOTCH_COLOUR = graphics.Color(  0,   0,   0)   # black = erase ring pixels


def sat_colour_bright(tle_index: int) -> graphics.Color:
    return _PALETTE_BRIGHT[tle_index % len(_PALETTE_BRIGHT)]


def sat_colour_dim(tle_index: int) -> graphics.Color:
    return _PALETTE_DIM[tle_index % len(_PALETTE_DIM)]


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
    """
    Draw the horizon circle with a notch at North.
    Should be called once per frame (or once on scene entry).
    """
    notch_lo = (360 - NOTCH_HALF_DEG) % 360
    notch_hi = NOTCH_HALF_DEG

    for az in range(360):
        # Skip the north notch
        if az >= notch_lo or az <= notch_hi:
            continue
        x, y = azel_to_xy(az, 0.0)
        canvas.SetPixel(x, y, _RING_COLOUR.red, _RING_COLOUR.green, _RING_COLOUR.blue)

    # Explicitly blank the notch pixels so redraw over prior content is clean
    for az in range(notch_lo, 360):
        x, y = azel_to_xy(az, 0.0)
        canvas.SetPixel(x, y, 0, 0, 0)
    for az in range(0, notch_hi + 1):
        x, y = azel_to_xy(az, 0.0)
        canvas.SetPixel(x, y, 0, 0, 0)


def draw_trajectory(canvas, trajectory: list[tuple[float, float]], tle_index: int) -> None:
    """
    Paint the full pass trajectory as dim pixels.

    Args:
        trajectory: list of (az_deg, el_deg) pairs for the pass
        tle_index : used to pick the dim palette colour
    """
    colour = sat_colour_dim(tle_index)
    for az, el in trajectory:
        x, y = azel_to_xy(az, el)
        canvas.SetPixel(x, y, colour.red, colour.green, colour.blue)


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

"""Airline logo widget - draws a 16x16 airline icon at (0, 0).

The icon is sourced from the operating carrier's ICAO code.  The primary
source is ``flight.airline_icao`` (populated by the data-source API -
FR24 provides it directly; tar1090/OSN get it via ``route_lookup``'s FR24
fallback).  When that is empty, the first 3 alphabetic characters of
``flight.icao_callsign`` are used as a fallback (e.g. ``UAL1583`` ->
``UAL``), corrected via ``_CALLSIGN_PREFIX_OVERRIDES`` for known
regional-subsidiary mismatches, and validated by an IATA-mapping gate
that rejects non-commercial operators (military, government, cargo)
whose 3-letter ICAO designators might otherwise match a logo file.  The
resulting code is the PNG filename - e.g. ``BAW`` ->
``assets/airlines/BAW.png``.  When no code resolves or the PNG is
missing, a black square with a white outline is drawn as a placeholder.

The widget is draw-once: it caches the last prefix rendered and skips
repainting while the prefix is unchanged (the icon is static per flight).
``reset()`` clears the cache so the next ``draw()`` always repaints -
used on flight change, route change, and scene re-entry to avoid leaving
a stale icon behind.
"""

from __future__ import annotations

import logging

from PIL import Image

from assets.airlines.lookups import (
    AirlineLogoNotFound,
    iata_to_png,
    icao_has_iata,
    icao_to_png,
)
from display.rgbpanel import Colour, RGBPanel
from utilities.flight import Flight

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Dimensions / position
# -----------------------------------------------------------------------

AIRLINE_ICON_SIZE = 16  # square: 16x16
AIRLINE_ICON_X = 0
AIRLINE_ICON_Y = 0

# White outline drawn when no icon PNG exists for the airline code.
_OUTLINE_COLOUR = Colour(255, 255, 255)

# -----------------------------------------------------------------------
# Asset loading (module-level cache, mirrors forecast_sprite._load_icon)
# -----------------------------------------------------------------------
_image_cache: dict[str, Image.Image | None] = {}


def _load_airline_icon(lookup: str) -> Image.Image | None:
    """Load an airline icon PNG, caching the result for reuse.

    Searches both the ``ica0`` and ``iata`` subdirectories.  Returns
    ``None`` if the prefix is empty or the PNG doesn't exist in either.
    """
    if not lookup:
        return None
    if lookup not in _image_cache:
        try:
            path = icao_to_png(lookup)
            _image_cache[lookup] = Image.open(path)
        except AirlineLogoNotFound:
            try:
                path = iata_to_png(lookup)
                _image_cache[lookup] = Image.open(path)
            except AirlineLogoNotFound:
                _image_cache[lookup] = None
    return _image_cache[lookup]


# Some regional/commuter callsign prefixes differ from the ICAO airline
# code used for the logo file.  For example, Aer Lingus regional flights
# use callsign prefix ``EAI`` but the logo is filed under ``EIN``.  When
# the API doesn't provide ``airline_icao`` and we fall back to the
# callsign prefix, this table corrects known mismatches before the file
# lookup.
#
# Expand this table as new callsign-to-ICAO mismatches are observed.
_CALLSIGN_PREFIX_OVERRIDES: dict[str, str] = {
    "EAI": "EIN",  # Aer Lingus regional -> Aer Lingus
}


def airline_icao_from_flight(flight: Flight) -> str:
    """Resolve the 3-letter ICAO airline code for logo lookup.

    Primary source: ``flight.airline_icao`` (operating carrier ICAO code
    from the data-source API).  This is trusted as-is and returned
    directly, even when the code has no IATA mapping (e.g. cargo carriers
    reported by FR24).

    Fallback: the first 3 alphabetic characters of
    ``flight.icao_callsign`` (e.g. ``UAL1583`` -> ``UAL``), corrected via
    ``_CALLSIGN_PREFIX_OVERRIDES`` for known regional-subsidiary
    mismatches.  The fallback is then validated with an IATA-mapping gate:
    codes without an IATA mapping are rejected (return ``""``) to avoid
    false positives from military, government, or other non-commercial
    operators whose 3-letter ICAO designators happen to match a logo
    file.  Commercial airlines virtually all have IATA codes; the gate
    is a pure local lookup via :func:`assets.airlines.lookups.icao_has_iata`
    and works for every data source.

    Returns ``""`` if neither path yields a valid code, so the
    placeholder outline is drawn instead.
    """
    icao = (flight.airline_icao or "").strip().upper()
    if icao:
        return icao
    callsign = (flight.icao_callsign or "").strip()
    if len(callsign) >= 3 and callsign[:3].isalpha():
        prefix = callsign[:3].upper()
        resolved = _CALLSIGN_PREFIX_OVERRIDES.get(prefix, prefix)
        if icao_has_iata(resolved):
            return resolved
        logger.debug(
            "Callsign-prefix fallback %r (from %r) rejected: no IATA mapping",
            resolved,
            prefix,
        )
    return ""


# -----------------------------------------------------------------------
# Widgets
# -----------------------------------------------------------------------


def _blank_region(panel: RGBPanel, canvas, x: int, y: int, size: int) -> None:
    """Blank a ``size``x``size`` region to black."""
    for py in range(y, y + size):
        for px in range(x, x + size):
            panel.set_pixel(canvas, px, py, 0, 0, 0)


def _draw_outline(panel: RGBPanel, canvas, x: int, y: int, size: int) -> None:
    """Draw a black square with a 1px white outline (placeholder icon)."""
    _blank_region(panel, canvas, x, y, size)
    last = size - 1
    panel.draw_line(canvas, x, y, x + last, y, _OUTLINE_COLOUR)  # top
    panel.draw_line(canvas, x, y + last, x + last, y + last, _OUTLINE_COLOUR)  # bottom
    panel.draw_line(canvas, x, y, x, y + last, _OUTLINE_COLOUR)  # left
    panel.draw_line(canvas, x + last, y, x + last, y + last, _OUTLINE_COLOUR)  # right


class AirlineLogoWidget:
    """Draws the airline logo at (0, 0), once per flight.

    When no icon PNG exists for the resolved airline code, nothing is
    drawn and ``icon_drawn`` is ``False`` - the caller uses this to
    decide whether to shift the journey text right or start at x=0.
    """

    def __init__(self, panel: RGBPanel):
        self.panel = panel
        self._last_prefix: str | None = None
        self._icon_drawn = False

    @property
    def width(self) -> int:
        """16 when an icon was drawn for the current flight, 0 otherwise."""
        return AIRLINE_ICON_SIZE if self._icon_drawn else 0

    @property
    def icon_drawn(self) -> bool:
        """Whether an icon was actually drawn for the current flight."""
        return self._icon_drawn

    def draw(self, canvas, flight: Flight) -> None:
        prefix = airline_icao_from_flight(flight)
        if prefix == self._last_prefix:
            return  # draw-once: icon is static per flight

        _blank_region(
            self.panel, canvas, AIRLINE_ICON_X, AIRLINE_ICON_Y, AIRLINE_ICON_SIZE
        )
        icon = _load_airline_icon(prefix)
        if icon is not None:
            self.panel.draw_image(canvas, AIRLINE_ICON_X, AIRLINE_ICON_Y, icon)
            self._icon_drawn = True
        else:
            self._icon_drawn = False
        self._last_prefix = prefix

    def reset(self) -> None:
        """Force the next ``draw()`` to repaint (clears stale-icon cache)."""
        self._last_prefix = None
        self._icon_drawn = False


class NullWidget:
    """No-op widget used when ``show_airline_icon`` is disabled."""

    width = 0

    def draw(self, canvas, flight: Flight) -> None:  # noqa: D401 - protocol
        pass

    def reset(self) -> None:
        pass

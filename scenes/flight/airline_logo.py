"""Airline logo widget - draws a 16x16 airline icon at (0, 0).

The icon is sourced from the operating carrier's ICAO code, resolved by
:func:`airline_icao_from_flight` from three sources in descending order of
confidence: ``flight.airline_icao`` (the flight's carrier, from a route
provider), ``flight.operator_icao`` (the airframe's registered operator,
from its Mode S hex address), and finally the first 3 alphabetic
characters of ``flight.icao_callsign``.  The two inferred sources are
corrected via ``_BRAND_OVERRIDES`` for franchise/wet-lease arrangements
and validated against a non-airline blocklist that rejects military,
government, and other non-commercial operators whose 3-letter ICAO
designators might otherwise match a logo file.  The resulting code is the
PNG filename - e.g. ``BAW`` -> ``assets/airlines/BAW.png``.  When no code
resolves or the PNG is missing, a black square with a white outline is
drawn as a placeholder.

The widget is draw-once: it caches the last prefix rendered and skips
repainting while the prefix is unchanged (the icon is static per flight).
``reset()`` clears the cache so the next ``draw()`` always repaints -
used on flight change, route change, and scene re-entry to avoid leaving
a stale icon behind.
"""

from __future__ import annotations

import logging
import re

from PIL import Image

from assets.airlines.lookups import (
    AirlineLogoNotFound,
    iata_to_png,
    icao_to_airline,
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


# Franchise / wet-lease brand overrides.
#
# These map an *operator* to the *brand* whose logo should be shown.  They
# are not data patches: they encode the stable commercial fact that one
# airline flies in another's livery.  Emerald Airlines (``EAI``) operates
# as Aer Lingus Regional, so its flights should show the Aer Lingus
# (``EIN``) logo even though the operator is a separate company.
#
# The table is applied to both resolution paths that produce an operator
# rather than a brand - the Mode S hex operator code and the callsign
# prefix - but never to a flight-level ``airline_icao`` from a provider,
# which is already the marketing carrier.
#
# Deliberately absent: entries for codes that merely *collide* with another
# operator (e.g. ``EAG``, shared by Emerald Airlines UK and European
# Aeronautical Group UK).  Collisions are resolved per-airframe by the Mode
# S hex operator code, which is unique to the aircraft; adding them here
# would show the wrong logo for whichever operator was not listed.
_BRAND_OVERRIDES: dict[str, str] = {
    "EAI": "EIN",  # Emerald Airlines / Aer Lingus Regional -> Aer Lingus
}

# Keywords in airline names that indicate a non-commercial operator
# (military, government, police, etc.).  When the callsign-prefix
# fallback resolves to a code whose ``icao_to_name`` entry contains one
# of these keywords, the fallback is rejected to avoid showing a
# military/government logo for a civilian flight (or vice-versa).
# This is more targeted than an IATA-mapping gate: many commercial
# shuttle/cargo/regional subsidiaries lack IATA codes but are still
# legitimate airlines with logos (e.g. SHT = British Airways Shuttle).
_NON_AIRLINE_KEYWORDS: tuple[str, ...] = (
    "air force",
    "army",
    "navy",
    "military",
    "government",
    "police",
    "coast guard",
    "ministry",
    "department of",
    "national guard",
    "armed forces",
    "air corps",
    "patrol",
    "squadron",
    "wing raf",
    "raf ",
)


# An ICAO flight identification (Doc 8585) is a 3-letter airline designator
# followed by a flight number, and that flight number always begins with a
# digit: ``BAW117``, ``UAL1583``, ``SHT7Z``, ``EAG56R``.
#
# Aircraft registrations do not have this shape.  Most non-US registrations
# are all-alphabetic once the dash is stripped by the ADS-B feed - ``G-BSFE``
# arrives as ``GBSFE``, ``D-AIZY`` as ``DAIZY``, ``EI-DEA`` as ``EIDEA`` -
# and general-aviation aircraft broadcast their registration in the callsign
# field because they have no flight number.  Taking the first 3 characters of
# one of those yields a meaningless prefix that nonetheless collides with a
# real airline designator (``GBSFE`` -> ``GBS`` -> "Global Air Services
# Nigeria"), so the prefix fallback must only run on callsigns that actually
# look like airline flights.
#
# Registrations that *do* contain digits fail the alphabetic prefix test
# instead (``N512SP`` -> ``N51``, ``JA8089`` -> ``JA8``, ``HL7402`` -> ``HL7``).
_AIRLINE_CALLSIGN_RE = re.compile(r"^([A-Z]{3})[0-9]")


def _is_non_airline(icao_code: str) -> bool:
    """Return True if *icao_code* is a known non-commercial operator.

    Checks the airline name in ``icao_to_name`` for military, government,
    police, or other non-commercial keywords.  Returns False for commercial
    airlines (including those without IATA codes, e.g. shuttle services)
    and for codes with no name mapping (treated as unknown, not non-airline).
    """
    name = icao_to_airline(icao_code)
    if not name:
        return False
    name_lower = name.lower()
    return any(kw in name_lower for kw in _NON_AIRLINE_KEYWORDS)


def airline_icao_from_flight(flight: Flight) -> str:
    """Resolve the 3-letter ICAO airline code for logo lookup.

    Three sources are tried in descending order of confidence.

    1. ``flight.airline_icao`` - the operating carrier reported by a route
       provider (adsbdb, AeroDataBox, FR24) for *this flight*.  Trusted
       as-is and returned directly, even when the code has no IATA mapping
       (e.g. cargo carriers or shuttle services) and even when it is a
       non-commercial operator: the blocklist below only guards the
       inferred paths.

    2. ``flight.operator_icao`` - the registered operator of *this
       airframe*, resolved from its Mode S hex address (see
       ``route_lookup._lookup_aircraft``).  This is the only per-aircraft
       signal available, so it is what resolves ICAO designator
       collisions: two operators sharing a 3-letter code still have
       distinct hex addresses.  Brand overrides and the non-airline
       blocklist both apply.  An operator code that matches no known
       airline name falls through to the callsign prefix rather than
       resolving to a logo that does not exist.

    3. The 3-letter designator of ``flight.icao_callsign``, but only when
       the callsign has the ICAO flight-identification shape of 3 letters
       followed by a digit (e.g. ``UAL1583`` -> ``UAL``).  A callsign that
       is a bare aircraft registration (``GBSFE``, ``DAIZY``) is rejected
       outright: a general-aviation aircraft has no airline, and slicing
       its first 3 characters would invent one.  Weakest signal even so -
       a callsign designator is not guaranteed to be the operator's ICAO
       code - so brand overrides and the blocklist apply here too.
       Commercial airlines without IATA codes (e.g. ``SHT`` = British
       Airways Shuttle) pass through correctly.

    Returns ``""`` if no path yields a usable code, so the placeholder
    outline is drawn instead.
    """
    icao = (flight.airline_icao or "").strip().upper()
    if icao:
        return icao

    operator = (getattr(flight, "operator_icao", "") or "").strip().upper()
    if len(operator) == 3 and operator.isalpha():
        resolved = _BRAND_OVERRIDES.get(operator, operator)
        if _is_non_airline(resolved):
            logger.debug(
                "Mode S operator %r (from %r) rejected: non-commercial operator",
                resolved,
                operator,
            )
            return ""
        # Only trust the operator code when it names a known airline.  An
        # unrecognised code would just produce a missing-logo placeholder,
        # so give the callsign prefix a chance instead.
        if icao_to_airline(resolved):
            return resolved
        logger.debug(
            "Mode S operator %r unknown to the airline database - "
            "falling through to the callsign prefix",
            resolved,
        )

    callsign = (flight.icao_callsign or "").strip().upper()
    match = _AIRLINE_CALLSIGN_RE.match(callsign)
    if not match:
        if callsign:
            logger.debug(
                "Callsign %r is not an airline flight identification "
                "(likely an aircraft registration) - no airline resolved",
                callsign,
            )
        return ""

    prefix = match.group(1)
    resolved = _BRAND_OVERRIDES.get(prefix, prefix)
    if _is_non_airline(resolved):
        logger.debug(
            "Callsign-prefix fallback %r (from %r) rejected: non-commercial operator",
            resolved,
            prefix,
        )
        return ""
    return resolved


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

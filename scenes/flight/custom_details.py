"""
Custom plane-info template parser and span builder.

Lets users define the content of the scrolling plane-info bar (rows 23-31)
via a template string with tagged placeholders, e.g.::

    {plane} | {symbol:altitude} {altitude} {symbol:speed} {ground_speed}

Tag syntax
----------
``{field}``                  bare field, uses default unit from config
``{field:unit}``             field with explicit unit override
``{field:#RRGGBB}``          field with custom hex colour, default unit
``{field:unit:#RRGGBB}``     field with both unit and colour
``{symbol:name}``            insert an icon glyph
literal text outside ``{}``  rendered as-is in the default plane colour

The parser produces ``Token`` objects which ``build_custom_spans()`` converts
to a ``Spans`` list (``list[Span]``) consumed by the existing
:class:`~display.scroller.Scroller`.
"""

from __future__ import annotations

import logging
import math
import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from display.spans import Span, Spans
from setup import fonts
from setup.themes import (
    TC,
    THEME_PLANE,
    THEME_PLANE_TLM,
    THEME_PLANE_TLM_UNITS,
)

if TYPE_CHECKING:
    from setup.configuration import Config
    from utilities.flight import Flight

logger = logging.getLogger(__name__)

# Sentinel shown when the template is empty or resolves to nothing.
NOT_DEFINED_TEXT = "<custom scroller not defined>"

# ---------------------------------------------------------------------------
# Field metadata
# ---------------------------------------------------------------------------

# Text fields - rendered with fonts.regular, colour THEME_PLANE.
TEXT_FIELDS: frozenset[str] = frozenset(
    {
        "callsign",
        "icao_callsign",
        "airline_icao",
        "operator_icao",
        "owner",
        "plane",
        "icao_type",
        "registration",
        "origin",
        "destination",
        "origin_name",
        "destination_name",
        "origin_municipality",
        "destination_municipality",
        "origin_country",
        "destination_country",
        "squawk",
    }
)

# Text fields that show a placeholder instead of being omitted when the
# flight has no value.  A Mode-A squawk is always four digits on real
# radar displays, so dashes keep the width and read as "no code".
FIELD_PLACEHOLDERS: dict[str, str] = {"squawk": "----"}

# Telemetry fields - rendered with fonts.small_symbols, colour THEME_PLANE_TLM.
# Each maps to a set of valid unit strings and a conversion function.
# Conversion functions take (raw_value, unit) and return (value_str, unit_str).


def format_number(value: int, separator: str) -> str:
    """Format an integer with the requested thousands separator.

    * ``"none"``   - ``10000``
    * ``"comma"``  - ``10,000``
    * ``"period"`` - ``10.000``
    """
    if separator == "comma":
        return f"{value:,}"
    if separator == "period":
        return f"{value:,}".replace(",", ".")
    return str(value)


def _convert_altitude(altitude_ft: float, unit: str) -> tuple[str, str]:
    """Convert altitude (stored in feet) to the requested unit."""
    if unit == "ft":
        return str(int(altitude_ft)), "ft"
    # metres
    return str(int(altitude_ft * 0.3048)), "m"


def _convert_ground_speed(ground_speed_kts: int, unit: str) -> tuple[str, str]:
    """Convert ground speed (stored in knots) to the requested unit."""
    if unit in ("kts", "knots"):
        return str(int(ground_speed_kts)), "kts"
    if unit == "mph":
        return str(int(ground_speed_kts * 1.15078)), "mph"
    # kmh / kph
    return str(int(ground_speed_kts * 1.852)), "kmh"


def _convert_heading(heading: int, unit: str) -> tuple[str, str]:
    """Heading has no unit options - always degrees."""
    return str(int(heading)), ""


def _convert_vertical_speed(vertical_speed_fpm: int, unit: str) -> tuple[str, str]:
    """Convert vertical speed (stored in feet/min) to the requested unit."""
    if unit == "fpm":
        return str(int(vertical_speed_fpm)), "fpm"
    # metres/sec
    return str(int(vertical_speed_fpm * 0.00508)), "ms"


def _convert_distance(distance_km: float, unit: str) -> tuple[str, str]:
    """Convert distance (stored in km) to the requested unit.

    ``knots``/``knts`` are accepted as aliases for nautical miles (nm) -
    the distance unit behind the knot.  An empty unit (unresolvable
    config preference) falls back to km.
    """
    if unit in ("", "km"):
        return str(int(distance_km)), "km"
    if unit == "m":
        return str(int(distance_km * 1000)), "m"
    if unit == "ft":
        return str(int(distance_km * 3280.84)), "ft"
    if unit in ("miles", "mi"):
        return str(int(distance_km * 0.621371)), "mi"
    # nm / knots / knts - nautical miles
    return str(int(distance_km * 0.539957)), "nm"


def _convert_bearing(bearing_deg: float, unit: str) -> tuple[str, str]:
    """Bearing has no unit options - always whole degrees, like heading."""
    return str(int(bearing_deg)), ""


# Map telemetry field -> (valid units, conversion function, config default key).
TELEMETRY_FIELDS: dict[str, tuple[frozenset[str], Callable, str | None]] = {
    "altitude": (frozenset({"ft", "m"}), _convert_altitude, "height_unit"),
    "ground_speed": (
        frozenset({"kts", "knots", "kmh", "kph", "mph"}),
        _convert_ground_speed,
        "speed_unit",
    ),
    "heading": (frozenset(), _convert_heading, None),
    "vertical_speed": (frozenset({"fpm", "ms"}), _convert_vertical_speed, None),
    # Distance from the observer, computed at fetch time (km canonical).
    # A bare tag follows the Height and Distance preference via
    # _DISTANCE_UNIT_MAP (metres -> km, feet -> ft).  "knots"/"knts" are
    # aliases for nautical miles.
    "distance_to_home": (
        frozenset({"km", "m", "ft", "miles", "mi", "nm", "knots", "knts"}),
        _convert_distance,
        "height_unit",
    ),
    # Initial bearing from the observer to the aircraft, computed at fetch
    # time (degrees clockwise from true north).  Like heading: no units and
    # no config default - add {symbol:degree} for the degree glyph.  The
    # value is None (field omitted) when no usable position was reported.
    "bearing_from_home": (frozenset(), _convert_bearing, None),
}

# All available fields (for validation / UI reference).
AVAILABLE_FIELDS: frozenset[str] = TEXT_FIELDS | frozenset(TELEMETRY_FIELDS)

# Config unit -> canonical unit string for altitude.
_HEIGHT_UNIT_MAP = {"ft": "ft", "m": "m"}

# Config unit -> canonical unit string for ground speed.
_SPEED_UNIT_MAP = {"kts": "kts", "kmh": "kmh", "mph": "mph"}

# Height and Distance config unit -> distance unit for the bare
# {distance_to_home} tag.  The metres preference keeps km - a horizontal
# distance in metres is unreadable - while the feet preference is
# honoured literally.
_DISTANCE_UNIT_MAP = {"m": "km", "ft": "ft"}

# ---------------------------------------------------------------------------
# Symbol metadata
# ---------------------------------------------------------------------------

# Symbol name -> glyph character in fonts.small_symbols (5x8-custom.bdf).
SYMBOL_MAP: dict[str, str] = {
    "altitude": "^",
    "speed": "~",
    "heading": "}",
    "degree": "*",
    "origin_arrow": ">",
    "dest_arrow": "<",
    # heading_arrow is a dynamic symbol: the glyph is selected at render
    # time from HEADING_ARROW_GLYPHS based on flight.heading.  The empty
    # string here is a placeholder so validate_template() accepts it;
    # build_custom_spans() handles it specially.
    "heading_arrow": "",
}

# 8 directional arrow glyphs (encodings 128-135 in 5x8-custom.bdf).
# Index = the result of _direction_index() - shared by the heading and
# bearing dynamic tags.
HEADING_ARROW_GLYPHS: tuple[str, ...] = (
    chr(129),  # 0 = N
    chr(130),  # 1 = NE
    chr(131),  # 2 = E
    chr(132),  # 3 = SE
    chr(133),  # 4 = S
    chr(134),  # 5 = SW
    chr(135),  # 6 = W
    chr(136),  # 7 = NW
)

# Cardinal direction names, indexed like HEADING_ARROW_GLYPHS.
HEADING_ARROW_DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

# Dynamic direction tags.  Their output is selected at render time from the
# flight's angles, so they are neither static SYMBOL_MAP glyphs (hence
# "{symbol:<name>}" is rejected) nor fields.  The heading pair reacts to
# where the aircraft's nose points; the bearing pair points from the
# observer toward the aircraft - the direction to look.
DYNAMIC_DIRECTION_TAGS: frozenset[str] = frozenset(
    {
        "heading_arrow",
        "heading_direction",
        "bearing_from_home_arrow",
        "bearing_from_home_direction",
    }
)


def _direction_index(degrees: float) -> int:
    """Index into the 8-point direction tables for degrees clockwise from north.

    Shared by the heading and bearing dynamic tags.  Uses floor(x + 0.5)
    instead of round() because Python's round() uses banker's rounding
    (round half to even), which gives wrong results at the .5 boundaries
    (e.g. 22.5° should be NE, not N).
    """
    return int(math.floor(degrees / 45.0 + 0.5)) % 8


# ---------------------------------------------------------------------------
# Token types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LiteralToken:
    """A run of literal text outside ``{}`` tags."""

    text: str


@dataclass(frozen=True)
class FieldToken:
    """A ``{field:unit:#colour}`` tag."""

    field: str
    unit: str | None  # None = use config default (telemetry) or N/A (text)
    colour: str | None  # None = use theme default for this field type


@dataclass(frozen=True)
class SymbolToken:
    """A ``{symbol:name}`` tag."""

    name: str
    colour: str | None  # None = use THEME_PLANE_TLM_UNITS


Token = LiteralToken | FieldToken | SymbolToken


# ---------------------------------------------------------------------------
# Tokenizer
# ---------------------------------------------------------------------------

# Matches a complete {...} tag.  Captures the inner content.
# Inner content is parsed separately to distinguish field tags from symbol tags.
_TAG_RE = re.compile(r"\{([^{}]*)\}")


def parse_template(template: str) -> list[Token]:
    """Split *template* into a list of :class:`Token` objects.

    Literal text between tags becomes :class:`LiteralToken`.  Each ``{...}``
    becomes either a :class:`FieldToken` or :class:`SymbolToken`.

    Unclosed braces (``{`` without a matching ``}``) are treated as literal
    text so the user sees the raw characters on the display rather than a
    parse error at render time.  Validation (``validate_template``) catches
    these as errors in the web UI before they are saved.
    """
    tokens: list[Token] = []
    pos = 0

    for match in _TAG_RE.finditer(template):
        # Literal text before this tag.
        if match.start() > pos:
            tokens.append(LiteralToken(template[pos : match.start()]))

        inner = match.group(1)
        tag_token = _parse_tag(inner)
        if tag_token is not None:
            tokens.append(tag_token)
        else:
            # Unparseable tag - keep the raw text as a literal so the
            # display shows something rather than crashing.
            tokens.append(LiteralToken(match.group(0)))

        pos = match.end()

    # Trailing literal text after the last tag.
    if pos < len(template):
        tokens.append(LiteralToken(template[pos:]))

    return tokens


def _parse_tag(inner: str) -> Token | None:
    """Parse the content inside ``{...}`` into a token.

    Returns ``None`` if the content is unparseable (caller treats the whole
    tag as literal text).
    """
    if not inner:
        return None

    # Dynamic direction tags ({heading_arrow}, {heading_direction} and the
    # bearing_from_home pair): {tag} or {tag:#colour} - not prefixed with
    # "symbol:" because they are not static glyphs, and not fields because
    # a unit makes no sense on them.
    for name in sorted(DYNAMIC_DIRECTION_TAGS):
        if inner == name or inner.startswith(name + ":"):
            colour = None
            if len(inner) > len(name):
                colour = inner[len(name) + 1 :]
                if not _is_valid_colour(colour):
                    return None
            return SymbolToken(name=name, colour=colour)

    # Symbol tag: {symbol:name} or {symbol:name:#colour}
    if inner.startswith("symbol:"):
        rest = inner[len("symbol:") :]
        name, colour = _split_colour(rest)
        if name not in SYMBOL_MAP:
            return None
        return SymbolToken(name=name, colour=colour)

    # Field tag: {field}, {field:unit}, {field:#colour}, {field:unit:#colour}
    # Split on the first ':' to separate field from options.
    # But we need to be careful: the colour also starts with '#'.
    # Format: field[:unit][:#RRGGBB]
    #   unit is alphanumeric, colour starts with '#'
    parts = inner.split(":", 2)

    field = parts[0]
    unit: str | None = None
    colour: str | None = None

    if len(parts) == 1:
        # {field}
        pass
    elif len(parts) == 2:
        # {field:unit} or {field:#colour}
        second = parts[1]
        if second.startswith("#"):
            colour = second
        else:
            unit = second
    else:
        # {field:unit:#colour}
        unit = parts[1]
        colour = parts[2]

    # Validate field name - if unknown, return None (treated as literal).
    if field not in AVAILABLE_FIELDS:
        return None

    # Validate unit if present - if invalid, return None.
    if unit is not None and field in TELEMETRY_FIELDS:
        valid_units = TELEMETRY_FIELDS[field][0]
        if valid_units and unit not in valid_units:
            return None
    elif unit is not None and field not in TELEMETRY_FIELDS:
        # Text fields don't accept units.
        return None

    # Validate colour format if present.
    if colour is not None and not _is_valid_colour(colour):
        return None

    return FieldToken(field=field, unit=unit, colour=colour)


def _split_colour(text: str) -> tuple[str, str | None]:
    """Split 'name' or 'name:#colour' into (name, colour)."""
    if ":" in text:
        name, colour = text.split(":", 1)
        return name, colour if _is_valid_colour(colour) else None
    return text, None


def _is_valid_colour(colour: str) -> bool:
    """Check if *colour* is a valid ``#RRGGBB`` hex string."""
    if not colour.startswith("#") or len(colour) != 7:
        return False
    try:
        int(colour[1:], 16)
        return True
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# Colour resolution
# ---------------------------------------------------------------------------


def _resolve_colour(colour_hex: str | None, theme_key: str):
    """Resolve a colour: custom hex if provided, else theme colour via TC."""
    if colour_hex is not None:
        r = int(colour_hex[1:3], 16)
        g = int(colour_hex[3:5], 16)
        b = int(colour_hex[5:7], 16)
        from display.rgbpanel import Colour

        return Colour(r, g, b)
    return TC(theme_key)


# ---------------------------------------------------------------------------
# Unit resolution
# ---------------------------------------------------------------------------


def _resolve_unit(field: str, requested_unit: str | None, cfg: Config) -> str:
    """Resolve the effective unit for a telemetry field.

    If *requested_unit* is provided, use it.  Otherwise fall back to the
    config default for fields that have one.
    """
    if requested_unit is not None:
        return requested_unit

    _valid_units, _convert, config_key = TELEMETRY_FIELDS[field]
    if config_key is None:
        # heading - no unit
        return ""

    config_val = getattr(cfg, config_key)
    if field == "altitude":
        return _HEIGHT_UNIT_MAP.get(config_val, "ft")
    if field == "ground_speed":
        return _SPEED_UNIT_MAP.get(config_val, "kmh")
    if field == "distance_to_home":
        return _DISTANCE_UNIT_MAP.get(config_val, "km")
    return config_val


# ---------------------------------------------------------------------------
# Span builder
# ---------------------------------------------------------------------------


def build_custom_spans(template: str, flight: Flight, cfg: Config) -> Spans:
    """Convert a template string into a ``Spans`` list for the Scroller.

    If the template is empty or all fields resolve to empty strings, returns
    a single span with the ``<custom scroller not defined>`` warning.
    """
    if not template or not template.strip():
        return [Span(TC(THEME_PLANE), fonts.regular, NOT_DEFINED_TEXT)]

    tokens = parse_template(template)
    spans: Spans = []

    for token in tokens:
        if isinstance(token, LiteralToken):
            if token.text:
                spans.append(Span(TC(THEME_PLANE), fonts.regular, token.text))

        elif isinstance(token, FieldToken):
            field_spans = _build_field_spans(token, flight, cfg)
            spans.extend(field_spans)

        elif isinstance(token, SymbolToken):
            if token.name == "heading_arrow":
                # Dynamic symbol: select glyph based on flight heading.
                heading = flight.heading or 0
                index = _direction_index(heading)
                glyph = HEADING_ARROW_GLYPHS[index]
                if glyph:
                    colour = _resolve_colour(token.colour, THEME_PLANE_TLM_UNITS)
                    spans.append(Span(colour, fonts.small_symbols, glyph))
            elif token.name == "heading_direction":
                # Dynamic text tag: select cardinal direction text (N, NE,
                # E, ...) based on flight heading.
                heading = flight.heading or 0
                index = _direction_index(heading)
                text = HEADING_ARROW_DIRECTIONS[index]
                colour = _resolve_colour(token.colour, THEME_PLANE)
                spans.append(Span(colour, fonts.regular, text))
            elif token.name == "bearing_from_home_arrow":
                # Dynamic symbol: the arrow points from the observer toward
                # the aircraft - the direction to look.  Nothing renders
                # while the bearing is unknown (None); 0 is a real bearing
                # (due north) and still renders.
                if flight.bearing_from_home is not None:
                    index = _direction_index(flight.bearing_from_home)
                    glyph = HEADING_ARROW_GLYPHS[index]
                    if glyph:
                        colour = _resolve_colour(token.colour, THEME_PLANE_TLM_UNITS)
                        spans.append(Span(colour, fonts.small_symbols, glyph))
            elif token.name == "bearing_from_home_direction":
                # Dynamic text tag: cardinal direction from the observer
                # toward the aircraft.
                if flight.bearing_from_home is not None:
                    index = _direction_index(flight.bearing_from_home)
                    text = HEADING_ARROW_DIRECTIONS[index]
                    colour = _resolve_colour(token.colour, THEME_PLANE)
                    spans.append(Span(colour, fonts.regular, text))
            else:
                glyph = SYMBOL_MAP.get(token.name, "")
                if glyph:
                    colour = _resolve_colour(token.colour, THEME_PLANE_TLM_UNITS)
                    spans.append(Span(colour, fonts.small_symbols, glyph))

    # If all spans are empty or the list is empty, show the warning.
    if not spans or all(s.text == "" for s in spans):
        return [Span(TC(THEME_PLANE), fonts.regular, NOT_DEFINED_TEXT)]

    return spans


def _build_field_spans(token: FieldToken, flight: Flight, cfg: Config) -> Spans:
    """Build Span(s) for a single field token."""
    raw_value = getattr(flight, token.field, "")

    # Text fields - simple value span.
    if token.field in TEXT_FIELDS:
        text = str(raw_value) if raw_value else FIELD_PLACEHOLDERS.get(token.field, "")
        if not text:
            return []
        colour = _resolve_colour(token.colour, THEME_PLANE)
        # Text fields use regular font; plane model and its ICAO type
        # designator are uppercased to match the existing model_spans()
        # behaviour.
        if token.field in ("plane", "icao_type"):
            text = text.upper()
        return [Span(colour, fonts.regular, text)]

    # Telemetry fields - value + optional unit suffix.
    if token.field in TELEMETRY_FIELDS:
        # None means no data at this fetch (an unknown bearing) - omit the
        # field entirely rather than rendering a default 0.
        if raw_value is None:
            return []

        valid_units, convert, _ = TELEMETRY_FIELDS[token.field]
        unit = _resolve_unit(token.field, token.unit, cfg)

        raw_num = raw_value if raw_value else 0
        value_str, unit_str = convert(raw_num, unit)
        value_str = format_number(int(value_str), cfg.number_separator)

        colour = _resolve_colour(token.colour, THEME_PLANE_TLM)
        result: Spans = [Span(colour, fonts.small_symbols, value_str)]

        if unit_str:
            unit_colour = _resolve_colour(token.colour, THEME_PLANE_TLM_UNITS)
            result.append(Span(unit_colour, fonts.small_symbols, unit_str))

        return result

    return []


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_template(template: str) -> list[str]:
    """Validate a template string and return a list of error messages.

    Returns an empty list if the template is valid.  This is called by the
    web UI before saving to reject invalid templates with inline errors.

    Checks:
    - Unclosed braces (``{`` without ``}``)
    - Unknown field names
    - Unknown unit names for telemetry fields
    - Units on text fields (which don't accept them)
    - Unknown symbol names
    - Invalid colour format
    - Empty tags (``{}``)
    """
    errors: list[str] = []

    if not template or not template.strip():
        # Empty template is allowed - it will show the warning message.
        return []

    # Check for unclosed braces.
    open_count = template.count("{")
    close_count = template.count("}")
    if open_count != close_count:
        errors.append(
            f"Mismatched braces: {open_count} opening '{{' but "
            f"{close_count} closing '}}'."
        )

    # Parse each tag and validate its contents.
    for match in _TAG_RE.finditer(template):
        inner = match.group(1)

        if not inner:
            errors.append("Empty tag '{}' is not allowed.")
            continue

        # Dynamic direction tags ({heading_arrow}, {heading_direction} and
        # the bearing_from_home pair): only a colour may follow the name.
        dynamic_name = None
        for name in DYNAMIC_DIRECTION_TAGS:
            if inner == name or inner.startswith(name + ":"):
                dynamic_name = name
                break

        if dynamic_name is not None:
            if ":" in inner:
                colour_part = inner.split(":", 1)[1]
                if not _is_valid_colour(colour_part):
                    errors.append(
                        f"Invalid colour '{colour_part}' in tag '{inner}'. "
                        f"Use #RRGGBB format (e.g. #FF8800)."
                    )
            continue

        # Symbol tag.
        if inner.startswith("symbol:"):
            rest = inner[len("symbol:") :]
            name, colour = _split_colour(rest)
            if name not in SYMBOL_MAP:
                valid = ", ".join(sorted(SYMBOL_MAP))
                errors.append(f"Unknown symbol '{name}'. Valid symbols: {valid}.")
            if ":" in rest and colour is None:
                errors.append(
                    f"Invalid colour in symbol tag '{inner}'. Use #RRGGBB format."
                )
            continue

        # Field tag.
        parts = inner.split(":", 2)
        field = parts[0]

        if field not in AVAILABLE_FIELDS:
            valid = ", ".join(sorted(AVAILABLE_FIELDS))
            errors.append(f"Unknown field '{field}'. Valid fields: {valid}.")
            continue

        unit: str | None = None
        colour: str | None = None

        if len(parts) == 2:
            second = parts[1]
            if second.startswith("#"):
                colour = second
            else:
                unit = second
        elif len(parts) == 3:
            unit = parts[1]
            colour = parts[2]

        # Validate unit.
        if unit is not None:
            if field in TEXT_FIELDS:
                errors.append(f"Field '{field}' does not accept units (got ':{unit}').")
            elif field in TELEMETRY_FIELDS:
                valid_units = TELEMETRY_FIELDS[field][0]
                if valid_units and unit not in valid_units:
                    valid_str = ", ".join(sorted(valid_units))
                    errors.append(
                        f"Invalid unit '{unit}' for field '{field}'. "
                        f"Valid units: {valid_str}."
                    )

        # Validate colour.
        if colour is not None and not _is_valid_colour(colour):
            errors.append(
                f"Invalid colour '{colour}' in tag '{inner}'. "
                f"Use #RRGGBB format (e.g. #FF8800)."
            )

    return errors

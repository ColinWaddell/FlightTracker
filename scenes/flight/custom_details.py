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
        "plane",
        "registration",
        "origin",
        "destination",
        "origin_name",
        "destination_name",
        "origin_municipality",
        "destination_municipality",
        "origin_country",
        "destination_country",
    }
)

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
}

# All available fields (for validation / UI reference).
AVAILABLE_FIELDS: frozenset[str] = TEXT_FIELDS | frozenset(TELEMETRY_FIELDS)

# Config unit -> canonical unit string for altitude.
_HEIGHT_UNIT_MAP = {"ft": "ft", "m": "m"}

# Config unit -> canonical unit string for ground speed.
_SPEED_UNIT_MAP = {"kts": "kts", "kmh": "kmh", "mph": "mph"}

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
# Index = floor(heading / 45 + 0.5) % 8 (round half up, matching the
# cardinal-direction logic from conditions_idle_theme._degrees_to_cardinal()).
HEADING_ARROW_GLYPHS: tuple[str, ...] = (
    chr(128),  # 0 = N
    chr(129),  # 1 = NE
    chr(130),  # 2 = E
    chr(131),  # 3 = SE
    chr(132),  # 4 = S
    chr(133),  # 5 = SW
    chr(134),  # 6 = W
    chr(135),  # 7 = NW
)

# Cardinal direction names for heading_arrow (used for error messages).
HEADING_ARROW_DIRECTIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

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

    # Dynamic symbol tag: {heading_arrow} or {heading_arrow:#colour}
    # (not prefixed with "symbol:" because it's not a static glyph).
    if inner == "heading_arrow" or inner.startswith("heading_arrow:"):
        rest = inner[len("heading_arrow") :]
        if rest:
            # Strip leading ":" and parse colour
            if rest.startswith(":"):
                colour = rest[1:]
                if not _is_valid_colour(colour):
                    return None
                return SymbolToken(name="heading_arrow", colour=colour)
            return None
        return SymbolToken(name="heading_arrow", colour=None)

    # Dynamic text tag: {heading_direction} or {heading_direction:#colour}
    # Outputs the cardinal direction (N, NE, E, ...) as text rather than a
    # glyph.  Not in SYMBOL_MAP so {symbol:heading_direction} is rejected.
    if inner == "heading_direction" or inner.startswith("heading_direction:"):
        rest = inner[len("heading_direction") :]
        if rest:
            if rest.startswith(":"):
                colour = rest[1:]
                if not _is_valid_colour(colour):
                    return None
                return SymbolToken(name="heading_direction", colour=colour)
            return None
        return SymbolToken(name="heading_direction", colour=None)

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
                # Use floor(x + 0.5) instead of round() because Python's
                # round() uses banker's rounding (round half to even),
                # which gives wrong results at the .5 boundaries
                # (e.g. 22.5° should be NE, not N).
                heading = flight.heading or 0
                index = int(math.floor(heading / 45.0 + 0.5)) % 8
                glyph = HEADING_ARROW_GLYPHS[index]
                if glyph:
                    colour = _resolve_colour(token.colour, THEME_PLANE_TLM_UNITS)
                    spans.append(Span(colour, fonts.small_symbols, glyph))
            elif token.name == "heading_direction":
                # Dynamic text tag: select cardinal direction text (N, NE,
                # E, ...) based on flight heading.  Same rounding math as
                # heading_arrow to avoid banker's rounding at .5 boundaries.
                heading = flight.heading or 0
                index = int(math.floor(heading / 45.0 + 0.5)) % 8
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
        text = str(raw_value) if raw_value else ""
        if not text:
            return []
        colour = _resolve_colour(token.colour, THEME_PLANE)
        # Text fields use regular font; plane model is uppercased to match
        # the existing model_spans() behaviour.
        if token.field == "plane":
            text = text.upper()
        return [Span(colour, fonts.regular, text)]

    # Telemetry fields - value + optional unit suffix.
    if token.field in TELEMETRY_FIELDS:
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

        # Dynamic heading_arrow tag: {heading_arrow} or {heading_arrow:#colour}
        if inner == "heading_arrow" or inner.startswith("heading_arrow:"):
            if ":" in inner:
                colour_part = inner.split(":", 1)[1]
                if not _is_valid_colour(colour_part):
                    errors.append(
                        f"Invalid colour '{colour_part}' in tag '{inner}'. "
                        f"Use #RRGGBB format (e.g. #FF8800)."
                    )
            continue

        # Dynamic heading_direction tag: {heading_direction} or
        # {heading_direction:#colour} - cardinal direction text (N, NE, ...).
        if inner == "heading_direction" or inner.startswith("heading_direction:"):
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

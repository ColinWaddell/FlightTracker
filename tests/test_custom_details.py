"""Tests for scenes/flight/custom_details.py - template parser and span builder."""

from unittest.mock import MagicMock, patch

from display.spans import Span
from scenes.flight.custom_details import (
    NOT_DEFINED_TEXT,
    AVAILABLE_FIELDS,
    SYMBOL_MAP,
    FieldToken,
    LiteralToken,
    SymbolToken,
    build_custom_spans,
    parse_template,
    validate_template,
)
from utilities.flight import Flight

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_flight(**kwargs) -> Flight:
    """Build a Flight with sensible defaults for testing."""
    defaults = dict(
        callsign="BAW123",
        icao_callsign="BAW123",
        airline_icao="BAW",
        plane="Boeing 787-9",
        registration="G-ZBKA",
        origin="EGLL",
        destination="KBOS",
        origin_name="London Heathrow",
        destination_name="Boston Logan Intl",
        origin_municipality="London",
        destination_municipality="Boston",
        origin_country="United Kingdom",
        destination_country="United States",
        altitude=38000,
        ground_speed=480,
        heading=270,
        vertical_speed=0,
    )
    defaults.update(kwargs)
    return Flight(**defaults)


def make_cfg(**kwargs):
    """Build a mock Config with sensible defaults."""
    cfg = MagicMock()
    cfg.height_unit = kwargs.get("height_unit", "ft")
    cfg.speed_unit = kwargs.get("speed_unit", "kts")
    return cfg


# ---------------------------------------------------------------------------
# parse_template - tokenization
# ---------------------------------------------------------------------------


class TestParseTemplate:
    def test_empty_string(self):
        assert parse_template("") == []

    def test_pure_literal(self):
        tokens = parse_template("hello world")
        assert len(tokens) == 1
        assert isinstance(tokens[0], LiteralToken)
        assert tokens[0].text == "hello world"

    def test_single_field_tag(self):
        tokens = parse_template("{plane}")
        assert len(tokens) == 1
        assert isinstance(tokens[0], FieldToken)
        assert tokens[0].field == "plane"
        assert tokens[0].unit is None
        assert tokens[0].colour is None

    def test_field_with_unit(self):
        tokens = parse_template("{altitude:ft}")
        assert len(tokens) == 1
        assert isinstance(tokens[0], FieldToken)
        assert tokens[0].field == "altitude"
        assert tokens[0].unit == "ft"

    def test_field_with_colour(self):
        tokens = parse_template("{altitude:#FF8800}")
        assert len(tokens) == 1
        assert isinstance(tokens[0], FieldToken)
        assert tokens[0].field == "altitude"
        assert tokens[0].colour == "#FF8800"
        assert tokens[0].unit is None

    def test_field_with_unit_and_colour(self):
        tokens = parse_template("{altitude:ft:#FF8800}")
        assert len(tokens) == 1
        assert isinstance(tokens[0], FieldToken)
        assert tokens[0].field == "altitude"
        assert tokens[0].unit == "ft"
        assert tokens[0].colour == "#FF8800"

    def test_symbol_tag(self):
        tokens = parse_template("{symbol:altitude}")
        assert len(tokens) == 1
        assert isinstance(tokens[0], SymbolToken)
        assert tokens[0].name == "altitude"
        assert tokens[0].colour is None

    def test_symbol_with_colour(self):
        tokens = parse_template("{symbol:altitude:#FF0000}")
        assert len(tokens) == 1
        assert isinstance(tokens[0], SymbolToken)
        assert tokens[0].name == "altitude"
        assert tokens[0].colour == "#FF0000"

    def test_mixed_literal_and_tags(self):
        tokens = parse_template("{plane} | {origin} to {destination}")
        assert len(tokens) == 5
        assert isinstance(tokens[0], FieldToken)
        assert isinstance(tokens[1], LiteralToken)
        assert tokens[1].text == " | "
        assert isinstance(tokens[2], FieldToken)
        assert isinstance(tokens[3], LiteralToken)
        assert tokens[3].text == " to "
        assert isinstance(tokens[4], FieldToken)

    def test_unknown_field_becomes_literal(self):
        tokens = parse_template("{unknown_field}")
        assert len(tokens) == 1
        assert isinstance(tokens[0], LiteralToken)
        assert tokens[0].text == "{unknown_field}"

    def test_empty_tag_becomes_literal(self):
        tokens = parse_template("{}")
        assert len(tokens) == 1
        assert isinstance(tokens[0], LiteralToken)
        assert tokens[0].text == "{}"

    def test_unclosed_brace_treated_as_literal(self):
        # The regex only matches complete {…} pairs, so an unclosed brace
        # ends up as literal text.
        tokens = parse_template("hello {world")
        assert len(tokens) == 1
        assert isinstance(tokens[0], LiteralToken)
        assert tokens[0].text == "hello {world"

    def test_text_field_with_unit_becomes_literal(self):
        # Text fields don't accept units - should fall back to literal.
        tokens = parse_template("{plane:ft}")
        assert len(tokens) == 1
        assert isinstance(tokens[0], LiteralToken)

    def test_invalid_unit_for_telemetry_becomes_literal(self):
        tokens = parse_template("{altitude:knots}")
        assert len(tokens) == 1
        assert isinstance(tokens[0], LiteralToken)

    def test_invalid_colour_becomes_literal(self):
        tokens = parse_template("{altitude:#XYZ}")
        assert len(tokens) == 1
        assert isinstance(tokens[0], LiteralToken)

    def test_knots_alias(self):
        tokens = parse_template("{ground_speed:knots}")
        assert len(tokens) == 1
        assert isinstance(tokens[0], FieldToken)
        assert tokens[0].unit == "knots"

    def test_kph_alias(self):
        tokens = parse_template("{ground_speed:kph}")
        assert len(tokens) == 1
        assert isinstance(tokens[0], FieldToken)
        assert tokens[0].unit == "kph"


# ---------------------------------------------------------------------------
# build_custom_spans - span construction
# ---------------------------------------------------------------------------


class TestBuildCustomSpans:
    def test_empty_template_returns_warning(self):
        flight = make_flight()
        cfg = make_cfg()
        spans = build_custom_spans("", flight, cfg)
        assert len(spans) == 1
        assert spans[0].text == NOT_DEFINED_TEXT

    def test_whitespace_only_template_returns_warning(self):
        flight = make_flight()
        cfg = make_cfg()
        spans = build_custom_spans("   ", flight, cfg)
        assert len(spans) == 1
        assert spans[0].text == NOT_DEFINED_TEXT

    def test_returns_list_of_spans(self):
        flight = make_flight()
        cfg = make_cfg()
        spans = build_custom_spans("{plane}", flight, cfg)
        assert isinstance(spans, list)
        assert all(isinstance(s, Span) for s in spans)

    def test_text_field_span(self):
        flight = make_flight()
        cfg = make_cfg()
        spans = build_custom_spans("{plane}", flight, cfg)
        assert len(spans) == 1
        assert spans[0].text == "BOEING 787-9"  # uppercased like model_spans

    def test_callsign_span(self):
        flight = make_flight()
        cfg = make_cfg()
        spans = build_custom_spans("{callsign}", flight, cfg)
        assert len(spans) == 1
        assert spans[0].text == "BAW123"

    def test_registration_span(self):
        flight = make_flight()
        cfg = make_cfg()
        spans = build_custom_spans("{registration}", flight, cfg)
        assert len(spans) == 1
        assert spans[0].text == "G-ZBKA"

    def test_origin_destination_spans(self):
        flight = make_flight()
        cfg = make_cfg()
        spans = build_custom_spans("{origin} to {destination}", flight, cfg)
        texts = [s.text for s in spans if s.text]
        assert "EGLL" in texts
        assert " to " in texts
        assert "KBOS" in texts

    def test_altitude_default_unit_ft(self):
        flight = make_flight(altitude=38000)
        cfg = make_cfg(height_unit="ft")
        spans = build_custom_spans("{altitude}", flight, cfg)
        texts = [s.text for s in spans]
        assert "38000" in texts
        assert "ft" in texts

    def test_altitude_unit_m(self):
        flight = make_flight(altitude=38000)
        cfg = make_cfg(height_unit="m")
        spans = build_custom_spans("{altitude}", flight, cfg)
        texts = [s.text for s in spans]
        # 38000 ft * 0.3048 = 11582 m
        assert "11582" in texts
        assert "m" in texts

    def test_altitude_explicit_unit_ft(self):
        flight = make_flight(altitude=38000)
        cfg = make_cfg(height_unit="m")  # config says m, but tag overrides
        spans = build_custom_spans("{altitude:ft}", flight, cfg)
        texts = [s.text for s in spans]
        assert "38000" in texts
        assert "ft" in texts

    def test_altitude_explicit_unit_m(self):
        flight = make_flight(altitude=38000)
        cfg = make_cfg(height_unit="ft")  # config says ft, but tag overrides
        spans = build_custom_spans("{altitude:m}", flight, cfg)
        texts = [s.text for s in spans]
        assert "11582" in texts
        assert "m" in texts

    def test_ground_speed_default_unit_kts(self):
        flight = make_flight(ground_speed=480)
        cfg = make_cfg(speed_unit="kts")
        spans = build_custom_spans("{ground_speed}", flight, cfg)
        texts = [s.text for s in spans]
        assert "480" in texts
        assert "kts" in texts

    def test_ground_speed_kmh(self):
        flight = make_flight(ground_speed=480)
        cfg = make_cfg(speed_unit="kmh")
        spans = build_custom_spans("{ground_speed}", flight, cfg)
        texts = [s.text for s in spans]
        # 480 kts * 1.852 = 888.96 -> int = 888 kmh
        assert "888" in texts
        assert "kmh" in texts

    def test_ground_speed_mph(self):
        flight = make_flight(ground_speed=480)
        cfg = make_cfg(speed_unit="mph")
        spans = build_custom_spans("{ground_speed}", flight, cfg)
        texts = [s.text for s in spans]
        # 480 kts * 1.15078 = 552 mph
        assert "552" in texts
        assert "mph" in texts

    def test_ground_speed_knots_alias(self):
        flight = make_flight(ground_speed=480)
        cfg = make_cfg(speed_unit="kmh")
        spans = build_custom_spans("{ground_speed:knots}", flight, cfg)
        texts = [s.text for s in spans]
        assert "480" in texts
        assert "kts" in texts  # normalised to "kts"

    def test_ground_speed_kph_alias(self):
        flight = make_flight(ground_speed=480)
        cfg = make_cfg(speed_unit="kts")
        spans = build_custom_spans("{ground_speed:kph}", flight, cfg)
        texts = [s.text for s in spans]
        # 480 kts * 1.852 = 888.96 -> int = 888 kmh
        assert "888" in texts
        assert "kmh" in texts  # normalised to "kmh"

    def test_heading_no_unit(self):
        flight = make_flight(heading=270)
        cfg = make_cfg()
        spans = build_custom_spans("{heading}", flight, cfg)
        assert len(spans) == 1
        assert spans[0].text == "270"

    def test_vertical_speed_fpm(self):
        flight = make_flight(vertical_speed=500)
        cfg = make_cfg()
        spans = build_custom_spans("{vertical_speed:fpm}", flight, cfg)
        texts = [s.text for s in spans]
        assert "500" in texts
        assert "fpm" in texts

    def test_vertical_speed_ms(self):
        flight = make_flight(vertical_speed=500)
        cfg = make_cfg()
        spans = build_custom_spans("{vertical_speed:ms}", flight, cfg)
        texts = [s.text for s in spans]
        # 500 fpm * 0.00508 = 2.54 -> int = 2
        assert "2" in texts
        assert "ms" in texts

    def test_symbol_span(self):
        flight = make_flight()
        cfg = make_cfg()
        spans = build_custom_spans("{symbol:altitude}", flight, cfg)
        assert len(spans) == 1
        assert spans[0].text == "^"

    def test_symbol_speed(self):
        spans = build_custom_spans("{symbol:speed}", make_flight(), make_cfg())
        assert spans[0].text == "~"

    def test_symbol_heading(self):
        spans = build_custom_spans("{symbol:heading}", make_flight(), make_cfg())
        assert spans[0].text == "}"

    def test_symbol_degree(self):
        spans = build_custom_spans("{symbol:degree}", make_flight(), make_cfg())
        assert spans[0].text == "*"

    def test_symbol_origin_arrow(self):
        spans = build_custom_spans("{symbol:origin_arrow}", make_flight(), make_cfg())
        assert spans[0].text == ">"

    def test_symbol_dest_arrow(self):
        spans = build_custom_spans("{symbol:dest_arrow}", make_flight(), make_cfg())
        assert spans[0].text == "<"

    def test_full_telemetry_template(self):
        flight = make_flight(altitude=38000, ground_speed=480, heading=270)
        cfg = make_cfg(height_unit="ft", speed_unit="kts")
        template = (
            "{symbol:altitude} {altitude} {symbol:speed} {ground_speed} "
            "{symbol:heading} {heading}{symbol:degree}"
        )
        spans = build_custom_spans(template, flight, cfg)
        texts = [s.text for s in spans]
        assert "^" in texts
        assert "38000" in texts
        assert "ft" in texts
        assert "~" in texts
        assert "480" in texts
        assert "kts" in texts
        assert "}" in texts
        assert "270" in texts
        assert "*" in texts

    def test_literal_text_preserved(self):
        spans = build_custom_spans(
            "{origin} -> {destination}", make_flight(), make_cfg()
        )
        texts = [s.text for s in spans]
        assert " -> " in texts

    def test_empty_field_value_skipped(self):
        flight = make_flight(plane="")
        cfg = make_cfg()
        spans = build_custom_spans("{plane}", flight, cfg)
        # Empty plane -> all spans empty -> warning
        assert len(spans) == 1
        assert spans[0].text == NOT_DEFINED_TEXT

    def test_mixed_empty_and_nonempty_fields(self):
        flight = make_flight(plane="", callsign="BAW123")
        cfg = make_cfg()
        spans = build_custom_spans("{plane} {callsign}", flight, cfg)
        texts = [s.text for s in spans if s.text]
        # plane is empty (skipped), space literal, callsign present
        assert "BAW123" in texts

    def test_custom_colour_applied(self):
        flight = make_flight()
        cfg = make_cfg()
        spans = build_custom_spans("{altitude:#FF8800}", flight, cfg)
        # The value span should have the custom colour
        from display.rgbpanel import Colour

        value_span = [s for s in spans if s.text.isdigit()][0]
        assert value_span.colour == Colour(255, 136, 0)

    def test_custom_colour_on_symbol(self):
        flight = make_flight()
        cfg = make_cfg()
        spans = build_custom_spans("{symbol:altitude:#00FF00}", flight, cfg)
        from display.rgbpanel import Colour

        assert spans[0].colour == Colour(0, 255, 0)

    def test_custom_colour_on_text_field(self):
        flight = make_flight()
        cfg = make_cfg()
        spans = build_custom_spans("{callsign:#0000FF}", flight, cfg)
        from display.rgbpanel import Colour

        assert spans[0].colour == Colour(0, 0, 255)

    def test_custom_colour_with_unit(self):
        flight = make_flight(altitude=38000)
        cfg = make_cfg(height_unit="ft")
        spans = build_custom_spans("{altitude:ft:#FF8800}", flight, cfg)
        from display.rgbpanel import Colour

        # Both value and unit spans should have the custom colour
        for s in spans:
            if s.text.isdigit() or s.text == "ft":
                assert s.colour == Colour(255, 136, 0)


# ---------------------------------------------------------------------------
# validate_template
# ---------------------------------------------------------------------------


class TestValidateTemplate:
    def test_empty_template_valid(self):
        assert validate_template("") == []

    def test_whitespace_only_valid(self):
        assert validate_template("   ") == []

    def test_valid_simple_field(self):
        assert validate_template("{plane}") == []

    def test_valid_field_with_unit(self):
        assert validate_template("{altitude:ft}") == []

    def test_valid_field_with_colour(self):
        assert validate_template("{altitude:#FF8800}") == []

    def test_valid_field_with_unit_and_colour(self):
        assert validate_template("{altitude:ft:#FF8800}") == []

    def test_valid_symbol(self):
        assert validate_template("{symbol:altitude}") == []

    def test_valid_symbol_with_colour(self):
        assert validate_template("{symbol:altitude:#FF0000}") == []

    def test_valid_mixed(self):
        template = "{plane} | {symbol:altitude} {altitude:ft} {callsign:#00FF00}"
        assert validate_template(template) == []

    def test_unknown_field(self):
        errors = validate_template("{unknown_field}")
        assert len(errors) == 1
        assert "unknown_field" in errors[0]

    def test_unknown_symbol(self):
        errors = validate_template("{symbol:unknown}")
        assert len(errors) == 1
        assert "unknown" in errors[0]

    def test_invalid_unit_for_altitude(self):
        errors = validate_template("{altitude:knots}")
        assert len(errors) == 1
        assert "knots" in errors[0]
        assert "altitude" in errors[0]

    def test_unit_on_text_field(self):
        errors = validate_template("{plane:ft}")
        assert len(errors) == 1
        assert "plane" in errors[0]

    def test_invalid_colour_format(self):
        errors = validate_template("{altitude:#XYZ}")
        assert len(errors) == 1
        assert "#XYZ" in errors[0]

    def test_invalid_colour_too_short(self):
        errors = validate_template("{altitude:#FF}")
        assert len(errors) == 1

    def test_empty_tag_error(self):
        errors = validate_template("{}")
        assert len(errors) == 1
        assert "Empty tag" in errors[0]

    def test_unclosed_brace_error(self):
        errors = validate_template("hello {world")
        assert len(errors) == 1
        assert "Mismatched braces" in errors[0]

    def test_multiple_errors(self):
        errors = validate_template("{bad_field} {altitude:knots} {}")
        assert len(errors) == 3

    def test_all_fields_valid(self):
        # Every field in AVAILABLE_FIELDS should validate without a unit.
        for field in sorted(AVAILABLE_FIELDS):
            assert validate_template("{{" + field + "}}") == []

    def test_all_symbols_valid(self):
        for name in sorted(SYMBOL_MAP):
            assert validate_template("{symbol:" + name + "}") == []

    def test_all_telemetry_units_valid(self):
        from scenes.flight.custom_details import TELEMETRY_FIELDS

        for field, (units, _, _) in TELEMETRY_FIELDS.items():
            for unit in units:
                assert validate_template("{" + field + ":" + unit + "}") == []

"""Tests for scenes/flight/journey/codes.py (ICAO display conversion)."""

from setup.configuration import Config
from scenes.flight.journey.codes import journey_display_code


def cfg(fmt: str = "iata") -> Config:
    c = Config.__new__(Config)
    c.data_store = {"airport_code_format": fmt}
    return c


class TestIataFormat:
    """Default format: codes pass through untouched."""

    def test_passthrough(self):
        assert journey_display_code("GLA", cfg()) == "GLA"

    def test_four_char_passthrough(self):
        # FAA local / ICAO codes relayed by providers stay as-is.
        assert journey_display_code("98KY", cfg()) == "98KY"

    def test_blank_untouched(self):
        assert journey_display_code("", cfg()) == ""


class TestIcaoFormat:
    def test_known_iata_converted(self):
        assert journey_display_code("GLA", cfg("icao")) == "EGPF"

    def test_london_heathrow(self):
        assert journey_display_code("LHR", cfg("icao")) == "EGLL"

    def test_lowercase_input_converted(self):
        assert journey_display_code("gla", cfg("icao")) == "EGPF"

    def test_us_local_style_code_converts(self):
        # OurAirports lists CTY (Cross City) in its IATA column, so the
        # reverse map carries it: ICAO display shows the real KCTY.
        assert journey_display_code("CTY", cfg("icao")) == "KCTY"

    def test_unknown_code_passthrough(self):
        # QQQ is FR24's no-IATA filler; KMQJ is already ICAO. Neither
        # is in the reverse table.
        for code in ("QQQ", "KMQJ", "98KY"):
            assert journey_display_code(code, cfg("icao")) == code

    def test_unknown_code_spacing_preserved(self):
        # Unconverted codes are returned untouched - no strip/upper.
        assert journey_display_code(" ? ", cfg("icao")) == " ? "

    def test_blank(self):
        assert journey_display_code("", cfg("icao")) == ""


class TestRealBundledTable:
    """Smoke tests against the shipped reverse map."""

    def test_map_file_exists(self):
        from pathlib import Path

        path = (
            Path(__file__).parent.parent
            / "assets"
            / "airports_iata_to_icao.json"
        )
        assert path.exists()

    def test_regional_airports_convert(self):
        assert journey_display_code("MAN", cfg("icao")) == "EGCC"
        assert journey_display_code("LTN", cfg("icao")) == "EGGW"
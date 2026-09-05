"""Tests for the assets/airports.py CSV builder (4-char airport codes plan).

The builder lives outside the packages (assets/ has no __init__.py), so
it is imported by file path.
"""

import importlib.util
import os

spec = importlib.util.spec_from_file_location(
    "airports_builder",
    os.path.join(os.path.dirname(__file__), "..", "assets", "airports.py"),
)
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def row(**overrides) -> dict:
    base = {
        "id": "1",
        "ident": "K0I8",
        "type": "small_airport",
        "name": "Cynthiana-Harrison County Airport",
        "continent": "NA",
        "country_name": "United States",
        "municipality": "Cynthiana",
        "gps_code": "K0I8",
        "icao_code": "",
        "iata_code": "",
        "local_code": "0I8",
        "score": "50",
    }
    base.update(overrides)
    return base


class TestIataPass:
    def test_iata_row_keyed_by_iata(self):
        airports, full, _ = builder.build_airports(
            [row(iata_code="LEX", icao_code="KLEX", local_code="")]
        )
        assert "LEX" in airports
        assert airports["LEX"]["name"] == "Cynthiana-Harrison County Airport"
        assert full == airports

    def test_icao_to_iata_mapping_built(self):
        _, _, ica0 = builder.build_airports(
            [row(iata_code="LEX", icao_code="KLEX", local_code="")]
        )
        assert ica0 == {"KLEX": "LEX"}

    def test_empty_icao_code_not_mapped(self):
        _, _, ica0 = builder.build_airports([row(iata_code="LEX", icao_code="")])
        assert "" not in ica0

    def test_overrides_win(self):
        airports, _, _ = builder.build_airports(
            [row(iata_code="LTN", icao_code="EGGW", local_code="")]
        )
        assert airports["LTN"]["name"] == "London Luton Airport"

    def test_full_is_a_copy_iata_untouched_by_locals(self):
        airports, full, _ = builder.build_airports([row(local_code="0I8")])
        assert "0I8" not in airports
        assert "0I8" in full
        assert "0I8" not in airports  # the returned IATA dict is unmodified


class TestLocalCodePass:
    def test_local_code_keyed(self):
        _, full, _ = builder.build_airports([row()])
        assert full["0I8"]["name"] == "Cynthiana-Harrison County Airport"

    def test_four_char_local_code_keyed(self):
        _, full, _ = builder.build_airports(
            [
                row(
                    ident="US-0789",
                    type="heliport",
                    name="Baptist Health Corbin Heliport",
                    local_code="98KY",
                )
            ]
        )
        assert "98KY" in full

    def test_iata_wins_collision(self):
        # Some countries' local codes coincide with real IATA codes.
        _, full, _ = builder.build_airports(
            [
                row(
                    iata_code="MAN", icao_code="EGCC", local_code="", name="Manchester"
                ),
                row(ident="OTHER", local_code="MAN", name="Some Other Field"),
            ]
        )
        assert full["MAN"]["name"] == "Manchester"

    def test_closed_airports_skipped(self):
        _, full, _ = builder.build_airports([row(type="closed")])
        assert "0I8" not in full

    def test_local_codes_over_four_chars_excluded(self):
        _, full, _ = builder.build_airports([row(local_code="SP0002")])
        assert "SP0002" not in full
        assert "SP00" not in full

    def test_duplicate_local_code_highest_score_wins(self):
        _, full, _ = builder.build_airports(
            [
                row(name="Low Score Field", local_code="0I8", score="10"),
                row(name="High Score Field", local_code="0I8", score="90"),
            ]
        )
        assert full["0I8"]["name"] == "High Score Field"

    def test_duplicate_local_code_score_fallback_on_garbage(self):
        _, full, _ = builder.build_airports(
            [
                row(name="Real Score", local_code="0I8", score="50"),
                row(name="Garbage Score", local_code="0I8", score="notanumber"),
            ]
        )
        assert full["0I8"]["name"] == "Real Score"

    def test_local_codes_uppercased(self):
        _, full, _ = builder.build_airports([row(local_code="  ab12 ")])
        assert "AB12" in full
        assert "ab12" not in full

"""Tests for the bundled aircraft body-class table (assets/aircraft_types.json)."""

import json
from pathlib import Path

import pytest

TABLE_PATH = Path(__file__).parents[1] / "assets" / "aircraft_types.json"
TOKENS = frozenset("wnrtbghm")

# Spot verdicts from the table's derivation rules (DOC 8643 wake/engine,
# curated narrow-body / regional / bizjet / military overrides).  Each pins a
# judgement call someone must not silently break while regenerating.
SPOT_CHECKS = {
    "A320": "n",  # mainstream narrow-body
    "A20N": "n",  # A320neo
    "B738": "n",
    "BCS3": "n",  # A220 family counts as narrow-body, not regional
    "C919": "n",
    "A339": "w",  # A330-900
    "B77W": "w",
    "A388": "w",  # wake S/J super-heavy
    "B748": "w",
    "B752": "n",  # wake-H narrow-fuselage exception
    "E145": "r",  # regional jets
    "E75L": "r",
    "CRJ9": "r",
    "E190": "r",
    "AT76": "t",  # turboprops
    "DH8D": "t",
    "C208": "t",  # Caravan: TP not bizjet
    "TBM9": "t",  # TBM is a private turboprop, not a business jet
    "B350": "t",  # King Air likewise
    "GLF5": "b",  # bizjets beat their wake category
    "GLEX": "b",
    "C56X": "b",
    "PC24": "b",
    "SF50": "b",  # light single-engine jet
    "C172": "g",
    "SR22": "g",
    "S92": "h",
    "R44": "h",
    "A139": "h",
    "F16": "m",
    "A124": "m",  # An-124 is cargo/military despite wake-H jet geometry
    "C17": "m",
}


def load_table():
    with open(TABLE_PATH) as fh:
        return json.load(fh)


def test_table_exists_and_loads():
    table = load_table()
    assert len(table) > 2500


def test_token_domain():
    table = load_table()
    assert set(table.values()) <= TOKENS


def test_spot_checks():
    table = load_table()
    mismatched = {
        code: (table.get(code), expect)
        for code, expect in SPOT_CHECKS.items()
        if table.get(code) != expect
    }
    assert not mismatched, mismatched


@pytest.mark.parametrize(
    ("code", "absent_reason"),
    [
        ("RRJ", "SSJ-100 designator exists in neither source"),
        ("CONC", "retired type absent from both sources"),
    ],
)
def test_known_absences(code, absent_reason):
    assert code not in load_table()

"""Airline IATA / ICAO code lookup, loaded from the bundled JSON table.

The data artifact is ``assets/lookups/airline_codes.json`` - generated
data; see ``README.md ## Attribution`` for the sources and never
hand-edit the file.  This module preserves the import surface the lookup
code has always used:
plain ``iata_to_icao`` / ``icao_to_iata`` / ``icao_to_name`` dicts.

Controlled-duplicate IATA keys (``4K*``/``K9*``) remain literal keys, as
they always did: they produce callsign strings for operators whose callsign
prefix is the asterisked duplicate.

The table loads once at import; a missing or broken file degrades to empty
dicts - asset problems must never crash a poll (same rule as
``utilities/aircraft_types.py``).
"""

from __future__ import annotations

import json
import logging

from utilities.lookup_data import LOOKUPS_DIR

logger = logging.getLogger(__name__)

_TABLE_PATH = LOOKUPS_DIR / "airline_codes.json"


def _load_table() -> dict:
    """Load the three maps; a missing/broken file degrades to empty."""
    try:
        with open(_TABLE_PATH, encoding="utf-8") as table_file:
            loaded = json.load(table_file)
        return loaded if isinstance(loaded, dict) else {}
    except Exception:  # noqa: BLE001 - asset problems must never crash a poll
        logger.warning("Failed to load %s: %s", _TABLE_PATH, "unavailable")
        return {}


_data = _load_table()

iata_to_icao: dict = _data.get("iata_to_icao") or {}
icao_to_iata: dict = _data.get("icao_to_iata") or {}
icao_to_name: dict = _data.get("icao_to_name") or {}

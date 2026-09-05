"""Shared helpers used by more than one route/aircraft provider."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bundled ICAO->IATA airport code table
# ---------------------------------------------------------------------------

_icao_to_iata: dict[str, str] = {}
_icao_to_iata_loaded = False


def _load_icao_to_iata() -> None:
    """Load the ICAO-to-IATA mapping from assets/airports_icao_to_iata.json."""
    global _icao_to_iata, _icao_to_iata_loaded
    if _icao_to_iata_loaded:
        return
    _icao_to_iata_loaded = True
    path = Path(__file__).parents[4] / "assets" / "airports_icao_to_iata.json"
    if path.exists():
        try:
            import json

            with open(path) as fh:
                _icao_to_iata = json.load(fh)
        except Exception:
            _icao_to_iata = {}


def icao_to_iata_code(icao: str) -> str:
    """Convert an ICAO airport code to IATA using the bundled table.

    Returns "" when unknown - the bundled table is the sole source.
    """
    icao = (icao or "").strip().upper()
    if not icao:
        return ""
    _load_icao_to_iata()
    return _icao_to_iata.get(icao, "")


def reset_icao_table_cache() -> None:
    """Reset the ICAO->IATA cache (used by tests)."""
    global _icao_to_iata, _icao_to_iata_loaded
    _icao_to_iata = {}
    _icao_to_iata_loaded = False


def fill_airport_details(route, side: str) -> bool:
    """Fill blank location fields for one end of *route* from airports.json.

    *side* is ``"origin"`` or ``"destination"``; the airport's name,
    municipality and country are looked up by the code stored on the
    route.  Only blank fields are filled, so callers can layer this over
    partial answers without losing data.  Returns True when anything
    changed.
    """
    from utilities.overhead_utilities import airport_info

    code = getattr(route, side, "") or ""
    if not code:
        return False

    details = airport_info(code) or {}
    name = details.get("name", "")
    municipality = details.get("municipality", "")
    country = details.get("country_name", "")
    if not (name or municipality or country):
        return False

    changed = False
    for field, value in (
        (f"{side}_name", name),
        (f"{side}_municipality", municipality),
        (f"{side}_country", country),
    ):
        if not getattr(route, field):
            setattr(route, field, value)
            changed = True
    return changed

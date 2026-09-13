"""Display-side journey codes: render IATA or ICAO per configuration.

Route providers emit IATA codes (plus ICAO/FAA-local codes for airports
without an IATA code).  The optional ICAO code format converts known
IATA codes to their 4-letter ICAO form at draw time, so the toggle needs
no re-lookup and works with cached routes.  Unknown codes - blank
fillers, FAA local codes, codes that are already ICAO - pass through
unchanged.
"""

from __future__ import annotations

from setup.configuration import Config
from utilities.lookups.providers.common.airports import iata_to_icao_code


def journey_display_code(code: str, cfg: Config) -> str:
    """Return *code* in the configured display family.

    ``airport_code_format == "icao"`` converts IATA codes via the bundled
    reverse table; anything the table cannot convert (filler text, FAA
    local codes, ICAO codes) is returned unchanged.
    """
    if not code or cfg.airport_code_format != "icao":
        return code
    return iata_to_icao_code(code) or code
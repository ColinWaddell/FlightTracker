"""Flight-number converters between IATA and ICAO forms.

A *flight number* is the airline code followed by the numeric (or
alphanumeric) suffix, e.g.::

    BA147   -> IATA form (passenger-facing)
    BAW147  -> ICAO form (operational / ATC)

The spoken ATC *callsign* (e.g. "Speedbird 147") is a separate mapping
and is **not** handled here -- only the code prefix is translated.

These helpers work on the full flight-number string: they split off the
leading airline code, translate it via the IATA<->ICAO tables in
``airline_codes``, and re-attach the suffix unchanged.
"""

from __future__ import annotations

import re

from assets.airlines import airline_codes

# A flight number = airline code prefix + suffix.
# IATA prefix is exactly 2 alphanumeric characters; ICAO prefix is exactly 3
# letters. The suffix is the rest (digits, sometimes with a trailing letter).
_IATA_FLIGHT_RE = re.compile(r"^([0-9A-Z]{2})([0-9A-Z].*)$")
_ICAO_FLIGHT_RE = re.compile(r"^([A-Z]{3})([0-9A-Z].*)$")


def flight_iata_to_icao(iata_code: str) -> str | None:
    """Return the ICAO airline code for a given IATA airline code, or ``None``
    if no mapping exists.
    """
    return airline_codes.iata_to_icao.get(iata_code.strip().upper(), None)


def flight_icao_to_iata(icao_code: str) -> str | None:
    """Return the IATA airline code for a given ICAO airline code, or ``None``
    if no mapping exists.
    """
    return airline_codes.icao_to_iata.get(icao_code.strip().upper(), None)


def icao_flight_to_iata(flight: str) -> str | None:
    """Convert an ICAO flight identifier to its IATA form.

    ``BAW147`` -> ``BA147``
    ``BAW147QA`` -> ``BA147``
    ``DLH401`` -> ``LH401``

    Returns ``None`` when the ICAO airline code has no IATA mapping, the
    suffix does not begin with digits, or the input is not recognisable.
    """
    m = _ICAO_FLIGHT_RE.match(flight.strip().upper())
    if not m:
        return None

    icao_prefix, suffix = m.group(1), m.group(2)
    iata_prefix = airline_codes.icao_to_iata.get(icao_prefix)
    if iata_prefix is None:
        return None

    numeric_suffix = re.match(r"\d+", suffix)
    if not numeric_suffix:
        return None

    return f"{iata_prefix}{numeric_suffix.group()}"


if __name__ == "__main__":
    # quick manual smoke test
    for f in ["BA147", "LH401", "AA100", "UA999", "DL42"]:
        print(f, "->", iata_flight_to_icao(f))
    for f in ["BAW147", "DLH401", "AAL100", "UAL999", "DAL42"]:
        print(f, "->", icao_flight_to_iata(f))

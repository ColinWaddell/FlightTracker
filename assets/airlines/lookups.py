"""
IATA / ICAO -> 16x16 airline logo PNG lookup.

Requires two things next to this file (or pass custom paths to `configure`):
  - airline_codes.py      (IATA<->ICAO mapping, included, built from OpenFlights)
  - airline_logos_16/      (folder of 16x16 PNGs named "<ICAO>.png", e.g. AAL.png)
    -> produced by download_logos.py

Usage:
    from airline_images import iata_to_png, iaco_to_png

    path = iata_to_png("BA")     # -> ".../airline_logos_16/BAW.png"
    path = iaco_to_png("BAW")    # -> ".../airline_logos_16/BAW.png"
"""

import os
from functools import cache

from assets.airlines import airline_codes

_HERE = os.path.dirname(os.path.abspath(__file__))

_IMAGE_DIR = os.path.join(_HERE, "airline_logos_16")

_IATA_TO_ICAO = airline_codes.iata_to_icao
_ICAO_TO_IATA = airline_codes.icao_to_iata
_ICAO_TO_NAME = airline_codes.icao_to_name


class AirlineLogoNotFound(Exception):
    """Raised when no logo file (or no code mapping) can be resolved."""


def configure(image_dir: str = None, codes_module=None) -> None:
    """Point the lookup at different data locations, e.g. if you store
    the logos folder or the code mappings somewhere other than next to
    this file.

    ``codes_module`` should be a module (or any object) exposing the same
    ``iata_to_icao``, ``icao_to_iata`` and ``icao_to_name`` mappings as
    ``airline_codes``.
    """
    global _IMAGE_DIR, _IATA_TO_ICAO, _ICAO_TO_IATA, _ICAO_TO_NAME
    if image_dir is not None:
        _IMAGE_DIR = image_dir
        icao_to_png.cache_clear()
    if codes_module is not None:
        _IATA_TO_ICAO = codes_module.iata_to_icao
        _ICAO_TO_IATA = codes_module.icao_to_iata
        _ICAO_TO_NAME = getattr(codes_module, "icao_to_name", {})
        iata_to_png.cache_clear()


@cache
def icao_to_airline(icao_code: str) -> str | None:
    """Return the airline name for a given ICAO airline code, or ``None``
    if no mapping exists.
    """
    return _ICAO_TO_NAME.get(icao_code.strip().upper(), None)


@cache
def icao_has_iata(icao_code: str) -> bool:
    """Return True if *icao_code* has an IATA airline code mapping.

    Used as a commercial-airline filter: virtually all scheduled passenger
    airlines have an IATA code, while military, government, cargo and
    charter operators typically do not.  Respects :func:`configure` overrides.
    """
    return icao_code.strip().upper() in _ICAO_TO_IATA


@cache
def icao_to_png(icao_code: str) -> str:
    """Return the path to the 16x16 PNG for a given ICAO airline code."""
    code = icao_code.strip().upper()
    path = os.path.join(_IMAGE_DIR, f"{code}.png")
    if os.path.isfile(path):
        return path
    raise AirlineLogoNotFound(
        f"No 16x16 logo found for ICAO code '{code}' (expected {path})"
    )


# Alias matching the name requested (note: "iaco" here, not "icao")
iaco_to_png = icao_to_png


@cache
def iata_to_png(iata_code: str) -> str:
    """Return the path to the 16x16 PNG for a given IATA airline code,
    by resolving it to an ICAO code first."""
    code = iata_code.strip().upper()
    icao_code = _IATA_TO_ICAO.get(code)
    if icao_code is None:
        raise AirlineLogoNotFound(f"No ICAO mapping found for IATA code '{code}'")
    return icao_to_png(icao_code)


if __name__ == "__main__":
    # quick manual smoke test
    for code in ["AA", "BA", "LH", "UA", "DL"]:
        try:
            print(code, "->", iata_to_png(code))
        except AirlineLogoNotFound as e:
            print(code, "->", e)

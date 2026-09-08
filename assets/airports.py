"""Build the bundled airport lookup tables from ourairports.com.

Run from the assets directory; generates three files relative to the
current working directory:

  airports.json                IATA-keyed lookup (the bundled default)
  airports-full.json           IATA + FAA/local + ICAO/gps codes (opt-in via
                               the ``airport_lookup_full`` config toggle)
  airports_icao_to_iata.json   ICAO -> IATA display-code mapping
"""

import csv
import json
import urllib.request

url = "https://ourairports.com/airports.csv"

OVERRIDES = {
    "LTN": {
        "country_name": "United Kingdom",
        "municipality": "Luton, Bedfordshire",
        "name": "London Luton Airport",
    }
}


def _entry(row: dict) -> dict:
    return {
        "name": row["name"].replace("–", "-"),
        "country_name": row["country_name"],
        "municipality": row["municipality"],
    }


def _score(row: dict) -> float:
    try:
        return float(row.get("score") or 0)
    except (TypeError, ValueError):
        return 0.0


def build_airports(rows: list[dict]) -> tuple[dict, dict, dict]:
    """Build the airport tables from ourairports CSV rows.

    Returns ``(airports, full, ica0)``:

    ``airports``
        IATA-keyed entries - the historic bundled behaviour.

    ``full``
        A copy of ``airports`` extended with FAA/local-code keys for
        rows without an IATA code, plus the row's ICAO/gps code when
        the airport has no IATA code.  Route services answer with
        ICAO-style codes for such airports (KRGA), and without the key
        the code survives the ICAO->IATA fallback as a bare code with
        no name.  A row's ``icao_code`` is preferred over its
        ``gps_code`` (the ICAO column is sparse, but authoritative
        when present).  Codes longer than four characters are
        excluded: ICAO and FAA local codes are four at most (0I8,
        98KY), and the longer values in the CSV are administrative
        numbering (mostly Brazil) that route services never send as a
        display code.  IATA always wins a colliding key - some
        countries' local codes coincide with real IATA codes (a local
        "MAN", "PVG", ...) and must not shadow them.  Closed airports
        are skipped, and repeated codes are settled by the CSV's
        ``score`` column.

    ``ica0``
        ICAO -> IATA mapping for rows that have both codes.
    """
    rows = list(rows)

    # Pass 1 - IATA-keyed entries (historic behaviour, unchanged).
    airports: dict = {}
    ica0: dict = {}
    for row in rows:
        iata = row["iata_code"].strip()
        if iata and len(iata) == 3:
            icao = row["icao_code"].strip()
            if icao:
                ica0[icao] = iata
            airports[iata] = OVERRIDES.get(iata, _entry(row))

    # Pass 2 - FAA/local, ICAO and GPS codes for rows the IATA table
    # does not cover.
    candidates: dict[str, tuple[float, dict]] = {}

    def _offer(code: str, row: dict) -> None:
        code = code.strip().upper()
        if not code or len(code) > 4 or code in airports:
            return
        score = _score(row)
        current = candidates.get(code)
        if current is None or score > current[0]:
            candidates[code] = (score, _entry(row))

    for row in rows:
        if row["type"] == "closed":
            continue
        _offer(row["local_code"], row)
        # Airports without an IATA code are answered by route services
        # with their ICAO-style code (KRGA), which the ICAO->IATA pass
        # cannot rewrite; index the row's own ICAO/gps code so the full
        # table can name it.
        if not row["iata_code"].strip():
            _offer(row["icao_code"] or row["gps_code"], row)

    full = dict(airports)
    full.update({code: entry for code, (_, entry) in candidates.items()})

    return airports, full, ica0


def _write(path: str, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, sort_keys=True, ensure_ascii=False)


def main() -> None:
    with urllib.request.urlopen(url) as r:
        rows = list(csv.DictReader(line.decode("utf-8") for line in r))
    airports, full, ica0 = build_airports(rows)
    _write("airports.json", airports)
    _write("airports-full.json", full)
    _write("airports_icao_to_iata.json", ica0)


if __name__ == "__main__":
    main()

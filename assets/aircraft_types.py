"""Body-class lookup: ICAO type designator -> single-letter class token.

Documents the provenance of ``assets/aircraft_types.json`` and rebuilds it
from the public sources below.  Regeneration is not part of the device's
workflow - the bundled JSON is a snapshot; per the November 2026 decision the
tables and airline logos move to a dedicated data repository refreshed by
scheduled CI.

Designator sources (merged, DOC 8643 mirror preferred):

* ``George88000/aircraft_models`` - MIT, mirrors ICAO DOC 8643 columns
  (Manufacturer, Model, ICAO Designator, Description, Engine Type,
  Engine Number, Wake Turbulence).
* ``atoff/OpenAircraftType`` - fills 75 codes newer than the mirror and
  contributes the CLASS column (helicopter / gyrocopter / tiltrotor) for
  codes absent from the mirror.
* ``FAA JO 7340.2E`` decode pages (public domain, 5-2-A..Z under
  faa.gov/air_traffic/publications/atpubs/CNT/) - fills-only third source.
  Its type/wake class suffix is FAA legacy wording, so only engine type and
  the rotor kinds are merged; 40-plus codes neither sibling source carries
  (F18, NIM, BA46, VC10, the DC-8/9/727 "Q" hushkits, ...).

Class tokens (the buckets of the body-type filter):

    w  wide-body jet        wake J/H/S jet, minus narrow-fuselage exceptions
    n  narrow-body jet      wake M jet, mainstream
    r  regional jet         wake M jet in the regional families
    t  turboprop            turboprop/turboshaft engine, non-rotorcraft
    b  business jet         bizjet family codes, or jet + wake L
    g  light / GA           wake L, non-rotorcraft, non-jet
    h  rotorcraft           helicopter / gyrocopter / tiltrotor
    m  military             tactical, transports, trainers, warbirds (curated)
    o  other                electric / rocket / unmatchable

Codes absent from the table are unclassified: the filter must treat them as
unknown, never as excluded.
"""

import csv
import glob
import json
import re
import sys

MIRROR_CSV = "/tmp/opencode/aircraft_model_list.csv"  # aircraft_model_list.csv
OAT_GLOB = "/tmp/opencode/oat/src/**/*.txt"
FAA_GLOB = "/tmp/opencode/faa/5-2-*.htm"  # FAA JO 7340.2E decode pages (5-2-A..Z)
OUT_PATH = sys.argv[3] if len(sys.argv) > 3 else "assets/aircraft_types.json"

# Wake H jets that are actually narrow-body airliners.
NARROW_EXCEPTIONS = {"B752", "B753"}

# Regional jets: wake M, regional not mainline.
REGIONAL = {
    "E135",
    "E140",
    "E145",
    "E170",
    "E75L",
    "E75S",
    "E190",
    "E195",
    "E290",
    "E295",
    "ER3",
    "ER4",
    "ER5",
    "ERJ",
    "ERD",
    "CRJ1",
    "CRJ2",
    "CRJ7",
    "CRJ9",
    "CRJX",
    "RRJ",
}

# Business jets. Codes only apply when a source knows them; the list is
# pruned of code families whose designators both sources spell differently
# (GL6T/GL70/GL75, ER3/ER5 variants, F2EX - recorded in the build log).
BIZJET_CODES = {
    # Gulfstream
    "GLF2",
    "GLF3",
    "GLF4",
    "GLF5",
    "GLF6",
    "GL5T",
    "GL6T",
    "GL7T",
    "GLEX",
    "GL70",
    "GL75",
    "G150",
    "G159",
    "G280",
    "ASTR",
    # Cessna Citation
    "C25A",
    "C25B",
    "C25C",
    "C25M",
    "C500",
    "C501",
    "C510",
    "C525",
    "C550",
    "C551",
    "C55B",
    "C560",
    "C56X",
    "C650",
    "C680",
    "C68A",
    "C750",
    # Dassault Falcon
    "FA10",
    "FA20",
    "FA50",
    "FA5X",
    "FA6X",
    "FA7X",
    "F2TH",
    "F2EX",
    "F900",
    # Learjet
    "LJ24",
    "LJ25",
    "LJ28",
    "LJ31",
    "LJ35",
    "LJ40",
    "LJ45",
    "LJ55",
    "LJ60",
    "LJ70",
    "LJ75",
    "LJ85",
    # Bombardier / Embraer exec / Hawker / other
    "CL30",
    "CL35",
    "CL45",
    "CL60",
    "PRM1",
    "E50P",
    "E55P",
    "E545",
    "E550",
    "E35L",
    "LEG2",
    "EA50",
    "H25A",
    "H25B",
    "H25C",
    "HA4T",
    "PC24",
    "HDJT",
    "SF50",
    "G300",
    "G850",
}

# Military: tactical, transports, trainers, warbirds, historic jets.
# Deliberately partial - anything missed falls through to its fuselage or
# engine bucket, which is wrong only for show-off rare traffic.  The
# 2026-11-25 additions pin UK/EU in-service types that fell through:
# EUFI (Eurofighter Typhoon), VF35 (F-35B, the RAF variant), RFAL
# (Rafale), Q9 (MQ-9 Reaper), Q4 (RQ-4 Global Hawk), E390 (C-390
# Millennium; OAT also carries KC39 under the same airframe, already
# curated), MIR4 (Mirage IV), F18 (legacy Hornet designator) and NIM
# (Nimrod).  Deliberately NOT here: P8, a 737 airframe kept narrow-body
# by the fuselage rule.
MILITARY_CODES = {
    # Fighters / attack / bombers
    "F4",
    "RF4",
    "F5",
    "RF5",
    "F14",
    "F15",
    "F16",
    "F16X",
    "F18H",
    "F18S",
    "F22",
    "F35",
    "VF35",
    "EUFI",
    "MIR4",
    "MIR2",
    "RFAL",
    "Q9",
    "Q4",
    "F104",
    "A10",
    "A7",
    "F111",
    "SR71",
    # Trainers
    "T38",
    "AJET",
    "HAWK",
    # Transports / tankers (An-124 included: cargo, not body-filter material)
    "C17",
    "C130",
    "C30J",
    "A400",
    "C295",
    "CN35",
    "C27J",
    "C5M",
    "C5",
    "C141",
    "C133",
    "KC39",
    "E390",
    "IL76",
    "A124",
    "F18",
    "NIM",
    # Eastern / other historic jets
    "SB37",
    "SB39",
    "VAMP",
    "VNOM",
    "FL53",
    "FL54",
    "FL55",
    "METR",
    "GNAT",
    "JAGR",
    "STRK",
    "LTNG",
    "HERN",
    "SF35",
    "TOR",
    "DC3",
    "DC3T",
    "DAKH",
    # Warbirds
    "SPIT",
    "HURI",
    "LANC",
    "P51",
    "T51",
    "P47",
    "CORS",
}

ROTOR_DESCRIPTIONS = {"helicopter", "gyrocopter", "tiltrotor"}
OAT_ROTOR_CLASS = {"H", "G", "T"}  # helicopter, gyrocopter, tiltrotor
OAT_ENGINE = {
    "J": "Jet",
    "T": "Turboprop/Turboshaft",
    "P": "Piston",
    "E": "Electric",
    "R": "Rocket",
}

TOKENS = {
    "wb": "w",
    "nb": "n",
    "rj": "r",
    "tp": "t",
    "bj": "b",
    "ga": "g",
    "ro": "h",
    "mil": "m",
}

# Wake M jets that all three sources omit (checked 2026-11-25).  Already
# members of REGIONAL, so the fill classifies them as regional jets.
CURATED_FILLS = {
    "E140": ("M", "Jet"),
    "ER3": ("M", "Jet"),
    "ER4": ("M", "Jet"),
    "ER5": ("M", "Jet"),
    "RRJ": ("M", "Jet"),
}

# Codes curated as BIZJET_CODES but documented by no source, so their
# curation is inert (see the BIZJET_CODES comment).  Wake L jets, which is
# both what the fuselage is and what the rule needs.  These deliberately
# replace any coarse FAA fill (no-wake jets would land narrow-body).
CURATED_REPLACE_FILLS = {
    "GL6T": ("L", "Jet"),
    "GL70": ("L", "Jet"),
    "GL75": ("L", "Jet"),
    "F2EX": ("L", "Jet"),
}


def classify(code, wake, engine, rotor):
    """One source record -> bucket name, or None to leave the code out.

    Electric / rocket designs are deliberately excluded: with no body class
    they surface to the filter as Unknown rather than a one-code bucket.
    """
    engine = engine.strip().upper()
    wake = wake.strip().upper()

    if rotor:
        return "ro"
    if code in MILITARY_CODES:
        return "mil"
    if code in BIZJET_CODES:
        return "bj"
    if wake == "L" and engine == "JET":
        return "bj"

    if code in NARROW_EXCEPTIONS:
        return "nb"
    if wake in ("J", "H", "S") and engine == "JET":
        return "wb"

    if engine.startswith("TURBOPROP"):
        return "tp"

    if engine == "JET":
        if wake in ("M", "L/M"):
            return "rj" if code in REGIONAL else "nb"
        return "nb"  # jet with no wake knowledge - assume light jet class

    if wake == "L":
        return "ga"

    return None  # electric/rocket, vintage piston with M/H wake: Unknown


def load_code_wake_engine_rotor():
    """code -> (wake, engine, rotor). DOC 8643 mirror wins; OAT fills."""
    merged = {}
    provenance = {}
    with open(MIRROR_CSV) as csv_file:
        for row in csv.DictReader(csv_file):
            code = row["ICAO Designator"].strip()
            if not code:
                continue
            pair = (row["Wake Turbulence"].strip(), row["Engine Type"].strip())
            rotor = row["Description"].strip().lower() in ROTOR_DESCRIPTIONS
            seen = merged.setdefault(code, (pair, rotor))
            provenance.setdefault(code, "mirror")
            if seen != (pair, rotor):
                sys.exit(
                    f"wake/engine/rotor conflict for {code}: {seen} vs {(pair, rotor)}"
                )

    filled = 0
    for path in glob.glob(OAT_GLOB, recursive=True):
        if path.rsplit("/", 1)[1] == "manufacturer.txt":
            continue
        props = {}
        with open(path, encoding="utf-8", errors="replace") as prop_file:
            for line in prop_file:
                if "=" not in line:
                    continue
                key, value = line.split("=", 1)
                props[key.strip()] = value.strip()
        code = props.get("ICAO", "")
        if not code or code in merged or "JUN-" in code.upper():
            continue
        wake = props.get("WAKE", "").strip().upper()
        engine = OAT_ENGINE.get(props.get("ENG_TYPE", "").strip().upper(), "")
        rotor = props.get("CLASS", "").strip().upper() in OAT_ROTOR_CLASS
        if not (wake and engine):
            continue
        merged[code] = ((wake, engine), rotor)
        provenance[code] = "oat"
        filled += 1

    # FAA JO 7340.2E decode pages: fills only.  Its "Type/Wt Class" suffix is
    # FAA legacy wake wording (S/L/H/M), not the ICAO categories, so only the
    # engine type and the rotor kinds (H/G/T) are trusted here; such codes
    # classify jets via the no-wake rule unless curated.
    faa = load_faa()
    faa_fills = 0
    for code, (engine, rotor) in faa.items():
        if code in merged:
            (wake_now, engine_now), rotor_now = merged[code]
            if engine_now != engine or rotor_now != rotor:
                print(
                    f"FAA disagreement for {code}: existing "
                    f"(engine={engine_now}, rotor={rotor_now}) vs "
                    f"(engine={engine}, rotor={rotor})"
                )
            continue
        merged[code] = (("", engine), rotor)
        provenance[code] = "faa"
        faa_fills += 1

    # Legacy/development codes no source documents (verified against the
    # mirror, OpenAircraftType and FAA JO 7340.2E on 2026-11-25; E140 added
    # after the same sweep).  Wake M jets; they are already members of
    # REGIONAL, so the fill lands them in the regional bucket.  Upstream
    # PRs to carry them are still worth doing.
    for code, (wake, engine) in CURATED_FILLS.items():
        if code in merged:
            continue
        merged[code] = ((wake, engine), False)
        provenance[code] = "fill"
        filled += 1

    # Curated codes that were inert because no source documents them: fill
    # with their correct fuselage metadata, replacing any coarse FAA entry
    # for the same code (no-wake jets would otherwise land narrow-body).  A
    # mirror or OAT source of truth still wins - that gets a loud notice
    # instead of an override.
    for code, (wake, engine) in CURATED_REPLACE_FILLS.items():
        seen_from = provenance.get(code)
        if seen_from in ("mirror", "oat"):
            print(
                f"curated replace-fill {code} skipped: {seen_from} already documents it"
            )
            continue
        merged[code] = ((wake, engine), False)
        provenance[code] = "fill"
    return merged, filled, faa_fills


def load_faa():
    """code -> (engine, rotor), parsed from the FAA 7340.2E decode pages."""
    class_pattern = re.compile(r"^[LSAHGT]\d[A-Z]([/][A-Z]{1,2}[+]?)?$")
    code_pattern = re.compile(r"^[A-Z0-9]{3,4}$")
    out = {}
    for path in sorted(glob.glob(FAA_GLOB)):
        with open(path, encoding="utf-8", errors="replace") as page_file:
            page = page_file.read()
        for row in re.findall(r"<tr[^>]*>(.*?)</tr>", page, re.S | re.I):
            raw_cells = re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)
            cells = [
                re.sub(r"\s+", " ", value).strip()
                for value in (re.sub(r"<[^>]+>", "", cell) for cell in raw_cells)
            ]
            if len(cells) < 3 or not code_pattern.match(cells[0]):
                continue
            if not class_pattern.match(cells[1]):
                continue
            kind = cells[1][0]
            engine = OAT_ENGINE.get(cells[1][2], "")
            if not engine:
                continue
            rotor = kind in "HGT"
            out.setdefault(cells[0], (engine, rotor))
    return out


def build_table():
    merged, filled, faa_fills = load_code_wake_engine_rotor()

    # Curated codes that neither source knows are dropped, loudly.
    missing = sorted(
        (NARROW_EXCEPTIONS | REGIONAL | BIZJET_CODES | MILITARY_CODES) - set(merged)
    )
    if missing:
        print("curated codes not in either source:", missing)

    table, stats = {}, {}
    for code, ((wake, engine), rotor) in sorted(merged.items()):
        bucket = classify(code, wake, engine, rotor)
        if bucket is None:
            continue
        table[code] = TOKENS[bucket]
        stats[bucket] = stats.get(bucket, 0) + 1

    print(
        f"codes {len(merged)} (OAT fill {filled}, FAA fill {faa_fills}), "
        f"classified {len(table)}, unclassified {len(merged) - len(table)}"
    )
    print("buckets:", dict(sorted(stats.items(), key=lambda kv: -kv[1])))
    return table


def main():
    table = build_table()
    with open(OUT_PATH, "w") as f:
        json.dump(table, f, sort_keys=True, indent=2)
    print(f"wrote {OUT_PATH} ({len(table)} codes)")


if __name__ == "__main__":
    main()

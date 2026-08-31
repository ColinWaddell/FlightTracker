#!/usr/bin/env python3
"""One-shot route report for idents AeroAPI reportedly fails on. MANUAL.

    python3 aeroapi-route-report.py --key-file /tmp/aero.key

For each ident: one call with the app's shape-derived ident_type and one
plain call. Saves fixtures + prints the routing info found per ident,
alongside what the app's adapter would return.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.getcwd())

BASE = "https://aeroapi.flightaware.com/aeroapi"
OUT = "tests/fixtures/aeroapi/route-check"
IDENTS = ["N688CB", "GOHAS", "EAI34N", "CFE772"]


def fetch(path: str, params: dict, key: str):
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"x-apikey": key, "Accept": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def main() -> int:
    key_file = os.environ.get("KEY_FILE", "/tmp/aero.key")
    with open(key_file) as fh:
        key = fh.read().strip()
    outdir = OUT
    if "--out" in sys.argv:
        outdir = sys.argv[sys.argv.index("--out") + 1]
    os.makedirs(outdir, exist_ok=True)

    from scenes.flight.lookups.providers.flightaware.routes import _ident_type

    for ident in IDENTS:
        chosen = _ident_type(ident)
        print(f"\n### {ident}  (app sends ident_type={chosen!r})")
        for label, params in (
            ("app-style", {"ident_type": chosen} if chosen else {}),
            ("plain", {}),
        ):
            time.sleep(1.0)
            path = f"/flights/{urllib.parse.quote(ident)}"
            status, body = fetch(path, params, key)
            name = f"{ident}-{label}".lower()
            try:
                parsed = json.loads(body)
            except ValueError:
                parsed = body[:500]
            record = {
                "name": name,
                "ident": ident,
                "params": params,
                "status": status,
                "body": parsed,
            }
            with open(os.path.join(outdir, f"{name}.json"), "w") as fh:
                json.dump(record, fh, indent=2, sort_keys=True)

            if status != 200:
                detail = parsed if isinstance(parsed, str) else json.dumps(parsed)[:120]
                print(f"  {label:9} HTTP {status}: {detail}")
                continue
            flights = parsed.get("flights") or []

            routes = [
                f"{code_of(f, 'origin')}-{code_of(f, 'destination')}" for f in flights
            ]
            print(
                f"  {label:9} HTTP 200 flights={len(flights)} routes={routes or ['-']}"
            )
        print()
    return 0


def code_of(flight: dict, side: str) -> str:
    node = flight.get(side) or {}
    return node.get("code_iata") or node.get("code") or "-"


if __name__ == "__main__":
    sys.exit(main())

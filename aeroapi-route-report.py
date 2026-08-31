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


def route_of(body: dict) -> str | None:
    """Route from the first flight carrying both ends (mirrors the app)."""
    for fl in body.get("flights") or []:
        o = (fl.get("origin") or {}).get("code_iata") or (fl.get("origin") or {}).get(
            "code"
        )
        d = (fl.get("destination") or {}).get("code_iata") or (
            fl.get("destination") or {}
        ).get("code")
        if o and d:
            return f"{o}->{d} (ident={fl.get('ident')} reg={fl.get('registration')} status={fl.get('status')})"
    return None


def main() -> int:
    key_file = os.environ.get("KEY_FILE", "/tmp/aero.key")
    with open(key_file) as fh:
        key = fh.read().strip()
    outdir = OUT
    if "--out" in sys.argv:
        outdir = sys.argv[sys.argv.index("--out") + 1]
    os.makedirs(outdir, exist_ok=True)

    sys.path.insert(0, os.getcwd())
    from scenes.flight.lookups..providers.flightaware.routes import _ident_type
    for ident in IDENTS:
        chosen = _ident_type(ident)
        print(f"\n### {ident}  (app sends ident_type={chosen!r})")
        for label, params in (
            ("app-style", {"ident_type": chosen} if chosen else {}),
            ("plain", {}),
        ):
            time.sleep(1.0)
            status, body = fetch(f"/flights/{urllib.parse.quote(ident)}", params, key)
            name = f"{ident}-{label}".lower()
            record = {"name": name, "ident": ident, "params": params, "status": status}
            try:
                parsed = json.loads(body)
            except ValueError:
                parsed = body[:500]
            record["body"] = parsed
            with open(os.path.join(outdir, f"{name}.json"), "w") as fh:
                json.dump(record, fh, indent=2, sort_keys=True)

            if status != 200:
                detail = parsed if isinstance(parsed, str) else json.dumps(parsed)[:120]
                print(f"  {label:9} HTTP {status}: {detail}")
                continue
            flights = parsed.get("flights") or []
            routes = [
                f"{(f.get('origin') or {}).get('code_iata') or (f.get('origin') or {}).get('code')}"
                f"-{(f.get('destination') or {}).get('code_iata') or (f.get('destination') or {}).get('code')}"
                for f in flights
            ]
            route = route_of(parsed)
            print(
                f"  {label:9} HTTP 200 flights={len(flights)} routes={routes or ['-']}"
            )
            if route:
                print(f"  {label:9} FIRST ROUTE: {route}")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())

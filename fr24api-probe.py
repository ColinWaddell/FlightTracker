#!/usr/bin/env python3
"""One-shot FlightRadar24 API contract probe — verifies the app's assumptions.

MANUAL, ONE-TIME diag tool (~7 billed calls total). Not wired into the app
or test suite. Saved responses become offline fixtures for pytest.

    FR24_API_TOKEN=*** python3 fr24api-probe.py [--tar1090-url URL] [--out tests/fixtures/fr24api]

Test selection: pulls a currently-airborne callsign + position from the
free tar1090 feed (zero FR24 cost) so the paid probes are guaranteed
data-bearing. Usage endpoints bookend the run to measure the actual
credit cost of the probe.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://fr24api.flightradar24.com"
OUT = "tests/fixtures/fr24api"

HEADERS = {
    "Accept": "application/json",
    "Accept-Version": "v1",
    "User-Agent": "fr24api-probe/1.0",  # edge WAF blocks default python-urllib UA
}


def fr24(path: str, params: dict, token: str) -> tuple[int, dict, str]:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={**HEADERS, "Authorization": f"Bearer {token}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return (
                resp.status,
                dict(resp.headers),
                resp.read().decode("utf-8", "replace"),
            )
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode("utf-8", "replace")


def pick_target(
    tar1090_url: str,
) -> tuple[str, str, tuple[float, float, float, float] | None]:
    """Free lookup: a live callsign + alt + bounds box around it."""
    if not tar1090_url:
        return "RYR52X", "unknown", None  # fallback callshape; may 200-empty
    try:
        raw = subprocess.run(
            [
                "curl",
                "-sfL",
                "--max-time",
                "8",
                f"{tar1090_url.rstrip('/')}/data/aircraft.json",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
        planes = [
            p
            for p in __import__("json").loads(raw).get("aircraft", [])
            if (p.get("t") or "").strip()
            and (p.get("flight") or "").strip()
            and (p.get("alt_baro") or 0) not in ("ground", None)
            and 3 <= len((p.get("flight") or "").strip()) <= 8
        ]
        pick = max(
            planes, key=lambda p: (p.get("seen", 99) < 5, p.get("alt_baro") or 0)
        )
        cs = (pick.get("flight") or "").strip()
        alt_ft = pick.get("alt_baro") or 0
        lat, lng = pick.get("lat"), pick.get("lon")
        box = (
            round(lat + 2.0, 3),
            round(lat - 2.0, 3),
            round(lng - 4.0, 3),
            round(lng + 4.0, 3),
        )
        return cs, alt_ft, box
    except Exception as e:
        print(f"tar1090 pick failed ({e}); using fallback callsign", file=sys.stderr)
        return "RYR52X", "unknown", None


def main() -> int:
    token = os.environ.get("FR24_API_TOKEN", "").strip()
    if not token:
        print("FR24_API_TOKEN not set", file=sys.stderr)
        return 1
    args = sys.argv
    outdir = args[args.index("--out") + 1] if "--out" in args else OUT
    tar1090 = args[args.index("--tar1090-url") + 1] if "--tar1090-url" in args else ""

    def usage(tag: str):
        status, headers, body = fr24("/api/usage", {"period": "24h"}, token)
        save(tag, status, headers, body, {})
        if status != 200:
            print(f"usage {tag}: HTTP {status} (skipping credit accounting)")
            return None
        return {d["endpoint"]: d["credits"] for d in json.loads(body).get("data", [])}

    def save(name: str, status: int, headers: dict, body: str, params: dict):
        os.makedirs(outdir, exist_ok=True)
        record = {
            "name": name,
            "url": "/api/live/flight-positions/full"
            if "live" in name or not name.startswith("usage")
            else "/api/usage",
            "params": params,
            "status": status,
            "rate_headers": {
                k: v
                for k, v in headers.items()
                if "rate" in k.lower() or "credit" in k.lower()
            },
            "body": json.loads(body) if body[:1] in "{[" else body[:2000],
        }
        with open(os.path.join(outdir, f"{name}.json"), "w") as fh:
            json.dump(record, fh, indent=2, sort_keys=True)

    before = usage("usage-before")

    live_cs, alt_ft, box = pick_target(tar1090)
    print(f"target callsign: {live_cs!r} alt={alt_ft} box={box}")
    lo = max(-2000, int(alt_ft) - 3000) if isinstance(alt_ft, int) else 0
    hi = int(alt_ft) + 3000 if isinstance(alt_ft, int) else 40000
    bounds = f"{box[0]},{box[1]},{box[2]},{box[3]}" if box else "60.0,50.0,-8.0,0.0"

    TESTS = [
        # 1: baseline — guaranteed-airborne callsign; captures full record shape.
        ("callsign-baseline", {"callsigns": live_cs, "limit": "1"}, 200),
        # 2: no-match semantics (200-empty vs 404) for the not_found mapping.
        ("callsign-no-match", {"callsigns": "ZZZ9ZZ", "limit": "1"}, None),
        # 3: bounds orientation (N,S,W,E) + feet altitude_ranges as the app sends.
        (
            "bounds-altitude",
            {"bounds": bounds, "altitude_ranges": f"{lo}-{hi}", "limit": "100"},
            200,
        ),
        # 4: unknown-param strictness (aeroapi lesson).
        (
            "undocumented-param",
            {"bounds": bounds, "altitude_ranges": f"{lo}-{hi}", "max_results": "5"},
            400,
        ),
        # 5: invalid callsign shape (2 chars) -> 400 per SDK pattern expectation.
        ("callsign-invalid", {"callsigns": "AB", "limit": "1"}, 400),
    ]

    failures = 0
    print(f"\n{'TEST':22} {'STATUS':6} {'EXPECT':6} RESULT")
    for name, params, expect in TESTS:
        time.sleep(0.5)
        status, headers, body = fr24("/api/live/flight-positions/full", params, token)
        save(name, status, headers, body, params)
        ok = status < 500 if expect is None else status == expect
        if not ok:
            failures += 1
        n = (
            len(json.loads(body).get("data", []))
            if body[:1] == "{" and status == 200
            else ""
        )
        err = ""
        if status != 200:
            try:
                err = json.loads(body).get("message", "")[:60]
            except Exception:
                err = body[:60]
        print(
            f"{name:22} {status:<6} {'any' if expect is None else expect:<6} {'PASS' if ok else 'FAIL'} records={n} {err}"
        )

    after = usage("usage-after")
    if before is not None and after is not None:
        print("\ncredit accounting (24h usage endpoint):")
        endpoints = set(before) | set(after)
        for ep in sorted(endpoints):
            d0, d1 = before.get(ep, 0), after.get(ep, 0)
            if d0 != d1:
                print(f"  {ep}: {d0} -> {d1} (+{d1 - d0})")

    total = len(TESTS)
    print(f"\n{total - failures}/{total} assertions confirmed; fixtures in {outdir}/")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

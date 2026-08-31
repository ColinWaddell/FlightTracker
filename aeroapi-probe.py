#!/usr/bin/env python3
"""One-shot AeroAPI contract probe — verifies assertions behind the #101 fix.

MANUAL, ONE-TIME diag tool (~8 billed calls total). Not wired into the app
or test suite. Saved responses become offline fixtures for pytest.

    AEROAPI_KEY=xxxx python3 aeroapi-probe.py [--out tests/fixtures/aeroapi]

Each numbered call tests exactly one assertion against
GET /flights/{ident}. Responses (status + body) are saved under --out so
live API behaviour is captured ONCE and replayed offline afterwards.
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
OUT = "tests/fixtures/aeroapi"

# name, path, query, expected_status (None = assert only <500; data-dependent)
TESTS = [
    # 1: baseline — the request Colin proved works manually (captures fixture)
    ("designator-plain", "/flights/AAY430", {}, 200),
    # 2: differential — exact request the app makes today; expect 400 if
    #    max_results is an undocumented/rejected param
    ("designator-max-results", "/flights/AAY430", {"max_results": "5"}, 400),
    # 3: documented enum + spec's recommendation for callsign disambiguation
    ("designator-explicit", "/flights/AAY430", {"ident_type": "designator"}, 200),
    # 4: what today's retry actually produces for a callsign
    (
        "designator-as-registration",
        "/flights/AAY430",
        {"ident_type": "registration"},
        None,
    ),
    # 5: #101's tail ident, plain — falsifies "plain idents get 400"
    ("registration-plain", "/flights/N40726", {}, None),
    # 6: explicit registration enum end-to-end
    ("registration-explicit", "/flights/N40726", {"ident_type": "registration"}, None),
    # 7: semantics of a well-formed but unknown ident (not_found mapping)
    ("unknown-ident", "/flights/ZZZ9ZZ", {}, 404),
    # 8: exact second call today's code makes for a tail ident
    (
        "registration-max-results",
        "/flights/N40726",
        {"max_results": "5", "ident_type": "registration"},
        400,
    ),
]


def fetch(path: str, params: dict[str, str], key: str) -> tuple[int, dict, str]:
    url = f"{BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url, headers={"x-apikey": key, "Accept": "application/json"}
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


def main() -> int:
    key = os.environ.get("AEROAPI_KEY", "").strip()
    if not key:
        print("AEROAPI_KEY not set", file=sys.stderr)
        return 1
    outdir = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else OUT
    os.makedirs(outdir, exist_ok=True)

    failures = 0
    print(f"{'TEST':30} {'STATUS':6} {'EXPECT':6} RESULT")
    for name, path, params, expect in TESTS:
        time.sleep(1.0)  # stay well away from any per-second rate limit
        status, headers, body = fetch(path, params, key)
        record = {
            "name": name,
            "url": path,
            "params": params,
            "status": status,
            "rate_limit_headers": {
                k: v
                for k, v in headers.items()
                if "rate" in k.lower() or "quota" in k.lower()
            },
            "body": json.loads(body) if body[:1] in "{[" else body[:2000],
        }
        with open(os.path.join(outdir, f"{name}.json"), "w") as fh:
            json.dump(record, fh, indent=2, sort_keys=True)

        if expect is None:
            ok = status < 500
            verdict = "PASS" if ok else "FAIL"
        else:
            ok = status == expect
            verdict = "PASS" if ok else "FAIL"
        if not ok:
            failures += 1
        err = (
            record["body"].get("detail", "") if isinstance(record["body"], dict) else ""
        )
        print(
            f"{name:30} {status:<6} {'any' if expect is None else expect:<6} {verdict}  {err[:80]}"
        )

    total = len(TESTS)
    print(f"\n{total - failures}/{total} assertions confirmed; fixtures in {outdir}/")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

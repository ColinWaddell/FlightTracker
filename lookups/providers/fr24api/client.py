"""Shared HTTP plumbing for the official FlightRadar24 API.

Pure REST against https://fr24api.flightradar24.com - no SDK, no extra
dependencies.  Authentication is a Bearer token in the Authorization
header; version selection uses the Accept-Version header.
"""

from __future__ import annotations

import threading
import time

import requests
from requests.exceptions import RequestException

BASE = "https://fr24api.flightradar24.com"

# Request timeout (seconds).
PROVIDER_TIMEOUT = 10

# Status codes the API documents:
#   400 bad request, 401 auth failure, 402 insufficient credits,
#   404 unknown resource, 429 rate limited.
CREDIT_CODES = (402,)


def api_key(settings: dict | None) -> str:
    """The configured Bearer token ('' when absent)."""
    return ((settings or {}).get("api_key") or "").strip()


def headers(token: str) -> dict:
    # NOTE: the FR24 edge WAF answers requests that carry no recognisable
    # User-Agent (e.g. bare urllib/http.client callers) with HTTP 403 and a
    # spurious "planned maintenance" HTML page - it looks like an outage but
    # is not.  requests' default python-requests UA passes (verified live
    # 2026-08-31); if this module ever moves off requests, still send some
    # User-Agent header or the API becomes unreachable.
    return {
        "Accept": "application/json",
        "Accept-Version": "v1",
        "Authorization": f"Bearer {token}",
    }


def get(path: str, token: str, params: dict | None = None):
    """GET an API path; raises RequestException on transport trouble."""
    return requests.get(
        f"{BASE}{path}",
        params=params,
        headers=headers(token),
        timeout=PROVIDER_TIMEOUT,
    )


def api_unavailable(resp) -> str:
    """A human reason for a non-200 answer (credits get a specific hint)."""
    if resp.status_code in CREDIT_CODES:
        return f"FR24 API credit balance exhausted (HTTP {resp.status_code})"
    if resp.status_code in (401, 403):
        return f"FR24 API rejected the token (HTTP {resp.status_code})"
    if resp.status_code == 429:
        return "FR24 API rate limit hit (HTTP 429)"
    return f"FR24 API error (HTTP {resp.status_code})"


def data_of(resp) -> list:
    """The response's data list ([] when absent or mis-shaped)."""
    data = resp.json().get("data")
    return data if isinstance(data, list) else []


def is_transport_error(exc: Exception) -> bool:
    return isinstance(exc, (RequestException, OSError))


# --- shared callsign lookups -------------------------------------------
#
# The route and aircraft capabilities both resolve a callsign via the
# IDENTICAL /api/live/flight-positions/full request, and every call is
# billed (measured 2026-08-31: max(1 credit, ~8 credits per returned
# record), with rapid re-calls tripping a credit-based burst limit).
# A short-TTL dedup cache folds those twin lookups into one call.
# Only 200 answers are cached so error paths always re-issue (and
# re-evaluate) their requests.

_DEDUP_TTL_SECONDS = 30
_CACHE_MAX_ENTRIES = 128
_position_cache: dict[tuple, tuple[float, object]] = {}
_position_cache_lock = threading.Lock()


def callsign_position(token: str, callsign: str):
    """One live-positions/full call for *callsign*, shared per capability.

    Routes and aircraft need the identical request for the same callsign
    within a single pipeline walk; this keeps it at one billed call.
    Errors are never cached - a rejected call re-fires on the next
    capability's request so per-capability handling still applies.
    """
    key = ("live-full-callsign", callsign, hash(token))
    now = time.monotonic()
    with _position_cache_lock:
        hit = _position_cache.get(key)
        if hit and now - hit[0] < _DEDUP_TTL_SECONDS:
            return hit[1]

    resp = get(
        "/api/live/flight-positions/full",
        token,
        {"callsigns": callsign, "limit": 1},
    )
    if resp.status_code == 200:
        with _position_cache_lock:
            if len(_position_cache) >= _CACHE_MAX_ENTRIES:
                _position_cache.clear()
            _position_cache[key] = (now, resp)
    return resp


def clear_position_cache() -> None:
    """Drop the dedup cache (test isolation; also usable on settings change)."""
    with _position_cache_lock:
        _position_cache.clear()

"""Shared request plumbing for AeroDataBox (RapidAPI) endpoints."""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

BASE = "https://aerodatabox.p.rapidapi.com"

# Request timeout (seconds).
PROVIDER_TIMEOUT_S = 10

# x-rapidapi-host required by RapidAPI gateways.
RAPIDAPI_HOST = "aerodatabox.p.rapidapi.com"

# Body keys that signal an error response rather than flight data.
# (Shared by routes.py / aircraft.py - imported from here.)
ERROR_BODY_KEYS = frozenset({"message", "error", "errors"})

# HTTP status codes that indicate rate-limiting or quota exhaustion.
# RapidAPI typically returns 429, but some gateways use 403.  (Check order
# in callers: rate-limit status first, then 404, then other errors.)
RATE_LIMIT_CODES = frozenset({429, 403})


def headers_for(api_key: str) -> dict:
    return {
        "X-RapidAPI-Key": api_key,
        "x-rapidapi-host": RAPIDAPI_HOST,
        "Accept": "application/json",
    }


def aerodatabox_get(path: str, api_key: str, timeout: int = PROVIDER_TIMEOUT_S):
    """GET an AeroDataBox endpoint.

    Returns ``(response, parsed_json_or_None)`` without raising for HTTP
    error statuses - callers classify:

    - connection failures raise ``requests.RequestException``
    - 429/403 = rate-limited (``RATE_LIMIT_CODES``)
    - 404 = unknown callsign/aircraft (body not parsed)
    - 400/422 = rejected parameters (body not parsed) - callers treat as
      "no answer", not a provider failure
    - other non-2xx = error (body not parsed)
    - 2xx with unparseable body raises ``ValueError``
    """
    resp = requests.get(f"{BASE}{path}", headers=headers_for(api_key), timeout=timeout)
    if resp.status_code == 404 or resp.status_code in RATE_LIMIT_CODES:
        return resp, None
    if resp.status_code in (400, 422):
        # Malformed request parameters (e.g. an ident the API cannot
        # parse): surface the raw response so the caller classifies it as
        # "no answer" rather than a provider failure.  (#101 family)
        return resp, None
    # Any other non-2xx: surface as HTTPError for callers that treat all
    # errors alike; 2xx responses fall through to parsing.
    if resp.status_code >= 400:
        resp.raise_for_status()
    return resp, resp.json()


def is_error_response(data) -> bool:
    """True when *data* looks like an API error / rate-limit body.

    AeroDataBox flight responses are either a list of flight objects or
    a single flight object, each containing ``departure``/``arrival``.
    A rate-limit or quota-exceeded response is a dict with a ``message``
    or ``error`` key and no flight structure.  Detecting this lets the
    service layer quarantine the provider instead of silently returning
    blanks or poisoning the miss cache.
    """
    if not isinstance(data, dict):
        return False
    # A genuine flight object has departure/arrival; an error body does not.
    has_flight_structure = bool(data.get("departure") or data.get("arrival"))
    if has_flight_structure:
        return False
    return any(k in data for k in ERROR_BODY_KEYS)

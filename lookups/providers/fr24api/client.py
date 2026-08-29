"""Shared HTTP plumbing for the official FlightRadar24 API.

Pure REST against https://fr24api.flightradar24.com - no SDK, no extra
dependencies.  Authentication is a Bearer token in the Authorization
header; version selection uses the Accept-Version header.
"""

from __future__ import annotations

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

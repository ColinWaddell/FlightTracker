"""
Multi-provider route and aircraft lookup with automatic failover.

Providers are tried in order.  When a provider fails (HTTP error, timeout,
or non-200 response), the next provider is attempted.  Failed providers are
quarantined for ``PROVIDER_RETRY_INTERVAL`` seconds (default 1 hour), after
which they are retried automatically.

Provider list (in priority order):
    1. hexdb.io       - free, no key (legacy default)
    2. adsbdb.com      - free, no key
    3. aerodatabox.com  - requires API key (only active if configured)

Each provider implements the ``RouteProvider`` protocol:

    class RouteProvider:
        name: str
        def is_available() -> bool
        def lookup_route(callsign) -> RouteInfo
        def lookup_aircraft(mode_s) -> tuple[str, str]

``is_available()`` returns False when the provider is quarantined (failed
recently) or lacks required configuration (e.g. aerodatabox without a key).

The startup health check (:func:`check_routing`) pings each provider in turn
and returns True if at least one is reachable.

This module is self-contained: route_lookup.py imports from here, but no
other source file needs modification for the provider chain to work.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

import requests
from requests.exceptions import RequestException

from utilities.flight import RouteInfo
from utilities.overhead_utilities import airport_info as _bundled_airport_info

logger = logging.getLogger(__name__)

# How long to quarantine a failed provider before retrying (seconds).
PROVIDER_RETRY_INTERVAL = 3600  # 1 hour

# Request timeout for provider API calls (seconds).
PROVIDER_TIMEOUT = 10

# Aerodatabox API base (RapidAPI-hosted, but direct URL also works with key).
AERODATABOX_BASE = "https://aerodatabox.p.rapidapi.com"

# ---------------------------------------------------------------------------
# Quarantine tracking
# ---------------------------------------------------------------------------

_lock = threading.Lock()
# provider_name -> monotonic timestamp of last failure (0 = never failed / healthy)
_failed_at: dict[str, float] = {}


def _quarantine(name: str) -> None:
    """Mark *name* as currently unavailable."""
    with _lock:
        _failed_at[name] = time.monotonic()
    logger.debug("Provider %s quarantined for %ds", name, PROVIDER_RETRY_INTERVAL)


def _is_quarantined(name: str) -> bool:
    """Return True if *name* is still in its quarantine window."""
    with _lock:
        ts = _failed_at.get(name)
        if ts is None or ts == 0:
            return False
        if time.monotonic() - ts < PROVIDER_RETRY_INTERVAL:
            return True
        # Quarantine expired - allow retry
        del _failed_at[name]
        return False


def _mark_healthy(name: str) -> None:
    """Mark *name* as healthy (clear quarantine)."""
    with _lock:
        _failed_at.pop(name, None)


def provider_status() -> dict[str, str]:
    """Return ``{name: "ok"|"fail"}`` for all registered providers.

    Used by the startup test to report which providers are available.
    """
    status: dict[str, str] = {}
    for p in _all_providers():
        if not p.is_configured():
            status[p.name] = "skip"
        elif _is_quarantined(p.name):
            status[p.name] = "fail"
        else:
            status[p.name] = "ok" if p.ping() else "fail"
    return status


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


class RouteProvider:
    """Base class for route/aircraft lookup providers."""

    name: str = "base"

    def is_configured(self) -> bool:
        """Return True if all required settings (API keys, etc.) are present."""
        return True

    def is_available(self) -> bool:
        """Return True if configured and not currently quarantined."""
        return self.is_configured() and not _is_quarantined(self.name)

    def ping(self) -> bool:
        """Return True if the service responds.  Does not raise."""
        raise NotImplementedError

    def lookup_route(self, callsign: str) -> RouteInfo:
        """Return route info for *callsign*.  Returns empty RouteInfo on miss/error."""
        raise NotImplementedError

    def lookup_aircraft(self, mode_s: str) -> tuple[str, str]:
        """Return ``(plane, registration)`` for *mode_s*.  Returns ("", "") on miss/error."""
        raise NotImplementedError

    # -- Helpers shared by all providers --------------------------------

    def _get(self, url: str, headers: dict | None = None) -> requests.Response | None:
        """GET *url* with timeout.  Returns Response or None on error.

        On failure, quarantines this provider.
        """
        try:
            resp = _session.get(url, timeout=PROVIDER_TIMEOUT, headers=headers)
            return resp
        except (RequestException, OSError) as e:
            logger.debug("%s: request failed for %s: %s", self.name, url, e)
            _quarantine(self.name)
            return None

    @staticmethod
    def _airport_details(iata: str) -> dict:
        """Return {name, municipality, country_name} for *iata* via bundled airports.json."""
        return _bundled_airport_info(iata) or {}


# Shared session (keeps connection pool alive)
_session = requests.Session()


# ---------------------------------------------------------------------------
# Hexdb.io provider
# ---------------------------------------------------------------------------


class HexdbProvider(RouteProvider):
    """hexdb.io - free, no API key.  The legacy default."""

    name = "hexdb"
    BASE = "https://hexdb.io/api/v1"

    def ping(self) -> bool:
        try:
            resp = _session.get("https://hexdb.io", timeout=5)
            return resp.status_code < 500
        except (RequestException, OSError):
            return False

    # -- Parsers (exposed for testing) ---------------------------------

    @staticmethod
    def _parse_route(route_str: str) -> tuple[str, str]:
        """Parse a hexdb route string into (origin_icao, dest_icao)."""
        parts = [p.strip().upper() for p in route_str.split("-") if p.strip()]
        if len(parts) < 2:
            return "", ""
        return parts[0], parts[-1]

    @staticmethod
    def _parse_aircraft_type(data: dict) -> str:
        """Build a 'Manufacturer Type' string from a hexdb aircraft response."""
        manufacturer = (data.get("Manufacturer") or "").strip()
        type_code = (data.get("ICAOTypeCode") or "").strip()
        if manufacturer and type_code:
            return f"{manufacturer} {type_code}"
        return type_code or manufacturer

    @staticmethod
    def _parse_aircraft_registration(data: dict) -> str:
        return (data.get("Registration") or "").strip()

    # -- Lookup methods ------------------------------------------------

    def lookup_route(self, callsign: str) -> RouteInfo:
        resp = self._get(f"{self.BASE}/route/icao/{callsign}")
        if resp is None:
            return RouteInfo()
        if resp.status_code == 404:
            logger.debug("hexdb: unknown callsign %r", callsign)
            return RouteInfo()
        try:
            resp.raise_for_status()
            data = resp.json()
        except (RequestException, ValueError) as e:
            logger.debug("hexdb route lookup failed for %r: %s", callsign, e)
            _quarantine(self.name)
            return RouteInfo()

        route_str = data.get("route", "")
        origin_icao, dest_icao = self._parse_route(route_str)
        if not origin_icao or not dest_icao:
            logger.debug(
                "hexdb: empty/unparseable route for %r (%r)", callsign, route_str
            )
            return RouteInfo()
        route = RouteInfo()

        # Use bundled ICAO→IATA table for conversion
        origin_iata = _icao_to_iata_code(origin_icao)
        dest_iata = _icao_to_iata_code(dest_icao)

        if origin_iata:
            route.origin = origin_iata
            details = self._airport_details(origin_iata)
            route.origin_name = details.get("name", "")
            route.origin_municipality = details.get("municipality", "")
            route.origin_country = details.get("country_name", "")

        if dest_iata:
            route.destination = dest_iata
            details = self._airport_details(dest_iata)
            route.destination_name = details.get("name", "")
            route.destination_municipality = details.get("municipality", "")
            route.destination_country = details.get("country_name", "")

        if not route.origin and not route.destination:
            logger.debug("hexdb: route ICAO codes unconvertible for %r", callsign)
            return RouteInfo()

        _mark_healthy(self.name)
        return route

    def lookup_aircraft(self, mode_s: str) -> tuple[str, str]:
        resp = self._get(f"{self.BASE}/aircraft/{mode_s.lower()}")
        if resp is None:
            return "", ""
        if resp.status_code == 404:
            logger.debug("hexdb: unknown aircraft %r", mode_s)
            return "", ""
        try:
            resp.raise_for_status()
            data = resp.json()
        except (RequestException, ValueError) as e:
            logger.debug("hexdb aircraft lookup failed for %r: %s", mode_s, e)
            _quarantine(self.name)
            return "", ""

        plane = self._parse_aircraft_type(data)
        registration = self._parse_aircraft_registration(data)

        _mark_healthy(self.name)
        return plane, registration


# ---------------------------------------------------------------------------
# adsbdb.com provider
# ---------------------------------------------------------------------------


class AdsbdbProvider(RouteProvider):
    """adsbdb.com - free, no API key.

    Provides:
        /v0/callsign/{callsign}  -> route with origin/destination (IATA+ICAO,
            name, municipality, country)
        /v0/aircraft/{mode_s}     -> aircraft type, manufacturer, registration
    """

    name = "adsbdb"
    BASE = "https://api.adsbdb.com/v0"

    def ping(self) -> bool:
        try:
            resp = _session.get(f"{self.BASE}/aircraft/random", timeout=5)
            return resp.status_code == 200
        except (RequestException, OSError):
            return False

    def lookup_route(self, callsign: str) -> RouteInfo:
        resp = self._get(f"{self.BASE}/callsign/{callsign}")
        if resp is None:
            return RouteInfo()
        if resp.status_code == 404:
            logger.debug("adsbdb: unknown callsign %r", callsign)
            return RouteInfo()
        try:
            resp.raise_for_status()
            data = resp.json()
        except (RequestException, ValueError) as e:
            logger.debug("adsbdb route lookup failed for %r: %s", callsign, e)
            _quarantine(self.name)
            return RouteInfo()

        fr = data.get("response", {}).get("flightroute", {})
        if not fr:
            # "unknown callsign" response
            logger.debug("adsbdb: no flightroute for %r", callsign)
            return RouteInfo()

        route = RouteInfo()

        origin = fr.get("origin", {})
        dest = fr.get("destination", {})

        if origin:
            # Prefer IATA; fall back to ICAO
            iata = (origin.get("iata_code") or "").strip()
            icao = (origin.get("icao_code") or "").strip()
            route.origin = iata or icao
            # Name/municipality/country come from the bundled airports.json
            # (single source of truth) rather than the provider API.
            if route.origin:
                details = self._airport_details(route.origin)
                route.origin_name = details.get("name", "")
                route.origin_municipality = details.get("municipality", "")
                route.origin_country = details.get("country_name", "")

        if dest:
            iata = (dest.get("iata_code") or "").strip()
            icao = (dest.get("icao_code") or "").strip()
            route.destination = iata or icao
            if route.destination:
                details = self._airport_details(route.destination)
                route.destination_name = details.get("name", "")
                route.destination_municipality = details.get("municipality", "")
                route.destination_country = details.get("country_name", "")

        # Airline ICAO from the airline block
        airline = fr.get("airline", {})
        route.airline_icao = (airline.get("icao") or "").strip()

        if route.origin or route.destination:
            _mark_healthy(self.name)
        return route

    def lookup_aircraft(self, mode_s: str) -> tuple[str, str]:
        resp = self._get(f"{self.BASE}/aircraft/{mode_s.lower()}")
        if resp is None:
            return "", ""
        if resp.status_code == 404:
            logger.debug("adsbdb: unknown aircraft %r", mode_s)
            return "", ""
        try:
            resp.raise_for_status()
            data = resp.json()
        except (RequestException, ValueError) as e:
            logger.debug("adsbdb aircraft lookup failed for %r: %s", mode_s, e)
            _quarantine(self.name)
            return "", ""

        ac = data.get("response", {}).get("aircraft", {})
        if not ac:
            return "", ""

        manufacturer = (ac.get("manufacturer") or "").strip()
        type_full = (ac.get("type") or "").strip()
        icao_type = (ac.get("icao_type") or "").strip()
        registration = (ac.get("registration") or "").strip()

        # Build a "Manufacturer TypeCode" string to match hexdb format.
        # Prefer icao_type for the type code (e.g. "A320"), use type_full as
        # the full model name (e.g. "A320 214").
        if manufacturer and icao_type:
            plane = f"{manufacturer} {icao_type}"
        elif type_full:
            plane = type_full
        else:
            plane = icao_type or manufacturer

        _mark_healthy(self.name)
        return plane, registration


# ---------------------------------------------------------------------------
# AeroDataBox provider (requires RapidAPI key)
# ---------------------------------------------------------------------------


class AeroDataBoxProvider(RouteProvider):
    """aerodatabox.com - requires a RapidAPI key.

    The key is passed as the ``X-RapidAPI-Key`` header.

    Provides:
        /flights/{callsign}           -> flight status with route info
        /aircraft/{mode_s_or_reg}     -> aircraft details
    """

    name = "aerodatabox"
    BASE = AERODATABOX_BASE

    def __init__(self, api_key: str = ""):
        self._api_key = api_key

    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _headers(self) -> dict:
        return {
            "X-RapidAPI-Key": self._api_key,
            "Accept": "application/json",
        }

    def ping(self) -> bool:
        if not self._api_key:
            return False
        try:
            resp = _session.get(
                f"{self.BASE}/subscriptions/balance",
                headers={
                    **self._headers(),
                    "x-rapidapi-host": "aerodatabox.p.rapidapi.com",
                },
                timeout=5,
            )
            return resp.status_code == 200
        except (RequestException, OSError):
            return False

    # -- Rate-limit / error detection ---------------------------------

    # HTTP status codes that indicate rate-limiting or quota exhaustion.
    # RapidAPI typically returns 429, but some gateways use 403.
    _RATE_LIMIT_CODES = frozenset({429, 403})

    # Body keys that signal an error response rather than flight data.
    # RapidAPI rate-limit bodies look like {"message": "You exceeded..."}
    # or {"error": "Quota exceeded"}.  A genuine flight object has none of
    # these top-level keys.
    _ERROR_BODY_KEYS = frozenset({"message", "error", "errors"})

    @classmethod
    def _is_error_response(cls, data) -> bool:
        """Return True if *data* looks like an API error / rate-limit body.

        AeroDataBox flight responses are either a list of flight objects or
        a single flight object, each containing ``departure``/``arrival``.
        A rate-limit or quota-exceeded response is a dict with a ``message``
        or ``error`` key and no flight structure.  Detecting this lets us
        quarantine the provider instead of silently returning blanks.
        """
        if not isinstance(data, dict):
            return False
        # A genuine flight object has departure/arrival; an error body does not.
        has_flight_structure = bool(data.get("departure") or data.get("arrival"))
        if has_flight_structure:
            return False
        return any(k in data for k in cls._ERROR_BODY_KEYS)

    def lookup_route(self, callsign: str) -> RouteInfo:
        if not self._api_key:
            return RouteInfo()
        resp = self._get(
            f"{self.BASE}/flights/callsign/{callsign}",
            headers=self._headers(),
        )
        if resp is None:
            return RouteInfo()
        if resp.status_code == 404:
            logger.debug("aerodatabox: unknown callsign %r", callsign)
            return RouteInfo()
        # Explicit rate-limit / quota handling.  RapidAPI returns 429 (or
        # sometimes 403) when the quota is exhausted; quarantine immediately
        # so we stop hitting the API for PROVIDER_RETRY_INTERVAL.
        if resp.status_code in self._RATE_LIMIT_CODES:
            logger.warning(
                "aerodatabox: rate limit / quota exceeded (HTTP %d) for %r - "
                "quarantining for %ds",
                resp.status_code,
                callsign,
                PROVIDER_RETRY_INTERVAL,
            )
            _quarantine(self.name)
            return RouteInfo()
        try:
            resp.raise_for_status()
            data = resp.json()
        except (RequestException, ValueError) as e:
            logger.debug("aerodatabox route lookup failed for %r: %s", callsign, e)
            _quarantine(self.name)
            return RouteInfo()

        # Some gateways return HTTP 200 with an error body when rate-limited
        # (e.g. {"message": "You exceeded your monthly quota"}).  Detect this
        # and quarantine rather than treating it as a genuine miss.
        if self._is_error_response(data):
            msg = ""
            for k in self._ERROR_BODY_KEYS:
                if k in data:
                    msg = str(data[k])[:200]
                    break
            logger.warning(
                "aerodatabox: error response for %r (%s) - quarantining for %ds",
                callsign,
                msg,
                PROVIDER_RETRY_INTERVAL,
            )
            _quarantine(self.name)
            return RouteInfo()

        # AeroDataBox returns a list of flight objects for the callsign
        flights = data if isinstance(data, list) else [data]
        if not flights:
            return RouteInfo()

        flight = flights[0]
        route = RouteInfo()

        # Departure / arrival are in the flight object
        dep = flight.get("departure", {}) or {}
        arr = flight.get("arrival", {}) or {}

        if dep:
            airport = dep.get("airport", {}) or {}
            iata = (airport.get("iata") or "").strip()
            icao = (airport.get("icao") or "").strip()
            route.origin = iata or icao
            # Name/municipality/country come from the bundled airports.json
            # (single source of truth) rather than the provider API.
            if route.origin:
                details = self._airport_details(route.origin)
                route.origin_name = details.get("name", "")
                route.origin_municipality = details.get("municipality", "")
                route.origin_country = details.get("country_name", "")

        if arr:
            airport = arr.get("airport", {}) or {}
            iata = (airport.get("iata") or "").strip()
            icao = (airport.get("icao") or "").strip()
            route.destination = iata or icao
            if route.destination:
                details = self._airport_details(route.destination)
                route.destination_name = details.get("name", "")
                route.destination_municipality = details.get("municipality", "")
                route.destination_country = details.get("country_name", "")

        # Airline
        airline = flight.get("airline", {}) or {}
        route.airline_icao = (airline.get("icao") or "").strip()

        if route.origin or route.destination:
            _mark_healthy(self.name)
        return route

    def lookup_aircraft(self, mode_s: str) -> tuple[str, str]:
        if not self._api_key:
            return "", ""
        resp = self._get(
            f"{self.BASE}/aircrafts/icao24/{mode_s.lower()}",
            headers=self._headers(),
        )
        if resp is None:
            return "", ""
        if resp.status_code == 404:
            logger.debug("aerodatabox: unknown aircraft %r", mode_s)
            return "", ""
        # Explicit rate-limit / quota handling (see lookup_route for rationale).
        if resp.status_code in self._RATE_LIMIT_CODES:
            logger.warning(
                "aerodatabox: rate limit / quota exceeded (HTTP %d) for %r - "
                "quarantining for %ds",
                resp.status_code,
                mode_s,
                PROVIDER_RETRY_INTERVAL,
            )
            _quarantine(self.name)
            return "", ""
        try:
            resp.raise_for_status()
            data = resp.json()
        except (RequestException, ValueError) as e:
            logger.debug("aerodatabox aircraft lookup failed for %r: %s", mode_s, e)
            _quarantine(self.name)
            return "", ""

        # Detect 200-with-error-body rate-limit responses (see lookup_route).
        if self._is_error_response(data):
            msg = ""
            for k in self._ERROR_BODY_KEYS:
                if k in data:
                    msg = str(data[k])[:200]
                    break
            logger.warning(
                "aerodatabox: error response for %r (%s) - quarantining for %ds",
                mode_s,
                msg,
                PROVIDER_RETRY_INTERVAL,
            )
            _quarantine(self.name)
            return "", ""

        # Response may be a list or single object
        ac_list = data if isinstance(data, list) else [data]
        if not ac_list:
            return "", ""

        ac = ac_list[0]
        plane = (ac.get("typeName") or ac.get("productionLine") or "").strip()
        registration = (ac.get("reg") or "").strip()

        _mark_healthy(self.name)
        return plane, registration


# ---------------------------------------------------------------------------
# Bundled ICAO→IATA lookup (moved from route_lookup.py, shared by providers)
# ---------------------------------------------------------------------------

_icao_to_iata: dict[str, str] = {}
_icao_to_iata_loaded = False


def _load_icao_to_iata() -> None:
    """Load the ICAO-to-IATA mapping from assets/airports_icao_to_iata.json."""
    global _icao_to_iata, _icao_to_iata_loaded
    if _icao_to_iata_loaded:
        return
    _icao_to_iata_loaded = True
    path = Path(__file__).parent.parent / "assets" / "airports_icao_to_iata.json"
    if path.exists():
        try:
            with open(path) as fh:
                _icao_to_iata = json.load(fh)
        except Exception:
            _icao_to_iata = {}


def _icao_to_iata_code(icao: str) -> str:
    """Convert an ICAO airport code to IATA using the bundled table.

    Returns "" if unknown (the hexdb airport endpoint fallback was removed;
    the bundled table is the sole source now).
    """
    icao = (icao or "").strip().upper()
    if not icao:
        return ""
    _load_icao_to_iata()
    return _icao_to_iata.get(icao, "")


# ---------------------------------------------------------------------------
# Provider registry / chain
# ---------------------------------------------------------------------------

# Module-level singleton providers.  The aerodatabox key is read from the
# Config on first access (see :func:`_all_providers`).
_hexdb: HexdbProvider | None = None
_adsbdb: AdsbdbProvider | None = None
_aerodatabox: AeroDataBoxProvider | None = None
_aerodatabox_key: str = ""


def set_aerodatabox_key(key: str) -> None:
    """Set the Aerodatabox API key (called once at startup from Config)."""
    global _aerodatabox_key, _aerodatabox
    _aerodatabox_key = (key or "").strip()
    _aerodatabox = AeroDataBoxProvider(_aerodatabox_key) if _aerodatabox_key else None


def _all_providers() -> list[RouteProvider]:
    """Return all registered providers in priority order."""
    global _hexdb, _adsbdb
    if _hexdb is None:
        _hexdb = HexdbProvider()
    if _adsbdb is None:
        _adsbdb = AdsbdbProvider()
    providers = [_hexdb, _adsbdb]
    if _aerodatabox is not None:
        providers.insert(0, _aerodatabox)
    return providers


def available_providers() -> list[RouteProvider]:
    """Return providers that are configured and not currently quarantined."""
    return [p for p in _all_providers() if p.is_available()]


# ---------------------------------------------------------------------------
# Public lookup functions (used by route_lookup.py)
# ---------------------------------------------------------------------------


def lookup_route(callsign: str) -> RouteInfo:
    """Try each available provider in turn until one returns route data.

    Returns an empty RouteInfo if all providers fail or return nothing.
    """
    for provider in available_providers():
        ri = provider.lookup_route(callsign)
        if ri.origin or ri.destination:
            logger.debug("Route for %r found via %s", callsign, provider.name)
            return ri
    return RouteInfo()


def lookup_aircraft(mode_s: str) -> tuple[str, str]:
    """Try each available provider in turn until one returns aircraft data.

    Returns ("", "") if all providers fail or return nothing.
    """
    for provider in available_providers():
        plane, reg = provider.lookup_aircraft(mode_s)
        if plane or reg:
            logger.debug("Aircraft for %r found via %s", mode_s, provider.name)
            return plane, reg
    return "", ""


def check_routing() -> bool:
    """Return True if at least one provider is reachable.

    Used by the startup test to show Routing OK/FAIL.
    """
    for provider in _all_providers():
        if not provider.is_configured():
            continue
        if _is_quarantined(provider.name):
            continue
        if provider.ping():
            _mark_healthy(provider.name)
            return True
        else:
            _quarantine(provider.name)
    return False

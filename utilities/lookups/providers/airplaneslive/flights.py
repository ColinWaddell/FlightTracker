"""airplanes.live live flight observations (community readsb aggregator)."""

from __future__ import annotations

from utilities.lookups.providers.common.aggregator import AggregatorFlightProvider


class FlightProvider(AggregatorFlightProvider):
    """Live aircraft from the airplanes.live community network.

    Same ADSBExchange-style v2 dialect as ADSB.lol.  The service asks for
    at most one request per second - the tracker's poll interval keeps us
    comfortably inside that.
    """

    endpoint = "https://api.airplanes.live/v2/point/{lat}/{lon}/{radius}"
    name = "airplanes.live"


def startup_check(settings: dict | None = None) -> bool:
    """Reachability probe for the startup screen (status-agnostic)."""
    import requests

    try:
        requests.get("https://airplanes.live", timeout=5)
        return True
    except Exception:
        return False

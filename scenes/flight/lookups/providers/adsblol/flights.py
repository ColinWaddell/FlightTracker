"""ADSB.lol live flight observations (community readsb aggregator)."""

from __future__ import annotations

from scenes.flight.lookups.providers.common.aggregator import AggregatorFlightProvider


class FlightProvider(AggregatorFlightProvider):
    """Live aircraft from the ADSB.lol community network.

    Same readsb dialect as adsb.fi; the envelope key is ``ac``.
    """

    endpoint = "https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/{radius}"


def startup_check(settings: dict | None = None) -> bool:
    """Reachability probe for the startup screen (status-agnostic)."""
    import requests

    try:
        requests.get("https://api.adsb.lol", timeout=5)
        return True
    except Exception:
        return False

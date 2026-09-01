"""ADS-B.fi live flight observations (community readsb aggregator)."""

from __future__ import annotations

from scenes.flight.lookups.providers.common.aggregator import AggregatorFlightProvider


class FlightProvider(AggregatorFlightProvider):
    """Live aircraft from the adsb.fi community network.

    The endpoint takes a point + radius in nautical miles and answers in
    the same aircraft.json dialect a local tar1090 would.
    """

    endpoint = "https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/{radius}"
    name = "adsb.fi"


def startup_check(settings: dict | None = None) -> bool:
    """Reachability probe for the startup screen (status-agnostic)."""
    import requests

    try:
        requests.get("https://opendata.adsb.fi", timeout=5)
        return True
    except Exception:
        return False

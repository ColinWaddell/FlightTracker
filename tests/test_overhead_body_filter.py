"""Tests for Overhead._apply_body_filter - the display-layer body filter.

The fetch-layer half lives in the providers via
``FlightQuery.allowed_body_types`` (see tests in test_providers_extra.py);
this facade layer governs what is displayed once every flight carries its
final ``icao_type`` - including the Unknown checkbox for unclassified
designators.  See tests/test_providers_extra.py's enrichment-isolation test
for the grab_data_impl wiring.
"""

from types import SimpleNamespace

import pytest

from utilities.flight import Flight
from utilities.overhead import Overhead


def _cfg(body_types="wnrtbghmu"):
    """Config stand-in exposing just what the display filter reads."""
    return SimpleNamespace(flight_body_types=body_types)


def _flight(callsign="", icao_type=""):
    return Flight(callsign=callsign, icao_type=icao_type)


class TestFilterOff:
    def test_default_keeps_everything_including_unknown(self):
        overhead = Overhead()
        flights = [
            _flight(callsign="BAW123", icao_type="A320"),
            _flight(callsign="VJT741", icao_type="GLX"),
            _flight(callsign=""),  # no type code -> Unknown bucket
        ]
        assert overhead._apply_body_filter(flights, _cfg()) == flights

    def test_empty_list_stays_empty(self):
        assert Overhead()._apply_body_filter([], _cfg()) == []


class TestKnownTypes:
    def test_disallowed_class_dropped(self):
        overhead = Overhead()
        turboprop = _flight(callsign="LOG8TR", icao_type="AT76")
        widebody = _flight(callsign="BAW117", icao_type="B77W")

        out = overhead._apply_body_filter([turboprop, widebody], _cfg("t"))

        assert out == [turboprop]

    def test_allowed_class_kept(self):
        overhead = Overhead()
        turboprop = _flight(callsign="LOG8TR", icao_type="AT76")

        assert overhead._apply_body_filter([turboprop], _cfg("tu")) == [turboprop]


class TestUnknownBucket:
    def test_unknown_kept_when_unknown_allowed(self):
        overhead = Overhead()
        ghost = _flight(callsign="")  # unclassified
        assert overhead._apply_body_filter([ghost], _cfg("u")) == [ghost]

    def test_unknown_dropped_when_unknown_not_allowed(self):
        overhead = Overhead()
        ghost = _flight(callsign="")

        assert overhead._apply_body_filter([ghost], _cfg("wnrtbghm")) == []

    def test_classified_flight_not_governed_by_unknown_box(self):
        overhead = Overhead()
        widebody = _flight(callsign="BAW117", icao_type="B77W")

        assert overhead._apply_body_filter([widebody], _cfg("u")) == []


class TestGrabDataWiring:
    """grab_data_impl: fetch-level pre-cap + the display filter together."""

    @pytest.fixture
    def _wired(self, monkeypatch):
        from unittest.mock import MagicMock

        config = SimpleNamespace(
            zone_home={"tl_y": 56.0, "tl_x": -5.0, "br_y": 55.0, "br_x": -3.0},
            location_home=[55.5, -4.0, 100],
            flight_min_altitude=100.0,
            flight_max_altitude=15000.0,
            max_flight_lookup=5,
            max_flight_track_minutes=0,
            flight_body_types="t",
            callsign_format="icao",
        )
        import setup.configuration as configuration

        monkeypatch.setattr(
            configuration.Config,
            "instance",
            classmethod(lambda cls: config),
            raising=True,
        )

        from utilities.lookups.flights import FlightFetchOutcome
        from utilities.lookups.results import FlightObservation

        wanted = FlightObservation(
            icao="400f5a", callsign="LOG8TR", icao_type="AT76", altitude_ft=10000
        )
        unwanted = FlightObservation(
            icao="400999", callsign="BAW117", icao_type="B77W", altitude_ft=10000
        )
        outcome = FlightFetchOutcome(
            ok=True,
            observations=[wanted, unwanted],
            provider_id="tar1090",
            source_name="tar1090",
        )
        captured = {"query": None, "observed": []}

        def fake_fetch(query):
            captured["query"] = query
            return outcome

        monkeypatch.setattr("utilities.lookups.flights.fetch_flights", fake_fetch)

        from utilities.lookups.results import RouteInfo

        enrich = MagicMock(return_value=RouteInfo())
        enrich.side_effect = lambda observation: (
            captured["observed"].append(observation),
            RouteInfo(),
        )[1]
        monkeypatch.setattr("utilities.lookups.enrichment.enrich", enrich)
        return config, captured

    def test_display_filter_backstops_the_fetch_layer(self, _wired):
        _config, captured = _wired
        overhead = Overhead()
        overhead.grab_data_impl()

        # This harness stubs fetch_flights, bypassing the provider's pre-cap
        # body filter - in production a disallowed type is culled there and
        # never enriches (asserted per-provider in test_providers_extra.py).
        # What this layer must still guarantee: anything that slips through
        # a type-blind provider or a late fill is held back from the display.
        assert len(captured["observed"]) == 2  # enrichment ran for both...
        assert [f.icao_callsign for f in overhead.data_store] == [
            "LOG8TR"
        ]  # ...but only the allowed one is displayed

    def test_query_carried_allowed_body_types(self, _wired):
        _config, captured = _wired
        Overhead().grab_data_impl()
        assert captured["query"].allowed_body_types == frozenset("t")

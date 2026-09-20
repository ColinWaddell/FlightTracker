"""Tests for the max-flight-track timeout (Overhead._apply_track_timeout).

The timeout keeps aircraft circling overhead from dominating the display:
the clock starts at first sighting, and an aircraft absent from a
successful fetch is forgotten so a later return counts as a new flight.
"""

from types import SimpleNamespace

import pytest

from utilities.flight import Flight
from utilities.overhead import Overhead


def _cfg(minutes):
    """Config stand-in exposing just what the timeout filter reads."""
    return SimpleNamespace(max_flight_track_minutes=minutes)


def _flight(icao="", callsign=""):
    return Flight(callsign=callsign, icao_callsign=icao)


@pytest.fixture
def frozen_clock(monkeypatch):
    """Let tests pin utilities.overhead's time.time() to a fixed instant.

    Rebinds the module-level ``time`` name (not the stdlib module) so other
    modules are unaffected.
    """
    state = {"now": 1_000_000.0}
    monkeypatch.setattr(
        "utilities.overhead.time", SimpleNamespace(time=lambda: state["now"])
    )
    return state


class TestDisabled:
    def test_zero_minutes_returns_flights_unchanged(self):
        overhead = Overhead()
        flights = [_flight(callsign="BAW123"), _flight(callsign="UAL456")]
        out = overhead._apply_track_timeout(flights, _cfg(0))
        assert out == flights
        assert overhead._track_first_seen == {}

    def test_zero_minutes_clears_existing_tracking_state(self):
        overhead = Overhead()
        overhead._apply_track_timeout([_flight(callsign="BAW123")], _cfg(30))
        assert overhead._track_first_seen

        out = overhead._apply_track_timeout([_flight(callsign="BAW123")], _cfg(0))
        assert len(out) == 1
        assert overhead._track_first_seen == {}


class TestFirstSighting:
    def test_first_sighting_is_kept_and_recorded(self):
        overhead = Overhead()
        flight = _flight(callsign="BAW123")

        out = overhead._apply_track_timeout([flight], _cfg(30))

        assert out == [flight]
        assert "BAW123" in overhead._track_first_seen

    def test_young_sighting_still_kept(self):
        overhead = Overhead()
        flight = _flight(callsign="BAW123")
        overhead._apply_track_timeout([flight], _cfg(30))

        # Age the sighting to just under the timeout
        overhead._track_first_seen["BAW123"] -= 29 * 60
        out = overhead._apply_track_timeout([flight], _cfg(30))

        assert out == [flight]

    def test_boundary_exactly_at_limit_is_kept(self, frozen_clock):
        overhead = Overhead()
        flight = _flight(callsign="BAW123")
        overhead._apply_track_timeout([flight], _cfg(30))

        # Freeze time at exactly the timeout boundary (30 min after first
        # sighting) - the <= comparison must keep the flight.
        first_seen = overhead._track_first_seen["BAW123"]
        frozen_clock["now"] = first_seen + 30 * 60
        out = overhead._apply_track_timeout([flight], _cfg(30))

        assert out == [flight]


class TestTimeout:
    def test_stale_sighting_is_dropped(self):
        overhead = Overhead()
        flight = _flight(callsign="BAW123")
        overhead._apply_track_timeout([flight], _cfg(30))

        overhead._track_first_seen["BAW123"] -= 31 * 60
        out = overhead._apply_track_timeout([flight], _cfg(30))

        assert out == []

    def test_mixed_fresh_and_stale(self):
        overhead = Overhead()
        fresh = _flight(callsign="BAW123")
        stale = _flight(icao="400910", callsign="UAL456")
        overhead._apply_track_timeout([fresh, stale], _cfg(30))

        overhead._track_first_seen["400910"] -= 120 * 60
        out = overhead._apply_track_timeout([fresh, stale], _cfg(30))

        assert out == [fresh]

    def test_dropped_aircraft_keeps_no_tracker_entry_removal_side_effect(self):
        # Being dropped must not prevent the entry from being pruned on a
        # later fetch where the aircraft is absent - the drop and the prune
        # are independent.
        overhead = Overhead()
        overhead._apply_track_timeout([_flight(callsign="BAW123")], _cfg(30))
        overhead._track_first_seen["BAW123"] -= 31 * 60
        assert overhead._apply_track_timeout([], _cfg(30)) == []
        assert overhead._track_first_seen == {}


class TestAbsenceResets:
    def test_absent_aircraft_is_forgotten(self):
        overhead = Overhead()
        overhead._apply_track_timeout([_flight(callsign="BAW123")], _cfg(30))
        assert "BAW123" in overhead._track_first_seen

        overhead._apply_track_timeout([_flight(callsign="UAL456")], _cfg(30))

        assert "BAW123" not in overhead._track_first_seen
        assert "UAL456" in overhead._track_first_seen

    def test_return_visit_gets_a_fresh_clock(self):
        overhead = Overhead()
        flight = _flight(callsign="BAW123")

        # Tracked until it times out...
        overhead._apply_track_timeout([flight], _cfg(30))
        overhead._track_first_seen["BAW123"] -= 31 * 60
        assert overhead._apply_track_timeout([flight], _cfg(30)) == []

        # ...leaves the monitored range...
        assert overhead._apply_track_timeout([], _cfg(30)) == []
        assert overhead._track_first_seen == {}

        # ...and returns as a new sighting.
        out = overhead._apply_track_timeout([flight], _cfg(30))
        assert out == [flight]

    def test_empty_fetch_clears_all_tracking_state(self):
        overhead = Overhead()
        overhead._apply_track_timeout([_flight(callsign="A"), _flight(callsign="B")], _cfg(30))

        overhead._apply_track_timeout([], _cfg(30))

        assert overhead._track_first_seen == {}


class TestIdentity:
    def test_icao_callsign_preferred_over_display_callsign(self):
        overhead = Overhead()
        overhead._apply_track_timeout([_flight(icao="400910", callsign="UAL456")], _cfg(30))

        assert "400910" in overhead._track_first_seen

    def test_unidentifiable_flight_is_always_kept(self):
        overhead = Overhead()
        anonymous = _flight()  # no ICAO, no callsign

        out = overhead._apply_track_timeout([anonymous], _cfg(30))

        assert out == [anonymous]
        assert overhead._track_first_seen == {}

    def test_unidentifiable_flight_kept_after_ageing(self):
        overhead = Overhead()
        anonymous = _flight()
        overhead._apply_track_timeout([anonymous], _cfg(30))

        out = overhead._apply_track_timeout([anonymous], _cfg(30))

        assert out == [anonymous]


class TestConfigProperty:
    def test_default_is_zero(self):
        from setup.configuration import Config

        assert Config().max_flight_track_minutes == 0

    def test_clamped_to_0_1440(self):
        from setup.configuration import Config

        cfg = Config()
        cfg.data_store["max_flight_track_minutes"] = 5000
        assert cfg.max_flight_track_minutes == 1440

        cfg.data_store["max_flight_track_minutes"] = -10
        assert cfg.max_flight_track_minutes == 0

        cfg.data_store["max_flight_track_minutes"] = "45"
        assert cfg.max_flight_track_minutes == 45

        cfg.data_store["max_flight_track_minutes"] = "nonsense"
        assert cfg.max_flight_track_minutes == 0
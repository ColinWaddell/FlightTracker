"""Tests for scenes/flight/flight_scene.py - pure helper functions."""

from scenes.flight.flight_scene import (
    EASING_STEPS,
    abbreviate,
    callsigns_match,
    telemetry_changed,
    tick_to_offset,
)
from utilities.flight import Flight

# ---------------------------------------------------------------------------
# callsigns_match
# ---------------------------------------------------------------------------


class TestCallsignsMatch:
    def test_identical_lists(self):
        a = [Flight(callsign="BAW123"), Flight(callsign="UAL456")]
        b = [Flight(callsign="BAW123"), Flight(callsign="UAL456")]
        assert callsigns_match(a, b) is True

    def test_different_order(self):
        a = [Flight(callsign="BAW123"), Flight(callsign="UAL456")]
        b = [Flight(callsign="UAL456"), Flight(callsign="BAW123")]
        assert callsigns_match(a, b) is True

    def test_different_sets(self):
        a = [Flight(callsign="BAW123"), Flight(callsign="UAL456")]
        b = [Flight(callsign="BAW123"), Flight(callsign="DAL789")]
        assert callsigns_match(a, b) is False

    def test_both_empty(self):
        assert callsigns_match([], []) is True

    def test_one_empty(self):
        assert callsigns_match([Flight(callsign="BAW123")], []) is False

    def test_duplicate_callsigns(self):
        a = [Flight(callsign="BAW123"), Flight(callsign="BAW123")]
        b = [Flight(callsign="BAW123")]
        # Sets are equal despite different list lengths
        assert callsigns_match(a, b) is True


# ---------------------------------------------------------------------------
# telemetry_changed
# ---------------------------------------------------------------------------


class TestTelemetryChanged:
    def test_no_change(self):
        old = [
            Flight(
                callsign="BAW123",
                altitude=35000,
                ground_speed=450,
                heading=90,
            )
        ]
        new = [
            Flight(
                callsign="BAW123",
                altitude=35000,
                ground_speed=450,
                heading=90,
            )
        ]
        assert telemetry_changed(old, new) is False

    def test_altitude_changed(self):
        old = [
            Flight(
                callsign="BAW123",
                altitude=35000,
                ground_speed=450,
                heading=90,
            )
        ]
        new = [
            Flight(
                callsign="BAW123",
                altitude=34000,
                ground_speed=450,
                heading=90,
            )
        ]
        assert telemetry_changed(old, new) is True

    def test_ground_speed_changed(self):
        old = [
            Flight(
                callsign="BAW123",
                altitude=35000,
                ground_speed=450,
                heading=90,
            )
        ]
        new = [
            Flight(
                callsign="BAW123",
                altitude=35000,
                ground_speed=460,
                heading=90,
            )
        ]
        assert telemetry_changed(old, new) is True

    def test_heading_changed(self):
        old = [
            Flight(
                callsign="BAW123",
                altitude=35000,
                ground_speed=450,
                heading=90,
            )
        ]
        new = [
            Flight(
                callsign="BAW123",
                altitude=35000,
                ground_speed=450,
                heading=120,
            )
        ]
        assert telemetry_changed(old, new) is True

    def test_new_flight_not_in_old(self):
        old = [Flight(callsign="BAW123", altitude=35000)]
        new = [Flight(callsign="UAL456", altitude=30000)]
        # New flight not in lookup - no comparison possible, so no change detected
        assert telemetry_changed(old, new) is False

    def test_empty_lists(self):
        assert telemetry_changed([], []) is False


# ---------------------------------------------------------------------------
# abbreviate
# ---------------------------------------------------------------------------


class TestAbbreviate:
    def test_international(self):
        assert "Intl" in abbreviate("Glasgow International Airport")

    def test_airport_removed(self):
        result = abbreviate("Heathrow Airport")
        assert "Airport" not in result

    def test_regional(self):
        result = abbreviate("Edinburgh Regional Airport")
        assert "Reg" in result
        assert "Regional" not in result

    def test_municipal(self):
        result = abbreviate("Bristol Municipal Airport")
        assert "Muni" in result
        assert "Municipal" not in result

    def test_multiple_replacements(self):
        result = abbreviate("London International Regional Municipal Airport")
        assert "Intl" in result
        assert "Reg" in result
        assert "Muni" in result
        assert "Airport" not in result
        assert "International" not in result
        assert "Regional" not in result
        assert "Municipal" not in result

    def test_no_replacements_needed(self):
        result = abbreviate("Glasgow")
        assert result == "Glasgow"

    def test_collapses_whitespace(self):
        result = abbreviate("Glasgow  International   Airport")
        # Extra spaces should be collapsed
        assert "  " not in result


# ---------------------------------------------------------------------------
# tick_to_offset
# ---------------------------------------------------------------------------


class TestTickToOffset:
    def test_all_easing_steps(self):
        for i, expected in enumerate(EASING_STEPS):
            assert tick_to_offset(i) == expected

    def test_beyond_easing_steps(self):
        assert tick_to_offset(len(EASING_STEPS)) == 1
        assert tick_to_offset(len(EASING_STEPS) + 5) == 1
        assert tick_to_offset(100) == 1

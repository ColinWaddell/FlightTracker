"""Tests for scenes/flight/flight_scene.py - pure helper functions."""

from unittest.mock import MagicMock

from display.scroller import EASING_STEPS
from display.scroller import _tick_offset as tick_to_offset
from scenes.flight.airline_logo import (
    AirlineLogoWidget,
    NullWidget,
    airline_icao_from_flight,
)
from scenes.flight.callsign_bar import (
    AirlineNameBar,
    CallsignBar,
    airline_name_from_flight,
    make_callsign_bar,
)
from scenes.flight.flight_scene import callsigns_match, telemetry_changed
from scenes.flight.journey import make_label
from scenes.flight.journey.full_label import FullNameLabel, abbreviate
from scenes.flight.journey.short_label import ShortCodeLabel
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

    def test_duplicate_callsigns_different_length(self):
        a = [Flight(callsign="BAW123"), Flight(callsign="BAW123")]
        b = [Flight(callsign="BAW123")]
        # Different list lengths mean the flight set changed even when
        # the callsigns are identical, so on_data() must reset.
        assert callsigns_match(a, b) is False

    def test_duplicate_callsigns_same_length(self):
        a = [Flight(callsign="BAW123"), Flight(callsign="BAW123")]
        b = [Flight(callsign="BAW123"), Flight(callsign="BAW123")]
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


# ---------------------------------------------------------------------------
# airline_icao_from_flight
# ---------------------------------------------------------------------------


class TestAirlineIcaoFromFlight:
    def test_airline_icao_from_field(self):
        flight = Flight(airline_icao="BAW")
        assert airline_icao_from_flight(flight) == "BAW"

    def test_falls_back_to_callsign_prefix(self):
        flight = Flight(icao_callsign="UAL1583")
        assert airline_icao_from_flight(flight) == "UAL"

    def test_airline_icao_takes_priority_over_callsign(self):
        flight = Flight(airline_icao="ENY", icao_callsign="UAL1583")
        assert airline_icao_from_flight(flight) == "ENY"

    def test_empty_everything(self):
        assert airline_icao_from_flight(Flight()) == ""

    def test_short_callsign_no_airline_icao(self):
        assert airline_icao_from_flight(Flight(icao_callsign="A1")) == ""

    def test_non_alpha_callsign_prefix(self):
        assert airline_icao_from_flight(Flight(icao_callsign="1AB234")) == ""

    def test_strips_whitespace(self):
        flight = Flight(airline_icao="  baw  ")
        assert airline_icao_from_flight(flight) == "BAW"


# ---------------------------------------------------------------------------
# AirlineLogoWidget
# ---------------------------------------------------------------------------


def _make_panel_and_canvas():
    panel = MagicMock()
    canvas = MagicMock()
    return panel, canvas


class TestAirlineLogoWidget:
    def test_width_is_0_before_draw(self):
        panel, _ = _make_panel_and_canvas()
        widget = AirlineLogoWidget(panel)
        assert widget.width == 0
        assert widget.icon_drawn is False

    def test_width_is_16_after_icon_drawn(self):
        panel, canvas = _make_panel_and_canvas()
        widget = AirlineLogoWidget(panel)
        widget.draw(canvas, Flight(airline_icao="BCO"))
        assert widget.width == 16
        assert widget.icon_drawn is True

    def test_draw_blanks_then_draws_image(self):
        panel, canvas = _make_panel_and_canvas()
        widget = AirlineLogoWidget(panel)
        # BCO icon exists in assets/airlines/airline_logos_16/
        flight = Flight(airline_icao="BCO")
        widget.draw(canvas, flight)
        # Should have blanked the region (set_pixel calls) then drawn the image
        assert panel.set_pixel.called
        assert panel.draw_image.called

    def test_draw_once_skips_repaint(self):
        panel, canvas = _make_panel_and_canvas()
        widget = AirlineLogoWidget(panel)
        flight = Flight(airline_icao="BCO")
        widget.draw(canvas, flight)
        panel.reset_mock()
        # Second draw with same airline_icao — should skip
        widget.draw(canvas, flight)
        assert not panel.set_pixel.called
        assert not panel.draw_image.called

    def test_reset_forces_repaint(self):
        panel, canvas = _make_panel_and_canvas()
        widget = AirlineLogoWidget(panel)
        flight = Flight(airline_icao="BCO")
        widget.draw(canvas, flight)
        panel.reset_mock()
        widget.reset()
        widget.draw(canvas, flight)
        assert panel.set_pixel.called
        assert panel.draw_image.called

    def test_flight_change_repaints(self):
        panel, canvas = _make_panel_and_canvas()
        widget = AirlineLogoWidget(panel)
        widget.draw(canvas, Flight(airline_icao="BCO"))
        panel.reset_mock()
        widget.draw(canvas, Flight(airline_icao="AAL"))
        assert panel.set_pixel.called
        assert panel.draw_image.called

    def test_missing_icon_no_draw(self):
        panel, canvas = _make_panel_and_canvas()
        widget = AirlineLogoWidget(panel)
        # QQQ icon file does not exist — no outline, no image, width=0
        widget.draw(canvas, Flight(airline_icao="QQQ"))
        assert panel.set_pixel.called  # blanks the region
        assert not panel.draw_image.called
        assert not panel.draw_line.called
        assert widget.width == 0
        assert widget.icon_drawn is False

    def test_empty_airline_icao_no_draw(self):
        panel, canvas = _make_panel_and_canvas()
        widget = AirlineLogoWidget(panel)
        widget.draw(canvas, Flight())
        assert not panel.draw_image.called
        assert not panel.draw_line.called
        assert widget.width == 0
        assert widget.icon_drawn is False

    def test_callsign_fallback_missing_icon_no_draw(self):
        panel, canvas = _make_panel_and_canvas()
        widget = AirlineLogoWidget(panel)
        # No airline_icao, callsign prefix is alphabetic but has no matching icon
        widget.draw(canvas, Flight(icao_callsign="QQQ999"))
        assert not panel.draw_image.called
        assert not panel.draw_line.called
        assert widget.width == 0
        assert widget.icon_drawn is False


class TestNullWidget:
    def test_width_is_0(self):
        assert NullWidget().width == 0

    def test_draw_is_noop(self):
        panel, canvas = _make_panel_and_canvas()
        widget = NullWidget()
        widget.draw(canvas, Flight(airline_icao="BAW"))
        assert not panel.set_pixel.called
        assert not panel.draw_image.called

    def test_reset_is_noop(self):
        widget = NullWidget()
        widget.reset()  # should not raise


# ---------------------------------------------------------------------------
# make_label
# ---------------------------------------------------------------------------


class TestMakeLabel:
    def test_style_0_returns_short_code_label(self, monkeypatch):
        cfg = MagicMock()
        cfg.airport_display_style = 0
        panel, _ = _make_panel_and_canvas()
        label = make_label(cfg, panel)
        assert isinstance(label, ShortCodeLabel)

    def test_style_1_returns_full_name_label(self):
        cfg = MagicMock()
        cfg.airport_display_style = 1
        panel, _ = _make_panel_and_canvas()
        label = make_label(cfg, panel)
        assert isinstance(label, FullNameLabel)

    def test_style_4_returns_full_name_label(self):
        cfg = MagicMock()
        cfg.airport_display_style = 4
        panel, _ = _make_panel_and_canvas()
        label = make_label(cfg, panel)
        assert isinstance(label, FullNameLabel)


# ---------------------------------------------------------------------------
# ShortCodeLabel
# ---------------------------------------------------------------------------


class TestShortCodeLabel:
    def test_loop_completed_after_draw(self):
        panel, canvas = _make_panel_and_canvas()
        # draw_text returns advance width; mock it to return small ints
        panel.draw_text.side_effect = lambda *a, **k: 5
        label = ShortCodeLabel(panel)
        assert label.loop_completed is False
        flight = Flight(origin="GLA", destination="LHR")
        label.draw(canvas, flight, 1, 63)
        assert label.loop_completed is True

    def test_reset_clears_loop_completed(self):
        panel, canvas = _make_panel_and_canvas()
        panel.draw_text.side_effect = lambda *a, **k: 5
        label = ShortCodeLabel(panel)
        label.draw(canvas, Flight(origin="GLA", destination="LHR"), 1, 63)
        label.reset()
        assert label.loop_completed is False

    def test_text_origin_shifts_with_icon(self):
        panel, canvas = _make_panel_and_canvas()
        panel.draw_text.side_effect = lambda *a, **k: 5
        label = ShortCodeLabel(panel)
        label.draw(canvas, Flight(origin="GLA", destination="LHR"), 17, 47)
        # First draw_text call should be at x=17 (the text_x_origin)
        first_call_args = panel.draw_text.call_args_list[0]
        assert first_call_args[0][2] == 17  # x argument position


# ---------------------------------------------------------------------------
# CallsignBar / AirlineNameBar / make_callsign_bar
# ---------------------------------------------------------------------------


class TestAirlineNameFromFlight:
    def test_known_airline(self):
        # BAW -> British Airways in airlines.json
        flight = Flight(airline_icao="BAW")
        assert airline_name_from_flight(flight) == "British Airways"

    def test_unknown_airline(self):
        flight = Flight(airline_icao="PPP")
        assert airline_name_from_flight(flight) == ""

    def test_empty_icao(self):
        flight = Flight()
        assert airline_name_from_flight(flight) == ""


class TestMakeCallsignBar:
    def test_callsign_mode_returns_callsign_bar(self):
        cfg = MagicMock()
        cfg.info_bar_mode = "callsign"
        panel, _ = _make_panel_and_canvas()
        bar = make_callsign_bar(cfg, panel)
        assert isinstance(bar, CallsignBar)

    def test_airline_mode_returns_airline_name_bar(self):
        cfg = MagicMock()
        cfg.info_bar_mode = "airline"
        panel, _ = _make_panel_and_canvas()
        bar = make_callsign_bar(cfg, panel)
        assert isinstance(bar, AirlineNameBar)


class TestCallsignBar:
    def test_draw_callsign_text(self):
        panel, canvas = _make_panel_and_canvas()
        panel.draw_text.side_effect = lambda *a, **k: 5
        bar = CallsignBar(panel)
        flights = [Flight(callsign="BAW123")]
        bar.draw(canvas, flights, 0)
        assert panel.draw_text.called
        assert panel.draw_square.called  # background blank

    def test_cached_redraw_skips(self):
        panel, canvas = _make_panel_and_canvas()
        panel.draw_text.side_effect = lambda *a, **k: 5
        bar = CallsignBar(panel)
        flights = [Flight(callsign="BAW123")]
        bar.draw(canvas, flights, 0)
        panel.reset_mock()
        bar.draw(canvas, flights, 0)
        assert not panel.draw_text.called
        assert not panel.draw_square.called

    def test_reset_clears_cache(self):
        panel, canvas = _make_panel_and_canvas()
        panel.draw_text.side_effect = lambda *a, **k: 5
        bar = CallsignBar(panel)
        flights = [Flight(callsign="BAW123")]
        bar.draw(canvas, flights, 0)
        panel.reset_mock()
        bar.reset()
        bar.draw(canvas, flights, 0)
        assert panel.draw_text.called

    def test_draws_index_for_multiple_flights(self):
        panel, canvas = _make_panel_and_canvas()
        panel.draw_text.side_effect = lambda *a, **k: 5
        bar = CallsignBar(panel)
        flights = [Flight(callsign="BAW123"), Flight(callsign="UAL456")]
        bar.draw(canvas, flights, 0)
        # The last draw_text call should be the N/M index
        last_call = panel.draw_text.call_args_list[-1]
        assert "1/2" in last_call[0]


class TestAirlineNameBar:
    def test_creates_scroller_on_first_draw(self):
        panel, canvas = _make_panel_and_canvas()
        panel.draw_text.side_effect = lambda *a, **k: 5
        bar = AirlineNameBar(panel)
        flights = [Flight(airline_icao="BAW")]
        bar.draw(canvas, flights, 0)
        assert bar.scroller is not None
        assert panel.draw_square.called  # background blank

    def test_rebuilds_scroller_on_flight_change(self):
        panel, canvas = _make_panel_and_canvas()
        panel.draw_text.side_effect = lambda *a, **k: 5
        bar = AirlineNameBar(panel)
        flights = [
            Flight(icao_callsign="BAW123", airline_icao="BAW"),
            Flight(icao_callsign="UAL456", airline_icao="UAL"),
        ]
        bar.draw(canvas, flights, 0)
        first_scroller = bar.scroller
        bar.draw(canvas, flights, 1)
        assert bar.scroller is not first_scroller

    def test_reset_clears_scroller(self):
        panel, canvas = _make_panel_and_canvas()
        panel.draw_text.side_effect = lambda *a, **k: 5
        bar = AirlineNameBar(panel)
        flights = [Flight(airline_icao="BAW")]
        bar.draw(canvas, flights, 0)
        bar.reset()
        assert bar.scroller is None

    def test_unknown_airline_falls_back_to_callsign(self):
        panel, canvas = _make_panel_and_canvas()
        panel.draw_text.side_effect = lambda *a, **k: 5
        cfg = MagicMock()
        cfg.info_bar_mode = "callsign"
        bar = AirlineNameBar(panel, cfg)
        # PPP is not in airlines.json; falls back to the display callsign
        flights = [Flight(airline_icao="PPP", callsign="PPP123")]
        bar.draw(canvas, flights, 0)
        assert bar.scroller is not None
        # The spans should reconstruct the callsign (split by colour)
        assert "".join(s.text for s in bar.spans) == "PPP123"

    def test_rebuilds_scroller_when_flight_count_changes(self):
        """The scroller width depends on flight_count (index area reserved
        when >1 flight).  Dropping to a single flight must rebuild the
        scroller at full width even when the displayed flight_id is
        unchanged — otherwise the bar keeps its narrow width and leaves
        a blank gap where the N/M index used to be.
        """
        panel, canvas = _make_panel_and_canvas()
        panel.draw_text.side_effect = lambda *a, **k: 5
        bar = AirlineNameBar(panel)
        # Two flights sharing the same flight_id (e.g. duplicate feed
        # entries) — callsigns_match sees the set change only via length.
        flights_two = [
            Flight(icao_callsign="BAW123", airline_icao="BAW"),
            Flight(icao_callsign="BAW123", airline_icao="BAW"),
        ]
        bar.draw(canvas, flights_two, 0)
        narrow_scroller = bar.scroller
        assert narrow_scroller is not None
        narrow_width = narrow_scroller.width

        # Rescan drops to a single flight with the same flight_id.
        flights_one = [Flight(icao_callsign="BAW123", airline_icao="BAW")]
        bar.draw(canvas, flights_one, 0)
        assert bar.scroller is not narrow_scroller
        assert bar.scroller.width > narrow_width


# ---------------------------------------------------------------------------
# build_spans — mode selection (0=model, 1=telemetry, 2=custom)
# ---------------------------------------------------------------------------


class TestBuildSpans:
    """Verify build_spans() dispatches to the correct span builder."""

    def _make_scene(self, flights):
        """Build a minimal FlightScene with mocked panel/canvas."""
        from scenes.flight.flight_scene import FlightScene

        panel, canvas = _make_panel_and_canvas()
        panel.draw_text.side_effect = lambda *a, **k: 5
        overhead = MagicMock()
        overhead.error = None
        overhead.new_data = False
        overhead.data = []
        overhead.processing = False
        scene = FlightScene(canvas, panel, overhead, refresh_interval=60)
        scene.flights = flights
        return scene

    def test_mode_0_returns_model_spans(self):
        scene = self._make_scene([Flight(plane="Boeing 787")])
        cfg = MagicMock()
        cfg.details = 0
        spans = scene.build_spans(cfg)
        assert len(spans) == 1
        assert spans[0].text == "BOEING 787"

    def test_mode_1_returns_telemetry_spans(self):
        scene = self._make_scene(
            [Flight(altitude=38000, ground_speed=480, heading=270)]
        )
        cfg = MagicMock()
        cfg.details = 1
        cfg.height_unit = "ft"
        cfg.speed_unit = "kts"
        spans = scene.build_spans(cfg)
        texts = [s.text for s in spans]
        assert "38000" in texts
        assert "480" in texts
        assert "270" in texts

    def test_mode_2_returns_custom_spans(self):
        scene = self._make_scene([Flight(plane="Boeing 787", callsign="BAW123")])
        cfg = MagicMock()
        cfg.details = 2
        cfg.details_custom_template = "{callsign} | {plane}"
        cfg.height_unit = "ft"
        cfg.speed_unit = "kts"
        spans = scene.build_spans(cfg)
        texts = [s.text for s in spans if s.text]
        assert "BAW123" in texts
        assert "BOEING 787" in texts

    def test_mode_2_empty_template_returns_warning(self):
        from scenes.flight.custom_details import NOT_DEFINED_TEXT

        scene = self._make_scene([Flight(plane="Boeing 787")])
        cfg = MagicMock()
        cfg.details = 2
        cfg.details_custom_template = ""
        cfg.height_unit = "ft"
        cfg.speed_unit = "kts"
        spans = scene.build_spans(cfg)
        assert len(spans) == 1
        assert spans[0].text == NOT_DEFINED_TEXT

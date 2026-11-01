"""Barely-overflowing content should not be scrolled.

``MIN_PIXELS_FOR_SCROLL`` treats bounce content whose overflow is at or below
the threshold as already legible: the scroller stays at rest and reports
``all_looped()`` without ever running the reveal/pause/retract cycle.
"""

from unittest.mock import MagicMock

import display.scroller as scroller_module
from display.scroller import (
    INITIAL_TICKS,
    MIN_PIXELS_FOR_SCROLL,
    BounceState,
    Scroller,
    spans_width,
)


def _make_scroller(monkeypatch, *, content_width, width, bounce):
    """Build a Scroller whose rendered content is exactly ``content_width``."""
    monkeypatch.setattr(
        scroller_module,
        "_render_spans",
        lambda spans: [{} for _ in range(content_width)],
    )
    return Scroller(MagicMock(), MagicMock(), 0, 0, width, [], bounce=bounce)


def test_bounce_fits_or_barely_overflows_never_scrolls(monkeypatch):
    for overflow in (0, MIN_PIXELS_FOR_SCROLL):
        scroller = _make_scroller(
            monkeypatch, content_width=30 + overflow, width=30, bounce=True
        )
        assert scroller.scroll_max == overflow
        assert scroller.all_looped()

        for _ in range(200):  # far past INITIAL_TICKS + a full cycle
            scroller.draw()

        assert scroller.state == BounceState.INITIAL
        assert scroller.position == 0


def test_bounce_overflow_past_threshold_still_scrolls(monkeypatch):
    scroller = _make_scroller(
        monkeypatch,
        content_width=30 + MIN_PIXELS_FOR_SCROLL + 1,
        width=30,
        bounce=True,
    )
    assert scroller.scroll_max == MIN_PIXELS_FOR_SCROLL + 1
    assert not scroller.all_looped()

    for _ in range(INITIAL_TICKS + 2):
        scroller.draw()

    assert scroller.state == BounceState.REVEAL
    assert scroller.position < 0


def test_bounce_update_shrink_to_barely_overflow_resets(monkeypatch):
    scroller = _make_scroller(monkeypatch, content_width=80, width=30, bounce=True)
    for _ in range(INITIAL_TICKS + 10):
        scroller.draw()
    assert scroller.position < 0

    monkeypatch.setattr(
        scroller_module,
        "_render_spans",
        lambda spans: [{} for _ in range(30 + MIN_PIXELS_FOR_SCROLL)],
    )
    scroller.update([MagicMock()])

    assert scroller.position == 0
    assert scroller.state == BounceState.INITIAL
    assert scroller.all_looped()


def test_continuous_still_scrolls_barely_overflowing_content(monkeypatch):
    scroller = _make_scroller(
        monkeypatch,
        content_width=30 + MIN_PIXELS_FOR_SCROLL,
        width=30,
        bounce=False,
    )
    for _ in range(5):
        scroller.draw()

    assert scroller.position < 30  # it moved
    assert not scroller.all_looped()


# ---------------------------------------------------------------------------
# spans_width + static prefix (viewport width == content width)
# ---------------------------------------------------------------------------


def test_spans_width_returns_rendered_length(monkeypatch):
    monkeypatch.setattr(
        scroller_module, "_render_spans", lambda spans: [{} for _ in range(41)]
    )
    assert spans_width([MagicMock()]) == 41


def test_bounce_viewport_equal_to_content_renders_statically(monkeypatch):
    """A bounce scroller whose viewport equals its content width - as used
    for the fixed emergency-squawk prefix - never scrolls, never counts a
    loop, and reports its content as looped."""
    scroller = _make_scroller(monkeypatch, content_width=24, width=24, bounce=True)
    for _ in range(200):  # far past INITIAL_TICKS + a full cycle
        scroller.draw()

    assert scroller.position == 0
    assert scroller.state == BounceState.INITIAL
    assert scroller.loop_count == 0
    assert scroller.all_looped()


def test_static_scroller_clear_blanks_exactly_drawn_pixels(monkeypatch):
    """clear() undoes only the pixels the scroller drew - not a rectangle."""
    from setup import colours

    panel, canvas = MagicMock(), MagicMock()
    monkeypatch.setattr(
        scroller_module,
        "_render_spans",
        lambda spans: [{3: colours.RED}, {}, {5: colours.RED}],
    )
    scroller = Scroller(panel, canvas, 10, 0, 3, [MagicMock()], bounce=True)
    scroller.draw()
    assert panel.set_pixel.call_count == 2

    panel.reset_mock()
    scroller.clear()
    assert panel.set_pixel.call_count == 2
    for call in panel.set_pixel.call_args_list:
        assert call.args[3:] == (0, 0, 0)  # blanked, not overwritten
    blanked_x = {call.args[1] for call in panel.set_pixel.call_args_list}
    assert blanked_x == {10, 12}

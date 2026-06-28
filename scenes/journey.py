"""
LocationWidget — ported from DotboxClient C++ LocationWidget.

Two display modes:
  IATA   — large 3-letter codes with a filled-triangle arrow (original look)
  FULL   — small font, "CODE>Full Airport Name" per line, with a bounce-scroll
            animation when the name overflows the screen width.

The mode is chosen at runtime from Config.full_airport_name.
"""

from __future__ import annotations
from enum import Enum, auto

from utilities.animator import Animator
from setup import fonts, screen
from setup.themes import TC
from setup.themes import (
    THEME_BG,
    THEME_ARROW,
    THEME_LOCATION_ORIGIN,
    THEME_LOCATION_DESTINATION,
    THEME_LOCATION_ORIGIN_FULL,
    THEME_LOCATION_DESTINATION_FULL,
    THEME_LOCATION_ORIGIN_ARROW,
    THEME_LOCATION_DESTINATION_ARROW,
)
from setup.configuration import Config

from rgbmatrix import graphics

# ---------------------------------------------------------------------------
# Bounce-scroll easing (mirrors C++ tick_to_offset)
# ---------------------------------------------------------------------------

_EASING_STEPS = (1, 0, 0, 1, 1, 0, 1, 1, 1)


def _tick_to_offset(tick: int) -> int:
    return 1 if tick >= len(_EASING_STEPS) else _EASING_STEPS[tick]


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INITIAL_TICKS = 100
PAUSE_TICKS = 25

# Y baseline for each line in FULL mode
_FULL_LINE_Y = (7, 15)  # origin, destination (within 0–16 region)

# X positions for IATA mode
_IATA_ORIGIN_X = 1
_IATA_DESTINATION_X = 40

# Arrow geometry for IATA mode
_ARROW_TIP_X = 34
_ARROW_TIP_Y = 7
_ARROW_WIDTH = 4
_ARROW_HEIGHT = 8


def _font_text_width(font, text: str) -> int:
    """Sum character widths using rgbmatrix Font.CharacterWidth."""
    return sum(font.CharacterWidth(ord(c)) for c in text)


# ---------------------------------------------------------------------------
# Bounce state machine
# ---------------------------------------------------------------------------


class _BounceState(Enum):
    INITIAL = auto()
    REVEAL = auto()
    PAUSE = auto()
    RETRACT = auto()


class _LineScroller:
    """Manages bounce-scroll state for one text line."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.state = _BounceState.INITIAL
        self.timer = 0
        self.position = 0  # current x offset (0 = at home, negative = scrolled left)
        self.scroll_max = 0  # how far left we need to scroll (pixels)
        self.loop_count = 0
        self.loop_done = False

    def tick(self):
        """Advance state machine by one frame. Returns current x position."""
        st = self.state

        # Movement
        if st == _BounceState.REVEAL:
            self.position -= _tick_to_offset(self.timer)
        elif st == _BounceState.RETRACT:
            self.position += _tick_to_offset(self.timer)

        # Transitions
        if st == _BounceState.INITIAL:
            if self.scroll_max > 0 and self.timer >= INITIAL_TICKS:
                self.state = _BounceState.REVEAL
                self.timer = 0
            elif self.scroll_max == 0:
                # Nothing to scroll — done immediately
                self.loop_done = True
        elif st == _BounceState.REVEAL:
            if self.position <= -self.scroll_max:
                self.position = -self.scroll_max
                self.state = _BounceState.PAUSE
                self.timer = 0
        elif st == _BounceState.PAUSE:
            if self.timer >= PAUSE_TICKS:
                if self.position <= -self.scroll_max:
                    self.state = _BounceState.RETRACT
                else:
                    self.state = _BounceState.INITIAL
                self.timer = 0
        elif st == _BounceState.RETRACT:
            if self.position >= 0:
                self.position = 0
                self.loop_count += 1
                self.loop_done = True
                self.state = _BounceState.PAUSE
                self.timer = 0

        self.timer += 1
        return self.position


# ---------------------------------------------------------------------------
# LocationWidget
# ---------------------------------------------------------------------------


class JourneyScene(object):
    """Draws origin → destination in either IATA or FULL (bounce) mode."""

    def __init__(self):
        super().__init__()
        self._loc_origin = ""
        self._loc_destination = ""
        self._origin_name = ""
        self._dest_name = ""
        self._first_draw = True
        self._mode = None  # 'iata' or 'full'
        self._origin_scroll = _LineScroller()
        self._dest_scroll = _LineScroller()
        self.loop_completed = False
        self._last_origin = None
        self._last_dest = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _text_width(self, font, text: str) -> int:
        return _font_text_width(font, text)

    def _draw_iata_mode(self):
        cfg = Config.instance()
        origin = (
            self._data[self._data_index].get("origin", "") or cfg.journey_blank_filler
        )
        destination = (
            self._data[self._data_index].get("destination", "")
            or cfg.journey_blank_filler
        )
        home_code = cfg.home_airport_code

        # Clear the location area
        self.draw_square(0, 0, screen.WIDTH - 1, 15, TC(THEME_BG))

        # Origin
        font = fonts.large_bold if origin == home_code else fonts.large
        graphics.DrawText(
            self.canvas,
            font,
            _IATA_ORIGIN_X,
            12,
            TC(THEME_LOCATION_ORIGIN),
            origin,
        )

        # Destination
        font = fonts.large_bold if destination == home_code else fonts.large
        graphics.DrawText(
            self.canvas,
            font,
            _IATA_DESTINATION_X,
            12,
            TC(THEME_LOCATION_DESTINATION),
            destination,
        )

        # Filled-triangle arrow
        ax, ay = _ARROW_TIP_X, _ARROW_TIP_Y
        x = ax - _ARROW_WIDTH
        y1 = ay - (_ARROW_HEIGHT // 2)
        y2 = ay + (_ARROW_HEIGHT // 2)
        self.canvas.SetPixel(
            ax, ay, TC(THEME_ARROW).red, TC(THEME_ARROW).green, TC(THEME_ARROW).blue
        )
        for _ in range(_ARROW_WIDTH):
            graphics.DrawLine(self.canvas, x, y1, x, y2, TC(THEME_ARROW))
            x += 1
            y1 += 1
            y2 -= 1

        self.loop_completed = True

    def _line_text(self, iata: str, name: str, arrow: str) -> str:
        return f"{iata}{arrow}{name}"

    def _draw_full_line(self, line_idx: int, x_offset: int):
        """Draw one scrolling line at the given x_offset."""
        if line_idx == 0:
            iata = self._data[self._data_index].get("origin") or "???"
            name = self._origin_name
            arrow = ">"
            colour_code = TC(THEME_LOCATION_ORIGIN)
            colour_name = TC(THEME_LOCATION_ORIGIN_FULL)
            colour_arrow = TC(THEME_LOCATION_ORIGIN_ARROW)
        else:
            iata = self._data[self._data_index].get("destination") or "???"
            name = self._dest_name
            arrow = "<"
            colour_code = TC(THEME_LOCATION_DESTINATION)
            colour_name = TC(THEME_LOCATION_DESTINATION_FULL)
            colour_arrow = TC(THEME_LOCATION_DESTINATION_ARROW)

        y = _FULL_LINE_Y[line_idx]
        x = x_offset

        # IATA code
        x += graphics.DrawText(self.canvas, fonts.small, x, y, colour_code, iata)
        # Arrow separator
        x += graphics.DrawText(self.canvas, fonts.small, x, y, colour_arrow, arrow)
        # Full name
        graphics.DrawText(self.canvas, fonts.small, x, y, colour_name, name)

    def _undraw_full_line(self, line_idx: int, x_offset: int):
        """Overdraw with BG to erase previous position."""
        if line_idx == 0:
            iata = self._data[self._data_index].get("origin") or "???"
            name = self._origin_name
            arrow = ">"
        else:
            iata = self._data[self._data_index].get("destination") or "???"
            name = self._dest_name
            arrow = "<"

        y = _FULL_LINE_Y[line_idx]
        full_text = f"{iata}{arrow}{name}"
        # Erase by drawing entire text in BG colour (simpler than tracking bounds)
        graphics.DrawText(
            self.canvas, fonts.small, x_offset, y, TC(THEME_BG), full_text
        )

    def _setup_full_mode(self):
        """Compute scroll distances for both lines."""
        cfg = Config.instance()
        origin = self._data[self._data_index].get("origin") or "???"
        destination = self._data[self._data_index].get("destination") or "???"
        origin_name = self._data[self._data_index].get("origin_name") or ""
        dest_name = self._data[self._data_index].get("destination_name") or ""

        if cfg.abbreviate_name:
            origin_name = _abbreviate(origin_name)
            dest_name = _abbreviate(dest_name)

        self._origin_name = origin_name or "unknown"
        self._dest_name = dest_name or "unknown"

        for scroller, iata, name, arrow in (
            (self._origin_scroll, origin, self._origin_name, ">"),
            (self._dest_scroll, destination, self._dest_name, "<"),
        ):
            scroller.reset()
            full_text = f"{iata}{arrow}{name}"
            w = _font_text_width(fonts.small, full_text)
            overflow = w - screen.WIDTH
            scroller.scroll_max = max(0, overflow)

    # ------------------------------------------------------------------
    # Animator keyframe
    # ------------------------------------------------------------------

    @Animator.KeyFrame.add(0)
    def journey_reset(self):
        """Called on every scene reset (frame == 0 in the Animator loop)."""
        self._first_draw = True
        self._mode = None
        self._origin_scroll.reset()
        self._dest_scroll.reset()
        self.loop_completed = False
        self._last_origin = None
        self._last_dest = None

    @Animator.KeyFrame.add(1)
    def journey(self, count):
        if len(self._data) == 0:
            return

        cfg = Config.instance()
        origin = self._data[self._data_index].get("origin")
        destination = self._data[self._data_index].get("destination")

        # Detect flight change
        if origin != self._last_origin or destination != self._last_dest:
            self._first_draw = True
            self._mode = None
            self._origin_scroll.reset()
            self._dest_scroll.reset()
            self.loop_completed = False
            self._last_origin = origin
            self._last_dest = destination

        target_mode = "full" if cfg.full_airport_name else "iata"

        if target_mode == "iata":
            if not self.loop_completed:
                self._draw_iata_mode()
            return

        # ----- FULL mode -----
        if self._mode != "full" or self._first_draw:
            self._mode = "full"
            self._setup_full_mode()
            # Clear location area on first draw
            self.draw_square(0, 0, screen.WIDTH - 1, 16, TC(THEME_BG))
            self._first_draw = False

        for line_idx, scroller in enumerate((self._origin_scroll, self._dest_scroll)):
            prev_x = scroller.position
            new_x = scroller.tick()

            if (
                prev_x != new_x
                or scroller.state == _BounceState.REVEAL
                or scroller.state == _BounceState.RETRACT
            ):
                self._undraw_full_line(line_idx, prev_x)
            self._draw_full_line(line_idx, new_x)

        # Sync timing between the two scrollers when both are active
        if self._origin_scroll.scroll_max > 0 and self._dest_scroll.scroll_max > 0:
            if self._origin_scroll.state != self._dest_scroll.state:
                # Keep them in lock-step by resetting the slower one's timer
                self._origin_scroll.timer = 0
                self._dest_scroll.timer = 0

        # Mark completed when both have done at least two loops (or have nothing to scroll)
        origin_done = (
            self._origin_scroll.loop_done or self._origin_scroll.scroll_max == 0
        )
        dest_done = self._dest_scroll.loop_done or self._dest_scroll.scroll_max == 0
        if origin_done and dest_done:
            self.loop_completed = True


# ---------------------------------------------------------------------------
# Optional name abbreviation helper
# ---------------------------------------------------------------------------

_ABBREVIATIONS = {
    "International": "Intl",
    "international": "Intl",
    "Airport": "",
    "airport": "",
    "Regional": "Reg",
    "regional": "Reg",
    "Municipal": "Muni",
    "municipal": "Muni",
}


def _abbreviate(name: str) -> str:
    for long, short in _ABBREVIATIONS.items():
        name = name.replace(long, short)
    # Collapse multiple spaces
    return " ".join(name.split())

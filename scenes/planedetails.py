"""
PlaneDetailsScene — scrolling bottom row.

details == 0  →  scrolls the plane make/model (e.g. "Airbus A320")
                 single span, fonts.regular, THEME_PLANE colour

details == 1  →  scrolls telemetry using multi-colour spans, fonts.small_symbols:
                     icon  (^  ~  }  *)  →  THEME_PLANE_TLM_UNITS
                     value (numbers + unit text)  →  THEME_PLANE_TLM

Spans are a list of (colour, font, text) tuples, mirroring the C++ MessageSpan
pattern from DotboxClient's ScrollText widget.
"""

from rgbmatrix import graphics

from utilities.animator import Animator
from setup import fonts, screen
from setup.themes import (
    TC,
    THEME_PLANE,
    THEME_PLANE_TLM,
    THEME_PLANE_TLM_UNITS,
    THEME_BG,
)
from setup.configuration import Config

PLANE_DISTANCE_FROM_TOP = 31
PLANE_TEXT_HEIGHT = 8


# ---------------------------------------------------------------------------
# Span helpers
# ---------------------------------------------------------------------------


def _spans_width(spans: list) -> int:
    """Total pixel width of a span list."""
    total = 0
    for _colour, font, text in spans:
        total += sum(font.CharacterWidth(ord(c)) for c in text)
    return total


def _draw_spans(canvas, spans: list, x: int, y: int) -> int:
    """Draw spans left-to-right from x. Returns total pixel width drawn."""
    start_x = x
    for colour, font, text in spans:
        x += graphics.DrawText(canvas, font, x, y, colour, text)
    return x - start_x


# ---------------------------------------------------------------------------
# Scene
# ---------------------------------------------------------------------------


class PlaneDetailsScene(object):
    def __init__(self):
        super().__init__()
        self.plane_position = screen.WIDTH
        self._data_all_looped = False
        self._last_details_mode = None

    # -- Span builders ----------------------------------------------------

    def _model_spans(self) -> list:
        text = self._data[self._data_index].get("plane", "")
        return [(TC(THEME_PLANE), fonts.regular, text)]

    def _telemetry_spans(self) -> list:
        cfg = Config.instance()
        flight = self._data[self._data_index]

        altitude_ft = flight.get("altitude", 0) or 0
        ground_speed_kts = flight.get("ground_speed", 0) or 0
        heading = flight.get("heading", 0) or 0

        if cfg.units == "i":
            alt_val = str(int(altitude_ft))
            alt_unit = "ft"
            speed_val = str(int(ground_speed_kts * 1.15078))
            speed_unit = "mph"
        else:
            alt_val = str(int(altitude_ft * 0.3048))
            alt_unit = "m"
            speed_val = str(int(ground_speed_kts * 1.852))
            speed_unit = "kmh"

        f = fonts.small_symbols
        val = TC(THEME_PLANE_TLM)
        ico = TC(THEME_PLANE_TLM_UNITS)

        # Mirror of the C++ updateText() call in flights.cpp:
        #   { units_colour, "^" }, { values_colour, alt }, { units_colour, alt_units },
        #   { values_colour, speed }, { units_colour, speed_units },
        #   { values_colour, heading }, { units_colour, "*" }
        return [
            (ico, f, "^"),
            (val, f, alt_val),
            (ico, f, alt_unit),
            (val, f, " "),
            (ico, f, "~"),
            (val, f, speed_val),
            (ico, f, speed_unit),
            (val, f, " "),
            (ico, f, "}"),
            (val, f, str(heading)),
            (ico, f, "*"),
        ]

    def _build_spans(self) -> list:
        cfg = Config.instance()
        return self._telemetry_spans() if cfg.details == 1 else self._model_spans()

    # -- Keyframes ---------------------------------------------------------

    @Animator.KeyFrame.add(1)
    def plane_details(self, count):
        if len(self._data) == 0:
            return

        cfg = Config.instance()
        current_mode = cfg.details

        # Reset scroller if mode changed mid-display
        if current_mode != self._last_details_mode:
            self.plane_position = screen.WIDTH
            self._last_details_mode = current_mode

        spans = self._build_spans()

        # Clear plane row
        self.draw_square(
            0,
            PLANE_DISTANCE_FROM_TOP - PLANE_TEXT_HEIGHT,
            screen.WIDTH,
            screen.HEIGHT,
            TC(THEME_BG),
        )

        # Draw spans from current scroll position
        total_width = _draw_spans(
            self.canvas, spans, self.plane_position, PLANE_DISTANCE_FROM_TOP
        )

        # Advance scroll; cycle to next flight when the text has fully passed
        self.plane_position -= 1
        if self.plane_position + total_width < 0:
            self.plane_position = screen.WIDTH
            if len(self._data) > 1:
                self._data_index = (self._data_index + 1) % len(self._data)
                self._data_all_looped = (not self._data_index) or self._data_all_looped
                self.reset_scene()

    @Animator.KeyFrame.add(0)
    def reset_scrolling(self):
        self.plane_position = screen.WIDTH

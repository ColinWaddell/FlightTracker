"""Short-code journey label — static IATA codes + pixel arrow."""

from __future__ import annotations

from setup import fonts
from setup.configuration import Config
from setup.themes import (
    TC,
    THEME_ARROW,
    THEME_BG,
    THEME_LOCATION_DESTINATION,
    THEME_LOCATION_ORIGIN,
)
from utilities.flight import Flight

# Vertical position of the IATA code baselines (unchanged from the
# original draw_iata_mode — both codes share y=12).
_IATA_Y = 12

# Relative offsets from the text x-origin.  The original layout used
# IATA_ORIGIN_X=1, IATA_DESTINATION_X=40, ARROW_TIP_X=34 — i.e. origin at
# +0, arrow tip at +33, destination at +39 relative to the origin.
_DEST_OFFSET = 39
_ARROW_TIP_OFFSET = 33
_ARROW_TIP_Y = 7
_ARROW_WIDTH = 4
_ARROW_HEIGHT = 8


class ShortCodeLabel:
    """Static IATA origin/destination codes with a pixel-drawn arrow.

    ``loop_completed`` is ``True`` immediately after the first draw —
    there is no scrolling to wait for.
    """

    def __init__(self, panel):
        self.panel = panel
        self.loop_completed = False

    def reset(self) -> None:
        self.loop_completed = False

    def draw(
        self,
        canvas,
        flight: Flight,
        text_x_origin: int,
        available_width: int,
        scroll_all: bool = False,  # noqa: ARG002 — short codes never scroll
    ) -> None:
        cfg = Config.instance()
        origin = flight.origin or cfg.journey_blank_filler
        destination = flight.destination or cfg.journey_blank_filler
        home_code = cfg.home_airport_code

        self.panel.draw_square(
            canvas,
            text_x_origin,
            0,
            text_x_origin + available_width - 1,
            15,
            TC(THEME_BG),
        )

        origin_x = text_x_origin
        dest_x = text_x_origin + _DEST_OFFSET

        font = fonts.large_bold if origin == home_code else fonts.large
        self.panel.draw_text(
            canvas, font, origin_x, _IATA_Y, TC(THEME_LOCATION_ORIGIN), origin
        )
        font = fonts.large_bold if destination == home_code else fonts.large
        self.panel.draw_text(
            canvas, font, dest_x, _IATA_Y, TC(THEME_LOCATION_DESTINATION), destination
        )

        self._draw_arrow(canvas, text_x_origin + _ARROW_TIP_OFFSET, _ARROW_TIP_Y)

        self.loop_completed = True

    def _draw_arrow(self, canvas, ax: int, ay: int) -> None:
        x = ax - _ARROW_WIDTH
        y1 = ay - (_ARROW_HEIGHT // 2)
        y2 = ay + (_ARROW_HEIGHT // 2)
        self.panel.set_pixel(
            canvas,
            ax,
            ay,
            TC(THEME_ARROW).red,
            TC(THEME_ARROW).green,
            TC(THEME_ARROW).blue,
        )
        for _ in range(_ARROW_WIDTH):
            self.panel.draw_line(canvas, x, y1, x, y2, TC(THEME_ARROW))
            x += 1
            y1 += 1
            y2 -= 1

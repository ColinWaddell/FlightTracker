"""Short-code journey label - static IATA codes + pixel arrow."""

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
# original draw_iata_mode - both codes share y=12).
_IATA_Y = 12

# Relative offsets from the text x-origin.  The original layout used
# IATA_ORIGIN_X=1, IATA_DESTINATION_X=40, ARROW_TIP_X=34 - i.e. origin at
# +0, arrow tip at +33, destination at +39 relative to the origin.
_DEST_OFFSET = 39
_ARROW_TIP_OFFSET = 33
_ARROW_TIP_Y = 7
_ARROW_WIDTH = 4
_ARROW_HEIGHT = 8
_ARROW_WIDTH_SMALL = 3
_ARROW_HEIGHT_SMALL = 6


def _display_code(code: str) -> str:
    """Clamp a journey code to what the fixed short-label geometry fits.

    Four characters is the ceiling: IATA codes are three, ICAO and FAA
    local codes are four (0I8, 98KY).  Longer codes are administrative
    numbering that route services do not send as a display code; they
    are truncated here and the full-name line carries the detail.
    """
    return code[:4]


def _code_font(is_home: bool, pair_compact: bool, base, base_bold, compact):
    """Pick the font for one side of the short label.

    Three-character codes (IATA) use the layout's base size - bold when
    the code is the home field.  If either end of the journey needs the
    compact size (a 4-char ICAO / FAA local code such as 98KY), both
    ends use it so the pair renders at the same size; the compact
    footprint is identical (4 x 6px = 3 x 8px), so the fixed arrow and
    destination offsets still clear.  No bold cut exists below 7px, so
    compact codes always render plain.
    """
    if pair_compact:
        return compact
    return base_bold if is_home else base


class ShortCodeLabel:
    """Static IATA origin/destination codes with a pixel-drawn arrow.

    ``loop_completed`` is ``True`` immediately after the first draw -
    there is no scrolling to wait for.
    """

    def __init__(self, panel, cfg: Config | None = None):
        self.panel = panel
        self.cfg = cfg or Config.instance()
        self.loop_completed = False

    def reset(self) -> None:
        self.loop_completed = False

    def draw(
        self,
        canvas,
        flight: Flight,
        text_x_origin: int,
        available_width: int,
        icon_required: bool = False,
    ) -> None:
        # icon_required indicates icon mode is enabled; text_x_origin > 1
        # confirms an icon was actually drawn (x=17 vs x=1).  If icon
        # mode is on but no icon resolved, fall back to the no-icon layout.
        with_icon = icon_required and text_x_origin > 1

        if with_icon:
            self._draw_with_icon(canvas, flight, text_x_origin, available_width)
        else:
            self._draw_without_icon(canvas, flight, text_x_origin, available_width)

        self.loop_completed = True

    # ------------------------------------------------------------------
    # No-icon layout - original positioning (origin at text_x_origin,
    # destination at +39, arrow tip at +33)
    # ------------------------------------------------------------------

    def _draw_without_icon(
        self, canvas, flight: Flight, text_x_origin: int, available_width: int
    ) -> None:
        cfg = self.cfg
        origin = _display_code(flight.origin or cfg.journey_blank_filler)
        destination = _display_code(flight.destination or cfg.journey_blank_filler)
        home_code = _display_code(cfg.home_airport_code)

        self.panel.draw_square(
            canvas,
            text_x_origin,
            0,
            text_x_origin + available_width,
            15,
            TC(THEME_BG),
        )

        origin_x = text_x_origin
        dest_x = text_x_origin + _DEST_OFFSET

        # If either end needs the compact size, render both ends with it
        # so the pair looks even.
        pair_compact = len(origin) > 3 or len(destination) > 3
        font = _code_font(
            origin == home_code,
            pair_compact,
            fonts.large,
            fonts.large_bold,
            fonts.regular,
        )
        self.panel.draw_text(
            canvas, font, origin_x, _IATA_Y, TC(THEME_LOCATION_ORIGIN), origin
        )
        font = _code_font(
            destination == home_code,
            pair_compact,
            fonts.large,
            fonts.large_bold,
            fonts.regular,
        )
        self.panel.draw_text(
            canvas, font, dest_x, _IATA_Y, TC(THEME_LOCATION_DESTINATION), destination
        )

        self._draw_arrow(
            canvas,
            text_x_origin + _ARROW_TIP_OFFSET,
            _ARROW_TIP_Y,
            _ARROW_WIDTH,
            _ARROW_HEIGHT,
        )

    # ------------------------------------------------------------------
    # Icon layout - repositioned to fit the narrower space beside the icon
    # ------------------------------------------------------------------

    def _draw_with_icon(
        self, canvas, flight: Flight, text_x_origin: int, available_width: int
    ) -> None:
        cfg = self.cfg
        origin = _display_code(flight.origin or cfg.journey_blank_filler)
        destination = _display_code(flight.destination or cfg.journey_blank_filler)
        home_code = _display_code(cfg.home_airport_code)

        self.panel.draw_square(
            canvas,
            text_x_origin,
            0,
            text_x_origin + available_width,
            15,
            TC(THEME_BG),
        )

        # TODO: tune these offsets for the icon layout.
        # For now, scale the original offsets proportionally to the
        # narrower width.  Origin at text_x_origin, arrow centred,
        # destination pushed left to fit.
        origin_x = text_x_origin
        arrow_tip_x = origin_x + 25
        dest_x = text_x_origin + 27

        pair_compact = len(origin) > 3 or len(destination) > 3
        font = _code_font(
            origin == home_code,
            pair_compact,
            fonts.medium,
            fonts.medium_bold,
            fonts.small,
        )
        self.panel.draw_text(
            canvas, font, origin_x, _IATA_Y, TC(THEME_LOCATION_ORIGIN), origin
        )
        font = _code_font(
            destination == home_code,
            pair_compact,
            fonts.medium,
            fonts.medium_bold,
            fonts.small,
        )
        self.panel.draw_text(
            canvas, font, dest_x, _IATA_Y, TC(THEME_LOCATION_DESTINATION), destination
        )

        self._draw_arrow(
            canvas,
            arrow_tip_x,
            _ARROW_TIP_Y,
            _ARROW_WIDTH_SMALL,
            _ARROW_HEIGHT_SMALL,
        )

    # ------------------------------------------------------------------
    # Shared arrow drawing
    # ------------------------------------------------------------------

    def _draw_arrow(self, canvas, ax: int, ay: int, width: int, height: int) -> None:
        x = ax - width
        y1 = ay - (height // 2)
        y2 = ay + (height // 2)
        self.panel.set_pixel(
            canvas,
            ax,
            ay,
            TC(THEME_ARROW).red,
            TC(THEME_ARROW).green,
            TC(THEME_ARROW).blue,
        )
        for _ in range(width):
            self.panel.draw_line(canvas, x, y1, x, y2, TC(THEME_ARROW))
            x += 1
            y1 += 1
            y2 -= 1

"""
PlaneDetailsScene — scrolling bottom row.

details == 0  →  scrolls the plane make/model (e.g. "Airbus A320")
details == 1  →  scrolls telemetry: altitude, speed, heading
                 using the custom Font5x8 characters:
                     ^  altitude icon
                     ~  speed icon
                     }  heading icon
                     *  degrees symbol
"""

from rgbmatrix import graphics

from utilities.animator import Animator
from setup import fonts, screen
from setup.themes import TC, THEME_PLANE, THEME_PLANE_TLM, THEME_PLANE_TLM_UNITS, THEME_BG
from setup.configuration import Config

PLANE_DISTANCE_FROM_TOP = 30
PLANE_TEXT_HEIGHT = 9


class PlaneDetailsScene(object):
    def __init__(self):
        super().__init__()
        self.plane_position  = screen.WIDTH
        self._data_all_looped = False
        self._last_details_mode = None

    def _build_telemetry_string(self) -> str:
        """Build the telemetry scroll string for the current flight."""
        cfg = Config.instance()
        flight = self._data[self._data_index]

        altitude_ft = flight.get("altitude", 0) or 0
        ground_speed_kts = flight.get("ground_speed", 0) or 0
        heading = flight.get("heading", 0) or 0

        if cfg.units == "i":
            alt_val   = f"{int(altitude_ft)}"
            alt_unit  = "ft"
            speed_val = f"{int(ground_speed_kts * 1.15078)}"
            speed_unit = "mph"
        else:
            alt_val   = f"{int(altitude_ft * 0.3048)}"
            alt_unit  = "m"
            speed_val = f"{int(ground_speed_kts * 1.852)}"
            speed_unit = "kmh"

        # ^ and ~ and } and * are custom pixel-art glyphs in Font5x8-custom
        return f"^ {alt_val}{alt_unit} ~ {speed_val}{speed_unit} }} {heading}*"

    def _get_scroll_text(self) -> str:
        cfg = Config.instance()
        if cfg.details == 1:
            return self._build_telemetry_string()
        return self._data[self._data_index].get("plane", "")

    def _get_font(self):
        cfg = Config.instance()
        return fonts.small_symbols if cfg.details == 1 else fonts.regular

    def _get_colour(self):
        cfg = Config.instance()
        return TC(THEME_PLANE_TLM) if cfg.details == 1 else TC(THEME_PLANE)

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

        font   = self._get_font()
        colour = self._get_colour()
        text   = self._get_scroll_text()

        # Clear plane row
        self.draw_square(
            0,
            PLANE_DISTANCE_FROM_TOP - PLANE_TEXT_HEIGHT,
            screen.WIDTH,
            screen.HEIGHT,
            TC(THEME_BG),
        )

        # Draw text at current scroll position
        text_length = graphics.DrawText(
            self.canvas,
            font,
            self.plane_position,
            PLANE_DISTANCE_FROM_TOP,
            colour,
            text,
        )

        # Advance scroll
        self.plane_position -= 1
        if self.plane_position + text_length < 0:
            self.plane_position = screen.WIDTH
            if len(self._data) > 1:
                self._data_index = (self._data_index + 1) % len(self._data)
                self._data_all_looped = (
                    (not self._data_index) or self._data_all_looped
                )
                self.reset_scene()

    @Animator.KeyFrame.add(0)
    def reset_scrolling(self):
        self.plane_position = screen.WIDTH

from utilities.animator import Animator
from setup import fonts, screen
from setup.themes import TC, THEME_BG, THEME_FLIGHT_ALPHA, THEME_FLIGHT_NUMERIC
from setup.themes import THEME_DIVIDING_BAR, THEME_DATA_INDEX

from rgbmatrix import graphics

BAR_STARTING_POSITION = (0, 18)
BAR_PADDING = 2

FLIGHT_NO_POSITION = (1, 21)
FLIGHT_NO_TEXT_HEIGHT = 8
FLIGHT_NO_FONT = fonts.small

DATA_INDEX_POSITION = (52, 21)
DATA_INDEX_TEXT_HEIGHT = 6
DATA_INDEX_FONT = fonts.extrasmall


class FlightDetailsScene(object):
    def __init__(self):
        super().__init__()

    @Animator.KeyFrame.add(0)
    def flight_details(self):
        if len(self._data) == 0:
            return

        # Clear the whole callsign/bar area
        self.draw_square(
            0,
            BAR_STARTING_POSITION[1] - (FLIGHT_NO_TEXT_HEIGHT // 2),
            screen.WIDTH - 1,
            BAR_STARTING_POSITION[1] + (FLIGHT_NO_TEXT_HEIGHT // 2),
            TC(THEME_BG),
        )

        # Draw flight number character by character (numeric / alpha colour split)
        flight_no_text_length = 0
        callsign = self._data[self._data_index].get("callsign", "")
        if callsign and callsign != "N/A":
            for ch in callsign:
                ch_length = graphics.DrawText(
                    self.canvas,
                    FLIGHT_NO_FONT,
                    FLIGHT_NO_POSITION[0] + flight_no_text_length,
                    FLIGHT_NO_POSITION[1],
                    TC(THEME_FLIGHT_NUMERIC) if ch.isnumeric() else TC(THEME_FLIGHT_ALPHA),
                    ch,
                )
                flight_no_text_length += ch_length

        # Dividing bar + optional N/M index
        if len(self._data) > 1:
            # Clear N/M area first
            self.draw_square(
                DATA_INDEX_POSITION[0] - BAR_PADDING,
                BAR_STARTING_POSITION[1] - (FLIGHT_NO_TEXT_HEIGHT // 2),
                screen.WIDTH,
                BAR_STARTING_POSITION[1] + (FLIGHT_NO_TEXT_HEIGHT // 2),
                TC(THEME_BG),
            )

            graphics.DrawLine(
                self.canvas,
                flight_no_text_length + BAR_PADDING,
                BAR_STARTING_POSITION[1],
                DATA_INDEX_POSITION[0] - BAR_PADDING - 1,
                BAR_STARTING_POSITION[1],
                TC(THEME_DIVIDING_BAR),
            )

            graphics.DrawText(
                self.canvas,
                DATA_INDEX_FONT,
                DATA_INDEX_POSITION[0],
                DATA_INDEX_POSITION[1],
                TC(THEME_DATA_INDEX),
                f"{self._data_index + 1}/{len(self._data)}",
            )
        else:
            graphics.DrawLine(
                self.canvas,
                flight_no_text_length + BAR_PADDING if flight_no_text_length else 0,
                BAR_STARTING_POSITION[1],
                screen.WIDTH,
                BAR_STARTING_POSITION[1],
                TC(THEME_DIVIDING_BAR),
            )

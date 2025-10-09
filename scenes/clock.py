from datetime import datetime

from utilities.animator import Animator
from setup import colours, fonts, frames

from rgbmatrix import graphics

# Setup
CLOCK_FONT = fonts.regular
CLOCK_POSITION = (1, 8)
CLOCK_COLOUR = colours.BLUE_DARK


class ClockScene(object):
    def __init__(self):
        super().__init__()
        self._last_time = None

    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def clock(self, count):
        if len(self._data) or self._reset_scene:
            # Ensure redraw when there's new data
            self._last_time = None

        else:
            # If there's no data to display
            # then draw a clock
            now = datetime.now()
            current_time = now.strftime("%H:%M")

            # Only draw if time needs updated
            if self._last_time != current_time:
                # Undraw last time if different from current
                if not self._last_time is None:
                    _ = graphics.DrawText(
                        self.canvas,
                        CLOCK_FONT,
                        CLOCK_POSITION[0],
                        CLOCK_POSITION[1],
                        colours.BLACK,
                        self._last_time,
                    )
                self._last_time = current_time

                # Draw Time
                _ = graphics.DrawText(
                    self.canvas,
                    CLOCK_FONT,
                    CLOCK_POSITION[0],
                    CLOCK_POSITION[1],
                    CLOCK_COLOUR,
                    current_time,
                )

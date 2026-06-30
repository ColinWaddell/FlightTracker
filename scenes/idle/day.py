from datetime import datetime

from utilities.animator import Animator
from setup import fonts, frames
from setup.themes import TC, THEME_CURRENT_DAY, THEME_BG
from setup.configuration import Config

from rgbmatrix import graphics

DAY_FONT = fonts.small
DAY_POSITION = (2, 23)


class DayScene(object):
    def __init__(self):
        super().__init__()
        self.last_day = None

    def now_local(self):
        return datetime.now()

    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def day(self, count):
        if len(self.data):
            self.last_day = None
            return

        current_day = self.now_local().strftime("%A")
        if self.last_day == current_day:
            return

        if self.last_day is not None:
            graphics.DrawText(
                self.canvas,
                DAY_FONT,
                DAY_POSITION[0],
                DAY_POSITION[1],
                TC(THEME_BG),
                self.last_day,
            )

        self.last_day = current_day
        graphics.DrawText(
            self.canvas,
            DAY_FONT,
            DAY_POSITION[0],
            DAY_POSITION[1],
            TC(THEME_CURRENT_DAY),
            current_day,
        )

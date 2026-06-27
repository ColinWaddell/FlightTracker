from datetime import datetime

import pytz

from utilities.animator import Animator
from setup import fonts, frames
from setup.themes import TC, THEME_CURRENT_DAY, THEME_BG
from setup.configuration import Config

from rgbmatrix import graphics

DAY_FONT     = fonts.small
DAY_POSITION = (2, 23)


class DayScene(object):
    def __init__(self):
        super().__init__()
        self._last_day = None

    def _now_local(self):
        cfg = Config.instance()
        try:
            tz = pytz.timezone(cfg.timezone)
        except Exception:
            tz = pytz.utc
        return datetime.now(tz)

    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def day(self, count):
        if len(self._data):
            self._last_day = None
            return

        current_day = self._now_local().strftime("%A")
        if self._last_day == current_day:
            return

        if self._last_day is not None:
            graphics.DrawText(self.canvas, DAY_FONT, DAY_POSITION[0], DAY_POSITION[1],
                              TC(THEME_BG), self._last_day)

        self._last_day = current_day
        graphics.DrawText(self.canvas, DAY_FONT, DAY_POSITION[0], DAY_POSITION[1],
                          TC(THEME_CURRENT_DAY), current_day)

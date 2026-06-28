from datetime import datetime

import pytz

from utilities.animator import Animator
from setup import fonts, frames
from setup.themes import TC, THEME_CURRENT_DATE, THEME_BG
from setup.configuration import Config

from rgbmatrix import graphics

DATE_FONT = fonts.small
DATE_POSITION = (1, 31)

_DATE_FORMATS = [
    "%Y-%m-%d",  # 0 = YYYY-MM-DD
    "%-d-%-m-%Y",  # 1 = DD-MM-YYYY
    "%-m-%-d-%Y",  # 2 = MM-DD-YYYY
]


class DateScene(object):
    def __init__(self):
        super().__init__()
        self._last_date = None

    def _now_local(self):
        cfg = Config.instance()
        try:
            tz = pytz.timezone(cfg.timezone)
        except Exception:
            tz = pytz.utc
        return datetime.now(tz)

    def _date_string(self) -> str:
        cfg = Config.instance()
        fmt = (
            _DATE_FORMATS[cfg.date_format]
            if cfg.date_format < len(_DATE_FORMATS)
            else _DATE_FORMATS[0]
        )
        return self._now_local().strftime(fmt)

    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def date(self, count):
        if len(self._data):
            self._last_date = None
            return

        current_date = self._date_string()
        if self._last_date == current_date:
            return

        if self._last_date is not None:
            graphics.DrawText(
                self.canvas,
                DATE_FONT,
                DATE_POSITION[0],
                DATE_POSITION[1],
                TC(THEME_BG),
                self._last_date,
            )

        self._last_date = current_date
        graphics.DrawText(
            self.canvas,
            DATE_FONT,
            DATE_POSITION[0],
            DATE_POSITION[1],
            TC(THEME_CURRENT_DATE),
            current_date,
        )

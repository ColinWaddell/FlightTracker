from datetime import datetime

from utilities.animator import Animator
from setup import fonts, frames
from setup.themes import TC, THEME_CURRENT_DATE, THEME_BG
from setup.configuration import Config

from rgbmatrix import graphics

DATE_FONT = fonts.small
DATE_POSITION = (1, 31)

DATE_FORMATS = [
    "%Y-%m-%d",  # 0 = YYYY-MM-DD
    "%-d-%-m-%Y",  # 1 = DD-MM-YYYY
    "%-m-%-d-%Y",  # 2 = MM-DD-YYYY
]


class DateScene(object):
    def __init__(self):
        super().__init__()
        self.last_date = None

    def now_local(self):
        return datetime.now()

    def date_string(self) -> str:
        cfg = Config.instance()
        fmt = (
            DATE_FORMATS[cfg.date_format]
            if cfg.date_format < len(DATE_FORMATS)
            else DATE_FORMATS[0]
        )
        return self.now_local().strftime(fmt)

    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def date(self, count):
        if len(self.data):
            self.last_date = None
            return

        current_date = self.date_string()
        if self.last_date == current_date:
            return

        if self.last_date is not None:
            graphics.DrawText(
                self.canvas,
                DATE_FONT,
                DATE_POSITION[0],
                DATE_POSITION[1],
                TC(THEME_BG),
                self.last_date,
            )

        self.last_date = current_date
        graphics.DrawText(
            self.canvas,
            DATE_FONT,
            DATE_POSITION[0],
            DATE_POSITION[1],
            TC(THEME_CURRENT_DATE),
            current_date,
        )

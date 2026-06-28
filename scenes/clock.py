from datetime import datetime

import pytz

from utilities.animator import Animator
from setup import fonts, frames
from setup.themes import TC, THEME_TIME, THEME_TIME_AMPM, THEME_BG
from setup.configuration import Config

from rgbmatrix import graphics

CLOCK_FONT = fonts.regular
CLOCK_AMPM_FONT = fonts.extrasmall
CLOCK_POSITION = (1, 8)
AMPM_POSITION = (44, 5)  # top-right, only shown in 12hr mode


class ClockScene(object):
    def __init__(self):
        super().__init__()
        self._last_time = None

    def _now_local(self):
        cfg = Config.instance()
        try:
            tz = pytz.timezone(cfg.timezone)
        except Exception:
            tz = pytz.utc
        return datetime.now(tz)

    def _time_string(self) -> tuple[str, str | None]:
        """Returns (time_str, ampm_str_or_None)."""
        cfg = Config.instance()
        now = self._now_local()
        if cfg.clock_24hr:
            return now.strftime("%H:%M"), None
        hour_str = now.strftime("%-I:%M")
        ampm_str = now.strftime("%p")
        return hour_str, ampm_str

    @Animator.KeyFrame.add(frames.PER_SECOND * 1)
    def clock(self, count):
        if len(self._data):
            self._last_time = None
            return

        time_str, ampm_str = self._time_string()
        current_time = time_str + (ampm_str or "")

        if self._last_time == current_time:
            return

        # Undraw old
        if self._last_time is not None:
            graphics.DrawText(
                self.canvas,
                CLOCK_FONT,
                CLOCK_POSITION[0],
                CLOCK_POSITION[1],
                TC(THEME_BG),
                self._last_time[:5],
            )  # just the HH:MM part
            if ampm_str:
                graphics.DrawText(
                    self.canvas,
                    CLOCK_AMPM_FONT,
                    AMPM_POSITION[0],
                    AMPM_POSITION[1],
                    TC(THEME_BG),
                    "AM" if "AM" in self._last_time else "PM",
                )

        self._last_time = current_time

        # Draw new
        graphics.DrawText(
            self.canvas,
            CLOCK_FONT,
            CLOCK_POSITION[0],
            CLOCK_POSITION[1],
            TC(THEME_TIME),
            time_str,
        )
        if ampm_str:
            graphics.DrawText(
                self.canvas,
                CLOCK_AMPM_FONT,
                AMPM_POSITION[0],
                AMPM_POSITION[1],
                TC(THEME_TIME_AMPM),
                ampm_str,
            )

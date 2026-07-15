"""
ForecastIdleTheme - placeholder for a future weather-forecast-themed idle screen.

Will display a detailed weather forecast layout.  For now, a minimal stub
that inherits the scene protocol from BaseIdleScene.
"""

from __future__ import annotations

from scenes.idle.idle_scene import BaseIdleScene


class ForecastIdleTheme(BaseIdleScene):
    """Forecast idle layout - stub for future implementation."""

    def theme_init(self) -> None:
        pass

    def theme_reset(self) -> None:
        pass

    def draw_content(self, count: int) -> None:
        # TODO: implement forecast display
        pass

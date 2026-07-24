"""
IdleScene - priority-0 fallback scene with pluggable themes.

Reads cfg.idle_screen_theme and instantiates the appropriate theme
subclass.  BaseIdleScene provides the shared scene-protocol boilerplate
(priority, has_data, active, on_enter, reset, frame-throttled draw);
each theme implements draw_content() with its own layout.

WeatherService (a singleton daemon thread in theme_utilities.py) is
started lazily and shared by all themes.
"""

from __future__ import annotations

from scenes.idle.themes.theme_utilities import WeatherService
from setup import frames
from setup.configuration import Config

PRIORITY = 0


class BaseIdleScene:
    """
    Base class for all idle screen themes.

    Provides the scene protocol expected by SceneManager:
        priority, poll(), has_data(), active(), on_enter(), reset(), draw()

    Subclasses implement:
        theme_init()        - set up theme-specific state (called from __init__)
        theme_reset()       - clear theme-specific state (called from reset())
        draw_content(count) - render one second's worth of content
    """

    priority = PRIORITY

    def __init__(self, canvas, panel):
        self.canvas = canvas
        self.panel = panel

        # Scene frame counter
        self.frame: int = 0

        # Shared weather service (singleton daemon thread)
        self.weather = WeatherService.instance()

        # Let the theme initialise its own state
        self.theme_init()

    # ------------------------------------------------------------------
    # Scene protocol
    # ------------------------------------------------------------------

    def poll(self) -> None:
        pass  # weather is handled by the background WeatherService thread

    def has_data(self) -> bool:
        return True  # always the guaranteed fallback

    def active(self) -> bool:
        return True  # never interrupted mid-draw

    def on_enter(self) -> None:
        """Called by SceneManager on scene transition. Clears canvas then resets."""
        self.panel.clear(self.canvas)
        self.reset()

    def reset(self) -> None:
        """Clear cached draw state so everything redraws on next tick."""
        self.frame = 0
        self.theme_reset()

    def draw(self) -> None:
        """Called every frame. Throttles to ~1 fps, then calls draw_content()."""
        self.frame += 1
        if self.frame % int(frames.PER_SECOND):
            return

        count = self.frame // int(frames.PER_SECOND)
        self.draw_content(count)

    # ------------------------------------------------------------------
    # Hooks for subclasses
    # ------------------------------------------------------------------

    def theme_init(self) -> None:
        """Override to set up theme-specific state."""
        pass

    def theme_reset(self) -> None:
        """Override to clear theme-specific state."""
        pass

    def draw_content(self, count: int) -> None:
        """Override to render content. Called once per second."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Theme registry - maps config string to theme class.
# Imports are deferred to avoid circular dependencies (themes import
# BaseIdleScene from this module).
# ---------------------------------------------------------------------------


def _load_themes() -> dict:
    """Lazy-load theme classes to avoid circular imports."""
    from scenes.idle.themes.classic_idle_theme import ClassicIdleTheme
    from scenes.idle.themes.conditions_idle_theme import ConditionsIdleTheme
    from scenes.idle.themes.forecast_idle_theme import ForecastIdleTheme

    return {
        "classic": ClassicIdleTheme,
        "forecast": ForecastIdleTheme,
        "conditions": ConditionsIdleTheme,
    }


def IdleScene(canvas, panel):
    """
    Factory that returns the idle scene theme selected by config.

    Reads cfg.idle_screen_theme and instantiates the matching theme
    subclass.  Unknown theme names fall back to 'classic'.
    """
    cfg = Config.instance()
    themes = _load_themes()
    theme_class = themes.get(cfg.idle_screen_theme, themes["classic"])
    return theme_class(canvas, panel)

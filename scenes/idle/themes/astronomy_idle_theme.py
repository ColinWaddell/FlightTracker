"""
AstronomyIdleTheme - placeholder for a future astronomy-themed idle screen.

Will display celestial information (moon phase, visible planets, etc.).
For now, a minimal stub that inherits the scene protocol from BaseIdleScene.
"""

from __future__ import annotations

from scenes.idle.idle_scene import BaseIdleScene


class AstronomyIdleTheme(BaseIdleScene):
    """Astronomy idle layout - stub for future implementation."""

    def theme_init(self) -> None:
        pass

    def theme_reset(self) -> None:
        pass

    def draw_content(self, count: int) -> None:
        # TODO: implement astronomy display (moon phase, planets, etc.)
        pass

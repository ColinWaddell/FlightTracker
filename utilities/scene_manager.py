"""
SceneManager — pure scene dispatch engine.

Mirrors the C++ SceneManager in DotboxClient exactly: registration and
kick() only.  No timing, no brightness, no data fetching — those belong
in the main loop (Display.run()).

Each scene must implement:
    priority    int     Higher value = higher priority.
    has_data()  bool    Scene has something to show right now.
    active()    bool    Scene is mid-presentation; prevent preemption.
    draw()      None    Render one frame. Scene owns its own frame counter.
    reset()     None    Internal state reset (e.g. carousel advance). No canvas clear.
    on_enter()  None    Called by SceneManager on scene transition. Clears canvas + resets.
"""

from __future__ import annotations


class SceneManager:
    """
    Priority-based scene dispatcher.

    Scenes are sorted by priority ascending so that index 0 is always the
    lowest-priority fallback (matching the C++ layout where scenes[0] is
    the always-on weather/idle scene).

    kick() logic (mirrors scene_manager.cpp):
      1. Search all non-fallback scenes for the highest-priority one that
         has_data() and the highest-priority one that is active().
      2. If the has_data scene outranks the active scene → reset + draw it.
      3. Else if something is active → keep drawing it.
      4. Else → fall back to scenes[0], resetting if we just arrived here.
    """

    def __init__(self):
        self._scenes: list = []
        self._current = None

    def register(self, scene) -> None:
        """Register a scene. Kept sorted lowest→highest priority so index 0
        is the fallback, matching the C++ array layout."""
        self._scenes.append(scene)
        self._scenes.sort(key=lambda s: s.priority)

    def kick(self) -> None:
        if not self._scenes:
            return

        for scene in self._scenes:
            scene.poll()

        fallback = self._scenes[0]
        non_fallback = self._scenes[1:]

        highest_with_data = None
        highest_active = None

        for scene in reversed(non_fallback):  # highest priority first
            if highest_with_data is None and scene.has_data():
                highest_with_data = scene
            if highest_active is None and scene.active():
                highest_active = scene
            if highest_with_data and highest_active:
                break

        # Determine winner
        if highest_with_data and (
            highest_active is None
            or highest_with_data.priority > highest_active.priority
        ):
            if highest_with_data is not self._current:
                highest_with_data.on_enter()
                self._current = highest_with_data
        elif highest_active:
            self._current = highest_active
        else:
            if self._current is not fallback:
                fallback.on_enter()
                self._current = fallback

        self._current.draw()

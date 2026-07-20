"""Shared lightning-flash mixin for thunder-style animations.

Provides the random lightning bolt flash logic used by ``thunder.py``,
``thunder_rain.py``, and ``thunder_snow.py``.  The mixin manages a
single ``_Flash`` event: a randomly-chosen bolt shape at a random
horizontal position, drawn at full brightness for a few frames then
fading through an afterglow before going dark.

Precipitation animations that mix in ``ThunderMixin`` should:
    1. Call ``_thunder_init()`` from their ``__init__`` (after ``super``).
    2. Call ``_thunder_active_pixels()`` to get the set of bolt pixels
       that are currently lit, so precipitation can skip clearing or
       drawing over them during a flash.
    3. Call ``_thunder_tick()`` *after* their own precipitation draw to
       advance the flash state machine and draw/clear the bolt.

The bounding box is shared with the precipitation animations:
    top-left     [3, 11]
    bottom-right [11, 14]
"""

from __future__ import annotations

import random

# Bounding box for the lightning (local coordinates, shared with rain).
_BOX_LEFT = 3
_BOX_RIGHT = 11      # inclusive
_BOX_TOP = 11
_BOX_BOTTOM = 14     # inclusive

# Bolt variants — each is a 3-column-wide zigzag spanning all 4 rows.
# Coordinates are relative to the bolt's top-left corner.
_BOLTS = [
    # Variant A: zigzag right then left
    [(1, 0), (1, 1), (2, 2), (0, 3)],
    # Variant B: zigzag left then right
    [(1, 0), (1, 1), (0, 2), (2, 3)],
    # Variant C: diagonal right then straight
    [(0, 0), (1, 1), (1, 2), (1, 3)],
    # Variant D: diagonal left then straight
    [(2, 0), (1, 1), (1, 2), (1, 3)],
    # Variant E: S-curve
    [(0, 0), (1, 1), (0, 2), (1, 3)],
    # Variant F: S-curve mirror
    [(2, 0), (1, 1), (2, 2), (1, 3)],
]

# Bolt is 3 columns wide (x offsets 0–2), so the left-edge x can range
# from _BOX_LEFT to _BOX_RIGHT - 2.
_X_OFFSETS = list(range(_BOX_LEFT, _BOX_RIGHT - 1))

# Per-frame probability of starting a new flash.
_FLASH_CHANCE = {
    0: 0.04,   # light:  ~1 flash every 2 s
    1: 0.07,   # medium: ~1 flash every 1 s
    2: 0.12,   # heavy:  ~1 flash every 0.6 s
}

# Bolt colour (yellow-white) per intensity.
_COLOURS = {
    0: (200, 200, 120),
    1: (230, 230, 150),
    2: (255, 255, 180),
}

# Afterglow brightness as a fraction of the bolt colour.
_AFTERGLOW = 0.5

# Flash timing: 3 frames full, 2 frames afterglow, then dark.
_FLASH_FULL = 3
_FLASH_AFTERGLOW = 2
_FLASH_TOTAL = _FLASH_FULL + _FLASH_AFTERGLOW


class _Flash:
    """A single lightning flash event."""

    __slots__ = ("bolt", "x_offset", "timer")

    def __init__(self, bolt: list[tuple[int, int]], x_offset: int) -> None:
        self.bolt = bolt
        self.x_offset = x_offset
        self.timer = 0


class ThunderMixin:
    """Mixin providing random lightning flashes for thunder animations.

    Expects to be combined with ``BaseAnimation`` (for ``set_pixel`` and
    ``self.intensity``).
    """

    # ------------------------------------------------------------------
    # Initialisation — call from the subclass __init__
    # ------------------------------------------------------------------

    def _thunder_init(self) -> None:
        """Set up lightning state.  Call after ``super().__init__``."""
        self._flash_chance: float = _FLASH_CHANCE.get(
            self.intensity, _FLASH_CHANCE[1]
        )
        self._thunder_colour: tuple[int, int, int] = _COLOURS.get(
            self.intensity, _COLOURS[1]
        )
        # No active flash at start — the box begins dark.
        self._flash: _Flash | None = None

    # ------------------------------------------------------------------
    # Pixel helpers
    # ------------------------------------------------------------------

    def _bolt_pixels(self, flash: _Flash) -> list[tuple[int, int]]:
        """Return absolute local pixel coords for the flash's bolt."""
        return [
            (flash.x_offset + dx, _BOX_TOP + dy)
            for dx, dy in flash.bolt
        ]

    def _draw_bolt(self, flash: _Flash, r: int, g: int, b: int) -> None:
        for px, py in self._bolt_pixels(flash):
            self.set_pixel(px, py, r, g, b)

    def _clear_bolt(self, flash: _Flash) -> None:
        for px, py in self._bolt_pixels(flash):
            self.set_pixel(px, py, 0, 0, 0)

    # ------------------------------------------------------------------
    # Public API for precipitation layers
    # ------------------------------------------------------------------

    def _thunder_active_pixels(self) -> set[tuple[int, int]]:
        """Return the set of bolt pixels currently lit.

        Precipitation layers should skip clearing or drawing over these
        pixels so the bolt stays visible during a flash.
        """
        if self._flash is None or self._flash.timer >= _FLASH_TOTAL:
            return set()
        return set(self._bolt_pixels(self._flash))

    # ------------------------------------------------------------------
    # Per-frame tick — call *after* the precipitation draw
    # ------------------------------------------------------------------

    def _thunder_tick(self) -> None:
        """Advance the flash state machine and draw/clear the bolt.

        Call at the end of ``draw()``, after precipitation has been
        rendered.  This ensures the bolt is drawn on top of any drops
        or flakes that may occupy the same pixels.
        """
        if self._flash is not None:
            flash = self._flash
            r, g, b = self._thunder_colour

            if flash.timer < _FLASH_FULL:
                # Full brightness
                self._draw_bolt(flash, r, g, b)
            elif flash.timer < _FLASH_TOTAL:
                # Afterglow — dimmer
                ar = int(r * _AFTERGLOW)
                ag = int(g * _AFTERGLOW)
                ab = int(b * _AFTERGLOW)
                self._draw_bolt(flash, ar, ag, ab)
            else:
                # Flash ended — clear and reset
                self._clear_bolt(flash)
                self._flash = None

            if self._flash is not None:
                flash.timer += 1

        # Maybe start a new flash (only when the box is dark)
        if self._flash is None and random.random() < self._flash_chance:
            bolt = random.choice(_BOLTS)
            x_offset = random.choice(_X_OFFSETS)
            self._flash = _Flash(bolt, x_offset)
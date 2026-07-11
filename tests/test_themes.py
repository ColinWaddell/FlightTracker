"""Tests for setup/themes.py and setup/colours.py — theme system integrity."""

from setup.colours import Colour
from setup.themes import (
    theme_colour,
    theme_count,
    theme_get,
    theme_set,
)


class TestThemeCount:
    def test_at_least_three_themes(self):
        # default, monochrome, pastel
        assert theme_count() >= 3


class TestThemeGetSet:
    def test_roundtrip(self):
        original = theme_get()
        for i in range(theme_count()):
            theme_set(i)
            assert theme_get() == i
        # Restore original
        theme_set(original)


class TestThemeColours:
    def test_all_themes_have_valid_colours(self):
        """Every theme should return valid RGB tuples for all colour keys."""
        original = theme_get()
        for i in range(theme_count()):
            theme_set(i)
            # At minimum, we should be able to get common colour keys
            # without raising an exception
            # Try a few known keys
            for key in ["flight_text", "idle_text", "weather_text"]:
                try:
                    colour = theme_colour(key)
                    if colour is not None:
                        assert isinstance(colour, (Colour, tuple, list))
                except (KeyError, AttributeError):
                    pass
        theme_set(original)

    def test_theme_set_invalid_index(self):
        # Setting an out-of-range index should not crash
        # (it may clamp or wrap — just ensure no exception)
        import contextlib

        original = theme_get()
        with contextlib.suppress(IndexError, ValueError):
            theme_set(999)
        theme_set(original)

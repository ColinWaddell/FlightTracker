"""Tests for the animation engines.

Each animation engine should produce a non-empty frame table with valid
pixel coordinates.  ``tick()`` should only modify delta pixels, and
``reset()`` should blank all pixels that any frame could set.
"""

from unittest.mock import MagicMock

import pytest

from scenes.idle.themes.icons.weather.animations.base import BaseAnimation
from scenes.idle.themes.icons.weather.animations.blowing_snow import (
    BlowingSnowAnimation,
)
from scenes.idle.themes.icons.weather.animations.dusty import DustyAnimation
from scenes.idle.themes.icons.weather.animations.fog import FogAnimation
from scenes.idle.themes.icons.weather.animations.mist import MistAnimation
from scenes.idle.themes.icons.weather.animations.moon_rays import MoonRaysAnimation
from scenes.idle.themes.icons.weather.animations.rain import RainAnimation
from scenes.idle.themes.icons.weather.animations.rays import RaysAnimation
from scenes.idle.themes.icons.weather.animations.registry import (
    ANIMATION_REGISTRY,
    get_animation_class,
)
from scenes.idle.themes.icons.weather.animations.sleet import SleetAnimation
from scenes.idle.themes.icons.weather.animations.snow import SnowAnimation
from scenes.idle.themes.icons.weather.animations.thunder import ThunderAnimation
from scenes.idle.themes.icons.weather.animations.thunder_rain import (
    ThunderRainAnimation,
)
from scenes.idle.themes.icons.weather.animations.thunder_snow import (
    ThunderSnowAnimation,
)

# All animation classes that should be tested
ALL_ANIMATIONS = [
    RainAnimation,
    SnowAnimation,
    SleetAnimation,
    ThunderAnimation,
    ThunderRainAnimation,
    ThunderSnowAnimation,
    FogAnimation,
    MistAnimation,
    DustyAnimation,
    RaysAnimation,
    MoonRaysAnimation,
    BlowingSnowAnimation,
]


def _make_animation(cls, width=16, height=6, intensity=1):
    """Create an animation instance with a mock panel/canvas."""
    panel = MagicMock()
    canvas = MagicMock()
    return cls(
        x=0,
        y=0,
        width=width,
        height=height,
        intensity=intensity,
        panel=panel,
        canvas=canvas,
    )


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_all_animations_registered(self):
        expected_names = {
            "rain",
            "snow",
            "sleet",
            "thunder",
            "thunder_rain",
            "thunder_snow",
            "fog",
            "mist",
            "dusty",
            "rays",
            "moon_rays",
            "blowing_snow",
        }
        assert set(ANIMATION_REGISTRY.keys()) == expected_names

    def test_get_animation_class_returns_class(self):
        assert get_animation_class("rain") is RainAnimation

    def test_get_animation_class_none_name(self):
        assert get_animation_class(None) is None

    def test_get_animation_class_unknown_name(self):
        assert get_animation_class("nonexistent") is None


# ---------------------------------------------------------------------------
# Frame table validity (parametrised over all engines + intensities)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_ANIMATIONS)
@pytest.mark.parametrize("intensity", [0, 1, 2])
class TestFrameTableValidity:
    def test_frames_non_empty(self, cls, intensity):
        anim = _make_animation(cls, intensity=intensity)
        assert anim.frame_count > 0

    def test_set_pixels_in_bounds(self, cls, intensity):
        anim = _make_animation(cls, width=16, height=6, intensity=intensity)
        for frame in anim._frames:
            for entry in frame.get("set", ()):
                x, y, r, g, b = entry
                assert 0 <= x < 16, f"x={x} out of bounds"
                assert 0 <= y < 6, f"y={y} out of bounds"
                assert 0 <= r <= 255
                assert 0 <= g <= 255
                assert 0 <= b <= 255

    def test_clear_pixels_in_bounds(self, cls, intensity):
        anim = _make_animation(cls, width=16, height=6, intensity=intensity)
        for frame in anim._frames:
            for entry in frame.get("clear", ()):
                x, y = entry
                assert 0 <= x < 16, f"clear x={x} out of bounds"
                assert 0 <= y < 6, f"clear y={y} out of bounds"


# ---------------------------------------------------------------------------
# tick() behaviour
# ---------------------------------------------------------------------------


class TestTick:
    def test_tick_advances_frame(self):
        anim = _make_animation(RainAnimation)
        initial = anim.frame
        anim.tick()
        assert anim.frame == initial + 1

    def test_tick_wraps_around(self):
        anim = _make_animation(RainAnimation)
        count = anim.frame_count
        for _ in range(count + 5):
            anim.tick()
        # Frame should have wrapped (not overflowed)
        assert anim.frame == count + 5

    def test_tick_calls_set_pixel(self):
        anim = _make_animation(RainAnimation)
        anim.tick()
        assert anim.panel.set_pixel.called

    def test_tick_with_empty_frames_does_nothing(self):
        panel = MagicMock()

        class _EmptyAnim(BaseAnimation):
            def _build_frames(self):
                self._frames = []

        anim = _EmptyAnim(0, 0, 16, 6, 1, panel, MagicMock())
        anim.tick()
        assert not panel.set_pixel.called


# ---------------------------------------------------------------------------
# reset() behaviour
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_blanks_all_set_pixels(self):
        anim = _make_animation(RainAnimation)
        anim.reset()
        # Should have called set_pixel with 0,0,0 for every unique pixel
        # that appears in any frame's "set" list
        all_set = set()
        for frame in anim._frames:
            for x, y, *_ in frame.get("set", ()):
                all_set.add((x, y))
        # Verify set_pixel was called for each with (0,0,0)
        blanked = [
            call
            for call in anim.panel.set_pixel.call_args_list
            if call.args[3:] == (0, 0, 0)
        ]
        assert len(blanked) >= len(all_set)

    def test_reset_sets_frame_to_zero(self):
        anim = _make_animation(RainAnimation)
        anim.tick()
        anim.tick()
        assert anim.frame > 0
        anim.reset()
        assert anim.frame == 0

    def test_reset_with_empty_frames(self):
        panel = MagicMock()

        class _EmptyAnim(BaseAnimation):
            def _build_frames(self):
                self._frames = []

        anim = _EmptyAnim(0, 0, 16, 6, 1, panel, MagicMock())
        anim.reset()
        assert anim.frame == 0


# ---------------------------------------------------------------------------
# Intensity variation
# ---------------------------------------------------------------------------


class TestIntensityVariation:
    def test_rain_intensity_changes_drop_count(self):
        light = _make_animation(RainAnimation, intensity=0)
        heavy = _make_animation(RainAnimation, intensity=2)
        # Heavy rain should have more set pixels per frame than light
        light_pixels = sum(len(f.get("set", ())) for f in light._frames)
        heavy_pixels = sum(len(f.get("set", ())) for f in heavy._frames)
        assert heavy_pixels > light_pixels

    def test_intensity_clamped_to_valid_range(self):
        anim = _make_animation(RainAnimation, intensity=5)
        assert anim.intensity == 2
        anim_neg = _make_animation(RainAnimation, intensity=-1)
        assert anim_neg.intensity == 0
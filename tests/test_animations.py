"""Tests for the live-draw weather animation engines.

Each engine implements ``draw(frame_idx)``, called every frame by
``tick()``.  The base class does no automatic restoration — engines are
responsible for clearing pixels they no longer want.  These tests mock
the panel and assert on the ``set_pixel`` / ``draw_*`` calls that
``tick()`` produces.
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


def _make_animation(cls, width=15, height=15, intensity=1):
    """Create an animation instance with a mock panel/canvas.

    The default area matches the real sprite size (15x15).  An
    all-black ``original`` grid is supplied so engines that query
    ``original_pixel()`` get black outside the (absent) icon.
    """
    panel = MagicMock()
    canvas = MagicMock()
    original = [[(0, 0, 0)] * width for _ in range(height)]
    return cls(
        x=0,
        y=0,
        width=width,
        height=height,
        intensity=intensity,
        panel=panel,
        canvas=canvas,
        original=original,
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
# tick() behaviour
# ---------------------------------------------------------------------------


class TestTick:
    def test_tick_advances_frame(self):
        anim = _make_animation(RainAnimation)
        initial = anim.frame
        anim.tick()
        assert anim.frame == initial + 1

    def test_tick_calls_set_pixel(self):
        anim = _make_animation(RainAnimation)
        anim.tick()
        assert anim.panel.set_pixel.called

    def test_tick_with_no_draw_does_nothing(self):
        panel = MagicMock()

        class _EmptyAnim(BaseAnimation):
            def draw(self, frame_idx):
                pass

        anim = _EmptyAnim(0, 0, 15, 15, 1, panel, MagicMock())
        anim.tick()
        assert not panel.set_pixel.called


# ---------------------------------------------------------------------------
# Bounds checking (parametrised over all engines + intensities)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_ANIMATIONS)
@pytest.mark.parametrize("intensity", [0, 1, 2])
class TestBounds:
    def test_set_pixels_in_bounds(self, cls, intensity):
        anim = _make_animation(cls, intensity=intensity)
        # Tick a few frames to exercise the draw path.
        for _ in range(5):
            anim.tick()
        for call in anim.panel.set_pixel.call_args_list:
            # set_pixel(canvas, x, y, r, g, b)
            _, x, y, r, g, b = call.args
            assert 0 <= x < 15, f"x={x} out of bounds"
            assert 0 <= y < 15, f"y={y} out of bounds"
            assert 0 <= r <= 255
            assert 0 <= g <= 255
            assert 0 <= b <= 255


# ---------------------------------------------------------------------------
# reset() behaviour
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_sets_frame_to_zero(self):
        anim = _make_animation(RainAnimation)
        anim.tick()
        anim.tick()
        assert anim.frame > 0
        anim.reset()
        assert anim.frame == 0

    def test_reset_does_not_touch_canvas(self):
        # The base reset() does not blank the canvas — the caller is
        # responsible for blanking the area at teardown.
        anim = _make_animation(RainAnimation)
        anim.tick()
        anim.panel.reset_mock()
        anim.reset()
        assert not anim.panel.set_pixel.called


# ---------------------------------------------------------------------------
# Original-pixel lookup
# ---------------------------------------------------------------------------


class TestOriginalPixel:
    def _make_with_original(self, original):
        panel = MagicMock()
        canvas = MagicMock()
        h = len(original)
        w = len(original[0]) if h else 0
        return RainAnimation(
            x=0,
            y=0,
            width=w,
            height=h,
            intensity=1,
            panel=panel,
            canvas=canvas,
            original=original,
        )

    def test_original_pixel_returns_cached_value(self):
        original = [[(10, 20, 30)] * 15 for _ in range(15)]
        anim = self._make_with_original(original)
        assert anim.original_pixel(0, 0) == (10, 20, 30)
        assert anim.original_pixel(14, 14) == (10, 20, 30)

    def test_original_pixel_out_of_bounds_is_black(self):
        anim = self._make_with_original([[(0, 0, 0)] * 15 for _ in range(15)])
        assert anim.original_pixel(-1, 0) == (0, 0, 0)
        assert anim.original_pixel(0, 99) == (0, 0, 0)

    def test_engine_can_restore_icon_pixel(self):
        # An engine that overwrites an icon pixel can restore it via
        # original_pixel().  Verify the helper returns the cached colour.
        original = [[(100, 150, 200)] * 15 for _ in range(15)]
        anim = self._make_with_original(original)
        r, g, b = anim.original_pixel(7, 7)
        assert (r, g, b) == (100, 150, 200)


# ---------------------------------------------------------------------------
# Drawing helpers (local-coordinate wrappers)
# ---------------------------------------------------------------------------


class TestDrawingHelpers:
    def test_set_pixel_applies_offset(self):
        anim = _make_animation(RainAnimation, width=15, height=15)
        anim.x, anim.y = 10, 20
        anim.set_pixel(3, 4, 1, 2, 3)
        anim.panel.set_pixel.assert_called_once_with(anim.canvas, 13, 24, 1, 2, 3)

    def test_draw_line_applies_offset(self):
        anim = _make_animation(RainAnimation)
        anim.x, anim.y = 5, 6
        colour = anim.make_colour(1, 2, 3)
        anim.draw_line(0, 0, 3, 4, colour)
        anim.panel.draw_line.assert_called_once_with(anim.canvas, 5, 6, 8, 10, colour)

    def test_draw_circle_applies_offset(self):
        anim = _make_animation(RainAnimation)
        anim.x, anim.y = 5, 6
        colour = anim.make_colour(1, 2, 3)
        anim.draw_circle(7, 8, 2, colour)
        anim.panel.draw_circle.assert_called_once_with(anim.canvas, 12, 14, 2, colour)

    def test_draw_square_applies_offset(self):
        anim = _make_animation(RainAnimation)
        anim.x, anim.y = 5, 6
        colour = anim.make_colour(1, 2, 3)
        anim.draw_square(0, 0, 3, 4, colour)
        anim.panel.draw_square.assert_called_once_with(anim.canvas, 5, 6, 8, 10, colour)


# ---------------------------------------------------------------------------
# Intensity variation
# ---------------------------------------------------------------------------


class TestIntensityVariation:
    def test_rain_intensity_changes_drop_count(self):
        light = _make_animation(RainAnimation, intensity=0)
        heavy = _make_animation(RainAnimation, intensity=2)
        light.panel.reset_mock()
        heavy.panel.reset_mock()
        light.tick()
        heavy.tick()
        # Heavy rain should set more pixels per frame than light.
        light_pixels = len(light.panel.set_pixel.call_args_list)
        heavy_pixels = len(heavy.panel.set_pixel.call_args_list)
        assert heavy_pixels > light_pixels

    def test_intensity_clamped_to_valid_range(self):
        anim = _make_animation(RainAnimation, intensity=5)
        assert anim.intensity == 2
        anim_neg = _make_animation(RainAnimation, intensity=-1)
        assert anim_neg.intensity == 0

    def test_intensity_clamped_to_valid_range(self):
        anim = _make_animation(RainAnimation, intensity=5)
        assert anim.intensity == 2
        anim_neg = _make_animation(RainAnimation, intensity=-1)
        assert anim_neg.intensity == 0

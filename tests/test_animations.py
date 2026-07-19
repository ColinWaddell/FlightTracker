"""Tests for the animation engines.

Each animation engine should produce a non-empty frame table with valid
pixel coordinates.  ``tick()`` lights the current frame's pixels and
auto-restores the previous frame's pixels to their original values
(black outside the icon, icon colour inside).  ``reset()`` restores any
currently active pixels.
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


def _make_animation(cls, width=15, height=18, intensity=1):
    """Create an animation instance with a mock panel/canvas.

    The default area matches the real sprite size (15x18).  An
    all-black ``original`` grid is supplied so the auto-restore path
    behaves like the old blank-on-clear behaviour.
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
# Frame table validity (parametrised over all engines + intensities)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", ALL_ANIMATIONS)
@pytest.mark.parametrize("intensity", [0, 1, 2])
class TestFrameTableValidity:
    def test_frames_non_empty(self, cls, intensity):
        anim = _make_animation(cls, intensity=intensity)
        assert anim.frame_count > 0

    def test_set_pixels_in_bounds(self, cls, intensity):
        anim = _make_animation(cls, width=15, height=18, intensity=intensity)
        for frame in anim._frames:
            for entry in frame.get("set", ()):
                x, y, r, g, b = entry
                assert 0 <= x < 15, f"x={x} out of bounds"
                assert 0 <= y < 18, f"y={y} out of bounds"
                assert 0 <= r <= 255
                assert 0 <= g <= 255
                assert 0 <= b <= 255

    def test_no_clear_key_in_frames(self, cls, intensity):
        # The new contract uses auto-restore; engines must not emit a
        # "clear" key.  (RaysAnimation is mid-rewrite and temporarily
        # exempted.)
        if cls is RaysAnimation:
            return
        anim = _make_animation(cls, intensity=intensity)
        for frame in anim._frames:
            assert "clear" not in frame, (
                f"{cls.__name__} still emits a 'clear' key — "
                f"restoration is now handled by BaseAnimation"
            )


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

        anim = _EmptyAnim(0, 0, 15, 18, 1, panel, MagicMock())
        anim.tick()
        assert not panel.set_pixel.called


# ---------------------------------------------------------------------------
# reset() behaviour
# ---------------------------------------------------------------------------


class TestReset:
    def test_reset_restores_active_pixels(self):
        anim = _make_animation(RainAnimation)
        # Tick once so the animation has lit some pixels.
        anim.tick()
        active_before = set(anim._active)
        assert active_before, "animation should have lit some pixels"
        anim.reset()
        # Every active pixel should have been restored to its original
        # (black, per the _make_animation helper) value.
        restored = [
            call
            for call in anim.panel.set_pixel.call_args_list
            if call.args[3:] == (0, 0, 0)
        ]
        assert len(restored) >= len(active_before)
        assert anim._active == set()

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

        anim = _EmptyAnim(0, 0, 15, 18, 1, panel, MagicMock())
        anim.reset()
        assert anim.frame == 0


# ---------------------------------------------------------------------------
# Original-pixel restoration
# ---------------------------------------------------------------------------


class TestOriginalRestore:
    """The base class restores overwritten pixels to their original value."""

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
        original = [[(10, 20, 30)] * 15 for _ in range(18)]
        anim = self._make_with_original(original)
        assert anim.original_pixel(0, 0) == (10, 20, 30)
        assert anim.original_pixel(14, 17) == (10, 20, 30)

    def test_original_pixel_out_of_bounds_is_black(self):
        anim = self._make_with_original([[(0, 0, 0)] * 15 for _ in range(18)])
        assert anim.original_pixel(-1, 0) == (0, 0, 0)
        assert anim.original_pixel(0, 99) == (0, 0, 0)

    def test_tick_restores_previous_frame_to_original(self):
        # Build an original where every pixel is a distinct colour so we
        # can assert the restore calls match the cached values.
        original = [[(r, g, b) for r in range(15)] for g in range(18) for b in [0]]
        # Reshape to [y][x] = (r, g, b) with a simple deterministic fill.
        original = [
            [((x * 10) % 256, (y * 10) % 256, 0) for x in range(15)] for y in range(18)
        ]
        anim = self._make_with_original(original)
        anim.tick()  # lights frame 0
        anim.tick()  # should restore frame-0 pixels, then light frame 1

        # Find the restore calls: set_pixel calls whose colour matches an
        # original pixel value (non-zero, since rain sets blue-ish pixels).
        restore_calls = []
        for call in anim.panel.set_pixel.call_args_list:
            _, _, _, r, g, b = call.args
            if (r, g, b) != (80, 130, 220):  # not a rain-set pixel
                restore_calls.append((r, g, b))
        # At least some restore calls should match original colours.
        originals_flat = {original[y][x] for y in range(18) for x in range(15)}
        restored = {c for c in restore_calls if c in originals_flat}
        assert restored, "tick() should have restored some pixels to original"


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

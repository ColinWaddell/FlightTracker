"""Tests for the ForecastSprite class."""

from unittest.mock import MagicMock

from scenes.idle.themes.icons.weather.forecast_sprite import (
    ANIMATION_HEIGHT,
    ICON_HEIGHT,
    ICON_OFFSET_Y,
    SPRITE_HEIGHT,
    SPRITE_WIDTH,
    ForecastSprite,
)


def _make_panel_and_canvas():
    """Return (panel, canvas) mocks suitable for sprite tests."""
    panel = MagicMock()
    canvas = MagicMock()
    return panel, canvas


class TestSpriteDimensions:
    def test_sprite_width(self):
        assert SPRITE_WIDTH == 15

    def test_sprite_height(self):
        assert SPRITE_HEIGHT == 18

    def test_icon_height(self):
        assert ICON_HEIGHT == 12

    def test_icon_offset_y(self):
        assert ICON_OFFSET_Y == 3

    def test_animation_height(self):
        # The animation now occupies the full sprite area.
        assert ANIMATION_HEIGHT == SPRITE_HEIGHT

    def test_icon_fits_within_sprite(self):
        assert ICON_OFFSET_Y + ICON_HEIGHT <= SPRITE_HEIGHT


class TestSpriteCreation:
    def test_creates_sprite_with_icon_and_animation(self):
        panel, canvas = _make_panel_and_canvas()
        sprite = ForecastSprite(
            canvas=canvas,
            panel=panel,
            x=0,
            y=0,
            icon_name="cloud",
            animation_name="rain",
            intensity=1,
            is_day=True,
        )
        assert sprite.icon_name == "cloud"
        assert sprite.animation_name == "rain"
        assert sprite.animation is not None
        assert sprite.frame == 0

    def test_creates_sprite_with_no_animation(self):
        panel, canvas = _make_panel_and_canvas()
        sprite = ForecastSprite(
            canvas=canvas,
            panel=panel,
            x=0,
            y=0,
            icon_name="cloud",
            animation_name=None,
            intensity=0,
            is_day=True,
        )
        assert sprite.animation is None

    def test_creates_sprite_with_no_icon(self):
        panel, canvas = _make_panel_and_canvas()
        sprite = ForecastSprite(
            canvas=canvas,
            panel=panel,
            x=0,
            y=0,
            icon_name=None,
            animation_name="fog",
            intensity=1,
            is_day=True,
        )
        assert sprite._has_icon is False
        assert sprite.animation is not None
        # Animation always fills the full sprite area.
        assert sprite.animation.height == SPRITE_HEIGHT

    def test_creates_sprite_with_no_icon_and_no_animation(self):
        panel, canvas = _make_panel_and_canvas()
        sprite = ForecastSprite(
            canvas=canvas,
            panel=panel,
            x=0,
            y=0,
            icon_name=None,
            animation_name=None,
            intensity=0,
            is_day=True,
        )
        assert sprite._has_icon is False
        assert sprite.animation is None

    def test_icon_drawn_on_creation(self):
        panel, canvas = _make_panel_and_canvas()
        sprite = ForecastSprite(
            canvas=canvas,
            panel=panel,
            x=5,
            y=7,
            icon_name="cloud",
            animation_name=None,
            intensity=0,
            is_day=True,
        )
        # draw_image should have been called once for the icon
        assert panel.draw_image.called
        call_args = panel.draw_image.call_args
        assert call_args.args[1] == 5  # x
        assert call_args.args[2] == 7 + ICON_OFFSET_Y  # y (icon inset)

    def test_icon_not_drawn_when_none(self):
        panel, canvas = _make_panel_and_canvas()
        sprite = ForecastSprite(
            canvas=canvas,
            panel=panel,
            x=0,
            y=0,
            icon_name=None,
            animation_name="fog",
            intensity=1,
            is_day=True,
        )
        assert not panel.draw_image.called

    def test_animation_area_is_full_sprite(self):
        panel, canvas = _make_panel_and_canvas()
        sprite = ForecastSprite(
            canvas=canvas,
            panel=panel,
            x=10,
            y=5,
            icon_name="cloud",
            animation_name="rain",
            intensity=1,
            is_day=True,
        )
        # The animation now occupies the entire sprite area (it may draw
        # over the icon).
        assert sprite.animation.x == 10
        assert sprite.animation.y == 5
        assert sprite.animation.width == SPRITE_WIDTH
        assert sprite.animation.height == SPRITE_HEIGHT


class TestSpriteDraw:
    def test_draw_advances_frame(self):
        panel, canvas = _make_panel_and_canvas()
        sprite = ForecastSprite(
            canvas=canvas,
            panel=panel,
            x=0,
            y=0,
            icon_name="cloud",
            animation_name="rain",
            intensity=1,
        )
        initial = sprite.frame
        sprite.draw()
        assert sprite.frame == initial + 1

    def test_draw_ticks_animation(self):
        panel, canvas = _make_panel_and_canvas()
        sprite = ForecastSprite(
            canvas=canvas,
            panel=panel,
            x=0,
            y=0,
            icon_name="cloud",
            animation_name="rain",
            intensity=1,
        )
        sprite.draw()
        # Animation tick should have called set_pixel
        assert panel.set_pixel.called

    def test_draw_with_no_animation_does_nothing(self):
        panel, canvas = _make_panel_and_canvas()
        sprite = ForecastSprite(
            canvas=canvas,
            panel=panel,
            x=0,
            y=0,
            icon_name="cloud",
            animation_name=None,
            intensity=0,
        )
        # Reset mock to clear draw_image calls from init
        panel.reset_mock()
        sprite.draw()
        assert not panel.set_pixel.called


class TestSpriteDestroy:
    def test_destroy_blanks_sprite_area(self):
        panel, canvas = _make_panel_and_canvas()
        sprite = ForecastSprite(
            canvas=canvas,
            panel=panel,
            x=3,
            y=7,
            icon_name="cloud",
            animation_name="rain",
            intensity=1,
        )
        panel.reset_mock()
        sprite.destroy()
        # Should blank the full sprite area (15x18 = 270 pixels)
        blank_calls = [
            call
            for call in panel.set_pixel.call_args_list
            if call.args[3:] == (0, 0, 0)
        ]
        assert len(blank_calls) >= SPRITE_WIDTH * SPRITE_HEIGHT

    def test_destroy_resets_animation(self):
        panel, canvas = _make_panel_and_canvas()
        sprite = ForecastSprite(
            canvas=canvas,
            panel=panel,
            x=0,
            y=0,
            icon_name="cloud",
            animation_name="rain",
            intensity=1,
        )
        sprite.draw()
        sprite.draw()
        assert sprite.animation.frame > 0
        sprite.destroy()
        assert sprite.animation.frame == 0


class TestSpriteAnimationProperties:
    def test_animation_frame_returns_current_index(self):
        panel, canvas = _make_panel_and_canvas()
        sprite = ForecastSprite(
            canvas=canvas,
            panel=panel,
            x=0,
            y=0,
            icon_name="cloud",
            animation_name="rain",
            intensity=1,
        )
        assert sprite.animation_frame == 0
        sprite.draw()
        assert sprite.animation_frame == 1

    def test_animation_frame_count(self):
        panel, canvas = _make_panel_and_canvas()
        sprite = ForecastSprite(
            canvas=canvas,
            panel=panel,
            x=0,
            y=0,
            icon_name="cloud",
            animation_name="rain",
            intensity=1,
        )
        assert sprite.animation_frame_count > 0

    def test_animation_frame_count_no_animation(self):
        panel, canvas = _make_panel_and_canvas()
        sprite = ForecastSprite(
            canvas=canvas,
            panel=panel,
            x=0,
            y=0,
            icon_name="cloud",
            animation_name=None,
            intensity=0,
        )
        assert sprite.animation_frame_count == 0
        assert sprite.animation_frame == 0

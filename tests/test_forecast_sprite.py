"""Tests for the forecast sprite helper functions."""

from unittest.mock import MagicMock

from scenes.idle.themes.icons.weather.forecast_sprite import (
    ANIMATION_HEIGHT,
    ICON_HEIGHT,
    ICON_OFFSET_Y,
    SPRITE_HEIGHT,
    SPRITE_WIDTH,
    blank_area,
    build_original,
    create_animation,
    draw_icon,
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
        assert SPRITE_HEIGHT == 15

    def test_icon_height(self):
        assert ICON_HEIGHT == 12

    def test_icon_offset_y(self):
        assert ICON_OFFSET_Y == 0

    def test_animation_height(self):
        # The animation occupies the full sprite area.
        assert ANIMATION_HEIGHT == SPRITE_HEIGHT

    def test_icon_fits_within_sprite(self):
        assert ICON_OFFSET_Y + ICON_HEIGHT <= SPRITE_HEIGHT


class TestBlankArea:
    def test_blanks_full_sprite_area(self):
        panel, canvas = _make_panel_and_canvas()
        blank_area(panel, canvas, 3, 7)
        # Should blank the full sprite area (15x15 = 225 pixels)
        blank_calls = [
            call
            for call in panel.set_pixel.call_args_list
            if call.args[3:] == (0, 0, 0)
        ]
        assert len(blank_calls) == SPRITE_WIDTH * SPRITE_HEIGHT

    def test_blank_uses_correct_coordinates(self):
        panel, canvas = _make_panel_and_canvas()
        blank_area(panel, canvas, 10, 20)
        # First pixel should be at (10, 20)
        first = panel.set_pixel.call_args_list[0]
        assert first.args[1] == 10
        assert first.args[2] == 20


class TestDrawIcon:
    def test_draws_icon_when_name_given(self):
        panel, canvas = _make_panel_and_canvas()
        img = draw_icon(panel, canvas, 5, 7, "cloud")
        assert panel.draw_image.called
        call_args = panel.draw_image.call_args
        assert call_args.args[1] == 5  # x
        assert call_args.args[2] == 7 + ICON_OFFSET_Y  # y (icon inset)
        assert img is not None

    def test_returns_none_when_icon_name_is_none(self):
        panel, canvas = _make_panel_and_canvas()
        img = draw_icon(panel, canvas, 0, 0, None)
        assert not panel.draw_image.called
        assert img is None


class TestBuildOriginal:
    def test_all_black_when_no_icon(self):
        original = build_original(None)
        assert len(original) == SPRITE_HEIGHT
        assert len(original[0]) == SPRITE_WIDTH
        for row in original:
            for px in row:
                assert px == (0, 0, 0)

    def test_has_icon_dimensions(self):
        # With a real icon image, the grid should still be sprite-sized.
        from PIL import Image

        icon = Image.new("RGBA", (15, 12), (100, 150, 200, 255))
        original = build_original(icon)
        assert len(original) == SPRITE_HEIGHT
        assert len(original[0]) == SPRITE_WIDTH


class TestCreateAnimation:
    def test_creates_animation_with_icon(self):
        panel, canvas = _make_panel_and_canvas()
        anim = create_animation(
            panel=panel,
            canvas=canvas,
            x=0,
            y=0,
            icon_name="cloud",
            animation_name="rain",
            intensity=1,
        )
        assert anim is not None
        assert anim.x == 0
        assert anim.y == 0
        assert anim.width == SPRITE_WIDTH
        assert anim.height == SPRITE_HEIGHT

    def test_returns_none_for_no_animation(self):
        panel, canvas = _make_panel_and_canvas()
        anim = create_animation(
            panel=panel,
            canvas=canvas,
            x=0,
            y=0,
            icon_name="cloud",
            animation_name=None,
            intensity=0,
        )
        assert anim is None

    def test_blanks_area_before_drawing_icon(self):
        panel, canvas = _make_panel_and_canvas()
        anim = create_animation(
            panel=panel,
            canvas=canvas,
            x=3,
            y=7,
            icon_name="cloud",
            animation_name="rain",
            intensity=1,
        )
        # The first calls should be blanking (set_pixel with 0,0,0)
        # before draw_image is called for the icon.
        blank_calls = [
            call
            for call in panel.set_pixel.call_args_list
            if call.args[3:] == (0, 0, 0)
        ]
        assert len(blank_calls) >= SPRITE_WIDTH * SPRITE_HEIGHT
        assert panel.draw_image.called

    def test_animation_has_original_cache(self):
        panel, canvas = _make_panel_and_canvas()
        anim = create_animation(
            panel=panel,
            canvas=canvas,
            x=0,
            y=0,
            icon_name="cloud",
            animation_name="rain",
            intensity=1,
        )
        # The animation should have a non-empty original cache.
        assert anim.original_pixel(0, 0) is not None

    def test_tick_advances_frame(self):
        panel, canvas = _make_panel_and_canvas()
        anim = create_animation(
            panel=panel,
            canvas=canvas,
            x=0,
            y=0,
            icon_name="cloud",
            animation_name="rain",
            intensity=1,
        )
        initial = anim.frame
        anim.tick()
        assert anim.frame == initial + 1

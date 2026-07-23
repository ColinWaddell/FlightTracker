"""Tests for the Scroller class and BDF font unification."""

import numpy as np
from collections import namedtuple
from PIL import Image
from unittest.mock import MagicMock

import pytest

from display.bdf_font import BDFFont, draw_text, draw_text_to_target
from display.scroller import (
    Scroller,
    render_spans_to_image,
    render_text_to_image,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FONT_PATH = "fonts/5x8.bdf"


@pytest.fixture
def font():
    return BDFFont(FONT_PATH)


@pytest.fixture
def mock_panel():
    """A mock panel that records set_pixel calls."""
    panel = MagicMock()
    panel.set_pixel = MagicMock()
    return panel


# ---------------------------------------------------------------------------
# BDFFont tests
# ---------------------------------------------------------------------------


class TestBDFFont:
    def test_loads_glyphs(self, font):
        assert len(font.glyphs) > 0

    def test_character_width_known(self, font):
        assert font.CharacterWidth(ord("A")) > 0

    def test_character_width_space(self, font):
        assert font.CharacterWidth(ord(" ")) >= 0

    def test_character_width_missing(self, font):
        assert font.CharacterWidth(0xFFFF) == 0

    def test_bounding_box(self, font):
        w, h, xo, yo = font.bounding_box
        assert w > 0
        assert h > 0

    def test_get_glyph_returns_dict(self, font):
        g = font.get_glyph(ord("A"))
        assert g is not None
        assert "bitmap" in g
        assert "bbx" in g
        assert "dwidth" in g

    def test_get_glyph_missing(self, font):
        assert font.get_glyph(0xFFFF) is None


class TestDrawTextPIL:
    def test_returns_advance_width(self, font):
        img = Image.new("RGB", (100, 20), (0, 0, 0))
        w = draw_text(img, font, 0, 10, (255, 255, 255), "Hi")
        assert w > 0

    def test_lights_pixels(self, font):
        img = Image.new("RGB", (100, 20), (0, 0, 0))
        draw_text(img, font, 0, 10, (255, 255, 255), "A")
        lit = sum(1 for y in range(20) for x in range(100) if img.getpixel((x, y)) != (0, 0, 0))
        assert lit > 0

    def test_empty_string(self, font):
        img = Image.new("RGB", (100, 20), (0, 0, 0))
        w = draw_text(img, font, 0, 10, (255, 255, 255), "")
        assert w == 0

    def test_colour_tuple(self, font):
        img = Image.new("RGB", (100, 20), (0, 0, 0))
        draw_text(img, font, 0, 10, (100, 200, 50), "A")
        # Find a lit pixel and check colour
        found = False
        for y in range(20):
            for x in range(100):
                px = img.getpixel((x, y))
                if px != (0, 0, 0):
                    assert px == (100, 200, 50)
                    found = True
        assert found

    def test_named_colour(self, font):
        """Colour objects with .red/.green/.blue attributes work."""
        Colour = namedtuple("Colour", ["red", "green", "blue"])
        c = Colour(255, 128, 0)
        img = Image.new("RGB", (100, 20), (0, 0, 0))
        draw_text(img, font, 0, 10, c, "A")
        found = False
        for y in range(20):
            for x in range(100):
                px = img.getpixel((x, y))
                if px != (0, 0, 0):
                    assert px == (255, 128, 0)
                    found = True
        assert found


class TestDrawTextToTarget:
    def test_returns_advance_width(self, font):
        target = MagicMock()
        w = draw_text_to_target(target, font, 0, 10, (255, 255, 255), "Hi", 100, 20)
        assert w > 0

    def test_calls_set_pixel(self, font):
        target = MagicMock()
        draw_text_to_target(target, font, 0, 10, (255, 255, 255), "A", 100, 20)
        assert target.set_pixel.call_count > 0

    def test_empty_string(self, font):
        target = MagicMock()
        w = draw_text_to_target(target, font, 0, 10, (255, 255, 255), "", 100, 20)
        assert w == 0
        target.set_pixel.assert_not_called()

    def test_same_pixel_count_as_pil(self, font):
        """PIL and target renderers should produce the same number of lit pixels."""
        img = Image.new("RGB", (100, 20), (0, 0, 0))
        w_pil = draw_text(img, font, 0, 10, (255, 255, 255), "Hello")
        pil_lit = sum(1 for y in range(20) for x in range(100) if img.getpixel((x, y)) != (0, 0, 0))

        target = MagicMock()
        w_target = draw_text_to_target(target, font, 0, 10, (255, 255, 255), "Hello", 100, 20)
        target_lit = target.set_pixel.call_count

        assert w_pil == w_target
        assert pil_lit == target_lit


# ---------------------------------------------------------------------------
# Scroller tests
# ---------------------------------------------------------------------------


class TestScrollerLinear:
    """Tests for linear (auto-advancing) scroll mode."""

    def test_first_tick_draws_all_pixels(self, mock_panel):
        scroller = Scroller(
            mock_panel, canvas=MagicMock(),
            x=0, y=0, width=10, height=4,
            bg_colour=(0, 0, 0), speed=1,
        )
        # Create a 20x4 content image with a distinctive pattern
        content = Image.new("RGB", (20, 4), (0, 0, 0))
        for x in range(20):
            content.putpixel((x, 0), (255, 0, 0))
        scroller.set_content(content)

        scroller.tick()
        # First tick should draw all viewport pixels (10x4 = 40)
        assert mock_panel.set_pixel.call_count == 40

    def test_second_tick_draws_only_changed(self, mock_panel):
        scroller = Scroller(
            mock_panel, canvas=MagicMock(),
            x=0, y=0, width=10, height=4,
            bg_colour=(0, 0, 0), speed=1,
        )
        content = Image.new("RGB", (20, 4), (0, 0, 0))
        for x in range(20):
            for y in range(4):
                content.putpixel((x, y), (x * 10, 0, 0))
        scroller.set_content(content)

        scroller.tick()  # full draw
        mock_panel.set_pixel.reset_mock()
        scroller.tick()  # should only draw changed pixels

        # With a 1px scroll, every pixel in the viewport changes (content is unique per column)
        # so all 40 pixels should be redrawn
        assert mock_panel.set_pixel.call_count == 40

    def test_static_content_draws_nothing_after_first(self, mock_panel):
        scroller = Scroller(
            mock_panel, canvas=MagicMock(),
            x=0, y=0, width=10, height=4,
            bg_colour=(0, 0, 0), speed=0,  # no movement
        )
        content = Image.new("RGB", (10, 4), (100, 100, 100))
        scroller.set_content(content)

        scroller.tick()  # full draw
        assert mock_panel.set_pixel.call_count == 40

        mock_panel.set_pixel.reset_mock()
        scroller.tick()  # nothing changed
        assert mock_panel.set_pixel.call_count == 0

    def test_offset_advances_by_speed(self, mock_panel):
        scroller = Scroller(
            mock_panel, canvas=MagicMock(),
            x=0, y=0, width=10, height=4,
            bg_colour=(0, 0, 0), speed=2,
        )
        content = Image.new("RGB", (30, 4), (0, 0, 0))
        scroller.set_content(content)
        # set_content resets offset to 0, tick advances by speed=2
        offset = scroller.tick()
        assert offset == 2

    def test_wrap_around(self, mock_panel):
        scroller = Scroller(
            mock_panel, canvas=MagicMock(),
            x=0, y=0, width=5, height=2,
            bg_colour=(0, 0, 0), speed=1, gap_pixels=1,
        )
        # Content 5px wide, gap 1px, period = 6
        # Offsets cycle: 1,2,3,4,5,0,1,2,...
        content = Image.new("RGB", (5, 2), (50, 50, 50))
        scroller.set_content(content)

        scroller.tick()
        assert scroller.offset == 1
        scroller.tick()
        assert scroller.offset == 2
        scroller.tick()
        assert scroller.offset == 3
        scroller.tick()
        assert scroller.offset == 4
        scroller.tick()
        assert scroller.offset == 5
        scroller.tick()
        assert scroller.offset == 0  # wrapped
        scroller.tick()
        assert scroller.offset == 1  # next cycle

    def test_gap_pixels(self, mock_panel):
        scroller = Scroller(
            mock_panel, canvas=MagicMock(),
            x=0, y=0, width=5, height=2,
            bg_colour=(0, 0, 0), speed=1, gap_pixels=3,
        )
        content = Image.new("RGB", (5, 2), (255, 255, 255))
        scroller.set_content(content)

        # Period = 5 + 3 = 8, offsets: 1,2,3,4,5,6,7,0,1,2...
        offsets = []
        for _ in range(10):
            offsets.append(scroller.tick())
        assert offsets[7] == 0  # wrapped
        assert offsets[8] == 1
        assert offsets[9] == 2

    def test_set_content_resets_offset(self, mock_panel):
        scroller = Scroller(
            mock_panel, canvas=MagicMock(),
            x=0, y=0, width=10, height=4,
            bg_colour=(0, 0, 0), speed=1,
        )
        content1 = Image.new("RGB", (30, 4), (255, 0, 0))
        scroller.set_content(content1)
        scroller.tick()
        scroller.tick()
        assert scroller.offset == 2

        content2 = Image.new("RGB", (20, 4), (0, 255, 0))
        scroller.set_content(content2)
        assert scroller.offset == 0

    def test_set_content_wrong_height_raises(self, mock_panel):
        scroller = Scroller(
            mock_panel, canvas=MagicMock(),
            x=0, y=0, width=10, height=4,
            bg_colour=(0, 0, 0),
        )
        content = Image.new("RGB", (20, 8), (255, 0, 0))  # wrong height
        with pytest.raises(ValueError, match="height"):
            scroller.set_content(content)

    def test_clear_blanks_viewport(self, mock_panel):
        scroller = Scroller(
            mock_panel, canvas=MagicMock(),
            x=5, y=10, width=8, height=3,
            bg_colour=(0, 0, 0),
        )
        scroller.clear()
        # Should write 8x3 = 24 background pixels at the viewport position
        assert mock_panel.set_pixel.call_count == 24
        # Check positions include the x,y offset
        # set_pixel(canvas, x, y, r, g, b) — canvas is arg 0, x is arg 1
        call_args = mock_panel.set_pixel.call_args_list[0]
        assert call_args[0][1] == 5  # x offset
        assert call_args[0][2] == 10  # y offset

    def test_pause_prevents_offset_advance(self, mock_panel):
        scroller = Scroller(
            mock_panel, canvas=MagicMock(),
            x=0, y=0, width=10, height=4,
            bg_colour=(0, 0, 0), speed=1,
        )
        content = Image.new("RGB", (30, 4), (100, 100, 100))
        scroller.set_content(content)

        scroller.tick()
        offset_after_first = scroller.offset

        scroller.pause()
        scroller.tick()
        assert scroller.offset == offset_after_first  # didn't advance

        scroller.resume()
        scroller.tick()
        assert scroller.offset > offset_after_first  # advanced again


class TestScrollerManual:
    """Tests for manual offset mode (bounce scroller use case)."""

    def test_set_offset_renders_at_position(self, mock_panel):
        scroller = Scroller(
            mock_panel, canvas=MagicMock(),
            x=0, y=0, width=10, height=4,
            bg_colour=(0, 0, 0), speed=0,
        )
        content = Image.new("RGB", (30, 4), (0, 0, 0))
        # Put unique pixels in each column
        for x in range(30):
            content.putpixel((x, 0), (x, 0, 0))
        scroller.set_content(content)

        scroller.set_offset(5)
        scroller.tick()

        # Check that the first pixel drawn corresponds to content column 5
        calls = mock_panel.set_pixel.call_args_list
        # Find the call at (0, 0) - top-left of viewport
        top_left_calls = [c for c in calls if c[0][1] == 0 and c[0][2] == 0]
        if top_left_calls:
            # Should be content column 5 = (5, 0, 0)
            call = top_left_calls[0]
            assert call[0][3] == 5  # r value

    def test_reset_forces_full_redraw(self, mock_panel):
        scroller = Scroller(
            mock_panel, canvas=MagicMock(),
            x=0, y=0, width=10, height=4,
            bg_colour=(0, 0, 0), speed=0,
        )
        content = Image.new("RGB", (10, 4), (100, 100, 100))
        scroller.set_content(content)

        scroller.tick()
        mock_panel.set_pixel.reset_mock()

        scroller.reset()
        scroller.tick()
        # After reset, should be a full draw
        assert mock_panel.set_pixel.call_count == 40

    def test_no_change_no_draws(self, mock_panel):
        scroller = Scroller(
            mock_panel, canvas=MagicMock(),
            x=0, y=0, width=10, height=4,
            bg_colour=(0, 0, 0), speed=0,
        )
        content = Image.new("RGB", (10, 4), (50, 50, 50))
        scroller.set_content(content)

        scroller.tick()  # full draw
        mock_panel.set_pixel.reset_mock()

        # Same offset, same content -> no changes
        scroller.tick()
        assert mock_panel.set_pixel.call_count == 0


# ---------------------------------------------------------------------------
# Content rendering helpers
# ---------------------------------------------------------------------------


class TestRenderSpansToImage:
    def test_creates_image_with_correct_width(self, font):
        spans = [
            ((255, 255, 255), font, "Hi"),
        ]
        img = render_spans_to_image(spans, height=8)
        expected_width = font.CharacterWidth(ord("H")) + font.CharacterWidth(ord("i"))
        assert img.width == expected_width
        assert img.height == 8

    def test_empty_spans(self):
        img = render_spans_to_image([], height=8)
        assert img.width == 1  # minimum
        assert img.height == 8

    def test_renders_pixels(self, font):
        spans = [((255, 255, 255), font, "A")]
        img = render_spans_to_image(spans, height=8)
        lit = sum(1 for y in range(8) for x in range(img.width) if img.getpixel((x, y)) != (0, 0, 0))
        assert lit > 0

    def test_background_colour(self, font):
        spans = [((255, 255, 255), font, "A")]
        img = render_spans_to_image(spans, height=8, bg_colour=(10, 20, 30))
        # Check a non-lit pixel has the background colour
        found_bg = False
        for y in range(8):
            for x in range(img.width):
                px = img.getpixel((x, y))
                if px == (10, 20, 30):
                    found_bg = True
        assert found_bg


class TestRenderTextToImage:
    def test_creates_image(self, font):
        img = render_text_to_image("Hello", font, height=8, colour=(255, 255, 255))
        expected_width = sum(font.CharacterWidth(ord(c)) for c in "Hello")
        assert img.width == expected_width
        assert img.height == 8

    def test_renders_pixels(self, font):
        img = render_text_to_image("A", font, height=8, colour=(255, 0, 0))
        found = False
        for y in range(8):
            for x in range(img.width):
                px = img.getpixel((x, y))
                if px == (255, 0, 0):
                    found = True
        assert found

    def test_empty_text(self, font):
        img = render_text_to_image("", font, height=8, colour=(255, 255, 255))
        assert img.width == 1  # minimum
"""Tests for panel colour order support (RGB/RBG/... panel wiring)."""

from display.rgbpanel import PANEL_COLOUR_ORDERS, channel_permutation

# ---------------------------------------------------------------------------
# channel_permutation
# ---------------------------------------------------------------------------


class TestChannelPermutation:
    def test_rgb_is_identity_none(self):
        assert channel_permutation("RGB") is None

    def test_all_six_orders_map(self):
        expected = {
            "RGB": None,
            "RBG": (0, 2, 1),
            "BGR": (2, 1, 0),
            "BRG": (2, 0, 1),
            "GBR": (1, 2, 0),
            "GRB": (1, 0, 2),
        }
        for order, perm in expected.items():
            assert channel_permutation(order) == perm

    def test_permutation_matches_rgbmatrix_semantics(self):
        """perm[i] is the logical channel ('RGB'.index) carried on physical
        channel i - mirrors rgbmatrix's led_rgb_sequence behaviour."""
        # "RBG": physical channel 2 (index 1) carries blue -> perm[1] == 2
        assert channel_permutation("RBG")[1] == 2
        # "BGR": physical channel 1 carries blue, channel 3 carries red
        assert channel_permutation("BGR") == (2, 1, 0)

    def test_case_insensitive(self):
        assert channel_permutation("rbg") == (0, 2, 1)
        assert channel_permutation("Bgr") == (2, 1, 0)

    def test_none_input_falls_back_to_identity(self):
        assert channel_permutation(None) is None

    def test_empty_string_falls_back_to_identity(self):
        assert channel_permutation("") is None

    def test_invalid_order_raises(self):
        for bad in ("RRG", "ABC", "RG", "RGBB", "GB"):
            try:
                channel_permutation(bad)
            except ValueError:
                pass
            else:
                raise AssertionError(f"{bad!r} should have raised ValueError")

    def test_panel_colour_orders_covers_all_permutations(self):
        assert sorted(PANEL_COLOUR_ORDERS) == ["BGR", "BRG", "GBR", "GRB", "RBG", "RGB"]


# ---------------------------------------------------------------------------
# Config property
# ---------------------------------------------------------------------------


class TestPanelColourOrderConfig:
    @staticmethod
    def _cfg(data):
        from setup.configuration import Config

        cfg = Config.__new__(Config)
        cfg.data_store = data
        return cfg

    def test_default_value(self):
        assert self._cfg({}).panel_colour_order == "RGB"

    def test_valid_orders_pass_through(self):
        for order in PANEL_COLOUR_ORDERS:
            assert self._cfg({"panel_colour_order": order}).panel_colour_order == order

    def test_lower_case_normalised(self):
        assert self._cfg({"panel_colour_order": "rbg"}).panel_colour_order == "RBG"

    def test_invalid_falls_back_to_default(self):
        for bad in ("bogus", "RRG", "123", "", None):
            assert (
                self._cfg({"panel_colour_order": bad}).panel_colour_order == "RGB"
            ), f"{bad!r} should fall back to RGB"

    def test_non_string_coerced(self):
        assert self._cfg({"panel_colour_order": 123}).panel_colour_order == "RGB"


# ---------------------------------------------------------------------------
# Piomatter channel remap (option A: software permutation in swap())
# ---------------------------------------------------------------------------


class TestPiomatterChannelRemap:
    """Verify the framebuffer remap applied in PiomatterPanel.swap().

    The piomatter library itself can't be imported off-Pi, so we test the
    permutation maths the panel applies rather than the panel class.
    Pure Python only - numpy is a Pi 5 backend dependency, not a test one.
    """

    def test_rbg_remap_swaps_green_and_blue(self):
        """The remap reorders each pixel's bytes so the panel's channel 2
        (wired blue on an RBG panel) carries the logical blue value and
        channel 3 carries green.  This mirrors the numpy indexing used in
        PiomatterPanel.swap(): out[i] = in[perm[i]]."""
        perm = channel_permutation("RBG")  # (0, 2, 1)

        logical = [255, 128, 64]  # R=255, G=128, B=64
        remapped = [logical[i] for i in perm]
        assert remapped == [255, 64, 128]

    def test_identity_order_returns_none_so_no_copy(self):
        assert channel_permutation("RGB") is None

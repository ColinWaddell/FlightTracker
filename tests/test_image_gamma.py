"""Tests for utilities.image_gamma - gamma correction for raster images.

The curve is ``out = round(255 * (in / 255) ** gamma)`` (the Adafruit
method, see issue #138); the sample values below are computed from it.
"""

from __future__ import annotations

import pytest
from PIL import Image

from scenes.flight import airline_logo
from utilities.image_gamma import apply as apply_gamma
from utilities.image_gamma import build_lut

# The shipped default exponent (Adafruit's converter value).
DEFAULT_GAMMA = 2.6


def _store(cfg, *, enabled=True, gamma=DEFAULT_GAMMA):
    """Point the patched Config singleton at the requested gamma settings."""
    cfg.data_store.update({"gamma_correction": enabled, "image_gamma": gamma})
    return cfg


class TestBuildLut:
    def test_shape_and_endpoints(self):
        lut = build_lut(DEFAULT_GAMMA)
        assert len(lut) == 256
        assert lut[0] == 0
        assert lut[255] == 255
        assert lut == sorted(lut)

    @pytest.mark.parametrize("gamma", [0.1, 0.5, 1.0, 2.2, 2.6, 3.0])
    def test_endpoints_hold_for_all_gammas(self, gamma):
        lut = build_lut(gamma)
        assert lut[0] == 0
        assert lut[255] == 255
        assert lut == sorted(lut)

    def test_identity_at_one(self):
        assert build_lut(1.0) == list(range(256))

    @pytest.mark.parametrize(
        ("gamma", "expected"),
        # round(255 * (128 / 255) ** gamma)
        [(0.5, 181), (2.2, 56), (2.6, 42)],
    )
    def test_known_midtone(self, gamma, expected):
        # gamma < 1 brightens mid-tones, gamma > 1 darkens them.
        assert build_lut(gamma)[128] == expected

    def test_cached_per_gamma(self):
        assert build_lut(DEFAULT_GAMMA) is build_lut(DEFAULT_GAMMA)
        assert build_lut(DEFAULT_GAMMA) is not build_lut(2.2)


class TestApply:
    def test_disabled_returns_input(self, fresh_config):
        _store(fresh_config, enabled=False)
        img = Image.new("RGBA", (2, 2), (128, 64, 200, 77))
        assert apply_gamma(img).tobytes() == img.tobytes()

    def test_rgb_correction_preserves_mode(self, fresh_config):
        # The boot splash reads .tobytes() as 3 bytes per pixel - an RGB
        # input must stay mode RGB so that stream is unchanged.
        _store(fresh_config)
        img = Image.new("RGB", (2, 2), (128, 128, 128))
        out = apply_gamma(img)
        assert out.mode == "RGB"
        assert out.getpixel((0, 0)) == (42, 42, 42)

    def test_rgba_correction_preserves_alpha(self, fresh_config):
        _store(fresh_config)
        img = Image.new("RGBA", (2, 2), (128, 128, 128, 77))
        out = apply_gamma(img)
        assert out.mode == "RGBA"
        assert out.getpixel((0, 0)) == (42, 42, 42, 77)

    def test_palette_input_converted_to_rgba(self, fresh_config):
        _store(fresh_config)
        img = Image.new("P", (2, 2))
        img.putpalette([128, 128, 128] * 256)
        img.putpixel((0, 0), 0)
        out = apply_gamma(img)
        assert out.mode == "RGBA"
        assert out.getpixel((0, 0)) == (42, 42, 42, 255)

    def test_input_not_mutated(self, fresh_config):
        _store(fresh_config)
        img = Image.new("RGBA", (2, 2), (128, 128, 128, 255))
        apply_gamma(img)
        assert img.getpixel((0, 0)) == (128, 128, 128, 255)


class TestAirlineLoaderIntegration:
    """_load_airline_icon transforms on load and caches post-transform."""

    LOOKUP = "GGG"  # deliberately not used by any real logo or other test

    @pytest.fixture(autouse=True)
    def _isolate_cache(self):
        assert self.LOOKUP not in airline_logo._image_cache
        yield
        airline_logo._image_cache.pop(self.LOOKUP, None)

    @pytest.fixture
    def logo_png(self, tmp_path):
        path = tmp_path / f"{self.LOOKUP}.png"
        Image.new("RGBA", (16, 16), (128, 128, 128, 255)).save(path)
        return path

    def test_transform_on_load_and_cached(self, fresh_config, monkeypatch, logo_png):
        _store(fresh_config)
        monkeypatch.setattr(airline_logo, "icao_to_png", lambda code: logo_png)
        first = airline_logo._load_airline_icon(self.LOOKUP)
        assert first is not None
        assert first.getpixel((0, 0)) == (42, 42, 42, 255)
        # The cache holds the already-transformed image: reloading returns
        # the same object without re-reading the PNG.
        assert airline_logo._load_airline_icon(self.LOOKUP) is first

    def test_untouched_when_disabled(self, fresh_config, monkeypatch, logo_png):
        _store(fresh_config, enabled=False)
        monkeypatch.setattr(airline_logo, "icao_to_png", lambda code: logo_png)
        icon = airline_logo._load_airline_icon(self.LOOKUP)
        assert icon.getpixel((0, 0)) == (128, 128, 128, 255)

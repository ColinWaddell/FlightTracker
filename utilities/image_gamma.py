"""Gamma-correct PIL raster images for the LED matrix.

RGB matrix panels are driven linearly: an 8-bit channel value lights the LED
with that share of its full brightness.  Asset images (airline logos, weather
icons, the splash screen) store sRGB-encoded values - what a normal graphics
editor produces - so shown raw their mid-tones look washed out on the panel:
on a desktop monitor the eye's non-linear response to light is compensated by
the display's own gamma curve, but nothing in this pipeline compensates for
it.

Applying the Adafruit gamma correction darkens mid-tones before display, so
the linearly-driven panel shows the intended tones (see
https://learn.adafruit.com/image-correction-for-rgb-led-matrices/overview).
The exact curve is:

    out = round(255 * (in / 255) ** gamma)

``gamma = 1.0`` is identity, values below 1.0 brighten mid-tones, values
above 1.0 darken them.  Adafruit's own converter script uses 2.6, which is
also the shipped default (``DEFAULT_IMAGE_GAMMA`` in ``setup/configuration``).

The enable flag and exponent are read from the config each time an image is
loaded.  Every caller caches its images for the life of the process - so in
practice the settings are read once at boot, and a change takes effect when
the service restarts.  Saving settings in the web interface restarts the
service automatically, so no live cache invalidation is needed.
"""

from __future__ import annotations

from functools import lru_cache

from PIL import Image

from setup.configuration import Config


@lru_cache(maxsize=8)
def build_lut(gamma: float) -> list[int]:
    """Build a 256-entry LUT mapping each channel value through the curve.

    Each entry is ``round(255 * (level / 255) ** gamma)``.  Cached per
    exponent; the ``min`` clamp only guards float error at the top end.
    """
    return [min(255, round(255 * (level / 255) ** gamma)) for level in range(256)]


def apply(img: Image.Image) -> Image.Image:
    """Gamma-correct *img* for the matrix panel per the gamma settings.

    Returns the image unchanged when ``gamma_correction`` is disabled.
    Otherwise every colour channel is mapped through the LUT built from the
    ``image_gamma`` exponent:

    - an RGB image is corrected and returned still in mode RGB, so consumers
      that read its raw bytes (the boot splash) keep 3 bytes per pixel;
    - anything else is converted to RGBA first and corrected there, with an
      untouched identity segment so alpha is preserved.

    The input image is never mutated; callers already cache the returned
    image, so the transform runs once per image load.
    """
    cfg = Config.instance()
    if not cfg.gamma_correction:
        return img

    lut = build_lut(cfg.image_gamma)
    if img.mode == "RGB":
        return img.point(lut * 3)
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    return img.point(lut * 3 + list(range(256)))

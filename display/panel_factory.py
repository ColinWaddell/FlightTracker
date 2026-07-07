"""
Panel factory — selects the appropriate RGBPanel driver at runtime.

Tries to import the piomatter (Pi 5) driver first; if unavailable, falls back
to the rgbmatrix (Pi 3/4) driver. The selected panel is cached as a singleton.
"""

import importlib

_panel = None


def get_panel():
    """Return the singleton RGBPanel instance, creating it if needed."""
    global _panel
    if _panel is not None:
        return _panel

    # Try Pi 5 driver first
    try:
        mod = importlib.import_module("display.rgbpanel_piomatter")
        _panel = mod.PiomatterPanel()
        return _panel
    except ImportError:
        pass

    # Fall back to Pi 3/4 driver
    try:
        mod = importlib.import_module("display.rgbpanel_rgbmatrix")
        _panel = mod.RGBMatrixPanel()
        return _panel
    except ImportError:
        pass

    raise ImportError(
        "No RGB panel driver available. "
        "Install adafruit-blinka-raspberry-pi5-piomatter (Pi 5) "
        "or rgbmatrix (Pi 3/4)."
    )


def reset_panel():
    """Clear the cached panel (used for testing)."""
    global _panel
    _panel = None
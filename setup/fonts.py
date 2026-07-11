import os

# Fonts are loaded lazily on first access so the panel driver can be
# selected at runtime (Pi 3/4 rgbmatrix vs Pi 5 piomatter).

DIR_PATH = os.path.dirname(os.path.realpath(__file__))

_loaded_fonts = {}


def _load_fonts():
    if _loaded_fonts:
        return
    from display.panel_factory import get_panel

    panel = get_panel()

    _loaded_fonts["extrasmall"] = panel.load_font(f"{DIR_PATH}/../fonts/4x6.bdf")
    _loaded_fonts["small"] = panel.load_font(f"{DIR_PATH}/../fonts/5x8.bdf")
    _loaded_fonts["small_symbols"] = panel.load_font(
        f"{DIR_PATH}/../fonts/5x8-custom.bdf"
    )
    _loaded_fonts["regular"] = panel.load_font(f"{DIR_PATH}/../fonts/6x12.bdf")
    _loaded_fonts["large"] = panel.load_font(f"{DIR_PATH}/../fonts/8x13.bdf")
    _loaded_fonts["large_bold"] = panel.load_font(f"{DIR_PATH}/../fonts/8x13B.bdf")


def __getattr__(name):
    if name in (
        "extrasmall",
        "small",
        "small_symbols",
        "regular",
        "large",
        "large_bold",
    ):
        _load_fonts()
        return _loaded_fonts[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

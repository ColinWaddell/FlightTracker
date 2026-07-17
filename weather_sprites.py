"""Minimal test harness: initialise a panel and write "hello" to it."""

from pathlib import Path

from PIL import Image

from display.panel_factory import get_panel
from scenes.idle.themes.icons.weather.codes import code_to_icon

panel = None
canvas = None
_ICON_DIR = Path(__file__).parent / "scenes" / "idle" / "themes" / "icons" / "weather"


def draw_test():
    icon, _ = code_to_icon(1003, False)
    path = _ICON_DIR / f"{icon}.png"
    if not path.exists():
        print(f"[draw_test] icon not found: {path}")
        return
    img = Image.open(path).convert("RGBA")
    panel.draw_image(canvas, 10, 10, img)
    panel.swap(canvas)


def main():
    global panel, canvas
    panel = get_panel()
    panel.init_matrix(width=64, height=32, brightness=50, rotation=180)

    # font = panel.load_font(os.path.join(os.path.dirname(__file__), "fonts", "6x12.bdf"))

    canvas = panel.create_canvas()
    panel.clear(canvas)
    panel.swap(canvas)

    draw_test()

    # Keep the display alive so we can see the text.
    print("Showing 'hello' - press Ctrl+C to exit.")
    try:
        while True:
            pass
    except KeyboardInterrupt:
        panel.clear(canvas)
        panel.swap(canvas)


if __name__ == "__main__":
    main()

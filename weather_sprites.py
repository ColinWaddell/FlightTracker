"""
weather_sprites.py — standalone manual test harness for forecast sprites.

Displays 3 weather sprites on the LED panel (or simulator) with live
animations, mimicking the real idle scene render loop.  Use this to
iterate on animation designs without booting the full application.

Usage:
    python weather_sprites.py

Tweak the constants below to change what's displayed.
"""

from __future__ import annotations

from time import perf_counter, sleep

from display.panel_factory import get_panel
from scenes.idle.themes.icons.weather.codes import code_to_weather
from scenes.idle.themes.icons.weather.forecast_sprite import (
    SPRITE_WIDTH,
    ForecastSprite,
)

# ======================================================================
# --- Tweak these to change what's displayed ---------------------------
# ======================================================================

# Weather condition codes to display (from codes.py CODE_MAPPINGS).
# Pick any 3 codes to see their icons + animations side by side.
CONDITION_CODES = [1000, 1003, 1183]

# Force night mode (uses night icon/animation variants from codes.py).
NIGHT_MODE = False

# Show top/bottom labels (condition code + intensity) to simulate the
# forecast theme layout.  Set to False to see just the sprites.
SHOW_LABELS = True

# Frame period in seconds (matches setup.frames.PERIOD = 0.08 -> 12.5 fps).
FRAME_PERIOD = 0.08

# Panel dimensions.
PANEL_WIDTH = 64
PANEL_HEIGHT = 32
PANEL_BRIGHTNESS = 50
PANEL_ROTATION = 180

# Sprite x-positions (matches forecast_idle_theme.py ICON_POSITIONS_X).
SPRITE_X_POSITIONS = (3, 23, 43)
SPRITE_Y = 7

# ======================================================================
# --- End of tweakable constants ---------------------------------------
# ======================================================================


def build_sprites(canvas, panel):
    """Instantiate 3 ForecastSprite instances from CONDITION_CODES."""
    sprites = []
    for i, code in enumerate(CONDITION_CODES):
        icon_name, animation_name, intensity = code_to_weather(code, NIGHT_MODE)
        sprite = ForecastSprite(
            canvas=canvas,
            panel=panel,
            x=SPRITE_X_POSITIONS[i],
            y=SPRITE_Y,
            icon_name=icon_name,
            animation_name=animation_name,
            intensity=intensity,
            is_day=not NIGHT_MODE,
        )
        sprites.append(sprite)
    return sprites


def draw_labels(canvas, panel):
    """Draw simple top/bottom labels for each sprite position."""
    if not SHOW_LABELS:
        return

    from setup import fonts
    from setup.themes import TC, THEME_TEXT

    label_font = fonts.extrasmall

    for i, code in enumerate(CONDITION_CODES):
        x = SPRITE_X_POSITIONS[i]

        # Top label: condition code
        top_text = str(code)
        top_width = sum(label_font.CharacterWidth(ord(c)) for c in top_text)
        top_x = x + round((SPRITE_WIDTH - top_width) / 2)
        panel.draw_text(canvas, label_font, top_x, 5, TC(THEME_TEXT), top_text)

        # Bottom label: intensity level (L/M/H)
        _, _, intensity = code_to_weather(code, NIGHT_MODE)
        intensity_text = ["L", "M", "H"][intensity] if intensity < 3 else "?"
        bot_width = label_font.CharacterWidth(ord(intensity_text))
        bot_x = x + round((SPRITE_WIDTH - bot_width) / 2)
        panel.draw_text(canvas, label_font, bot_x, 31, TC(THEME_TEXT), intensity_text)


def run_loop(sprites, canvas, panel):
    """Main render loop — mimics display.run() at FRAME_PERIOD cadence."""
    print(f"Showing {len(sprites)} sprites — press Ctrl+C to exit.")
    print(f"Condition codes: {CONDITION_CODES} (night={NIGHT_MODE})")

    try:
        while True:
            start = perf_counter()

            # Tick each sprite's animation
            for sprite in sprites:
                sprite.draw()

            panel.swap(canvas)

            elapsed = perf_counter() - start
            sleep_time = FRAME_PERIOD - elapsed
            if sleep_time < 0.001:
                sleep_time = 0.001
            sleep(sleep_time)

    except KeyboardInterrupt:
        print("\nExiting...")


def main():
    panel = get_panel()
    panel.init_matrix(
        width=PANEL_WIDTH,
        height=PANEL_HEIGHT,
        brightness=PANEL_BRIGHTNESS,
        rotation=PANEL_ROTATION,
    )

    canvas = panel.create_canvas()
    panel.clear(canvas)
    panel.swap(canvas)

    # Build sprites (this draws the static icons immediately)
    sprites = build_sprites(canvas, panel)

    # Draw labels if enabled
    draw_labels(canvas, panel)

    # Initial swap so we see the static icons
    panel.swap(canvas)

    # Enter the animation loop
    run_loop(sprites, canvas, panel)

    # Clean up on exit
    for sprite in sprites:
        sprite.destroy()
    panel.clear(canvas)
    panel.swap(canvas)


if __name__ == "__main__":
    main()

"""
FlightTracker display entry-point.

Boot sequence:
  1. Initialise Config singleton (migrates legacy config.py if needed)
  2. Apply theme
  3. Start Flask config UI on port 8584 as a daemon thread
  4. Show QR-code boot screen:
       • Always shown for 5 s
       • If no config.json existed → stays up until the user saves config
  5. Enter the main animation loop
"""

import sys
import socket
import threading
import time

from setup.configuration import Config, CONFIG_PATH
from setup import frames
from setup.themes import theme_set
from utilities.animator import Animator

from rgbmatrix import graphics
from rgbmatrix import RGBMatrix, RGBMatrixOptions

from scenes.weather import WeatherScene
from scenes.flightdetails import FlightDetailsScene
from scenes.journey import JourneyScene
from scenes.loadingpulse import LoadingPulseScene
from scenes.loadingled import LoadingLEDScene
from scenes.clock import ClockScene
from scenes.planedetails import PlaneDetailsScene
from scenes.day import DayScene
from scenes.date import DateScene


# ---------------------------------------------------------------------------
# Helper: local IP
# ---------------------------------------------------------------------------

def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


# ---------------------------------------------------------------------------
# Flask daemon
# ---------------------------------------------------------------------------

def _start_flask_daemon():
    from web.app import app, FLASK_PORT
    import logging
    log = logging.getLogger("werkzeug")
    log.setLevel(logging.ERROR)
    t = threading.Thread(
        target=lambda: app.run(host="0.0.0.0", port=FLASK_PORT, debug=False, use_reloader=False),
        daemon=True,
        name="flask-config",
    )
    t.start()
    return t


# ---------------------------------------------------------------------------
# QR-code rendering helpers
# ---------------------------------------------------------------------------

def _render_qr_frame(canvas, matrix, url: str, fonts_small, bg_colour, fg_colour, text_colour):
    """Draw a QR code + URL hint onto canvas and swap it to the matrix."""
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_L

        qr = qrcode.QRCode(
            version=1,
            error_correction=ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(url)
        qr.make(fit=True)
        modules = qr.get_matrix()

        # Centre the QR code vertically in the 32px height.
        # The matrix fits at the LEFT of the 64-wide canvas.
        qr_size = len(modules)  # square
        y_offset = max(0, (32 - qr_size) // 2)

        canvas.Clear()

        for row_idx, row in enumerate(modules):
            for col_idx, cell in enumerate(row):
                x = col_idx
                y = y_offset + row_idx
                if 0 <= x < 64 and 0 <= y < 31:
                    canvas.SetPixel(x, y, *(
                        (fg_colour.red, fg_colour.green, fg_colour.blue) if cell
                        else (bg_colour.red, bg_colour.green, bg_colour.blue)
                    ))

    except Exception as exc:
        # If qrcode isn't installed, just show text
        canvas.Clear()

    # Draw "config at:" label to the right of the QR if there's space
    label = "config:"
    from setup import fonts as _fonts
    graphics.DrawText(canvas, _fonts.extrasmall, qr_size + 2, 7,  text_colour, label)
    graphics.DrawText(canvas, _fonts.extrasmall, qr_size + 2, 14, text_colour, ":8584")

    matrix.SwapOnVSync(canvas)


def _show_boot_screen(matrix, canvas, cfg_existed: bool):
    """
    Show QR code pointing to the config UI.
    Always shown for 5 s. If no config existed, loop until config.json appears.
    """
    from setup import fonts as _fonts
    from setup.themes import TC, THEME_BG, THEME_TEXT, THEME_FLIGHT_NUMERIC

    from rgbmatrix import graphics as _graphics

    bg     = TC(THEME_BG)
    fg     = _graphics.Color(255, 255, 255)
    text_c = TC(THEME_FLIGHT_NUMERIC)

    ip  = _local_ip()
    url = f"http://{ip}:8584"

    deadline = time.time() + 5  # always show at least 5 s

    while True:
        _render_qr_frame(canvas, matrix, url, _fonts.extrasmall, bg, fg, text_c)
        time.sleep(0.5)

        now = time.time()
        if now >= deadline:
            if cfg_existed or CONFIG_PATH.exists():
                break
            # No config yet — keep spinning so the user can configure


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def callsigns_match(flights_a, flights_b):
    get_callsigns = lambda flights: [f["callsign"] for f in flights]
    return set(get_callsigns(flights_a)) == set(get_callsigns(flights_b))


# ---------------------------------------------------------------------------
# Display class
# ---------------------------------------------------------------------------

cfg = Config.instance()
theme_set(cfg.theme)

if cfg.use_tar1090:
    from utilities.overhead_tar1090 import Overhead
else:
    from utilities.overhead_fr24 import Overhead

_loading_scene = LoadingLEDScene if cfg.loading_led_enabled else LoadingPulseScene


class Display(
    WeatherScene,
    FlightDetailsScene,
    JourneyScene,
    _loading_scene,
    PlaneDetailsScene,
    ClockScene,
    DayScene,
    DateScene,
    Animator,
):
    def __init__(self):
        _cfg = Config.instance()

        options = RGBMatrixOptions()
        options.hardware_mapping = (
            "adafruit-hat-pwm" if _cfg.hat_pwm_enabled else "adafruit-hat"
        )
        options.rows = 32
        options.cols = 64
        options.chain_length = 1
        options.parallel = 1
        options.row_address_type = 0
        options.multiplexing = 0
        options.pwm_bits = 11
        options.brightness = _cfg.brightness_percent
        options.pwm_lsb_nanoseconds = 130
        options.led_rgb_sequence = "RGB"
        options.pixel_mapper_config = "Rotate:180" if _cfg.screen_rotate else ""
        options.show_refresh_rate = 0
        options.gpio_slowdown = _cfg.gpio_slowdown
        options.disable_hardware_pulsing = True
        options.drop_privileges = True

        self.matrix = RGBMatrix(options=options)
        self.canvas = self.matrix.CreateFrameCanvas()
        self.canvas.Clear()

        self._data_index = 0
        self._data = []

        self.overhead = Overhead()
        self.overhead.grab_data()

        super().__init__()

        self.delay = frames.PERIOD

    def draw_square(self, x0, y0, x1, y1, colour):
        for x in range(x0, x1):
            _ = graphics.DrawLine(self.canvas, x, y0, x, y1, colour)

    @Animator.KeyFrame.add(0)
    def clear_screen(self):
        self.canvas.Clear()

    @Animator.KeyFrame.add(frames.PER_SECOND * 5)
    def check_for_loaded_data(self, count):
        if self.overhead.error is not None:
            print(f"overhead data grab failed: {self.overhead.error}")
            return

        if self.overhead.new_data:
            there_is_data = len(self._data) > 0 or not self.overhead.data_is_empty
            new_data = self.overhead.data
            data_is_different = not callsigns_match(self._data, new_data)

            if data_is_different:
                self._data_index = 0
                self._data_all_looped = False
                self._data = new_data

            if there_is_data and data_is_different:
                self.reset_scene()

    @Animator.KeyFrame.add(1)
    def sync(self, count):
        _ = self.matrix.SwapOnVSync(self.canvas)

    @Animator.KeyFrame.add(frames.PER_SECOND * 30)
    def grab_new_data(self, count):
        if (
            not self.overhead.processing
            and not self.overhead.new_data
            and (self._data_all_looped or len(self._data) <= 1)
        ):
            self.overhead.grab_data()

    def run(self):
        # Remember whether config.json existed before we started
        cfg_existed = CONFIG_PATH.exists()

        # Start Flask config UI daemon thread
        _start_flask_daemon()

        # Boot screen (QR code)
        _show_boot_screen(self.matrix, self.canvas, cfg_existed)

        # Clear and enter main loop
        self.canvas.Clear()

        try:
            print("Press CTRL-C to stop")
            self.play()

        except KeyboardInterrupt:
            print("Exiting\n")
            if self.overhead.processing:
                self.overhead.wait(timeout=15)
            sys.exit(0)

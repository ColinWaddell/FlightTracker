import os
import socket
import sys
import threading
import time

from setup.configuration import Config, CONFIG_PATH

# Default port for the web config interface - must match web/app.py FLASK_PORT
_DEFAULT_FLASK_PORT = 8584


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _render_splash(matrix, canvas, Image, url=None, qrcode=None, ERROR_CORRECT_L=None):
    """
    Render the splash BMP to canvas and swap it onto the display.

    Called twice during startup:
      - Without url: shows the splash image only (loading state).
      - With url:    re-renders the splash and overlays the QR code on top.

    Re-rendering the splash on the second call avoids having to keep a copy
    of the bitmap pixels in memory between the two phases.
    """
    # canvas.SetImage() is broken with Pillow 10+ (unsafe_ptrs removed).
    # Read raw bytes and set pixels manually instead.
    splash_path = os.path.join(os.path.dirname(__file__), "assets", "splash.bmp")
    splash = Image.open(splash_path)
    pixels = splash.tobytes()
    for y in range(32):
        for x in range(64):
            i = (y * 64 + x) * 3
            canvas.SetPixel(x, y, pixels[i], pixels[i + 1], pixels[i + 2])

    if url is not None and qrcode is not None:
        qr = qrcode.QRCode(
            version=1,
            error_correction=ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(url)
        qr.make(fit=True)
        for qy, row in enumerate(qr.get_matrix()):
            for qx, cell in enumerate(row):
                px, py = qx, qy + 2
                if 0 <= px < 64 and 0 <= py < 32:
                    v = 0 if cell else 255
                    canvas.SetPixel(px, py, v, v, v)

    matrix.SwapOnVSync(canvas)


def _flask_load(ready_event: threading.Event, result: dict):
    """
    Thread A: import and start the Flask config server.

    make_server() binds the port synchronously, so by the time ready_event
    is set Flask can already accept connections.  serve_forever() is handed
    off to a daemon thread so this function can return promptly.
    """
    try:
        from web.app import app, FLASK_PORT
        from werkzeug.serving import make_server
        import logging

        logging.getLogger("werkzeug").setLevel(logging.ERROR)

        server = make_server("0.0.0.0", FLASK_PORT, app, threaded=True)
        # Prevent the inheritable socket flag causing "Address already in use"
        # if the process is restarted via os.execv.
        server.socket.set_inheritable(False)

        # Port is bound — signal the main thread to show the QR code.
        ready_event.set()

        threading.Thread(
            target=server.serve_forever,
            daemon=True,
            name="flask-config",
        ).start()

        result["flask_started"] = True

    except Exception as exc:
        result["flask_error"] = exc
        import traceback
        traceback.print_exc(file=sys.stderr)
        # Unblock the main thread even on failure so startup doesn't hang.
        ready_event.set()


def _display_load(matrix, canvas, result: dict):
    """
    Thread B: import and build the Display class (heavy: FR24 API, scenes, fonts).

    Runs in parallel with _flask_load so both complete during the splash window.
    """
    try:
        from display import get_display_class

        DisplayClass = get_display_class()
        display = DisplayClass(matrix=matrix, canvas=canvas)
        result["display"] = display

    except Exception as exc:
        result["error"] = exc
        import traceback
        traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":
    cfg = Config.instance()

    # -- Phase 1: Minimal imports for the splash screen -----------------------
    # Only rgbmatrix + PIL + qrcode are needed here.  Imported before the
    # background threads start to avoid GIL contention with heavy imports.
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
    from PIL import Image

    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_L
    except ImportError:
        qrcode = None
        ERROR_CORRECT_L = None

    options = RGBMatrixOptions()
    options.hardware_mapping = (
        "adafruit-hat-pwm" if cfg.hat_pwm_enabled else "adafruit-hat"
    )
    options.rows = 32
    options.cols = 64
    options.chain_length = 1
    options.parallel = 1
    options.row_address_type = 0
    options.multiplexing = 0
    options.pwm_bits = 11
    options.brightness = cfg.brightness_percent
    options.pwm_lsb_nanoseconds = 130
    options.led_rgb_sequence = "RGB"
    options.pixel_mapper_config = "Rotate:180" if cfg.screen_rotate else ""
    options.show_refresh_rate = 0
    options.gpio_slowdown = cfg.gpio_slowdown
    options.disable_hardware_pulsing = True
    options.drop_privileges = True

    matrix = RGBMatrix(options=options)
    canvas = matrix.CreateFrameCanvas()
    canvas.Clear()

    # -- Phase 2: Show splash (loading state, no QR) --------------------------
    _render_splash(matrix, canvas, Image)

    result = {}

    if cfg.web_interface_enabled:
        url = f"http://{_local_ip()}:{_DEFAULT_FLASK_PORT}/settings"
        print(f"[web] Config interface: {url}", flush=True)

        flask_ready = threading.Event()

        # Thread A: Flask (fast — just binds a port)
        flask_thread = threading.Thread(
            target=_flask_load,
            args=(flask_ready, result),
            daemon=True,
            name="flask-load",
        )
        # Thread B: Display class (slow — FR24 API, scenes, fonts)
        display_thread = threading.Thread(
            target=_display_load,
            args=(matrix, canvas, result),
            daemon=True,
            name="display-load",
        )

        flask_thread.start()
        display_thread.start()

        # -- Phase 3: Wait for Flask, then show QR and start 8-second clock --
        # The countdown begins only once Flask is provably ready so the user
        # always has a full 8 seconds to scan the code.
        flask_ready.wait()
        if "flask_error" not in result:
            _render_splash(matrix, canvas, Image, url, qrcode, ERROR_CORRECT_L)

        cfg_existed = CONFIG_PATH.exists()
        deadline = time.time() + 8
        while True:
            time.sleep(0.5)
            if time.time() >= deadline and (cfg_existed or CONFIG_PATH.exists()):
                break

        # -- Phase 4: Wait for display build to finish ------------------------
        display_thread.join()
        flask_thread.join()

    else:
        # No web UI — brief splash, then build display in the background.
        display_thread = threading.Thread(
            target=_display_load,
            args=(matrix, canvas, result),
            daemon=True,
            name="display-load",
        )
        display_thread.start()
        time.sleep(2)
        display_thread.join()

    if "error" in result:
        print(f"[startup] Display build failed: {result['error']}", file=sys.stderr)
        sys.exit(1)

    display = result["display"]

    # -- Phase 5: Run the main display loop -----------------------------------
    display.run()

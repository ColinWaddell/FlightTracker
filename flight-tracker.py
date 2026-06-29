import os
import socket
import sys
import threading
import time

from setup.configuration import Config, CONFIG_PATH

# Default port for the web config interface — must match web/app.py FLASK_PORT
_DEFAULT_FLASK_PORT = 8584


def _local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _start_flask_daemon():
    from web.app import app, FLASK_PORT
    from werkzeug.serving import make_server
    import logging

    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    server = make_server("0.0.0.0", FLASK_PORT, app, threaded=True)
    # Werkzeug sets the socket inheritable so its reloader can pass it to child
    # processes. We don't use the reloader, but the flag survives os.execv and
    # causes "Address already in use" on restart. Clear it here.
    server.socket.set_inheritable(False)

    t = threading.Thread(
        target=server.serve_forever,
        daemon=True,
        name="flask-config",
    )
    t.start()


def _render_splash(matrix, canvas, url: str, Image, qrcode, ERROR_CORRECT_L):
    """
    Splash-image boot screen with QR code overlaid at the top-left.

    Loads assets/splash.bmp (64x32) via PIL and pushes it to the canvas
    with SetImage, then paints QR modules on top at (0, 0).
    The frame is left on screen after the deadline; the animator overwrites
    it on its first render pass.
    """
    # -- Load splash image ----------------------------------------------------
    # canvas.SetImage() is broken with Pillow 10+ (unsafe_ptrs removed).
    # Read raw bytes and set pixels manually instead.
    splash_path = os.path.join(os.path.dirname(__file__), "assets", "splash.bmp")
    splash = Image.open(splash_path)
    pixels = splash.tobytes()
    for y in range(32):
        for x in range(64):
            i = (y * 64 + x) * 3
            canvas.SetPixel(x, y, pixels[i], pixels[i + 1], pixels[i + 2])

    # -- Overlay QR at top-left -----------------------------------------------
    if qrcode is not None:
        qr = qrcode.QRCode(
            version=1,
            error_correction=ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(url)
        qr.make(fit=True)
        modules = qr.get_matrix()
        qr_size = len(modules)

        for qy, row in enumerate(modules):
            for qx, cell in enumerate(row):
                px, py = qx, qy + 2
                if 0 <= px < 64 and 0 <= py < 32:
                    if cell:
                        canvas.SetPixel(px, py, 0, 0, 0)
                    else:
                        canvas.SetPixel(px, py, 255, 255, 255)

    matrix.SwapOnVSync(canvas)


def _background_load(matrix, canvas, result: dict):
    """
    Background thread: import and initialise everything that isn't needed
    for the splash screen.  Stores the fully-constructed Display in
    result['display'] and starts the Flask daemon.
    """
    try:
        # Import the display module and build the class lazily.
        # This triggers all scene imports, the FR24 API library,
        # fonts, themes, etc. — but only when called, not at module load.
        from display import get_display_class

        DisplayClass = get_display_class()

        # Construct the Display, reusing the matrix/canvas from the splash
        display = DisplayClass(matrix=matrix, canvas=canvas)
        result['display'] = display

        # Start the Flask config web server
        cfg = Config.instance()
        if cfg.web_interface_enabled:
            _start_flask_daemon()
            result['flask_started'] = True

    except Exception as exc:
        result['error'] = exc
        import traceback
        traceback.print_exc(file=sys.stderr)


if __name__ == "__main__":
    cfg = Config.instance()

    # -- Phase 1: Minimal imports for splash screen ---------------------------
    # Only rgbmatrix + PIL + qrcode are needed to show the QR code.
    # These are imported synchronously BEFORE the background thread starts
    # to avoid GIL contention with the heavy FR24/Flask imports.
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
    from PIL import Image
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_L
    except ImportError:
        qrcode = None

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

    # -- Phase 2: Show splash + QR immediately --------------------------------
    # Build the QR URL using the default port constant (no Flask import needed).
    # The URL just points the phone at the right address; Flask will be ready
    # by the time the user actually scans and connects.
    if cfg.web_interface_enabled:
        url = f"http://{_local_ip()}:{_DEFAULT_FLASK_PORT}/settings"
        print(f"[web] Config interface: {url}", flush=True)
        _render_splash(matrix, canvas, url, Image, qrcode, ERROR_CORRECT_L)

        # -- Phase 3: Kick off background loading -----------------------------
        # Start heavy imports (FR24 API, Flask, scenes, fonts) in a background
        # thread so they overlap with the splash screen display time.
        result = {}
        bg_thread = threading.Thread(
            target=_background_load,
            args=(matrix, canvas, result),
            daemon=True,
            name="background-load",
        )
        bg_thread.start()

        # Wait the minimum 8 seconds (or indefinitely if no config yet)
        cfg_existed = CONFIG_PATH.exists()
        deadline = time.time() + 8
        while True:
            time.sleep(0.5)
            if time.time() >= deadline and (cfg_existed or CONFIG_PATH.exists()):
                break
    else:
        # No web UI — brief splash only
        _render_splash(matrix, canvas, f"http://{_local_ip()}:{_DEFAULT_FLASK_PORT}/settings", Image, qrcode, ERROR_CORRECT_L)
        result = {}
        bg_thread = threading.Thread(
            target=_background_load,
            args=(matrix, canvas, result),
            daemon=True,
            name="background-load",
        )
        bg_thread.start()
        time.sleep(2)

    # -- Phase 4: Wait for background loading to finish -----------------------
    bg_thread.join()

    if 'error' in result:
        print(f"[startup] Background load failed: {result['error']}", file=sys.stderr)
        sys.exit(1)

    display = result['display']

    # -- Phase 5: Run the main display loop -----------------------------------
    display.run()
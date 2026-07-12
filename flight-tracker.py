import logging
import os
import socket
import sys
import threading
import time

from PIL import Image

# -- Phase 1: Minimal imports for the splash screen -----------------------
# Only the panel factory + PIL + qrcode are needed here.  Imported before the
# background threads start to avoid GIL contention with heavy imports.
from display.panel_factory import get_panel
from setup.configuration import CONFIG_PATH, Config
from setup.logging import setup_logging
from utilities.cli import dispatch_cli_command
from version import VERSION

panel = get_panel()
# Font loading doesn't require the matrix to be initialised
loading_font = panel.load_font(
    os.path.join(os.path.dirname(__file__), "fonts", "4x6.bdf")
)
test_font = panel.load_font(os.path.join(os.path.dirname(__file__), "fonts", "4x6.bdf"))

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_L
except ImportError:
    qrcode = None
    ERROR_CORRECT_L = None

SPLASH_TIMEOUT = 5  # seconds to show the splash screen before switching to display


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def _check_data_source(cfg: Config) -> bool:
    """Return True if the configured data source endpoint is reachable."""
    import requests

    try:
        if cfg.data_source == "fr24":
            requests.get(
                "https://data-cloud.flightradar24.com/zones/fcgi/feed.js",
                timeout=5,
            )
            return True
        elif cfg.data_source == "osn":
            requests.get(
                "https://opensky-network.org/api/states/all",
                timeout=5,
            )
            return True
        elif cfg.data_source == "tar1090":
            if not cfg.tar1090_url:
                return False
            requests.get(cfg.tar1090_url, timeout=5)
            return True
    except Exception:
        return False
    return False


def _check_celestrack() -> bool:
    """Return True if the configured TLE source is reachable."""
    import requests

    try:
        requests.get("https://celestrak.org/NORAD/elements/gp.php", timeout=5)
        return True
    except Exception:
        return False


def _render_ip_address(panel, canvas, y):
    from setup.colours import GREY

    ip = local_ip()
    panel.draw_text(canvas, test_font, 1, y, GREY, ip)
    panel.swap(canvas)


def _render_celestrack_test(panel, canvas, cfg: Config, y):
    from setup.colours import GREEN, GREY, ORANGE, RED

    panel.draw_text(canvas, test_font, 1, y, GREY, "TLE: ")
    panel.swap(canvas)

    if not cfg.satellite_tracking_enabled:
        result_text = "OFF"
        result_colour = ORANGE
    else:
        working = _check_celestrack()
        result_text = "OK" if working else "FAIL"
        result_colour = GREEN if working else RED

    # Right-align the result label on the 64px-wide screen
    result_width = len(result_text) * 4
    panel.draw_text(
        canvas, test_font, 64 - result_width - 1, y, result_colour, result_text
    )
    panel.swap(canvas)


def _render_data_source_test(panel, canvas, cfg: Config, y):
    from setup.colours import GREEN, GREY, RED

    labels = {
        "fr24": "FR24: ",
        "osn": "OSN: ",
        "tar1090": "TAR: ",
    }
    label = labels.get(cfg.data_source, "?: ")
    panel.draw_text(canvas, test_font, 1, y, GREY, label)
    panel.swap(canvas)

    ok = _check_data_source(cfg)
    result_text = "OK" if ok else "FAIL"
    result_colour = GREEN if ok else RED
    # Right-align the result label on the 64px-wide screen
    result_width = len(result_text) * 4
    panel.draw_text(
        canvas, test_font, 64 - result_width - 1, y, result_colour, result_text
    )
    panel.swap(canvas)


def render_tests(panel, canvas):
    from time import sleep

    from setup.configuration import Config

    cfg = Config.instance()

    _render_data_source_test(panel, canvas, cfg, 5)
    _render_celestrack_test(panel, canvas, cfg, 13)
    _render_ip_address(panel, canvas, 31)

    panel.swap(canvas)
    sleep(2)


def render_splash(
    panel,
    canvas,
    Image,
    loading_font,
    url=None,
    qrcode=None,
    ERROR_CORRECT_L=None,
):
    """
    Render the splash BMP to canvas and swap it onto the display.
    """
    # Read raw bytes and set pixels manually (works on both Pi 3/4 and Pi 5).
    splash_path = os.path.join(os.path.dirname(__file__), "assets", "splash.bmp")
    splash = Image.open(splash_path)
    pixels = splash.tobytes()
    for y in range(32):
        for x in range(64):
            i = (y * 64 + x) * 3
            panel.set_pixel(canvas, x, y, pixels[i], pixels[i + 1], pixels[i + 2])

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
                    panel.set_pixel(canvas, px, py, v, v, v)
    else:
        # Loading state: dim white "loading..." at top-left while Flask starts.
        from setup.colours import WHITE

        dim = WHITE.__class__(180, 180, 180)
        panel.draw_text(canvas, loading_font, 1, 20, dim, "Loading...")
        panel.draw_text(
            canvas, loading_font, 1, 28, dim, f"v{'.'.join(map(str, VERSION))}"
        )

    panel.swap(canvas)


def flask_load(ready_event: threading.Event, result: dict):
    """
    Thread A: import and start the Flask config server.

    make_server() binds the port synchronously, so by the time ready_event
    is set Flask can already accept connections.  serve_forever() is handed
    off to a daemon thread so this function can return promptly.
    """
    try:
        import logging

        from werkzeug.serving import make_server

        from web.app import FLASK_PORT, app

        logging.getLogger("werkzeug").setLevel(logging.ERROR)

        server = make_server("0.0.0.0", FLASK_PORT, app, threaded=True)
        # Prevent the inheritable socket flag causing "Address already in use"
        # if the process is restarted via os.execv.
        server.socket.set_inheritable(False)

        logging.getLogger("startup").info(
            "Flask config server bound on port %d", FLASK_PORT
        )

        # Port is bound - signal the main thread to show the QR code.
        ready_event.set()

        threading.Thread(
            target=server.serve_forever,
            daemon=True,
            name="flask-config",
        ).start()

        result["flask_started"] = True

    except Exception as exc:
        result["flask_error"] = exc
        logging.getLogger("startup").error("Flask startup failed: %s", exc)
        import traceback

        traceback.print_exc(file=sys.stderr)
        # Unblock the main thread even on failure so startup doesn't hang.
        ready_event.set()


def display_load(panel, canvas, result: dict):
    """
    Thread B: import and build the Display class (heavy: FR24 API, scenes, fonts).

    Runs in parallel with flask_load so both complete during the splash window.
    """
    try:
        from display import get_display_class

        DisplayClass = get_display_class()
        display = DisplayClass(matrix=panel, canvas=canvas)
        result["display"] = display
        logging.getLogger("startup").info("Display class built successfully")

    except Exception as exc:
        result["error"] = exc
        logging.getLogger("startup").error("Display build failed: %s", exc)
        import traceback

        traceback.print_exc(file=sys.stderr)


def load_full_interface(panel, canvas, cfg: Config):
    url = f"http://{local_ip()}:{cfg.web_port}/settings"
    print(f"[web] Config interface: {url}", flush=True)

    result: dict = {}
    flask_ready = threading.Event()

    # Thread A: Flask (fast - just binds a port)
    flask_thread = threading.Thread(
        target=flask_load,
        args=(flask_ready, result),
        daemon=True,
        name="flask-load",
    )
    # Thread B: Display class (slow - FR24 API, scenes, fonts)
    display_thread = threading.Thread(
        target=display_load,
        args=(panel, canvas, result),
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
        render_splash(
            panel,
            canvas,
            Image,
            loading_font,
            url,
            qrcode,
            ERROR_CORRECT_L,
        )

    cfg_existed = CONFIG_PATH.exists()
    deadline = time.time() + SPLASH_TIMEOUT
    while True:
        time.sleep(0.5)
        if time.time() >= deadline and (cfg_existed or CONFIG_PATH.exists()):
            break

    # -- Phase 4: Wait for display build to finish ------------------------
    display_thread.join()
    flask_thread.join()

    return result


def load_minimum_interface(panel, canvas, cfg: Config):
    # No web UI - brief splash, then build display in the background.
    result: dict = {}
    display_thread = threading.Thread(
        target=display_load,
        args=(panel, canvas, result),
        daemon=True,
        name="display-load",
    )
    display_thread.start()
    time.sleep(2)
    display_thread.join()
    return result


def run_flight_tracker():
    setup_logging()
    logger = logging.getLogger("startup")

    cfg = Config.instance()
    logger.info("FlightTracker starting (log level: %s)", cfg.log_level)

    # Initialise matrix once with full config values
    panel.init_matrix(
        width=64,
        height=32,
        brightness=cfg.brightness_percent,
        rotation=180 if cfg.screen_rotate else 0,
        hat_pwm=cfg.hat_pwm_enabled,
        gpio_slowdown=cfg.gpio_slowdown,
    )
    canvas = panel.create_canvas()
    panel.clear(canvas)
    logger.info(
        "RGB matrix initialised (64x32, brightness %d%%)",
        cfg.brightness_percent,
    )

    # -- Phase 2: Show start-up tests --------------------------
    render_tests(panel, canvas)

    # -- Phase 3: Show splash (loading state, no QR) --------------------------
    render_splash(panel, canvas, Image, loading_font)

    # -- Phase 4: Start web interface --------------------------
    result = {}

    if cfg.web_interface_enabled:
        logger.info("Web interface enabled - starting full interface")
        result = load_full_interface(panel, canvas, cfg)

    else:
        logger.info("Web interface disabled - starting minimum interface")
        result = load_minimum_interface(panel, canvas, cfg)

    if "error" in result:
        logger.error("Display build failed: %s", result["error"])
        print(f"[startup] Display build failed: {result['error']}", file=sys.stderr)
        sys.exit(1)

    display = result["display"]
    logger.info("Display built - entering main loop")

    # -- Phase 5: Run the main display loop -----------------------------------
    display.run()


def _config_exists() -> bool:
    return CONFIG_PATH.exists()


def _warn_no_config() -> None:
    print(f"No config found at {CONFIG_PATH}", file=sys.stderr)
    print(
        "Run the application once or create a config before using this command.",
        file=sys.stderr,
    )


def _load_existing_config() -> Config | None:
    if not _config_exists():
        _warn_no_config()
        return None
    return Config.instance()


def _save_config_change(key: str, value) -> int:
    cfg = _load_existing_config()
    if cfg is None:
        return 1
    cfg.set(key, value)
    cfg.save()
    print(f"Updated {key} in {CONFIG_PATH}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) == 1:
        run_flight_tracker()
    else:
        sys.exit(dispatch_cli_command(sys.argv))

import contextlib
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
from setup.configuration import CONFIG_PATH, PLATFORM_DATA_DIR, Config
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
    """Return True if the top enabled flight provider's endpoint is reachable."""
    from scenes.flight.lookups.flights import startup_check as flights_startup_check

    try:
        return flights_startup_check()
    except Exception:
        return False


def _check_celestrack() -> bool:
    """Return True if the configured TLE source is reachable."""
    import requests

    try:
        requests.get("https://celestrak.org/NORAD/elements/gp.php", timeout=5)
        return True
    except Exception:
        return False


def _check_routing_reachable(cfg: Config) -> bool:
    """Return True if at least one enabled route provider is reachable."""
    from scenes.flight.lookups.routes import check_routing

    return check_routing()


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
    panel.draw_text(canvas, test_font, 64 - result_width, y, result_colour, result_text)
    panel.swap(canvas)


def _render_data_source_test(panel, canvas, cfg: Config, y):
    from scenes.flight.lookups.flights import top_flight_provider
    from setup.colours import GREEN, GREY, RED

    pid, _name = top_flight_provider()
    label = {
        "fr24": "FR24: ",
        "opensky": "OSN: ",
        "tar1090": "TAR: ",
    }.get(pid, "FLY: ")
    panel.draw_text(canvas, test_font, 1, y, GREY, label)
    panel.swap(canvas)

    ok = _check_data_source(cfg)
    result_text = "OK" if ok else "FAIL"
    result_colour = GREEN if ok else RED
    # Right-align the result label on the 64px-wide screen
    result_width = len(result_text) * 4
    panel.draw_text(canvas, test_font, 64 - result_width, y, result_colour, result_text)
    panel.swap(canvas)


def _render_routing_test(panel, canvas, cfg: Config, y):
    from setup.colours import GREEN, GREY, RED

    panel.draw_text(canvas, test_font, 1, y, GREY, "ROUTE: ")
    panel.swap(canvas)

    working = _check_routing_reachable(cfg)
    result_text = "OK" if working else "FAIL"
    result_colour = GREEN if working else RED

    result_width = len(result_text) * 4
    panel.draw_text(canvas, test_font, 64 - result_width, y, result_colour, result_text)
    panel.swap(canvas)


def render_tests(panel, canvas):
    from time import sleep

    from setup.configuration import Config

    cfg = Config.instance()

    _render_data_source_test(panel, canvas, cfg, 5)
    _render_celestrack_test(panel, canvas, cfg, 11)
    _render_routing_test(panel, canvas, cfg, 17)
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
        panel.draw_text(canvas, loading_font, 1, 20, dim, "Loading")
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


def _warn_if_root() -> None:
    """Print a root-related advisory to stderr.

    If the process is running as root, warn that this is not recommended
    for security reasons.  If not running as root, note that the RGB
    matrix driver may still print a root-related message to stderr and
    that it can be safely ignored.

    On platforms where ``os.geteuid`` is unavailable (e.g. Windows) the
    check is skipped and the application continues to load as expected.
    """
    try:
        is_root = os.geteuid() == 0
    except AttributeError:
        # os.geteuid() is not available on this platform (e.g. Windows).
        return

    if is_root:
        print(
            "[startup] Warning: running as root.  This is not recommended "
            "for security reasons.",
            file=sys.stderr,
        )
    else:
        print(
            "[startup] Note: the RGB matrix driver may print a message about "
            "running as root - this is safe to ignore providing you gave python "
            "real-time permissions during installation.",
            file=sys.stderr,
        )


def apply_pending_config_update() -> None:
    """Swap a staged config import into place before the app boots.

    The web import flow writes ``config-update.json`` and reboots.  This
    function runs at the very start of boot - before logging or
    ``Config.instance()`` - to atomically swap it into ``config.json``,
    preserving the previous config as ``config-backup.json``.

    A ``.import-in-progress`` marker records that a swap has happened.  If
    the process crashes before :func:`cleanup_successful_import` removes
    it, the next boot sees the marker still present, restores the backup,
    and writes a ``.import-failed`` marker so the web UI can notify the
    user.

    This logic lives only in the boot path - CLI commands and other entry
    points are unaffected.
    """
    update_path = PLATFORM_DATA_DIR / "config-update.json"
    backup_path = PLATFORM_DATA_DIR / "config-backup.json"
    in_progress = PLATFORM_DATA_DIR / ".import-in-progress"
    failed_marker = PLATFORM_DATA_DIR / ".import-failed"

    # A previous import failed and was already restored - leave the marker
    # for the UI to read this boot, then nothing else to do.
    if failed_marker.exists():
        return

    # Check for a crash FIRST: the marker survives a crash, but the
    # config-update.json that triggered the swap has already been consumed
    # (renamed to config.json), so we can't gate on its presence here.
    if in_progress.exists():
        # Previous boot crashed mid-import: restore the backup.
        print(
            "[startup] Previous config import crashed - restoring backup",
            file=sys.stderr,
        )
        try:
            if backup_path.exists():
                os.replace(backup_path, CONFIG_PATH)
        except OSError as exc:
            print(f"[startup] Failed to restore config backup: {exc}", file=sys.stderr)
        with contextlib.suppress(OSError):
            update_path.unlink()
        with contextlib.suppress(OSError):
            in_progress.unlink()
        with contextlib.suppress(OSError):
            failed_marker.touch()
        return

    # No crash marker - check for a fresh staged import.
    if not update_path.exists():
        return

    # Fresh import: swap config.json -> config-backup.json,
    # config-update.json -> config.json, write marker.
    try:
        if CONFIG_PATH.exists():
            os.replace(CONFIG_PATH, backup_path)
        os.replace(update_path, CONFIG_PATH)
        in_progress.touch()
        print("[startup] Staged config import applied", file=sys.stderr)
    except OSError as exc:
        print(f"[startup] Failed to apply config import: {exc}", file=sys.stderr)
        # Roll back if we got partway.
        with contextlib.suppress(OSError):
            if backup_path.exists() and not CONFIG_PATH.exists():
                os.replace(backup_path, CONFIG_PATH)
        with contextlib.suppress(OSError):
            update_path.unlink()


def cleanup_successful_import() -> None:
    """Discard the backup and marker after boot completes successfully.

    Called once ``app_ready.set()`` fires, meaning the app booted without
    crashing.  The imported config is now confirmed good, so the backup is
    no longer needed.
    """
    backup_path = PLATFORM_DATA_DIR / "config-backup.json"
    in_progress = PLATFORM_DATA_DIR / ".import-in-progress"
    with contextlib.suppress(OSError):
        backup_path.unlink()
    with contextlib.suppress(OSError):
        in_progress.unlink()


def run_flight_tracker(disable_tests: bool = False):
    # Apply any staged config import before anything else initialises.
    apply_pending_config_update()

    setup_logging()
    logger = logging.getLogger("startup")

    _warn_if_root()

    cfg = Config.instance()
    logger.info("FlightTracker starting (log level: %s)", cfg.log_level)

    # Initialise matrix once with full config values
    panel.init_matrix(
        width=64,
        height=64 if cfg.display_scan_rate == 32 else 32,
        brightness=cfg.brightness_percent,
        rotation=180 if cfg.screen_rotate else 0,
        hat_pwm=cfg.hat_pwm_enabled,
        gpio_slowdown=cfg.gpio_slowdown,
        colour_order=cfg.panel_colour_order,
    )
    canvas = panel.create_canvas()
    panel.clear(canvas)
    logger.info(
        "RGB matrix initialised (64x32, brightness %d%%)",
        cfg.brightness_percent,
    )

    # -- Phase 2: Show start-up tests --------------------------
    if not disable_tests:
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

    if cfg.web_interface_enabled:
        try:
            from web.app import app_ready

            app_ready.set()
        except Exception:
            pass

    # Boot completed successfully - discard any import backup/marker.
    cleanup_successful_import()

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
    if "--disable-tests" in sys.argv:
        sys.argv.remove("--disable-tests")
        if len(sys.argv) == 1:
            run_flight_tracker(disable_tests=True)
        else:
            sys.exit(dispatch_cli_command(sys.argv))
    elif len(sys.argv) == 1:
        run_flight_tracker()
    else:
        sys.exit(dispatch_cli_command(sys.argv))

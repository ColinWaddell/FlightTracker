import os
import socket
import sys
import threading
import time

from setup.configuration import Config, CONFIG_PATH


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


def _show_boot_screen(matrix, canvas, cfg_existed: bool):
    """
    Splash-image boot screen with QR code overlaid at the top-left.

    Loads assets/splash.bmp (64x32) via PIL and pushes it to the canvas
    with SetImage, then paints QR modules on top at (0, 0).
    Waits at least 8 s (or indefinitely if no config.json exists yet).
    The frame is left on screen after the deadline; the animator overwrites
    it on its first render pass.
    """
    from PIL import Image
    from web.app import FLASK_PORT

    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_L
    except ImportError:
        qrcode = None

    url = f"http://{_local_ip()}:{FLASK_PORT}"
    print(f"[web] Config interface: {url}/settings")

    # -- Load splash image ----------------------------------------------------
    splash_path = os.path.join(os.path.dirname(__file__), "assets", "splash.bmp")
    splash = Image.open(splash_path)
    canvas.SetImage(splash)

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
                if 0 <= qx < 64 and 0 <= qy < 32:
                    if cell:
                        canvas.SetPixel(qx, qy, 0, 0, 0)
                    else:
                        canvas.SetPixel(qx, qy, 255, 255, 255)

    matrix.SwapOnVSync(canvas)

    # -- Wait out the minimum display period ----------------------------------
    deadline = time.time() + 8
    while True:
        time.sleep(0.5)
        if time.time() >= deadline and (cfg_existed or CONFIG_PATH.exists()):
            break
    # Frame stays on screen; display.run() overwrites it on first render pass


if __name__ == "__main__":
    cfg = Config.instance()

    from display import Display

    display = Display()

    if cfg.web_interface_enabled:
        cfg_existed = CONFIG_PATH.exists()
        _start_flask_daemon()
        _show_boot_screen(display.matrix, display.canvas, cfg_existed)

    display.run()

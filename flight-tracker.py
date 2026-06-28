import math
import random
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
    Static plasma boot screen with centred QR code.

    A single plasma frame is generated from a random seed, painted once,
    and left on screen until the animator overwrites it on its first pass.
    Waits at least 8 s (or indefinitely if no config.json exists yet).
    """
    from rgbmatrix import graphics
    from web.app import FLASK_PORT

    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_L
    except ImportError:
        qrcode = None

    url = f"http://{_local_ip()}:{FLASK_PORT}"
    print(f"[web] Config interface: {url}/settings")

    # -- Pre-compute QR module grid ----------------------------------------
    qr_modules = None
    qr_size = 0
    x_offset = 0
    y_offset = 0

    if qrcode is not None:
        qr = qrcode.QRCode(
            version=1,
            error_correction=ERROR_CORRECT_L,
            box_size=1,
            border=1,
        )
        qr.add_data(url)
        qr.make(fit=True)
        qr_modules = qr.get_matrix()
        qr_size = len(qr_modules)
        x_offset = max(0, (64 - qr_size) // 2)
        y_offset = max(0, (32 - qr_size) // 2)

    # -- HSV → RGB helper -------------------------------------------------
    def _hsv(h):
        h = h % 360
        hi = int(h / 60)
        f = (h / 60) - hi
        q = int((1 - f) * 255)
        t_ = int(f * 255)
        return (
            (255, t_, 0),
            (q, 255, 0),
            (0, 255, t_),
            (0, q, 255),
            (t_, 0, 255),
            (255, 0, q),
        )[hi]

    # -- Draw a single plasma frame at a random time offset ----------------
    t = random.uniform(0, 100)

    for y in range(32):
        for x in range(64):
            qx, qy = x - x_offset, y - y_offset
            if qr_modules and 0 <= qx < qr_size and 0 <= qy < qr_size:
                if qr_modules[qy][qx]:
                    canvas.SetPixel(x, y, 0, 0, 0)
                else:
                    canvas.SetPixel(x, y, 255, 255, 255)
                continue

            v = math.sin(x / 5.0 + t)
            v += math.sin(y / 3.0 + t * 1.3)
            v += math.sin((x + y) / 7.0 + t * 0.7)
            v += math.sin(math.sqrt((x - 32) ** 2 + (y - 16) ** 2) / 5.0 + t * 0.9)
            hue = (v * 45.0 + t * 40.0) % 360
            r, g, b = _hsv(hue)
            canvas.SetPixel(x, y, r, g, b)

    matrix.SwapOnVSync(canvas)

    # -- Wait out the minimum display period ------------------------------
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

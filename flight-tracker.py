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

    server = make_server("0.0.0.0", FLASK_PORT, app)
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
    Render a QR code pointing to the config UI, centred on the display.
    Background is 80% white; modules are black.
    Always shown for at least 5 s. If no config.json existed at launch,
    stays up indefinitely until the user saves one.
    After the deadline the QR is left on screen — the animator will
    overwrite it naturally once rendering begins.
    """
    from rgbmatrix import graphics
    from web.app import FLASK_PORT

    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_L
    except ImportError:
        qrcode = None

    off_white = graphics.Color(204, 204, 204)   # ~80 % white
    black     = graphics.Color(0, 0, 0)
    url = f"http://{_local_ip()}:{FLASK_PORT}"

    def _render():
        canvas.Clear()

        # Fill entire canvas with off-white
        for x in range(64):
            graphics.DrawLine(canvas, x, 0, x, 31, off_white)

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
            x_offset = max(0, (64 - qr_size) // 2)
            y_offset = max(0, (32 - qr_size) // 2)

            for row_idx, row in enumerate(modules):
                for col_idx, cell in enumerate(row):
                    x = x_offset + col_idx
                    y = y_offset + row_idx
                    if 0 <= x < 64 and 0 <= y < 32 and cell:
                        canvas.SetPixel(x, y, black.red, black.green, black.blue)

        matrix.SwapOnVSync(canvas)

    print(f"[web] Config interface: {url}/settings")

    deadline = time.time() + 5

    _render()
    while True:
        time.sleep(0.5)
        if time.time() >= deadline and (cfg_existed or CONFIG_PATH.exists()):
            break
    # QR remains visible; display.run() will overwrite it on its first frame


if __name__ == "__main__":
    cfg = Config.instance()

    from display import Display

    display = Display()

    if cfg.web_interface_enabled:
        cfg_existed = CONFIG_PATH.exists()
        _start_flask_daemon()
        _show_boot_screen(display.matrix, display.canvas, cfg_existed)

    display.run()

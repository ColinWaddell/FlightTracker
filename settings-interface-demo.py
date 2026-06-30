#!/usr/bin/env python3
"""
Standalone settings-interface demo.

Runs the FlightTracker web config UI without any display / GPIO / matrix
hardware.  Useful for tinkering with the settings page on a desktop/laptop.

Usage:
    python settings-interface-demo.py

Then open http://localhost:8584/settings in a browser.
Default password: flighttracker
"""

import os
import sys
import socket

# Ensure the project root is on sys.path so that 'web.app' and
# 'setup.configuration' can be imported.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)


def local_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


def patch_restart():
    """
    Replace the real os.execv restart with a harmless print + config reload.

    The production code calls os.execv to restart the whole process after
    saving settings.  In the demo we just reload Config from disk so the
    new values are visible immediately without killing the server.
    """
    import web.app as web_app

    def fake_restart_after(delay: float = 1.0):
        import time
        from setup.configuration import Config

        time.sleep(delay)
        Config.reload()
        print("[demo] Config reloaded (fake restart)", flush=True)

    web_app.restart_after = fake_restart_after
    print("[demo] Patched restart -> config reload only", flush=True)


def main():
    patch_restart()

    from web.app import app, FLASK_PORT

    ip = local_ip()
    url = f"http://{ip}:{FLASK_PORT}"
    print(f"\n{'='*60}")
    print(f"  FlightTracker Settings Demo")
    print(f"  Open: {url}/settings")
    print(f"  Default password: flighttracker")
    print(f"{'='*60}\n")

    # Flask dev server - threaded, with reloader disabled so the patched
    # restart doesn't get clobbered by a watchdog reload.
    app.run(
        host="0.0.0.0",
        port=FLASK_PORT,
        debug=False,
        use_reloader=False,
    )


if __name__ == "__main__":
    main()

"""
FlightTracker web configuration interface.

Runs as a Flask daemon thread on port 8584.
GET  /           → redirect to /settings
GET  /settings   → settings form (current config values)
POST /settings   → save config.json, return restarting page, exec after 1 s
GET  /ping       → health-check used by the restarting page to detect when
                   the server is back up
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

from setup.configuration import Config, CONFIG_PATH

FLASK_PORT = 8584

app = Flask(__name__, template_folder="templates")
app.secret_key = "flighttracker-web-config"


# ---------------------------------------------------------------------------
# Coerce helpers
# ---------------------------------------------------------------------------

def _str(v, default="") -> str:
    return str(v) if v is not None else default


def _int(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _float(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _bool(v) -> bool:
    """HTML checkboxes send 'on' when checked, nothing when unchecked."""
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("on", "true", "1", "yes")


# ---------------------------------------------------------------------------
# Restart helper
# ---------------------------------------------------------------------------

def _restart_after(delay: float = 1.0):
    """Schedule os.execv to run after `delay` seconds on a daemon thread."""
    def _do_restart():
        import time
        time.sleep(delay)
        print(f"[web] Restarting process: {sys.executable} {sys.argv}", flush=True)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    t = threading.Thread(target=_do_restart, daemon=True, name="restart")
    t.start()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return redirect(url_for("settings"))


@app.route("/ping")
def ping():
    """Lightweight health-check used by the restarting page."""
    return "ok", 200


@app.route("/settings", methods=["GET", "POST"])
def settings():
    cfg = Config.instance()

    if request.method == "POST":
        form = request.form
        print("[web] POST /settings received", flush=True)
        print(f"[web] Raw form keys: {list(form.keys())}", flush=True)

        try:
            new_data = {
                # Location / flight zone
                "flight_lat":           _float(form.get("flight_lat"),      cfg.flight_lat),
                "flight_lng":           _float(form.get("flight_lng"),      cfg.flight_lng),
                "flight_radius":        _float(form.get("flight_radius"),   cfg.flight_radius),
                "flight_min_altitude":  _float(form.get("flight_min_altitude"), cfg.flight_min_altitude),
                "flight_max_altitude":  _float(form.get("flight_max_altitude"), cfg.flight_max_altitude),
                # Airport display
                "home_airport_code":    _str(form.get("home_airport_code")).upper()[:4],
                "full_airport_name":    _bool(form.get("full_airport_name")),
                "abbreviate_name":      _bool(form.get("abbreviate_name")),
                "journey_blank_filler": _str(form.get("journey_blank_filler"), " ? "),
                # Plane info row
                "details":              _int(form.get("details"), 0),
                # Weather
                "weatherapi_key":  _str(form.get("weatherapi_key"),  cfg.weatherapi_key),
                "weather_mode":    _int(form.get("weather_mode"),    0),
                "units":           _str(form.get("units"),           "m"),
                # Display
                "theme":                _int(form.get("theme"), 0),
                "screen_brightness":    max(1, min(5, _int(form.get("screen_brightness"), 3))),
                "screen_rotate":        _bool(form.get("screen_rotate")),
                # Brightness schedule
                "screen_schedule_enabled":    _bool(form.get("screen_schedule_enabled")),
                "screen_schedule_start":      _str(form.get("screen_schedule_start"),     "22:00"),
                "screen_schedule_end":        _str(form.get("screen_schedule_end"),       "07:00"),
                "screen_schedule_brightness": max(0, min(5, _int(form.get("screen_schedule_brightness"), 0))),
                # Clock / date
                "clock_24hr":  _bool(form.get("clock_24hr")),
                "timezone":    _str(form.get("timezone"),    cfg.timezone),
                "date_format": _int(form.get("date_format"), 0),
                # Web interface
                "web_interface_enabled": _bool(form.get("web_interface_enabled")),
                # Hardware
                "gpio_slowdown":        max(1, min(4, _int(form.get("gpio_slowdown"), 1))),
                "hat_pwm_enabled":      _bool(form.get("hat_pwm_enabled")),
                "loading_led_enabled":  _bool(form.get("loading_led_enabled")),
                "loading_led_gpio_pin": _int(form.get("loading_led_gpio_pin"), 25),
                # Data source
                "tar1090_url": _str(form.get("tar1090_url"), ""),
            }

            print(f"[web] Parsed settings: {new_data}", flush=True)

            cfg.update(new_data)
            cfg.save()
            print(f"[web] Config saved to {CONFIG_PATH}", flush=True)

        except Exception as exc:
            print(f"[web] ERROR processing form: {exc}", flush=True)
            import traceback
            traceback.print_exc()
            return render_template("settings.html", cfg=cfg.as_dict(),
                                   airports_json=_airports_json(),
                                   error=str(exc)), 500

        # Respond first, then exec — otherwise the browser gets a connection
        # reset and appears to do nothing.
        _restart_after(delay=1.0)
        return render_template("restarting.html")

    # GET
    return render_template(
        "settings.html",
        cfg=cfg.as_dict(),
        airports_json=_airports_json(),
    )


def _airports_json() -> str:
    airports_path = Path(__file__).parent.parent / "assets" / "airports.json"
    try:
        with open(airports_path) as fh:
            return fh.read()
    except Exception:
        return "{}"

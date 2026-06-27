"""
FlightTracker web configuration interface.

Runs as a Flask daemon thread on port 8584.
GET  /          → redirect to /settings
GET  /settings  → settings form (current config values)
POST /settings  → save config.json, then restart the process via os.execv
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for

from setup.configuration import Config, DEFAULTS, CONFIG_PATH

FLASK_PORT = 8584

app = Flask(__name__, template_folder="templates")
# Secret key only used for flashing messages - not security-critical here
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
# Routes
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return redirect(url_for("settings"))


@app.route("/settings", methods=["GET", "POST"])
def settings():
    cfg = Config.instance()

    if request.method == "POST":
        form = request.form

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

        cfg.update(new_data)
        cfg.save()

        # Restart the main process so all new settings take effect
        os.execv(sys.executable, [sys.executable] + sys.argv)

    # GET
    values = cfg.as_dict()
    airports_path = Path(__file__).parent.parent / "assets" / "airports.json"
    try:
        with open(airports_path) as fh:
            airports_json = fh.read()
    except Exception:
        airports_json = "{}"

    return render_template(
        "settings.html",
        cfg=values,
        airports_json=airports_json,
    )

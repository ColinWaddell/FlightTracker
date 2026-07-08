"""
FlightTracker web configuration interface.

Runs as a Flask daemon thread on port 8584.
GET  /               -> redirect to /settings
GET  /login          -> login form
POST /login          -> check password, set session
GET  /logout         -> clear session, redirect to /login
GET  /settings       -> settings form (requires login)
POST /settings       -> save config.json, return restarting page, exec after 1 s
GET  /ping           -> health-check used by the restarting page
GET  /update         -> update status page (requires login)
POST /update/check   -> check for updates, return JSON (requires login)
POST /update/apply   -> apply update via git + pip, then restart (requires login)
GET  /debug-config   -> download config JSON with secrets redacted
GET  /logs           -> view in-memory log buffer
GET  /logs/download  -> download full log buffer as .txt
"""

from __future__ import annotations

import functools
import hashlib
import logging
import os
import secrets
import sys
import threading
from pathlib import Path

from flask import Flask, Response, redirect, render_template, request, session, url_for

from setup.configuration import Config, CONFIG_PATH
from setup.logging import get_buffer
from utilities.updater import get_update_info, perform_update, version_string
from version import VERSION

# Port is read from config.json via Config.web_port (default 8584).
FLASK_PORT = Config.instance().web_port

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)

logger = logging.getLogger("web")


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def check_password(password: str) -> bool:
    return hash_password(password) == Config.instance().web_password_hash


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_hex(16)
        session["csrf_token"] = token
    return token


def validate_csrf(form) -> bool:
    return str(form.get("csrf_token", "")) == session.get("csrf_token")


def login_required(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("authenticated"):
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)

    return decorated


# ---------------------------------------------------------------------------
# Coerce helpers
# ---------------------------------------------------------------------------


def str_val(v, default="") -> str:
    return str(v) if v is not None else default


def int_val(v, default=0) -> int:
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def float_val(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def bool_val(v) -> bool:
    """HTML checkboxes send 'on' when checked, nothing when unchecked."""
    if isinstance(v, bool):
        return v
    return str(v).lower() in ("on", "true", "1", "yes")


# ---------------------------------------------------------------------------
# Restart helper
# ---------------------------------------------------------------------------


def restart_after(delay: float = 1.0):
    """Schedule os.execv after `delay` seconds on a daemon thread."""

    def do_restart():
        import time

        time.sleep(delay)
        logger.info("Restarting process: %s %s", sys.executable, sys.argv)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    threading.Thread(target=do_restart, daemon=True, name="restart").start()


# ---------------------------------------------------------------------------
# Settings form parsing
# ---------------------------------------------------------------------------


def parse_settings_form(form, cfg) -> dict:
    """Coerce the submitted HTML form into a config dict, applying clamps."""
    return {
        # Location / flight zone
        "flight_lat": float_val(form.get("flight_lat"), cfg.flight_lat),
        "flight_lng": float_val(form.get("flight_lng"), cfg.flight_lng),
        "flight_radius": float_val(form.get("flight_radius"), cfg.flight_radius),
        "flight_min_altitude": float_val(
            form.get("flight_min_altitude"), cfg.flight_min_altitude
        ),
        "flight_max_altitude": float_val(
            form.get("flight_max_altitude"), cfg.flight_max_altitude
        ),
        # Airport display
        "home_airport_code": str_val(form.get("home_airport_code")).upper()[:4],
        "full_airport_name": bool_val(form.get("full_airport_name")),
        "abbreviate_name": bool_val(form.get("abbreviate_name")),
        "journey_blank_filler": str_val(form.get("journey_blank_filler"), " ? "),
        # Plane info row
        "details": int_val(form.get("details"), 0),
        # Weather
        "weatherapi_key": str_val(form.get("weatherapi_key"), cfg.weatherapi_key),
        "weather_mode": int_val(form.get("weather_mode"), 0),
        "rain_sensitivity": max(0, min(2, int_val(form.get("rain_sensitivity"), 1))),
        "units": str_val(form.get("units"), "m"),
        # Display
        "theme": int_val(form.get("theme"), 0),
        "screen_brightness": max(1, min(5, int_val(form.get("screen_brightness"), 3))),
        "screen_rotate": bool_val(form.get("screen_rotate")),
        # Brightness schedule
        "screen_schedule_enabled": bool_val(form.get("screen_schedule_enabled")),
        "screen_schedule_auto": bool_val(form.get("screen_schedule_auto")),
        "screen_schedule_start": str_val(form.get("screen_schedule_start"), "22:00"),
        "screen_schedule_end": str_val(form.get("screen_schedule_end"), "07:00"),
        "screen_schedule_brightness": max(
            0, min(5, int_val(form.get("screen_schedule_brightness"), 0))
        ),
        # Clock / date
        "clock_24hr": bool_val(form.get("clock_24hr")),
        "date_format": int_val(form.get("date_format"), 0),
        # Web interface
        "web_interface_enabled": bool_val(form.get("web_interface_enabled")),
        "web_port": max(1024, min(65535, int_val(form.get("web_port"), cfg.web_port))),
        "log_level": (
            str_val(form.get("log_level"), cfg.log_level).upper()
            if str_val(form.get("log_level"), cfg.log_level).upper()
            in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL")
            else cfg.log_level
        ),
        # Hardware
        "gpio_slowdown": max(1, min(4, int_val(form.get("gpio_slowdown"), 1))),
        "hat_pwm_enabled": bool_val(form.get("hat_pwm_enabled")),
        "loading_led_enabled": bool_val(form.get("loading_led_enabled")),
        "loading_led_gpio_pin": int_val(form.get("loading_led_gpio_pin"), 25),
        # Data source
        "data_source": (
            "tar1090"
            if str_val(form.get("data_source"), "fr24").lower() == "tar1090"
            else "fr24"
        ),
        "tar1090_url": str_val(form.get("tar1090_url"), ""),
        "max_flight_lookup": max(1, int_val(form.get("max_flight_lookup"), 5)),
        # Satellite tracking
        "satellite_tracking_enabled": bool_val(form.get("satellite_tracking_enabled")),
        "satellite_norad_ids": [
            int(n.strip())
            for n in form.get("satellite_norad_ids", "").splitlines()
            if n.strip().isdigit()
        ],
        "satellite_min_elevation": max(
            0, min(90, int_val(form.get("satellite_min_elevation"), 20))
        ),
        "satellite_max_count": max(
            1, min(10, int_val(form.get("satellite_max_count"), 5))
        ),
    }


def handle_password_change(form, cfg) -> str:
    """Return the web_password_hash to store, raising on mismatch."""
    new_password = form.get("new_password", "").strip()
    confirm_password = form.get("confirm_password", "").strip()
    if new_password:
        if new_password != confirm_password:
            raise ValueError("New passwords do not match.")
        logger.info("Web password updated")
        return hash_password(new_password)
    # Preserve existing hash
    return cfg.web_password_hash


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return redirect(url_for("settings"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("settings"))

    error = None
    if request.method == "POST":
        if not validate_csrf(request.form):
            error = "Invalid request."
        else:
            password = request.form.get("password", "")
            logger.info("Login attempt")
            if check_password(password):
                session["authenticated"] = True
                logger.info("Login successful")
                next_url = request.args.get("next") or url_for("settings")
                return redirect(next_url)
            else:
                logger.warning("Login failed - wrong password")
                error = "Incorrect password."

    using_default_password = not bool(Config.instance().get("web_password_hash"))
    return render_template(
        "login.html",
        error=error,
        csrf_token=csrf_token(),
        using_default_password=using_default_password,
    )


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/settings", methods=["GET", "POST"])
@login_required
def settings():
    cfg = Config.instance()

    if request.method == "POST":
        form = request.form
        logger.info("POST /settings received")
        logger.debug("Raw form keys: %s", list(form.keys()))

        try:
            if not validate_csrf(form):
                raise ValueError("Invalid CSRF token.")

            new_data = parse_settings_form(form, cfg)
            new_data["web_password_hash"] = handle_password_change(form, cfg)

            logger.debug("Parsed settings: %s", new_data)

            cfg.update(new_data)
            cfg.save()
            logger.info("Config saved to %s", CONFIG_PATH)

        except Exception as exc:
            logger.error("Error processing settings form: %s", exc)
            import traceback

            traceback.print_exc()
            return (
                render_template(
                    "settings.html",
                    cfg=cfg.as_dict(),
                    airports_json=airports_json(),
                    error=str(exc),
                    csrf_token=csrf_token(),
                    in_schedule=cfg.is_in_brightness_schedule(),
                    schedule_window=cfg.brightness_schedule_window,
                    current_version=version_string(VERSION),
                ),
                400,
            )

        restart_after(delay=1.0)
        return render_template("restarting.html")

    return render_template(
        "settings.html",
        cfg=cfg.as_dict(),
        airports_json=airports_json(),
        csrf_token=csrf_token(),
        in_schedule=cfg.is_in_brightness_schedule(),
        schedule_window=cfg.brightness_schedule_window,
        current_version=version_string(VERSION),
    )


AIRPORTS_JSON: str | None = None


def load_airports_json() -> str:
    global AIRPORTS_JSON
    if AIRPORTS_JSON is None:
        airports_path = Path(__file__).parent.parent / "assets" / "airports.json"
        try:
            with open(airports_path) as fh:
                AIRPORTS_JSON = fh.read()
        except Exception:
            AIRPORTS_JSON = "{}"
    return AIRPORTS_JSON


def airports_json() -> str:
    return load_airports_json()


# Keys that may contain sensitive information and should be stripped from
# the debug config export.
SENSITIVE_KEYS = {"weatherapi_key", "web_password_hash"}


@app.route("/debug-config")
@login_required
def debug_config():
    """Return the current config as JSON with all API keys / passwords removed.

    Intended for users to safely share their configuration when requesting
    help via GitHub issues.
    """
    import json

    cfg = Config.instance()
    safe = {
        k: ("***REDACTED***" if k in SENSITIVE_KEYS and v else v)
        for k, v in cfg.as_dict().items()
    }
    payload = json.dumps(safe, indent=2, sort_keys=True)
    return Response(
        payload,
        mimetype="application/json",
        headers={
            "Content-Disposition": "attachment; filename=flighttracker-debug-config.json"
        },
    )


@app.route("/logs")
@login_required
def logs():
    """Show the most recent in-memory log entries (newest-first).

    Refresh the page to see new entries.  The buffer is capped at
    BUFFER_SIZE records and cleared on restart.
    """
    import datetime as _dt

    records = get_buffer().records()
    # Format the epoch timestamp into something readable once, server-side.
    rows = [
        {
            "time": _dt.datetime.fromtimestamp(r["time"]).strftime("%Y-%m-%d %H:%M:%S"),
            "level": r["level"],
            "source": r["source"],
            "message": r["message"],
        }
        for r in records
    ]
    return render_template("logs.html", rows=rows)


@app.route("/logs/download")
@login_required
def logs_download():
    """Return the full in-memory log buffer as a plain-text download.

    Intended for users to easily share their logs when requesting help.
    """
    import datetime as _dt

    records = get_buffer().records()
    lines = [
        f"{ _dt.datetime.fromtimestamp(r['time']).strftime('%Y-%m-%d %H:%M:%S') } "
        f"{ r['level']:<8} { r['source']:<20} { r['message'] }"
        for r in records
    ]
    payload = "\n".join(lines)
    return Response(
        payload,
        mimetype="text/plain",
        headers={
            "Content-Disposition": "attachment; filename=flighttracker-logs.txt"
        },
    )


# ---------------------------------------------------------------------------
# Update routes
# ---------------------------------------------------------------------------


@app.route("/update")
@login_required
def update():
    """Show the update status page."""
    info = get_update_info()
    return render_template("update.html", info=info, csrf_token=csrf_token())


@app.route("/update/check", methods=["POST"])
@login_required
def update_check():
    """Check for updates and return JSON status."""
    if not validate_csrf(request.form):
        return {"error": "Invalid CSRF token."}, 403
    info = get_update_info()
    return info, 200


@app.route("/update/apply", methods=["POST"])
@login_required
def update_apply():
    """Apply an update by checking out the given tag and restarting."""
    if not validate_csrf(request.form):
        return render_template(
            "update.html",
            info=get_update_info(),
            csrf_token=csrf_token(),
            error="Invalid CSRF token.",
        ), 403

    tag = request.form.get("tag", "").strip()
    if not tag:
        return render_template(
            "update.html",
            info=get_update_info(),
            csrf_token=csrf_token(),
            error="No tag specified.",
        ), 400

    logger.info("Applying update to tag %s", tag)
    success, message = perform_update(tag)

    if not success:
        logger.error("Update failed: %s", message)
        return render_template(
            "update.html",
            info=get_update_info(),
            csrf_token=csrf_token(),
            error=message,
        ), 500

    logger.info("Update succeeded, restarting...")
    restart_after(delay=2.0)
    return render_template("restarting.html")

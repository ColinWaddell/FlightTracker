"""
FlightTracker web configuration interface.

Runs as a Flask daemon thread on port 8584.
GET  /           → redirect to /settings
GET  /login      → login form
POST /login      → check password, set session
GET  /logout     → clear session, redirect to /login
GET  /settings   → settings form (requires login)
POST /settings   → save config.json, return restarting page, exec after 1 s
GET  /ping       → health-check used by the restarting page
"""

from __future__ import annotations

import functools
import hashlib
import os
import secrets
import sys
import threading
from pathlib import Path

from flask import Flask, redirect, render_template, request, session, url_for

from setup.configuration import Config, CONFIG_PATH

FLASK_PORT = 8584

app = Flask(__name__, template_folder="templates")
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or secrets.token_hex(32)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------


def _hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def _check_password(password: str) -> bool:
    return _hash_password(password) == Config.instance().web_password_hash


def _csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_hex(16)
        session["csrf_token"] = token
    return token


def _validate_csrf(form) -> bool:
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
    """Schedule os.execv after `delay` seconds on a daemon thread."""

    def _do_restart():
        import time

        time.sleep(delay)
        print(f"[web] Restarting process: {sys.executable} {sys.argv}", flush=True)
        os.execv(sys.executable, [sys.executable] + sys.argv)

    threading.Thread(target=_do_restart, daemon=True, name="restart").start()


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@app.route("/")
def index():
    return redirect(url_for("settings"))


@app.route("/ping")
def ping():
    return "ok", 200


@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get("authenticated"):
        return redirect(url_for("settings"))

    error = None
    if request.method == "POST":
        if not _validate_csrf(request.form):
            error = "Invalid request."
        else:
            password = request.form.get("password", "")
            print(f"[web] Login attempt", flush=True)
            if _check_password(password):
                session["authenticated"] = True
                print("[web] Login successful", flush=True)
                next_url = request.args.get("next") or url_for("settings")
                return redirect(next_url)
            else:
                print("[web] Login failed — wrong password", flush=True)
                error = "Incorrect password."

    using_default_password = not bool(Config.instance().get("web_password_hash"))
    return render_template(
        "login.html",
        error=error,
        csrf_token=_csrf_token(),
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
        print("[web] POST /settings received", flush=True)
        print(f"[web] Raw form keys: {list(form.keys())}", flush=True)

        try:
            if not _validate_csrf(form):
                raise ValueError("Invalid CSRF token.")

            new_data = {
                # Location / flight zone
                "flight_lat": _float(form.get("flight_lat"), cfg.flight_lat),
                "flight_lng": _float(form.get("flight_lng"), cfg.flight_lng),
                "flight_radius": _float(form.get("flight_radius"), cfg.flight_radius),
                "flight_min_altitude": _float(
                    form.get("flight_min_altitude"), cfg.flight_min_altitude
                ),
                "flight_max_altitude": _float(
                    form.get("flight_max_altitude"), cfg.flight_max_altitude
                ),
                # Airport display
                "home_airport_code": _str(form.get("home_airport_code")).upper()[:4],
                "full_airport_name": _bool(form.get("full_airport_name")),
                "abbreviate_name": _bool(form.get("abbreviate_name")),
                "journey_blank_filler": _str(form.get("journey_blank_filler"), " ? "),
                # Plane info row
                "details": _int(form.get("details"), 0),
                # Weather
                "weatherapi_key": _str(form.get("weatherapi_key"), cfg.weatherapi_key),
                "weather_mode": _int(form.get("weather_mode"), 0),
                "units": _str(form.get("units"), "m"),
                # Display
                "theme": _int(form.get("theme"), 0),
                "screen_brightness": max(
                    1, min(5, _int(form.get("screen_brightness"), 3))
                ),
                "screen_rotate": _bool(form.get("screen_rotate")),
                # Brightness schedule
                "screen_schedule_enabled": _bool(form.get("screen_schedule_enabled")),
                "screen_schedule_start": _str(
                    form.get("screen_schedule_start"), "22:00"
                ),
                "screen_schedule_end": _str(form.get("screen_schedule_end"), "07:00"),
                "screen_schedule_brightness": max(
                    0, min(5, _int(form.get("screen_schedule_brightness"), 0))
                ),
                # Clock / date
                "clock_24hr": _bool(form.get("clock_24hr")),
                "date_format": _int(form.get("date_format"), 0),
                # Web interface
                "web_interface_enabled": _bool(form.get("web_interface_enabled")),
                # Hardware
                "gpio_slowdown": max(1, min(4, _int(form.get("gpio_slowdown"), 1))),
                "hat_pwm_enabled": _bool(form.get("hat_pwm_enabled")),
                "loading_led_enabled": _bool(form.get("loading_led_enabled")),
                "loading_led_gpio_pin": _int(form.get("loading_led_gpio_pin"), 25),
                # Data source
                "data_source": (
                    "tar1090"
                    if _str(form.get("data_source"), "fr24").lower() == "tar1090"
                    else "fr24"
                ),
                "tar1090_url": _str(form.get("tar1090_url"), ""),
            }

            # Password change — only update if a new password was supplied
            new_password = form.get("new_password", "").strip()
            confirm_password = form.get("confirm_password", "").strip()
            if new_password:
                if new_password != confirm_password:
                    raise ValueError("New passwords do not match.")
                new_data["web_password_hash"] = _hash_password(new_password)
                print("[web] Password updated", flush=True)
            else:
                # Preserve existing hash
                new_data["web_password_hash"] = cfg.web_password_hash

            print(f"[web] Parsed settings: {new_data}", flush=True)

            cfg.update(new_data)
            cfg.save()
            print(f"[web] Config saved to {CONFIG_PATH}", flush=True)

        except Exception as exc:
            print(f"[web] ERROR processing form: {exc}", flush=True)
            import traceback

            traceback.print_exc()
            return (
                render_template(
                    "settings.html",
                    cfg=cfg.as_dict(),
                    airports_json=_airports_json(),
                    error=str(exc),
                    csrf_token=_csrf_token(),
                    in_schedule=cfg.is_in_brightness_schedule(),
                ),
                400,
            )

        _restart_after(delay=1.0)
        return render_template("restarting.html")

    return render_template(
        "settings.html",
        cfg=cfg.as_dict(),
        airports_json=_airports_json(),
        csrf_token=_csrf_token(),
        in_schedule=cfg.is_in_brightness_schedule(),
    )


_AIRPORTS_JSON: str | None = None


def _load_airports_json() -> str:
    global _AIRPORTS_JSON
    if _AIRPORTS_JSON is None:
        airports_path = Path(__file__).parent.parent / "assets" / "airports.json"
        try:
            with open(airports_path) as fh:
                _AIRPORTS_JSON = fh.read()
        except Exception:
            _AIRPORTS_JSON = "{}"
    return _AIRPORTS_JSON


def _airports_json() -> str:
    return _load_airports_json()

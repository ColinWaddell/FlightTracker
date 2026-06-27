# Installation Guide

This guide covers both fresh installs and upgrades from the previous version of FlightTracker.

---

## Hardware

- Raspberry Pi (any model - Pi 4 recommended)
- [Adafruit RGB Matrix Bonnet](https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/overview) + 64×32 RGB LED matrix
- Optional: solder bridge on the HAT to enable PWM via the Pi's audio hardware (reduces flicker)

---

## Upgrading from a previous version

If you already have FlightTracker running with a `config.py`, this is all you need:

```bash
cd /home/pi/FlightTracker
git pull
source env/bin/activate
pip install -r requirements.txt
```

Your `config.py` will be detected on first boot and automatically migrated to `config.json`. The old file is left untouched.

After pulling, restart the service:

```bash
sudo systemctl restart FlightTracker.service
```

---

## Fresh install

### 1. System update

```bash
sudo apt-get update
sudo apt-get dist-upgrade
```

### 2. Install the RGB matrix driver

```bash
cd /home/pi
curl https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/main/rgb-matrix.sh > /tmp/rgb-matrix.sh
sudo bash /tmp/rgb-matrix.sh
```

Verify with the demo:

```bash
cd /home/pi/rpi-rgb-led-matrix/examples-api-use
sudo ./demo --led-rows=32 --led-cols=64 -D0
```

### 3. Clone and install FlightTracker

```bash
cd /home/pi
git clone https://github.com/ColinWaddell/FlightTracker
cd FlightTracker
python3 -m venv env
source env/bin/activate
pip install -r requirements.txt
```

Then install the rgbmatrix Python bindings into the same environment:

```bash
cd /home/pi/rpi-rgb-led-matrix/bindings/python
pip install .
```

### 4. Permissions

Grant Python permission to set real-time scheduling priorities (avoids running as root):

```bash
sudo setcap 'cap_sys_nice=eip' /usr/bin/python3.11
```

Adjust `python3.11` to match the version in your virtual environment if different.

---

## Configuration

### Option A - Web interface (recommended)

On first boot, the display shows a QR code pointing to the config UI. If no `config.json` exists yet the QR code stays up until you save your settings. Otherwise it shows for 5 seconds before the main display starts.

Scan the QR code or open a browser on the same network and go to:

```
http://<pi-ip-address>:8584
```

The settings page lets you configure everything: your location (with a map), flight filters, airport display, weather, display theme, brightness, clock, and hardware options. Saving the form writes `config.json` and restarts the tracker automatically.

### Option B - Edit config.json directly

You can also create or edit `config.json` by hand in `/home/pi/FlightTracker/`. A minimal example:

```json
{
  "flight_lat": 55.87,
  "flight_lng": -4.25,
  "flight_radius": 20,
  "flight_min_altitude": 100,
  "home_airport_code": "GLA",
  "weather_location": "Glasgow",
  "units": "m",
  "screen_brightness": 3,
  "gpio_slowdown": 2,
  "hat_pwm_enabled": true,
  "timezone": "Europe/London"
}
```

Any key omitted will use the built-in default.

### Key settings reference

| Key | Description | Default |
|-----|-------------|---------|
| `flight_lat` / `flight_lng` | Centre of the flight search zone | `55.87` / `-4.25` |
| `flight_radius` | Search radius in km | `20.0` |
| `flight_min_altitude` | Ignore aircraft below this altitude (metres) | `100.0` |
| `home_airport_code` | IATA code of your local airport - highlighted on display | `""` |
| `full_airport_name` | Scroll the full airport name instead of just the IATA code | `false` |
| `weather_location` | City name for weather data | `"London"` |
| `openweather_api_key` | Optional - enables OpenWeatherMap. [Get a free key here](https://openweathermap.org/price) | `""` |
| `units` | `"m"` for metric (°C / km), `"i"` for imperial (°F / mi) | `"m"` |
| `rainfall_enabled` | Show 24-hour rainfall chart (requires taps-aff data source) | `false` |
| `details` | Bottom row: `0` = aircraft make/model, `1` = altitude/speed/heading | `0` |
| `theme` | `0` = Default, `1` = Monochrome, `2` = Pastel | `0` |
| `screen_brightness` | 1 (dim) – 5 (full) | `3` |
| `clock_24hr` | `true` for 24-hour clock | `true` |
| `timezone` | IANA timezone name, e.g. `"America/New_York"` | `"Europe/London"` |
| `date_format` | `0` = YYYY-MM-DD, `1` = DD-MM-YYYY, `2` = MM-DD-YYYY | `0` |
| `gpio_slowdown` | 1–4; increase if display flickers. Pi 4 typically needs `4` | `1` |
| `hat_pwm_enabled` | Enable PWM via Pi audio hardware (requires solder bridge) | `true` |
| `loading_led_enabled` | Blink a GPIO LED while loading flight data | `false` |
| `loading_led_gpio_pin` | GPIO pin number for the loading LED | `25` |
| `tar1090_url` | URL of a local ADS-B receiver's `aircraft.json`. When set, FlightRadar24 is not used | `""` |

---

## Running manually

```bash
cd /home/pi/FlightTracker
env/bin/python3 flight-tracker.py
```

Press `Ctrl-C` to quit.

---

## Running on boot (systemd)

```bash
sudo cp /home/pi/FlightTracker/assets/FlightTracker.service /etc/systemd/system/FlightTracker.service
sudo systemctl daemon-reload
sudo systemctl enable FlightTracker.service
sudo systemctl start FlightTracker.service
```

Check status and logs:

```bash
sudo systemctl status FlightTracker.service
journalctl -u FlightTracker.service -f
```

---

## Using a local ADS-B receiver (tar1090)

If you run your own receiver with [tar1090](https://github.com/wiedehopf/tar1090), dump1090-fa, or PiAware, you can use it instead of FlightRadar24. Set `tar1090_url` in the web UI or in `config.json`:

```json
"tar1090_url": "http://your-receiver/tar1090/data/aircraft.json"
```

Common URL patterns to try (replace `your-receiver` with the hostname or IP):

```
http://your-receiver/tar1090/data/aircraft.json
http://your-receiver:8080/data/aircraft.json
http://your-receiver/dump1090-fa/data/aircraft.json
http://your-receiver/skyaware/data/aircraft.json
```

The response should be a JSON object containing an `"aircraft"` array. Once set, no API key or FlightRadar24 account is needed.

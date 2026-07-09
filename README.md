# RGB Matrix Flight Tracker

[![Finished flight tracker showing a flight](https://blog.colinwaddell.com/user/pages/01.articles/02.flight-tracker/screen-flight-thumb.jpg)](https://blog.colinwaddell.com/user/pages/01.articles/02.flight-tracker/screen-flight-thumb.jpg)

<video src="assets/full_names_and_plane_type.webm" autoplay loop muted playsinline width="100%"></video>

<video src="assets/satellite_pass.webm" autoplay loop muted playsinline width="100%"></video>

A Raspberry Pi-powered RGB LED matrix that shows you what aircraft are overhead. It sits on your fridge, or a shelf, or wherever you decide to put it, and quietly answers the important question: **"What's that plane?"**

FlightTracker takes live aircraft data, works out what is nearby, and displays it on a 64x32 RGB LED matrix. When there's nothing overhead, it shows the time, weather, temperature, rainfall, or satellite passes.

---

## Installation

### Quick install

Choose the script for your hardware and run it over SSH on a fresh Raspberry Pi OS (Lite) install:

```bash
# Raspberry Pi 3 / 4 / Zero
curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/main/platforms/pi/install.sh | bash

# Raspberry Pi 5
curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/main/platforms/pi5/install.sh | bash
```

Each installer detects your hardware, clones the repo, sets up the Python environment, and configures a systemd service so FlightTracker starts on boot. Each script will redirect you to the correct one if it detects it's running on the wrong platform.

### Step-by-step install

If you'd rather do it manually - or you want to understand what the script does - follow the guide for your platform:

| Platform | Guide |
|----------|-------|
| Raspberry Pi 3 / 4 / Zero | [platforms/pi/INSTALL.md](platforms/pi/INSTALL.md) |
| Raspberry Pi 5 | [platforms/pi5/INSTALL.md](platforms/pi5/INSTALL.md) |
| Desktop simulator | [platforms/simulator/INSTALL.md](platforms/simulator/INSTALL.md) |

---

## Optional features

### Loading LED

An LED wired to a GPIO pin can blink while flight data is loading. Enable it in the web UI under Hardware settings, and set the GPIO pin number to match your wiring.

### Rainfall chart

If you have a WeatherAPI key configured, you can display a 24-hour rainfall chart alongside the temperature. Set the weather mode to "temperature + rainfall" in the web UI.

[![Example Weather Chart](https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/main/assets/weather.jpg)](https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/main/assets/weather.jpg)

### Using a local ADS-B receiver (tar1090)

By default the tracker pulls flight data from FlightRadar24. If you run your own ADS-B receiver with [tar1090](https://github.com/wiedehopf/tar1090) or a compatible [PiAware](https://www.flightaware.com/adsb/piaware/) / [dump1090-fa](https://github.com/flightaware/dump1090) setup, you can use that as your data source instead - no FlightRadar24 account or API access required.

#### What you need

- A device running dump1090-fa, readsb, or similar, with tar1090 installed
- The device must be reachable on your local network from the Flight Tracker Pi
- tar1090-db enrichment active (the default in most installations) - it provides the aircraft type descriptions used by this software

#### Finding your aircraft.json URL

Try each of the following in your browser, replacing `your-receiver` with your device's hostname or IP address, until you get a response containing a list of aircraft:

```
http://your-receiver/tar1090/data/aircraft.json
http://your-receiver:8080/data/aircraft.json
http://your-receiver/dump1090-fa/data/aircraft.json
http://your-receiver/skyaware/data/aircraft.json
```

The response should be a JSON object with an `"aircraft"` array.

#### Enabling tar1090 as your data source

Once you have the URL, enter it in the web UI under the ADS-B / tar1090 settings. The tracker will automatically use your local receiver when a URL is configured, and fall back to FlightRadar24 if it is not.

#### Differences from FlightRadar24 mode

- Aircraft type (e.g. "Airbus A-320") is sourced directly from the tar1090 aircraft database
- Origin and destination airport codes are looked up via [adsbdb.com](https://api.adsbdb.com)
- All position and altitude data comes from your receiver in real time
- No rate limiting or API key required

---

## Updating to the most recent version

```bash
cd /home/pi/FlightTracker
git pull
source env/bin/activate
pip install -r platforms/pi/requirements.txt
sudo systemctl restart FlightTracker.service
```

---

## Settings reference

This table is for reference if you've disabled the web interface (`web_interface_enabled: false`). All settings are otherwise accessible through the web UI.

| Key | Description | Default |
|-----|-------------|---------|
| `flight_lat` / `flight_lng` | Centre of the flight search zone | `55.87` / `-4.25` |
| `flight_radius` | Search radius in km | `20.0` |
| `flight_min_altitude` | Ignore aircraft below this altitude (metres) | `100.0` |
| `home_airport_code` | IATA code of your local airport - highlighted on display | `""` |
| `full_airport_name` | Scroll the full airport name instead of just the IATA code | `false` |
| `weatherapi_key` | API key for [weatherapi.com](https://www.weatherapi.com/pricing.aspx). Weather uses your flight location coordinates. Leave blank to disable weather entirely | `""` |
| `weather_mode` | `0` = off, `1` = temperature only, `2` = temperature + 24-hour rainfall graph | `0` |
| `units` | `"m"` for metric (C / km), `"i"` for imperial (F / mi) | `"m"` |
| `details` | Bottom row: `0` = aircraft make/model, `1` = altitude/speed/heading | `0` |
| `theme` | `0` = Default, `1` = Monochrome, `2` = Pastel | `0` |
| `screen_brightness` | 1 (dim) - 5 (full) | `3` |
| `clock_24hr` | `true` for 24-hour clock | `true` |
| `timezone` | IANA timezone name, e.g. `"America/New_York"` | `"Europe/London"` |
| `date_format` | `0` = YYYY-MM-DD, `1` = DD-MM-YYYY, `2` = MM-DD-YYYY | `0` |
| `web_interface_enabled` | Set to `false` to disable the config UI entirely - Flask will not start and no QR code will be shown on boot. To re-enable, set this back to `true` in `config.json` | `true` |
| `web_port` | TCP port for the Flask config server (1024-65535). Change requires a restart | `8584` |
| `gpio_slowdown` | 1-4; increase if display flickers. Pi 4 typically needs `4` | `1` |
| `hat_pwm_enabled` | Enable PWM via Pi audio hardware (requires solder bridge) | `true` |
| `loading_led_enabled` | Blink a GPIO LED while loading flight data | `false` |
| `loading_led_gpio_pin` | GPIO pin number for the loading LED | `25` |
| `tar1090_url` | URL of a local ADS-B receiver's `aircraft.json`. When set, FlightRadar24 is not used | `""` |

---

## License

Flight Tracker is released under the GNU General Public License v3.0. You're welcome to use, modify, and share the code - just keep it under the same license and include proper attribution (retain the copyright and license notice). See [LICENSE](LICENSE) for details.

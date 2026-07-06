# Flight Tracking Update

The recent breakage affecting overhead flight data has now been resolved. If your flight tracker is not working, see [Fixing recent flight tracking breakage](#fixing-recent-flight-tracking-breakage) at the bottom of this README.

# RBG Matrix Flight Tracker

- 📖 [Blog post about this project](https://blog.colinwaddell.com/flight-tracker/)
- ☢️ [Why you should **avoid** buying this pre-built from Flight Tracker LED](https://colinwaddell.com/articles/flight-tracker-led-ripoff-part-2-its-so-much-worse)
  - They are being sold with a hidden backdoor allowing remote access to your home network

[![Finished flight tracker showing a flight](https://blog.colinwaddell.com/user/pages/01.articles/02.flight-tracker/screen-flight-thumb.jpg)](https://blog.colinwaddell.com/user/pages/01.articles/02.flight-tracker/screen-flight-thumb.jpg)

## Installation

### Supported Hardware

- Raspberry Pi 3B, 4B, Zero 2 W, or Zero W
- Adafruit RGB Matrix Bonnet or HAT + RTC
- 8GB SD card minimum (16GB recommended)
- Raspbian based on Debian Trixie (Debian 13)

### Quick Install

1. Assemble the RGB matrix, Pi, and Bonnet/HAT as described in [this Adafruit guide](https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/overview).
2. If using Quality mode, [solder the bridge between GPIO4 and GPIO18](https://learn.adafruit.com/assets/57727) on the Bonnet/HAT.
3. Boot your Raspberry Pi with a fresh Raspbian Trixie install and ensure you have internet access.
4. Run the install script:

```
curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/feature/feature-upgrade/install.sh | bash
```

The script will ask you a few questions up front (interface type, Quality/Convenience mode, CPU isolation), then install everything automatically:

- System update and required packages
- RGB Matrix driver library
- FlightTracker software and Python dependencies
- Real-time scheduling permissions
- systemd service (starts on boot)
- Boot configuration (sound blacklist, CPU isolation, RTC as applicable)

Once complete, it will reboot your Pi into a fully working system.

**Note:** On a Pi Zero W, the installation will take a long time due to the single-core ARMv6 processor compiling the RGB matrix library and Python packages. If SSH drops during the install, just reconnect and re-run the script — it will detect the existing installation and offer to uninstall it before starting fresh.

### After Installation

After reboot, the FlightTracker service starts automatically. A web interface is available for configuring your location and settings:

```
http://<your-pi-ip>:8584/
```

It may take a few minutes after reboot before the web interface loads — be patient while the Pi boots and starts the service.

To check service status or logs:

```
sudo systemctl status FlightTracker.service
journalctl -u FlightTracker.service -f
```

### Installation Locations

For reference, the install script uses the following locations:

- `~/rpi-rgb-led-matrix` — RGB Matrix driver library
- `~/FlightTracker` — The Flight Tracking software (this repo)
- `~/FlightTracker/env` — Python virtual environment
- `~/FlightTracker/config.py` — Config file (generated via web interface)

### Uninstalling

Re-run the install script. It will detect the existing installation and offer to uninstall it (removing the service, directories, and boot config changes), then exit so you can run it again for a fresh install.

### Configuration file details

| Variable                 | Description |
|--------------------------|-------------|
| `ZONE_HOME`              | Defines the area within which flights should be tracked. |
| `LOCATION_HOME`          | Latitude/longitude of your home. |
| `WEATHER_LOCATION`       | City used to display the temperature. Format: `"City"` or `"City,Province/State,Country"` (e.g., `"Paris"` or `"Paris,Ile-de-France,FR"`). |
| `OPENWEATHER_API_KEY`    | If provided, enables OpenWeather API. [Get a free key here](https://openweathermap.org/price). *(Optional)* |
| `TEMPERATURE_UNITS`      | One of `"metric"` or `"imperial"`. Defaults to `"metric"`. |
| `MIN_ALTITUDE`           | Removes planes below this altitude (in feet). Useful for filtering out planes on the tarmac. |
| `BRIGHTNESS`             | Range 0-100. Adjusts brightness of the display. |
| `GPIO_SLOWDOWN`          | Range 0-4. Higher values help reduce flickering on faster hardware (e.g., `2` for Pi Zero 2 W). |
| `JOURNEY_CODE_SELECTED`  | Three-letter airport code of a local airport to display in **bold**. *(Optional)* |
| `JOURNEY_BLANK_FILLER`   | Three-letter text used in place of an unknown airport. Defaults to `" ? "`. |
| `HAT_PWM_ENABLED`        | Enables PWM via Pi's soundcard. Requires [solder bridge modification](https://learn.adafruit.com/assets/57727). Defaults to `True`. |
| `TAR1090_URL`            | URL of your local tar1090 `aircraft.json` endpoint. When set, flight data is pulled from your own ADS-B receiver instead of FlightRadar24. *(Optional - see below)* |

### Running the software manually

The software can be tested by running it from the command line:

```
cd ~/FlightTracker
env/bin/python3 flight-tracker.py
```

To quit tap `Ctrl-C`.

## Optional

### Loading LED
An LED can be wired to a GPIO on the Raspberry Pi which can then blink when data is being loaded.

To enable this add the following to your `config.py`. Adjust `LOADING_LED_GPIO_PIN` to suit your setup.

```
LOADING_LED_ENABLED = True
LOADING_LED_GPIO_PIN = 25
```

### Rainfall chart
If weather data is being pulled from my server (as opposed to using `OPENWEATHER_API_KEY`) then you can
display a chart of rainfall by adding the following to your `config.py`:

```
RAINFALL_ENABLED = True
```

[![Example Weather Chart](https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/master/assets/weather.jpg)](https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/master/assets/weather.jpg)

### Using a local ADS-B receiver (tar1090)

**EXPERIMENTAL 🧪**

By default the tracker pulls flight data from FlightRadar24. If you run your own ADS-B receiver with [tar1090](https://github.com/wiedehopf/tar1090) or a compatible [PiAware](https://www.flightaware.com/adsb/piaware/) / [dump1090-fa](https://github.com/flightaware/dump1090) setup, you can use that as your data source instead - no FlightRadar24 account or API access required.

#### What you need

- A Raspberry Pi (or other device) running dump1090-fa, readsb, or similar, with tar1090 installed
- The device must be reachable on your local network from the Flight Tracker Pi
- tar1090-db enrichment should be active (this is the default in most installations) - it provides the aircraft type descriptions used by this software

#### Finding your aircraft.json URL

The URL varies depending on your setup. Try each of the following in your browser, replacing `your-receiver` with your device's hostname or IP address, until you get a response containing a list of aircraft:

```
http://your-receiver/tar1090/data/aircraft.json
http://your-receiver:8080/data/aircraft.json
http://your-receiver/dump1090-fa/data/aircraft.json
http://your-receiver/skyaware/data/aircraft.json
```

The response should be a JSON object with an `"aircraft"` array. If you see that, you have the right URL.

#### Enabling tar1090 as your data source

Add a single line to your `config.py`, using the URL you found above:

```python
TAR1090_URL = "http://your-receiver:8080/data/aircraft.json"
```

That's all. The tracker will automatically use your local receiver when `TAR1090_URL` is present, and fall back to FlightRadar24 if it is not set. Existing `config.py` files require no changes.

#### Differences from FlightRadar24 mode

- Aircraft type (e.g. "Airbus A-320") is sourced directly from the tar1090 aircraft database - no external lookup needed
- Origin and destination airport codes are looked up via [adsbdb.com](https://api.adsbdb.com) by callsign, with an 8-hour local cache
- All position and altitude data comes from your receiver in real time
- No rate limiting or API key required

## Fixing recent flight tracking breakage

If flight tracking stopped working during the recent `FlightRadarAPI` breakage, try either of the following fixes. The `Fix #1` is to update everything, but if you don't want to do that attempt `Fix #2` instead which only targets the broken package:

### Fix 1: Pull the latest changes and reinstall requirements

This is the recommended fix because it updates both the code and the pinned dependencies from this repo.

```
cd ~/FlightTracker
git pull
source env/bin/activate
pip install -r requirements.txt
```

### Fix 2: Upgrade `FlightRadarAPI` in the existing virtual environment

If your checkout is already up to date and you only need the package fix, this is the quickest option.

```
cd ~/FlightTracker
source env/bin/activate
pip install FlightRadarAPI -U
```

### Last step

After applying any of the fixes above, restart the service if you run Flight Tracker on boot:

```
sudo systemctl restart FlightTracker.service
```

# License Update:
As of April 2025, Flight Tracker is released under the GNU General Public License v3.0

You're welcome to use, modify, and share the code-just keep it under the same license and include
proper attribution (retain my copyright and license notice). See LICENSE for details.

[I had to add this license as folks have started selling these online as their own with zero attribution](https://colinwaddell.com/articles/flight-radar-ripoff). Open-source projects like this are our CVs: they show peers and potential employers what we can do. Passing off someone else's work as your own robs us of our chance to promote ourselves.
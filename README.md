# Flight Tracking Update

The recent breakage affecting overhead flight data has now been resolved. If your flight tracker is not working, see [Fixing recent flight tracking breakage](#fixing-recent-flight-tracking-breakage) at the bottom of this README.

# RBG Matrix Flight Tracker

- 📖 [Blog post about this project](https://blog.colinwaddell.com/flight-tracker/)
- ☢️ [Why you should **avoid** buying this pre-built from Flight Tracker LED](https://colinwaddell.com/articles/flight-tracker-led-ripoff-part-2-its-so-much-worse)
  - They are being sold with a hidden backdoor allowing remote access to your home network

[![Finished flight tracker showing a flight](https://blog.colinwaddell.com/user/pages/01.articles/02.flight-tracker/screen-flight-thumb.jpg)](https://blog.colinwaddell.com/user/pages/01.articles/02.flight-tracker/screen-flight-thumb.jpg)

# Setup

## Installation

Choose the guide for your platform:

- **[Raspberry Pi 3 / 4 / Zero](platforms/pi/INSTALL.md)** - uses hzeller's rpi-rgb-led-matrix (C++ driver)
- **[Raspberry Pi 5](platforms/pi5/INSTALL.md)** - uses Adafruit's piomatter library (PIO driver)
- **[Desktop simulator](platforms/simulator/INSTALL.md)** - runs in a pygame window for development

Or use the automated installers:

```bash
# Pi 3 / 4 / Zero
curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/master/platforms/pi/install.sh | bash

# Pi 5
curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/master/platforms/pi5/install.sh | bash
```

Each installer detects your hardware and redirects you to the correct one if needed.

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
cd /home/pi/FlightTracker
git pull
source env/bin/activate
pip install -r platforms/pi/requirements.txt
```

### Fix 2: Upgrade `FlightRadarAPI` in the existing virtual environment

If your checkout is already up to date and you only need the package fix, this is the quickest option.

```
cd /home/pi/FlightTracker
source env/bin/activate
pip install FlightRadarAPI -U
```

### Last step

After applying any of the fixes above, restart the service if you run Flight Tracker on boot:

```
sudo systemctl restart FlightTracker.service
```

# License Update:
Flight Tracker is released under the GNU General Public License v3.0

You're welcome to use, modify, and share the code-just keep it under the same license and include
proper attribution (retain my copyright and license notice). See LICENSE for details.

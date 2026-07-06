# Flight Tracking Update

The recent breakage affecting overhead flight data has now been resolved. If your flight tracker is not working, see [Fixing recent flight tracking breakage](#fixing-recent-flight-tracking-breakage) at the bottom of this README.

# RBG Matrix Flight Tracker

- 📖 [Blog post about this project](https://blog.colinwaddell.com/flight-tracker/)
- ☢️ [Why you should **avoid** buying this pre-built from Flight Tracker LED](https://colinwaddell.com/articles/flight-tracker-led-ripoff-part-2-its-so-much-worse)
  - They are being sold with a hidden backdoor allowing remote access to your home network

[![Finished flight tracker showing a flight](https://blog.colinwaddell.com/user/pages/01.articles/02.flight-tracker/screen-flight-thumb.jpg)](https://blog.colinwaddell.com/user/pages/01.articles/02.flight-tracker/screen-flight-thumb.jpg)

# Setup

## Installation

These instructions assume you're running the Flight Tracker on a Raspberry Pi as the only thing the device is doing. Supported hardware:

- Raspberry Pi 3B, 4B, Zero 2 W, or Zero W
- Adafruit RGB Matrix Bonnet or HAT + RTC
- 8GB SD card minimum (16GB recommended)
- Raspbian based on Debian Trixie (Debian 13)
- If you're not using a screen/keyboard attached to the Pi then you've figured out how to remote edit over SSH

There are two ways to install:

- **[Quick Install](#quick-install)** — a single `curl | bash` script that handles everything automatically
- **[Manual Install](#manual-install)** — step-by-step instructions for those who prefer to run each command themselves

### Quick Install

If you're happy to run the automated installer, the entire process is a single command. The script will ask you a few questions up front (interface board type, Quality/Convenience mode, CPU isolation), then install everything and reboot into a working system.

1. Assemble the RGB matrix, Pi, and Bonnet/HAT as described in [this Adafruit guide](https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/overview).
2. If using Quality mode, [solder the bridge between GPIO4 and GPIO18](https://learn.adafruit.com/assets/57727) on the Bonnet/HAT.
3. Boot your Raspberry Pi with a fresh Raspbian Trixie install and ensure you have internet access.
4. Run the install script:

```
curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/feature/feature-upgrade/install.sh | bash
```

The script handles:

- System update and required packages
- RGB Matrix driver library (download, build, install)
- FlightTracker software and Python dependencies
- Real-time scheduling permissions (setcap)
- systemd service (starts on boot)
- Boot configuration (sound blacklist, CPU isolation, RTC as applicable)
- Single reboot into a fully working system

**Note:** On a Pi Zero W, the installation will take a long time due to the single-core ARMv6 processor compiling the RGB matrix library and Python packages. If SSH drops during the install, just reconnect and re-run the script — it will detect the existing installation and offer to uninstall it before starting fresh.

After reboot, the FlightTracker service starts automatically. A web interface is available for configuring your location and settings:

```
http://<your-pi-ip>:8584/
```

To check service status or logs:

```
sudo systemctl status FlightTracker.service
journalctl -u FlightTracker.service -f
```

To uninstall, re-run the script — it will detect the existing installation and offer to remove it.

### Manual Install

The previous instructions were written against Debian Buster and can be found [at this commit](https://github.com/ColinWaddell/FlightTracker/blob/44aa282bdc54a897ab72cbd0dc49017f6a11c11a/README.md). These instructions target Raspbian Trixie (Debian 13). If you run into any problems please raise it as an issue.

#### Installation Locations

For future reference, in this installation process we're going to use the following locations (substitute your username and home directory if not `pi`):

| Location                                | Purpose                                                             |
| --------------------------------------- | ------------------------------------------------------------------- |
| `~/rpi-rgb-led-matrix`                  | RGB Matrix Driver                                                   |
| `~/FlightTracker`                       | The Flight Tracking software (this repo)                            |
| `~/FlightTracker/env`                   | The virtual environment we'll install the necessary Python packages  |
| `~/FlightTracker/config.py`            | Config file for this flight tracking software                       |

#### First steps

Before installing anything let's ensure our system is up-to-date:

```
sudo apt-get update
sudo apt-get dist-upgrade
```

This will take a while on a fresh device as it picks up all its updates.

Install the required packages:

```
sudo apt-get install -y git curl python3 python3-venv python3-pip python3-dev python3-pillow cython3 python3-setuptools libcap2-bin unzip
```

#### Install the RGB Screen

1. Assemble the RGB matrix, Pi, and Bonnet as described in [this Adafruit guide](https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/overview).
2. It is recommended that the [solder bridge is added to the HAT](https://learn.adafruit.com/assets/57727) in order to use the Pi's soundcard to drive the device's PWM.
3. Please [read the official installation instructions](https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/install-using-script) for further details before proceeding **but don't run any commands or install anything yet**.

4. Download the RGB matrix library. We pin to the same commit used by the Adafruit installer:

```
cd ~
curl -L https://github.com/hzeller/rpi-rgb-led-matrix/archive/7a503494378a67f3baa4ac680cecbae2703cc58f.zip -o rpi-rgb-led-matrix.zip
unzip rpi-rgb-led-matrix.zip
rm rpi-rgb-led-matrix.zip
mv rpi-rgb-led-matrix-7a503494378a67f3baa4ac680cecbae2703cc58f rpi-rgb-led-matrix
```

5. Build the library. If you're using Quality mode (solder bridge installed), add `-DDISABLE_HARDWARE_PULSES` to `USER_DEFINES`:

```
cd ~/rpi-rgb-led-matrix
make build-python USER_DEFINES="-DDISABLE_HARDWARE_PULSES"
```

If you're using Convenience mode (no solder bridge), omit the `USER_DEFINES`:

```
cd ~/rgb-led-matrix
make build-python
```

6. Apply the boot configuration changes. For Quality mode, disable the internal sound card:

```
echo "blacklist snd_bcm2835" | sudo tee /etc/modprobe.d/blacklist-rgb-matrix.conf
```

If you have multiple CPU cores and want to reserve one for driving the display (reduces flicker), add `isolcpus=N` to your boot cmdline (where N is the last core number, e.g. `isolcpus=3` on a 4-core Pi):

```
CMDLINE=/boot/firmware/cmdline.txt
[ ! -f "$CMDLINE" ] && CMDLINE=/boot/cmdline.txt
sudo sed -i "s/$/ isolcpus=$(($(nproc --all) - 1))/" "$CMDLINE"
```

If using the HAT + RTC, enable I2C and the RTC overlay:

```
sudo raspi-config nonint do_i2c 0
echo "dtoverlay=i2c-rtc,ds1307" | sudo tee -a /boot/firmware/config.txt
sudo apt-get -y remove fake-hwclock
sudo update-rc.d -f fake-hwclock remove
```

7. If the installation has worked successfully then there should be some demo applications available to run:

```
cd ~/rpi-rgb-led-matrix/examples-api-use
sudo ./demo --led-rows=32 --led-cols=64 -D0
```

#### Install this Flight Tracking software

1. Clone this repository (use `--depth 1` to avoid a large download, especially on Pi Zero W):

```
cd ~
git clone --depth 1 -b feature/feature-upgrade https://github.com/ColinWaddell/FlightTracker
```

2. Create a virtual environment and install the Python dependencies:

```
cd ~/FlightTracker
python3 -m venv env
source env/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

**Note:** On a Pi Zero W, `/tmp` is a small tmpfs (RAM-backed filesystem, ~200MB). Building some Python packages (e.g. `curl_cffi`) requires more space. If you get "No space left on device" errors during `pip install`, resize the tmpfs first:

```
sudo mount -o remount,size=512M /tmp
```

3. Install the RGB Matrix Python bindings. The `setup.py` in rpi-rgb-led-matrix uses `distutils` which was removed in Python 3.12+, so `pip install .` fails on Trixie (Python 3.13). Instead, copy the pre-built `.so` files directly into your virtual environment:

```
SITE_PACKAGES=$(python3 -c "import sys; print(f'lib/python{sys.version_info.major}.{sys.version_info.minor}/site-packages')")
cp -r ~/rpi-rgb-led-matrix/bindings/python/rgbmatrix ~/FlightTracker/env/$SITE_PACKAGES/
```

Verify the import works:

```
python3 -c "from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics"
```

#### Configure the Flight Tracking software for your location

A web interface is available for configuration — after starting the service (see below), visit `http://<your-pi-ip>:8584/` in a browser to generate your `config.py` automatically.

Alternatively, you can create the config file manually:

```
cd ~/FlightTracker
nano config.py
```

Here is an example config you can copy into that file:

```
ZONE_HOME = {
    "tl_y": 56.06403, # Top-Left Latitude (deg)
    "tl_x": -4.51589, # Top-Left Longitude (deg)
    "br_y": 55.89088, # Bottom-Right Latitude (deg)
    "br_x": -4.19694 # Bottom-Right Longitude (deg)
}
LOCATION_HOME = [
    55.9074356, # Latitude (deg)
    -4.3331678, # Longitude (deg)
    0.01781 # Altitude (km)
]
WEATHER_LOCATION = "Glasgow"
OPENWEATHER_API_KEY = "" # Get an API key from https://openweathermap.org/price
TEMPERATURE_UNITS = "metric"
MIN_ALTITUDE = 100
BRIGHTNESS = 50
GPIO_SLOWDOWN = 2
JOURNEY_CODE_SELECTED = "GLA"
JOURNEY_BLANK_FILLER = " ? "
HAT_PWM_ENABLED = True
```

To save and exit nano hit `Ctrl-X` followed by `Y`.

In reality you'll want to customise `config.py` for your own purposes.

#### Configuration file details

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

#### Configuring permissions to avoid running as root

Previous versions of the instructions always pointed out to run everything as root for performance reasons but for security I think this is best avoided. Plus the latest version of the GPIO driver and rgb-matrix have strong opinions about who is in charge when running as root.

To avoid running as root and to grant Python permission to set real-time scheduling priorities, run the command (substituting your Python binary path — find it with `readlink -f $(which python3)`):

```
sudo setcap 'cap_sys_nice=eip' $(readlink -f $(which python3))
```

#### Running the software manually

The software can now be tested by running it from the command line:

```
cd ~/FlightTracker
env/bin/python3 flight-tracker.py
```

To quit tap `Ctrl-C`.

#### Running the software on start-up

This repo contains an example `.service` file to allow this software to be easily run on boot. The service file contains `__USER__` and `__HOME__` placeholders that need to be substituted with your username and home directory:

```
sed -e "s|__USER__|$(whoami)|g" -e "s|__HOME__|$HOME|g" ~/FlightTracker/assets/FlightTracker.service | sudo tee /etc/systemd/system/FlightTracker.service
sudo systemctl daemon-reload
sudo systemctl enable FlightTracker.service
sudo systemctl start FlightTracker.service
```

Any problems, check the status and logs:

```
sudo systemctl status FlightTracker.service
journalctl -u FlightTracker.service -f
```

#### Reboot

If you applied boot configuration changes (sound blacklist, CPU isolation, RTC), reboot to apply them:

```
sudo reboot
```

After reboot, the FlightTracker service will start automatically. It may take a few minutes before the web interface at `http://<your-pi-ip>:8584/` becomes available.

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
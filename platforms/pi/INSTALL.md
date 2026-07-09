# Installation Guide - Raspberry Pi 3 / 4 / Zero

This guide covers both fresh installs and upgrades from the previous version of FlightTracker.

---

## Automated install (recommended)

```bash
curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/main/platforms/pi/install.sh | bash
```

The installer detects your hardware, clones the repo, creates a virtual environment, installs dependencies (including the hzeller rpi-rgb-led-matrix C++ driver), and sets up a systemd service.

---

## Hardware

- Raspberry Pi (Tested with 3, 4 and Zero W. For Pi 5 see the guide at [platforms/pi5/INSTALL.md](../pi5/INSTALL.md))
- [Adafruit RGB Matrix Bonnet](https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/overview) + 64x32 RGB LED matrix
- Optional: solder bridge on the HAT to enable PWM via the Pi's audio hardware (reduces flicker)

---

## Upgrading from a previous version

If you already have FlightTracker running with a `config.py`, this is all you need:

If your checkout is still on the old `master` branch, switch to `main` before pulling updates:

```bash
cd /home/pi/FlightTracker
git fetch --all
git checkout main
git pull
source env/bin/activate
pip install -r platforms/pi/requirements.txt
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
pip install -r platforms/pi/requirements.txt
```

Then install the rgbmatrix Python bindings into the same environment:

```bash
cd /home/pi/rpi-rgb-led-matrix/bindings/python
pip install .
```

### 4. Permissions

Grant Python permission to set real-time scheduling priorities (avoids running as root):

```bash
sudo setcap 'cap_sys_nice=eip' /usr/bin/python3.13
```

Adjust `python3.13` to match the version in your virtual environment if different.

---

## Configuration

On first boot, the display shows a QR code pointing to the config UI. The QR code stays up until you save your settings for the first time, then shows briefly for 5 seconds on subsequent boots before the main display starts.

Scan the QR code or open a browser on the same network and go to:

```
http://<pi-ip-address>:8584
```

The settings page covers everything: your location (with a map), flight filters, airport display, weather, display theme, brightness, clock, and hardware options. FlightTracker generates and manages the configuration file automatically - there's no need to edit it by hand.

If you've disabled the web interface, see the [main README](../../README.md) for the full settings reference.

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

If you run your own receiver with [tar1090](https://github.com/wiedehopf/tar1090), dump1090-fa, or PiAware, you can use it instead of FlightRadar24 - no API key required.

First, find the right URL for your receiver. Try each of these in a browser, replacing `your-receiver` with the hostname or IP, until you get back a JSON response containing an `"aircraft"` array:

```
http://your-receiver/tar1090/data/aircraft.json
http://your-receiver:8080/data/aircraft.json
http://your-receiver/dump1090-fa/data/aircraft.json
http://your-receiver/skyaware/data/aircraft.json
```

Once you have the URL, enter it in the web UI under the ADS-B / tar1090 settings.

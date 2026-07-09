# Installation Guide - Raspberry Pi 5

This guide covers installing FlightTracker on a Raspberry Pi 5 using Adafruit's `adafruit-blinka-raspberry-pi5-piomatter` library, which drives the RGB panel via the Pi 5's PIO subsystem - no C++ compilation needed.

---

## Hardware

- Raspberry Pi 5
- [Adafruit RGB Matrix Bonnet](https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/overview) + 64x32 RGB LED matrix
- Optional: solder bridge on the HAT to enable PWM (reduces flicker)

---

## Automated install (recommended)

```bash
curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/main/platforms/pi5/install.sh | bash
```

The installer detects your hardware, clones the repo, creates a virtual environment, installs dependencies, and sets up a systemd service.

---

## Manual install

### 1. System update

```bash
sudo apt-get update
sudo apt-get dist-upgrade
```

### 2. Clone and install FlightTracker

```bash
cd /home/pi
git clone https://github.com/ColinWaddell/FlightTracker
cd FlightTracker
python3 -m venv env
source env/bin/activate
pip install -r platforms/pi5/requirements.txt
```

### 3. Verify piomatter

```bash
python3 -c "import adafruit_blinka_raspberry_pi5_piomatter; print('piomatter OK')"
```

---

## Configuration

On first boot, the display shows a QR code pointing to the config UI. The QR code stays up until you save your settings for the first time, then shows briefly for 5 seconds on subsequent boots before the main display starts.

Scan the QR code or open a browser on the same network and go to:

```
http://<pi-ip-address>:8584
```

The settings page covers everything: your location (with a map), flight filters, airport display, weather, display theme, brightness, clock, and hardware options. FlightTracker generates and manages the configuration file automatically.

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

## Upgrading from a previous version

If your checkout is still on the old `master` branch, switch to `main` before pulling updates:

```bash
cd /home/pi/FlightTracker
git fetch --all
git checkout main
git pull
source env/bin/activate
pip install -r platforms/pi5/requirements.txt
```

Then restart the service:

```bash
sudo systemctl restart FlightTracker.service
```

---

## Using a local ADS-B receiver (tar1090)

See the [main README](../../README.md) for tar1090 setup instructions - this is platform-independent.
# Installation Guide — Raspberry Pi 3 / 4 / Zero

This guide covers both fresh installations and upgrades from previous versions of FlightTracker.

> **Raspberry Pi 5 users:** Follow the separate [Raspberry Pi 5 installation guide](../pi5/INSTALL.md).

---

## Automated install (recommended)

The automated installer:

* Detects your Raspberry Pi hardware
* Clones FlightTracker
* Creates a Python virtual environment
* Installs the required dependencies
* Installs the Hzeller `rpi-rgb-led-matrix` driver
* Configures FlightTracker to run as a systemd service

Run:

```bash
curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/main/platforms/pi/install.sh | bash
```

For most users, this is the recommended installation method.

---

## Hardware

You will need:

* A Raspberry Pi 3, Raspberry Pi 4, or Raspberry Pi Zero W
* An [Adafruit RGB Matrix Bonnet](https://learn.adafruit.com/adafruit-rgb-matrix-bonnet-for-raspberry-pi/overview)
* A 64×32 HUB75 RGB LED matrix
* A suitable 5 V power supply for the matrix
* A microSD card containing Raspberry Pi OS

FlightTracker has been tested with the Raspberry Pi 3, Raspberry Pi 4, and Raspberry Pi Zero W.

### Optional PWM modification

The Adafruit installer offers two display-timing configurations:

* **Quality:** Better display quality and reduced flicker, but requires the PWM solder bridge.
* **Convenience:** Requires no soldering, but may exhibit occasional flicker.

On the single-matrix Adafruit RGB Matrix Bonnet, the quality configuration requires soldering the GPIO 4 and GPIO 18 pads together.

Select the configuration matching your hardware when prompted by the Adafruit installer.

---

## Upgrading from a previous version

Change to the existing FlightTracker checkout:

```bash
cd ~/FlightTracker
```

Fetch the current branches:

```bash
git fetch origin
```

If your checkout is still using the old `master` branch, switch to `main`:

```bash
if git show-ref --verify --quiet refs/heads/main; then
    git switch main
else
    git switch --track origin/main
fi
```

Pull the latest changes:

```bash
git pull --ff-only
```

Activate the existing FlightTracker virtual environment:

```bash
source env/bin/activate
```

Update the Python dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r platforms/pi/requirements.txt
```

Install or update the RGB matrix Python bindings:

```bash
python -m pip install --force-reinstall \
    ~/rgb-matrix-install/rpi-rgb-led-matrix/bindings/python
```

Copy the latest systemd service file:

```bash
sudo cp \
    ~/FlightTracker/assets/FlightTracker.service \
    /etc/systemd/system/FlightTracker.service
```

Reload systemd and restart FlightTracker:

```bash
sudo systemctl daemon-reload
sudo systemctl restart FlightTracker.service
```

Check that FlightTracker started successfully:

```bash
sudo systemctl status FlightTracker.service
```

Press `q` to leave the status display.

### Configuration migration

If your existing installation contains a `config.py`, FlightTracker will detect it during startup and automatically migrate its settings to `config.json`.

The original `config.py` file is left untouched.

> If `~/rgb-matrix-install/rpi-rgb-led-matrix` does not exist, follow the [Install the RGB matrix driver](#2-install-the-rgb-matrix-driver) section before reinstalling the bindings.

---

# Fresh install

## 1. Update Raspberry Pi OS

Update the package list and install available operating-system upgrades:

```bash
sudo apt update
sudo apt full-upgrade -y
```

Reboot if required:

```bash
sudo reboot
```

After the Pi restarts, reconnect over SSH or open a new terminal.

---

## 2. Install the RGB matrix driver

FlightTracker uses Henner Zeller’s `rpi-rgb-led-matrix` driver. The recommended installation method is Adafruit’s installer script.

Install the required system packages:

```bash
sudo apt install -y python3-venv wget
```

Create a dedicated directory for the installer and driver source:

```bash
mkdir -p ~/rgb-matrix-install
cd ~/rgb-matrix-install
```

Create a virtual environment for the Adafruit installer:

```bash
python3 -m venv env --system-site-packages
source env/bin/activate
```

Install the Adafruit Python shell helper:

```bash
python -m pip install --upgrade pip
python -m pip install adafruit-python-shell
```

Download the Adafruit installer:

```bash
wget -O rgb-matrix.py \
    https://github.com/adafruit/Raspberry-Pi-Installer-Scripts/raw/main/rgb-matrix.py
```

Run it using the virtual environment:

```bash
sudo -E env PATH="$PATH" python3 rgb-matrix.py
```

Select the Adafruit RGB Matrix Bonnet when prompted.

Choose the display-timing option matching your hardware:

* Select **quality** if you have completed the PWM solder bridge.
* Select **convenience** if you have not modified the Bonnet.

The installer creates the driver checkout at:

```text
~/rgb-matrix-install/rpi-rgb-led-matrix
```

> The installer may replace an existing `rpi-rgb-led-matrix` directory inside `~/rgb-matrix-install`.

### Reboot after installation

The installer may ask to reboot the Raspberry Pi.

Allow it to reboot when prompted. A reboot is required when changing between the quality and convenience configurations.

After the Pi restarts, reconnect over SSH or open a new terminal.

### Verify the driver

Change to the example-program directory:

```bash
cd ~/rgb-matrix-install/rpi-rgb-led-matrix/examples-api-use
```

Run the demo for a single 64×32 matrix:

```bash
sudo ./demo \
    --led-rows=32 \
    --led-cols=64 \
    --led-gpio-mapping=adafruit-hat \
    -D0
```

The matrix should display a test animation.

Press `Ctrl-C` to stop the demo.

If the display does not work correctly, check that:

* The matrix has a suitable external 5 V power supply.
* The ribbon cable is connected in the correct orientation.
* The selected quality/convenience configuration matches the hardware modification.
* The Raspberry Pi is not overclocked.

---

## 3. Clone and install FlightTracker

Install Git:

```bash
sudo apt install -y git
```

Clone FlightTracker:

```bash
cd ~
git clone https://github.com/ColinWaddell/FlightTracker.git
cd FlightTracker
```

Create the FlightTracker virtual environment:

```bash
python3 -m venv env
source env/bin/activate
```

Upgrade `pip` and install FlightTracker’s dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r platforms/pi/requirements.txt
```

Install the RGB matrix Python bindings into the FlightTracker virtual environment:

```bash
python -m pip install \
    ~/rgb-matrix-install/rpi-rgb-led-matrix/bindings/python
```

Verify that the bindings can be imported:

```bash
python -c 'from rgbmatrix import RGBMatrix; print("rgbmatrix bindings installed")'
```

You should see:

```text
rgbmatrix bindings installed
```

---

## Configuration

FlightTracker provides a browser-based configuration interface.

On first boot, the matrix displays a QR code pointing to the configuration page. The QR code remains on screen until the settings are saved for the first time.

On subsequent boots, the QR code appears for five seconds before the normal display begins.

Scan the QR code or open the following address from another device on the same network:

```text
http://<pi-ip-address>:8584
```

Replace `<pi-ip-address>` with the Raspberry Pi’s IP address.

You can find the Pi’s IP addresses with:

```bash
hostname -I
```

The web interface allows you to configure:

* Your location
* Flight filters
* Airport display options
* Weather information
* Display themes
* Brightness and brightness scheduling
* Clock settings
* Matrix and hardware options
* Local ADS-B receiver integration

FlightTracker creates and manages `config.json` automatically. There is normally no need to edit the configuration file manually.

If the web interface has been disabled, see the [main README](../../README.md) for the complete settings reference.

---

## Running FlightTracker manually

Change to the FlightTracker directory:

```bash
cd ~/FlightTracker
```

Run FlightTracker using the virtual environment’s interpreter:

```bash
env/bin/python3 flight-tracker.py
```

Press `Ctrl-C` to stop FlightTracker.

You can also activate the environment first:

```bash
cd ~/FlightTracker
source env/bin/activate
python flight-tracker.py
```

---

## Running FlightTracker on boot

FlightTracker includes a systemd service file.

The supplied service:

* Runs FlightTracker as the `pi` user
* Starts after the network is online
* Restarts FlightTracker if it fails
* Grants FlightTracker the `CAP_SYS_NICE` capability required for elevated scheduling priority
* Does not grant the capability globally to the system Python interpreter

Install the service file:

```bash
sudo cp \
    ~/FlightTracker/assets/FlightTracker.service \
    /etc/systemd/system/FlightTracker.service
```

Reload the systemd configuration:

```bash
sudo systemctl daemon-reload
```

Enable FlightTracker at boot:

```bash
sudo systemctl enable FlightTracker.service
```

Start FlightTracker:

```bash
sudo systemctl start FlightTracker.service
```

### Check service status

```bash
sudo systemctl status FlightTracker.service
```

Press `q` to leave the status display.

### Follow the logs

```bash
journalctl -u FlightTracker.service -f
```

Press `Ctrl-C` to stop following the logs.

### Restart FlightTracker

```bash
sudo systemctl restart FlightTracker.service
```

### Stop FlightTracker

```bash
sudo systemctl stop FlightTracker.service
```

### Verify scheduling capabilities

Check the capabilities assigned to the service:

```bash
systemctl show FlightTracker.service \
    -p AmbientCapabilities \
    -p CapabilityBoundingSet
```

The output should include `CAP_SYS_NICE`.

The corresponding service file contains:

```ini
AmbientCapabilities=CAP_SYS_NICE
CapabilityBoundingSet=CAP_SYS_NICE
```

There is no need to run `setcap` against `/usr/bin/python3` or the virtual environment’s Python executable.

---

## FlightTracker systemd service

The supplied `assets/FlightTracker.service` file should contain:

```ini
[Unit]
Description=Flight Tracker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/FlightTracker

ExecStartPre=/bin/sleep 20
ExecStart=/home/pi/FlightTracker/env/bin/python /home/pi/FlightTracker/flight-tracker.py

Environment=PYTHONUNBUFFERED=1

Restart=on-failure
RestartSec=5

Nice=-10
IOSchedulingClass=realtime
IOSchedulingPriority=0

AmbientCapabilities=CAP_SYS_NICE
CapabilityBoundingSet=CAP_SYS_NICE

StandardOutput=append:/home/pi/plane.log
StandardError=append:/home/pi/plane.log

[Install]
WantedBy=multi-user.target
```

---

## Using a local ADS-B receiver

FlightTracker can use aircraft data from a local ADS-B receiver instead of FlightRadar24. No FlightRadar24 API key is required when using a compatible local receiver.

Compatible systems include:

* [tar1090](https://github.com/wiedehopf/tar1090)
* `dump1090-fa`
* PiAware / SkyAware

### Find the aircraft JSON URL

Try each of the following addresses in a browser, replacing `your-receiver` with the receiver’s hostname or IP address:

```text
http://your-receiver/tar1090/data/aircraft.json
http://your-receiver:8080/data/aircraft.json
http://your-receiver/dump1090-fa/data/aircraft.json
http://your-receiver/skyaware/data/aircraft.json
```

The correct URL should return JSON containing an `aircraft` array, similar to:

```json
{
  "aircraft": [
    {
      "hex": "406abc",
      "flight": "BAW123"
    }
  ]
}
```

Enter the working URL in the FlightTracker web interface under the ADS-B / tar1090 settings.

For example:

```text
http://garagepi.local:8080/data/aircraft.json
```

The Raspberry Pi running FlightTracker must be able to access the receiver over the local network.

---

## Directory layout

After a manual installation, the relevant directories should look approximately like this:

```text
/home/pi/
├── FlightTracker/
│   ├── env/
│   ├── platforms/
│   ├── assets/
│   ├── flight-tracker.py
│   └── config.json
│
└── rgb-matrix-install/
    ├── env/
    ├── rgb-matrix.py
    └── rpi-rgb-led-matrix/
        ├── bindings/
        │   └── python/
        └── examples-api-use/
```

The two `env` directories are separate virtual environments:

* `~/rgb-matrix-install/env` runs the Adafruit installation script.
* `~/FlightTracker/env` contains FlightTracker and its runtime dependencies.

FlightTracker does not need the Adafruit installer virtual environment after installation. Keep the `rpi-rgb-led-matrix` source directory so that its Python bindings can be rebuilt or reinstalled later.

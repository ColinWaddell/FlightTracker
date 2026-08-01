# Installation Guide — Raspberry Pi 3 / 4 / Zero

This guide covers both fresh installations and upgrades from previous versions of FlightTracker.

> **Raspberry Pi 5 users:** Follow the separate [Raspberry Pi 5 installation guide](../pi5/INSTALL.md).

---

## Automated install (recommended)

The automated installer detects your hardware, clones FlightTracker, creates a Python virtual environment, installs the required dependencies—including the Hzeller `rpi-rgb-led-matrix` C++ driver—and configures the systemd service.

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

For improved display quality and reduced flicker, the Adafruit installer offers a **quality** configuration.

On the single-matrix Adafruit RGB Matrix Bonnet, this requires soldering the GPIO 4 and GPIO 18 pads together. Without this modification, select the **convenience** configuration during installation.

The convenience configuration requires no soldering but may exhibit occasional display flicker.

---

## Upgrading from a previous version

If FlightTracker is already installed, first switch the checkout to the current `main` branch and pull the latest changes.

```bash
cd ~/FlightTracker
git fetch origin

if git show-ref --verify --quiet refs/heads/main; then
    git switch main
else
    git switch --track origin/main
fi

git pull --ff-only
```

Activate the existing FlightTracker virtual environment and update its dependencies:

```bash
source env/bin/activate
pip install --upgrade pip
pip install -r platforms/pi/requirements.txt
```

Restart FlightTracker:

```bash
sudo systemctl restart FlightTracker.service
```

Check that it started successfully:

```bash
sudo systemctl status FlightTracker.service
```

Press `q` to leave the status display.

### Configuration migration

If your existing installation contains a `config.py`, FlightTracker will detect it during startup and automatically migrate its settings to `config.json`.

The original `config.py` file is left untouched.

---

# Fresh install

## 1. Update Raspberry Pi OS

Update the package list and install available operating-system upgrades:

```bash
sudo apt update
sudo apt full-upgrade -y
```

Reboot if the upgrade requests it:

```bash
sudo reboot
```

After the Pi has restarted, reconnect over SSH or open a new terminal.

---

## 2. Install the RGB matrix driver

FlightTracker uses Henner Zeller’s `rpi-rgb-led-matrix` driver. The recommended installation method is Adafruit’s installer script.

Install the required system packages:

```bash
sudo apt install -y python3-venv wget
```

Create a dedicated directory for the installer and its files:

```bash
mkdir -p ~/rgb-matrix-install
cd ~/rgb-matrix-install
```

Create and activate a virtual environment for the Adafruit installer:

```bash
python3 -m venv env --system-site-packages
source env/bin/activate
```

Install the Adafruit Python shell helper:

```bash
python -m pip install --upgrade pip
python -m pip install adafruit-python-shell
```

Download and run the installer:

```bash
wget -O rgb-matrix.py \
    https://github.com/adafruit/Raspberry-Pi-Installer-Scripts/raw/main/rgb-matrix.py

sudo -E env PATH="$PATH" python3 rgb-matrix.py
```

The installer will ask which adapter you are using. Select:

```text
Adafruit RGB Matrix Bonnet
```

It will then ask whether you want the **quality** or **convenience** configuration:

* Choose **quality** if you have completed the required PWM solder bridge.
* Choose **convenience** if you have not modified the Bonnet.

The installer creates the driver checkout at:

```text
~/rgb-matrix-install/rpi-rgb-led-matrix
```

> Any existing `rpi-rgb-led-matrix` directory inside `~/rgb-matrix-install` may be replaced by the installer.

### Reboot after installation

The installer may ask whether it should reboot the Pi.

A reboot is required when changing between the quality and convenience configurations. Allow the installer to reboot when prompted.

After the Pi restarts, reconnect over SSH or open a new terminal before continuing.

### Verify the driver

Change to the driver’s example directory:

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

If the display flickers or shows visual corruption, confirm that:

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

Clone FlightTracker into your home directory:

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

Upgrade `pip` and install the FlightTracker dependencies:

```bash
python -m pip install --upgrade pip
python -m pip install -r platforms/pi/requirements.txt
```

Install the RGB matrix Python bindings into the same virtual environment:

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

## 4. Grant real-time scheduling permission

The RGB matrix driver uses real-time scheduling to maintain consistent display timing.

Rather than running FlightTracker as root, grant the Python interpreter used by the FlightTracker virtual environment permission to adjust scheduling priority:

```bash
PYTHON_BIN="$(readlink -f ~/FlightTracker/env/bin/python3)"
sudo setcap 'cap_sys_nice=eip' "$PYTHON_BIN"
```

Verify the capability:

```bash
getcap "$PYTHON_BIN"
```

The output should resemble:

```text
/usr/bin/python3.x cap_sys_nice=eip
```

> The virtual environment normally links to the Raspberry Pi OS system Python interpreter. Reinstalling or upgrading the system Python package may remove this capability, in which case the command must be repeated.

---

## Configuration

FlightTracker provides a browser-based configuration interface.

On first boot, the matrix displays a QR code pointing to the configuration page. The QR code remains on screen until the settings are saved for the first time.

On subsequent boots, the QR code is shown briefly for five seconds before the normal display begins.

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

Activate the FlightTracker virtual environment and start the application:

```bash
cd ~/FlightTracker
source env/bin/activate
python flight-tracker.py
```

Alternatively, invoke the virtual environment’s interpreter directly:

```bash
cd ~/FlightTracker
env/bin/python3 flight-tracker.py
```

Press `Ctrl-C` to stop FlightTracker.

---

## Running FlightTracker on boot

FlightTracker includes a systemd service file.

Install it with:

```bash
sudo cp \
    ~/FlightTracker/assets/FlightTracker.service \
    /etc/systemd/system/FlightTracker.service
```

Reload systemd:

```bash
sudo systemctl daemon-reload
```

Enable FlightTracker to start automatically:

```bash
sudo systemctl enable FlightTracker.service
```

Start it immediately:

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

* `~/rgb-matrix-install/env` is used to run the Adafruit installation script.
* `~/FlightTracker/env` contains FlightTracker and its runtime Python dependencies.

FlightTracker does not need the Adafruit installer environment after installation, but the `rpi-rgb-led-matrix` source directory should be retained in case you need to rebuild or reinstall its Python bindings.

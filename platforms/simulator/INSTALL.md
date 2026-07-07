# Installation Guide — Desktop Simulator

Runs FlightTracker in a pygame window on your desktop machine. No Raspberry Pi or LED hardware required — perfect for development and testing.

The simulator renders the 64×32 LED grid as circular LEDs on a dark background, matching the look of the physical panel.

---

## Requirements

- Python 3.10+
- pygame (installed automatically via requirements)

---

## Setup

```bash
git clone https://github.com/ColinWaddell/FlightTracker
cd FlightTracker
python3 -m venv env
source env/bin/activate
pip install -r platforms/simulator/requirements.txt
```

---

## Running

```bash
env/bin/python3 flight-tracker.py
```

A pygame window opens showing the simulated LED matrix. The app runs exactly as it would on a Pi — same scenes, same data sources, same config.

---

## Capture keys

The simulator supports saving screenshots and video frame sequences for documentation:

| Key | Action |
|-----|--------|
| `P` | Save a photo to `captures/<timestamp>.png` |
| `R` | Toggle video recording on/off |

Video frames are saved as a PNG sequence to `captures/<timestamp>/frame_XXXXX.png`. Encode to WebM afterward with:

```bash
cd captures/<timestamp>
ffmpeg -framerate 15 -i frame_%05d.png \
  -vf "select=not(mod(n\,2)),setpts=N/7.5/TB" \
  -r 7.5 -c:v libvpx-vp9 -crf 50 -b:v 0 out.webm
```

---

## Configuration

The simulator uses the same `config.json` as the Pi versions. On first run, a web interface is available at `http://localhost:8584` for configuration. See the [main README](../../README.md) for the full settings reference.

---

## Display tuning

The simulator has tunable constants at the top of `display/rgbpanel_simulator.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `_PIXEL_SIZE` | 10 | Size of each LED cell in screen pixels |
| `_GAP` | 1 | Dark gap between LEDs |
| `_ANTIALIAS` | True | Anti-alias circle edges |
| `BRIGHTNESS` | 1.5 | Brightness boost multiplier (1.0 = no boost) |
| `_OFF_LED_LEVEL` | 8 | Brightness of dim circles for off-LEDs |
#!/bin/bash
#
# FlightTracker Install Script (router)
#
# Detects your Raspberry Pi model and runs the correct install script
# from the FlightTracker GitHub repository.
#
# Usage:
#   curl -sSL https://flight-tracker.dev/install.sh | bash
#

set -e

GITHUB_BASE="https://raw.githubusercontent.com/ColinWaddell/FlightTracker/refs/heads/main/platforms"

# --- Detect Pi model -------------------------------------------------------

PI_MODEL=""
if [ -f /proc/device-tree/model ]; then
    PI_MODEL=$(tr -d '\0' < /proc/device-tree/model)
fi

# If we can't detect the model, ask the user to pick.
if [ -z "$PI_MODEL" ]; then
    echo ""
    echo "  Could not auto-detect your Raspberry Pi model."
    echo ""
    echo "  Which Pi are you installing on?"
    echo "    1) Raspberry Pi 3 / 4 / Zero 2 W / Zero W"
    echo "    2) Raspberry Pi 5"
    echo ""
    read -r -p "  Choice [1 or 2]: " CHOICE
    case "$CHOICE" in
        1) PI_MODEL="Raspberry Pi 4" ;;
        2) PI_MODEL="Raspberry Pi 5" ;;
        *)
            echo "  Invalid choice. Exiting."
            exit 1
            ;;
    esac
fi

# --- Route to the correct script -------------------------------------------

if echo "$PI_MODEL" | grep -iq "Raspberry Pi 5"; then
    echo ""
    echo "  Detected: $PI_MODEL"
    echo "  Using Pi 5 install script."
    echo ""
    exec bash -c "curl -sSL ${GITHUB_BASE}/pi5/install.sh | bash"
else
    echo ""
    echo "  Detected: $PI_MODEL"
    echo "  Using Pi 3/4/Zero install script."
    echo ""
    exec bash -c "curl -sSL ${GITHUB_BASE}/pi/install.sh | bash"
fi
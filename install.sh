#!/bin/bash
#
# FlightTracker Install Script
# For Raspberry Pi (3B, 4B, Zero 2 W, Zero W) running Raspbian Trixie
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/feature/feature-upgrade/install.sh | bash
#

set -e

# ============================================================================
# CONFIGURATION
# ============================================================================

# Git branch to clone (change to "master" when merged)
BRANCH="feature/feature-upgrade"

# ============================================================================
# HELPERS
# ============================================================================

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}[INFO]${NC} $*"; }
success() { echo -e "${GREEN}[OK]${NC} $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC} $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; }

confirm() {
    local prompt="$1"
    local default="${2:-y}"
    local reply
    if [ "$default" = "y" ]; then
        read -p "${prompt} [Y/n] " reply < /dev/tty
        reply=${reply:-y}
    else
        read -p "${prompt} [y/N] " reply < /dev/tty
        reply=${reply:-n}
    fi
    [[ "$reply" =~ ^[Yy]$ ]]
}

# ============================================================================
# PRE-FLIGHT CHECKS
# ============================================================================

echo ""
echo -e "${BOLD}========================================${NC}"
echo -e "${BOLD}  FlightTracker Install Script${NC}"
echo -e "${BOLD}========================================${NC}"
echo ""

# Detect user and home directory (don't assume 'pi')
CURRENT_USER=$(whoami)
CURRENT_HOME="$HOME"
info "User: ${CURRENT_USER}"
info "Home: ${CURRENT_HOME}"

# Check we're on a Raspberry Pi
if [ ! -f /proc/device-tree/model ]; then
    error "This doesn't appear to be a Raspberry Pi (no /proc/device-tree/model)."
    exit 1
fi
PI_MODEL=$(cat /proc/device-tree/model | tr -d '\0')
info "Detected: ${PI_MODEL}"

# Warn Pi Zero W users about long compile times
if echo "$PI_MODEL" | grep -q "Zero W" && ! echo "$PI_MODEL" | grep -q "Zero 2"; then
    warn "Pi Zero W detected. Compilation steps will be slow (single-core ARMv6)."
    warn "If running over SSH, the connection may drop during long builds."
    warn "Consider using screen/tmux, or just re-run the script if this happens."
    echo ""
fi

# Check we're on Raspbian
if [ ! -f /etc/os-release ]; then
    error "Cannot determine OS (no /etc/os-release)."
    exit 1
fi
. /etc/os-release
info "OS: ${PRETTY_NAME}"

if [ "$ID" != "raspbian" ]; then
    warn "This script is designed for Raspbian. You're running ${ID}. Things may not work."
    if ! confirm "Continue anyway?"; then
        exit 1
    fi
fi

# Check for existing installation
INSTALL_DIR="${CURRENT_HOME}/FlightTracker"
RGB_MATRIX_DIR="${CURRENT_HOME}/rpi-rgb-led-matrix"

if [ -d "$INSTALL_DIR" ] || [ -d "$RGB_MATRIX_DIR" ]; then
    warn "An existing FlightTracker installation was detected."
    [ -d "$INSTALL_DIR" ] && echo "  - ${INSTALL_DIR}"
    [ -d "$RGB_MATRIX_DIR" ] && echo "  - ${RGB_MATRIX_DIR}"
    echo ""
    echo "This script is designed for fresh installs and takes no responsibility"
    echo "for installed software on deployed hardware."
    echo ""
    if confirm "Would you like to uninstall the existing installation?"; then
        info "Uninstalling existing FlightTracker installation..."

        # Stop and remove service
        if systemctl is-active --quiet FlightTracker.service 2>/dev/null; then
            sudo systemctl stop FlightTracker.service
            success "Stopped FlightTracker service"
        fi
        if systemctl is-enabled --quiet FlightTracker.service 2>/dev/null; then
            sudo systemctl disable FlightTracker.service
        fi
        if [ -f /etc/systemd/system/FlightTracker.service ]; then
            sudo rm /etc/systemd/system/FlightTracker.service
            sudo systemctl daemon-reload
            success "Removed systemd service"
        fi

        # Remove directories
        if [ -d "$INSTALL_DIR" ]; then
            rm -rf "$INSTALL_DIR"
            success "Removed ${INSTALL_DIR}"
        fi
        if [ -d "$RGB_MATRIX_DIR" ]; then
            rm -rf "$RGB_MATRIX_DIR"
            success "Removed ${RGB_MATRIX_DIR}"
        fi

        # Remove setcap (best effort, harmless if left)
        PYTHON_BIN=$(readlink -f "$(which python3)" 2>/dev/null)
        if [ -n "$PYTHON_BIN" ]; then
            SETCAP_BIN=$(which setcap 2>/dev/null || echo /usr/sbin/setcap)
            if [ -x "$SETCAP_BIN" ]; then
                sudo "$SETCAP_BIN" -r "$PYTHON_BIN" 2>/dev/null || true
                success "Removed setcap from ${PYTHON_BIN}"
            fi
        fi

        warn "Some system-level changes from the Adafruit RGB Matrix installer may remain"
        warn "in /boot/firmware/config.txt, /boot/firmware/cmdline.txt, and installed apt packages."
        echo ""
        success "Uninstall complete. Re-run this script to perform a fresh install."
        exit 0
    else
        error "Cannot proceed with existing installation in place."
        exit 1
    fi
fi

# Check internet connectivity
if ! ping -c 1 -W 5 github.com >/dev/null 2>&1; then
    error "Cannot reach github.com. Check your internet connection."
    exit 1
fi
info "Internet connectivity: OK"

# Check sudo access
if ! sudo -n true 2>/dev/null; then
    if ! sudo true 2>/dev/null; then
        error "This script requires sudo access."
        exit 1
    fi
fi
info "Sudo access: OK"

# Fresh install warning
echo ""
warn "This script is designed for fresh Raspbian installs."
warn "No responsibility is taken for installed software on deployed hardware."
echo ""

if ! confirm "Ready to begin installation?"; then
    info "Aborted by user."
    exit 0
fi

# ============================================================================
# STEP 1: System Update
# ============================================================================

echo ""
echo -e "${BOLD}--- Step 1: System Update ---${NC}"
echo ""

info "Updating system packages. This may take a while, especially on Pi Zero W..."
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get dist-upgrade -y

info "Installing required packages..."
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git \
    curl \
    python3 \
    python3-venv \
    python3-pip \
    libcap2-bin

success "System update complete."

# ============================================================================
# STEP 2: Install RGB Matrix Driver
# ============================================================================

echo ""
echo -e "${BOLD}--- Step 2: Install RGB Matrix Driver ---${NC}"
echo ""

info "Downloading Adafruit RGB Matrix installer..."
curl -sSL "https://raw.githubusercontent.com/adafruit/Raspberry-Pi-Installer-Scripts/refs/heads/main/converted_shell_scripts/rgb-matrix.sh" > /tmp/rgb-matrix.sh

echo ""
echo -e "${BOLD}The Adafruit installer is about to run.${NC}"
echo ""
echo "It will ask you some questions about your hardware setup:"
echo "  - Which interface board you're using (Adafruit RGB Matrix Bonnet or HAT+RTC)"
echo "  - If HAT: whether you have an RTC connected"
echo "  - Quality vs Convenience mode (Quality disables sound and requires"
echo "    a solder bridge between GPIO4 and GPIO18 on the Bonnet)"
echo ""
echo "If you have a multi-core Pi (3B, 4B, Zero 2 W), it may also ask about"
echo "isolating a core for the matrix driver."
echo ""
echo "At the end, the installer will ask if you want to reboot."
echo -e "${BOLD}Say NO to the reboot prompt${NC} — this script will handle the reboot."
echo ""

if ! confirm "Ready to run the Adafruit installer?"; then
    warn "Skipping RGB Matrix driver installation. The FlightTracker won't work without it."
    exit 1
fi

# Run interactively
sudo bash /tmp/rgb-matrix.sh

echo ""
if ! confirm "Did the Adafruit installer complete successfully?"; then
    warn "The Adafruit installer may not have completed properly."
    if confirm "Would you like to try running it again?"; then
        sudo bash /tmp/rgb-matrix.sh
        echo ""
        if ! confirm "Did it complete successfully this time?"; then
            error "Adafruit installer failed twice. Please check your hardware setup and try again."
            exit 1
        fi
    else
        error "Cannot continue without the RGB Matrix driver."
        exit 1
    fi
fi

# Verify install
if [ ! -d "$RGB_MATRIX_DIR" ]; then
    error "RGB Matrix library not found at ${RGB_MATRIX_DIR}"
    error "The Adafruit installer may have used a different path or failed."
    exit 1
fi
success "RGB Matrix library installed at ${RGB_MATRIX_DIR}"

# Fix ownership — Adafruit installer runs as root, files end up root-owned
info "Fixing file ownership..."
sudo chown -R "$CURRENT_USER":"$CURRENT_USER" "$RGB_MATRIX_DIR"
success "Ownership set to ${CURRENT_USER}"

# Run demo to verify screen
echo ""
echo -e "${BOLD}Testing the RGB Matrix display...${NC}"
echo ""
echo "A demo pattern should now appear on your RGB Matrix screen."
echo "If you see something, the screen is working correctly."
echo ""

if confirm "Ready to run the demo test?"; then
    cd "${RGB_MATRIX_DIR}/examples-api-use"
    sudo ./demo --led-rows=32 --led-cols=64 -D0 || true
    echo ""
    if ! confirm "Did you see something on the screen?"; then
        warn "The screen test didn't show output. This could be a wiring issue."
        if confirm "Would you like to re-run the Adafruit installer?"; then
            sudo bash /tmp/rgb-matrix.sh
            echo ""
            if confirm "Did the installer complete successfully?"; then
                sudo chown -R "$CURRENT_USER":"$CURRENT_USER" "$RGB_MATRIX_DIR"
                success "OK, continuing."
            else
                error "Unable to get the RGB Matrix working. Please check your hardware."
                exit 1
            fi
        else
            warn "Continuing without a confirmed working screen. You can test manually later."
        fi
    else
        success "Screen is working!"
    fi
    cd "$CURRENT_HOME"
fi

# ============================================================================
# STEP 3: Clone FlightTracker Repo
# ============================================================================

echo ""
echo -e "${BOLD}--- Step 3: Clone FlightTracker ---${NC}"
echo ""

info "Cloning FlightTracker (branch: ${BRANCH})..."
cd "$CURRENT_HOME"
git clone --depth 1 --branch "${BRANCH}" https://github.com/ColinWaddell/FlightTracker

if [ ! -d "$INSTALL_DIR" ]; then
    error "Failed to clone FlightTracker repository."
    exit 1
fi
success "FlightTracker cloned to ${INSTALL_DIR}"

# ============================================================================
# STEP 4: Create Virtual Environment & Install Dependencies
# ============================================================================

echo ""
echo -e "${BOLD}--- Step 4: Install Python Dependencies ---${NC}"
echo ""

# Detect Python binary path dynamically
PYTHON_BIN=$(readlink -f "$(which python3)")
PYTHON_VERSION=$("$PYTHON_BIN" --version 2>&1)
info "Python: ${PYTHON_VERSION}"
info "Binary: ${PYTHON_BIN}"

info "Creating Python virtual environment..."
cd "$INSTALL_DIR"
python3 -m venv env

# Use TMPDIR on disk for pip builds — /tmp is tmpfs (RAM) on Raspberry Pi
# and can be too small for building packages like curl_cffi on Pi Zero W
PIP_TMPDIR="${CURRENT_HOME}/.pip-tmp"
mkdir -p "$PIP_TMPDIR"
info "Using build directory: ${PIP_TMPDIR} (avoids /tmp RAM disk space issues)"

info "Installing Python dependencies (this may take a while)..."
TMPDIR="$PIP_TMPDIR" ./env/bin/pip install --upgrade pip
TMPDIR="$PIP_TMPDIR" ./env/bin/pip install -r requirements.txt

info "Installing RGB Matrix Python bindings from local library..."
cd "${RGB_MATRIX_DIR}/bindings/python"
TMPDIR="$PIP_TMPDIR" "${INSTALL_DIR}/env/bin/pip" install .

# Clean up build temp
rm -rf "$PIP_TMPDIR"
success "Python dependencies installed."

# ============================================================================
# STEP 5: Configure setcap
# ============================================================================

echo ""
echo -e "${BOLD}--- Step 5: Configure Permissions ---${NC}"
echo ""

info "Python binary: ${PYTHON_BIN}"

# Detect setcap binary path dynamically
SETCAP_BIN=$(which setcap 2>/dev/null || echo /usr/sbin/setcap)
if [ ! -x "$SETCAP_BIN" ]; then
    error "setcap not found. Install libcap2-bin and try again."
    exit 1
fi
info "setcap binary: ${SETCAP_BIN}"

sudo "$SETCAP_BIN" 'cap_sys_nice=eip' "$PYTHON_BIN"
success "Real-time scheduling permissions configured."

# ============================================================================
# STEP 6: Install systemd Service
# ============================================================================

echo ""
echo -e "${BOLD}--- Step 6: Install System Service ---${NC}"
echo ""

SERVICE_TEMPLATE="${INSTALL_DIR}/assets/FlightTracker.service"
if [ ! -f "$SERVICE_TEMPLATE" ]; then
    error "Service template not found at ${SERVICE_TEMPLATE}"
    exit 1
fi

info "Generating service file from template..."
# Substitute __USER__ and __HOME__ placeholders
GENERATED_SERVICE="/tmp/FlightTracker.service"
sed -e "s|__USER__|${CURRENT_USER}|g" \
    -e "s|__HOME__|${CURRENT_HOME}|g" \
    "$SERVICE_TEMPLATE" > "$GENERATED_SERVICE"

info "Installing systemd service..."
sudo cp "$GENERATED_SERVICE" /etc/systemd/system/FlightTracker.service
rm -f "$GENERATED_SERVICE"
sudo systemctl daemon-reload
sudo systemctl enable FlightTracker.service

success "Service installed and enabled."

# ============================================================================
# STEP 7: Reboot
# ============================================================================

echo ""
echo -e "${BOLD}========================================${NC}"
echo -e "${BOLD}  Installation Complete!${NC}"
echo -e "${BOLD}========================================${NC}"
echo ""

# Get the Pi's IP address
PI_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo "The RGB Matrix driver needs a reboot to take effect — sound blacklist,"
echo "boot config changes, etc."
echo ""

if confirm "Reboot now? (The FlightTracker service will start automatically on boot)"; then
    success "Rebooting..."
    echo ""
    echo "After the Pi reboots, configure your FlightTracker via the web interface:"
    if [ -n "$PI_IP" ]; then
        echo "  http://${PI_IP}:8584/"
    else
        echo "  http://<your-pi-ip>:8584/"
    fi
    echo ""
    echo "Check service logs with:"
    echo "  journalctl -u FlightTracker.service -f"
    echo ""
    sync
    sudo reboot
else
    echo ""
    info "You can reboot later with: sudo reboot"
    echo ""
    echo "After reboot, configure your FlightTracker via the web interface:"
    if [ -n "$PI_IP" ]; then
        echo "  http://${PI_IP}:8584/"
    else
        echo "  http://<your-pi-ip>:8584/"
    fi
    echo ""
    echo "The service is enabled and will start automatically on boot."
    echo ""
    echo "To start it manually without rebooting:"
    echo "  sudo systemctl start FlightTracker.service"
    echo ""
    echo "Check service logs with:"
    echo "  journalctl -u FlightTracker.service -f"
fi

# Clean up
rm -f /tmp/rgb-matrix.sh

echo ""
info "Done!"

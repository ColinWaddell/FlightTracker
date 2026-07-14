#!/bin/bash
#
# FlightTracker Install Script - Raspberry Pi 5 Edition
# For Raspberry Pi 5 running Raspberry Pi OS (64-bit, Debian Trixie)
#
# This script uses Adafruit's Adafruit_Blinka_Raspberry_Pi5_Piomatter library
# which drives the RGB panel via the Pi 5's PIO subsystem - no C++ compilation
# needed, unlike the Pi 3/4 installer which builds hzeller's rpi-rgb-led-matrix.
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/main/platforms/pi5/install.sh | bash
#

set -e

# If stdin is not a terminal (e.g. curl | bash), the script content is being
# piped in. Interactive prompts need terminal access, so we save ourselves
# to a temp file and re-exec with stdin connected to /dev/tty.
if [ ! -t 0 ]; then
    TMP_SCRIPT=$(mktemp /tmp/flighttracker-install.XXXXXX.sh)
    cat > "$TMP_SCRIPT"
    exec bash "$TMP_SCRIPT" < /dev/tty
fi

# ============================================================================
# CONFIGURATION
# ============================================================================

# Git branch to clone
BRANCH="main"

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
        read -p "${prompt} [Y/n] " reply
        reply=${reply:-y}
    else
        read -p "${prompt} [y/N] " reply
        reply=${reply:-n}
    fi
    [[ "$reply" =~ ^[Yy]$ ]]
}

# Run a long command quietly, showing dots while it works.
# If the command fails, dump the last 30 lines of output for debugging.
# Usage: run_quiet "message" command args...
run_quiet() {
    local msg="$1"
    shift
    local log
    log=$(mktemp /tmp/flighttracker-log.XXXXXX)
    echo -ne "${BLUE}[INFO]${NC} ${msg}"
    "$@" > "$log" 2>&1 &
    local pid=$!
    while kill -0 "$pid" 2>/dev/null; do
        echo -n "."
        sleep 3
    done
    wait "$pid"
    local rc=$?
    echo ""
    if [ $rc -ne 0 ]; then
        error "Command failed (exit code ${rc}). Last 30 lines of output:"
        echo ""
        tail -30 "$log"
        echo ""
        rm -f "$log"
        return $rc
    fi
    rm -f "$log"
    success "${msg} done."
}

# ============================================================================
# SYSTEM DETECTION
# ============================================================================

echo ""
echo -e "${BOLD}========================================${NC}"
echo -e "${BOLD}  FlightTracker Install (Pi 5)${NC}"
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

# Verify it's a Pi 5
if ! echo "$PI_MODEL" | grep -q "Raspberry Pi 5"; then
    error "This script is for Raspberry Pi 5 only. Detected: ${PI_MODEL}"
    error "For Pi 3/4/Zero, use the Pi installer instead:"
    error "  curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/main/platforms/pi/install.sh | bash"
    exit 1
fi

# Check we're on a Debian-based system
if [ ! -f /etc/os-release ]; then
    error "Cannot determine OS (no /etc/os-release)."
    exit 1
fi
. /etc/os-release
info "OS: ${PRETTY_NAME}"

if ! command -v apt-get >/dev/null 2>&1; then
    error "This system doesn't use apt. The installer requires a Debian-based system."
    exit 1
fi

IS_DEBIAN_DERIV=0
if [ "$ID" = "debian" ] || [ "$ID" = "raspbian" ]; then
    IS_DEBIAN_DERIV=1
fi
if [ -n "$ID_LIKE" ] && echo "$ID_LIKE" | grep -qw debian 2>/dev/null; then
    IS_DEBIAN_DERIV=1
fi

if [ "$IS_DEBIAN_DERIV" -ne 1 ]; then
    warn "This script is designed for Raspberry Pi OS (Raspbian/Debian). You're running ${ID}."
    warn "Things may not work."
    if ! confirm "Continue anyway?"; then
        exit 1
    fi
fi

# Check for PIO device (required by piomatter)
if [ ! -e /dev/pio0 ]; then
    error "PIO device /dev/pio0 not found."
    error "This is required for the Pi 5 RGB matrix driver."
    error "Run 'sudo rpi-update' to update your firmware, then reboot and try again."
    exit 1
fi
info "PIO device: /dev/pio0 present"

# Check user is in gpio group (needed for /dev/pio0 access)
if ! groups "$CURRENT_USER" | grep -qw gpio; then
    warn "User '${CURRENT_USER}' is not in the 'gpio' group."
    warn "Adding you now - you'll need to log out and back in for it to take effect."
    sudo usermod -aG gpio "$CURRENT_USER"
    success "Added ${CURRENT_USER} to gpio group."
    NEEDS_RELOGIN=1
else
    info "GPIO group membership: OK"
    NEEDS_RELOGIN=0
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

# Paths
INSTALL_DIR="${CURRENT_HOME}/FlightTracker"

# ============================================================================
# EXISTING INSTALLATION CHECK
# ============================================================================

if [ -d "$INSTALL_DIR" ]; then
    echo ""
    warn "An existing FlightTracker installation was detected at ${INSTALL_DIR}"
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

        # Remove directory
        rm -rf "$INSTALL_DIR"
        success "Removed ${INSTALL_DIR}"

        warn "Some system-level changes may remain (installed apt packages)."
        echo ""
        success "Uninstall complete. Re-run this script to perform a fresh install."
        exit 0
    else
        error "Cannot proceed with existing installation in place."
        exit 1
    fi
fi

# ============================================================================
# READY TO BEGIN
# ============================================================================

echo ""
warn "This script is designed for fresh Raspberry Pi OS installs."
warn "No responsibility is taken for installed software on deployed hardware."
echo ""

if ! confirm "Ready to begin installation?"; then
    info "Aborted by user."
    exit 0
fi

echo ""
echo -e "${BOLD}========================================${NC}"
echo -e "${BOLD}  Installation - This will take a moment${NC}"
echo -e "${BOLD}========================================${NC}"
echo ""

# ============================================================================
# STEP 1: System Update & Packages
# ============================================================================

echo -e "${BOLD}--- Step 1: System Update ---${NC}"
echo ""

info "Updating firmware (rpi-update)..."
# rpi-update gets the latest firmware, important for Pi 5 PIO support
# on older board revisions.
sudo rpi-update -y || warn "rpi-update failed (non-fatal, continuing)"

info "Updating system packages..."
sudo apt-get update
run_quiet "Upgrading system packages" sudo DEBIAN_FRONTEND=noninteractive apt-get dist-upgrade -y || exit 1

info "Installing required packages..."
# No C++ build tools needed - piomatter is a pre-built wheel.
# No cython3, python3-setuptools, or python3-pillow needed (those were for
# building hzeller's C++ library). No libcap2-bin needed - piomatter uses
# the PIO hardware, not real-time scheduling.
run_quiet "Installing required packages" sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git \
    curl \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev || exit 1

# Ensure PIO udev rule exists (allows non-root access to /dev/pio0)
# On current Raspberry Pi OS, this is provided by raspberrypi-sys-mods
# in /lib/udev/rules.d/60-piolib.rules, but we ensure it as a safety net.
PIO_RULE_FILE="/etc/udev/rules.d/99-com.rules"
PIO_RULE='SUBSYSTEM=="*-pio", GROUP="gpio", MODE="0660"'
if ! sudo grep -q '\*-pio' "$PIO_RULE_FILE" 2>/dev/null; then
    info "Adding PIO udev rule to ${PIO_RULE_FILE}..."
    echo "$PIO_RULE" | sudo tee -a "$PIO_RULE_FILE" > /dev/null
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    success "PIO udev rule added."
else
    info "PIO udev rule already present."
fi

success "System update complete."

# ============================================================================
# STEP 2: Clone FlightTracker Repo
# ============================================================================

echo ""
echo -e "${BOLD}--- Step 2: Clone FlightTracker ---${NC}"
echo ""

run_quiet "Cloning FlightTracker (branch: ${BRANCH})" git clone --depth 1 --branch "${BRANCH}" https://github.com/ColinWaddell/FlightTracker || exit 1

if [ ! -d "$INSTALL_DIR" ]; then
    error "Failed to clone FlightTracker repository."
    exit 1
fi
success "FlightTracker cloned to ${INSTALL_DIR}"

# ============================================================================
# STEP 3: Create Virtual Environment & Install Python Dependencies
# ============================================================================

echo ""
echo -e "${BOLD}--- Step 3: Install Python Dependencies ---${NC}"
echo ""

PYTHON_BIN=$(readlink -f "$(which python3)")
PYTHON_VERSION=$("$PYTHON_BIN" --version 2>&1)
info "Python: ${PYTHON_VERSION}"
info "Binary: ${PYTHON_BIN}"

info "Creating Python virtual environment..."
cd "$INSTALL_DIR"
python3 -m venv env

# /tmp is tmpfs on Raspberry Pi. Give it more headroom for pip operations.
TMP_SIZE="512M"
info "Resizing /tmp tmpfs to ${TMP_SIZE} (needed for pip builds)..."
sudo mount -o remount,size=${TMP_SIZE} /tmp 2>/dev/null || true

# Use a disk-based temp dir as a secondary measure for large pip builds
PIP_TMPDIR="${CURRENT_HOME}/.pip-tmp"
mkdir -p "$PIP_TMPDIR"

info "Installing Python dependencies (this may take a few minutes)..."
echo ""

run_quiet "Upgrading pip" env TMPDIR="$PIP_TMPDIR" ./env/bin/pip install --upgrade pip || exit 1
run_quiet "Installing Pi 5 Python requirements" env TMPDIR="$PIP_TMPDIR" ./env/bin/pip install -r platforms/pi5/requirements.txt || exit 1

# Verify piomatter import works
info "Verifying piomatter installation..."
if ! "${INSTALL_DIR}/env/bin/python" -c 'import adafruit_blinka_raspberry_pi5_piomatter' 2>/dev/null; then
    error "Failed to import adafruit_blinka_raspberry_pi5_piomatter."
    error "Ensure /dev/pio0 exists and you're in the gpio group."
    exit 1
fi

# Clean up build temp
rm -rf "$PIP_TMPDIR"
success "Python dependencies installed."

# ============================================================================
# STEP 4: Install systemd Service
# ============================================================================

echo ""
echo -e "${BOLD}--- Step 4: Install System Service ---${NC}"
echo ""

SERVICE_TEMPLATE="${INSTALL_DIR}/assets/FlightTracker.service"
if [ ! -f "$SERVICE_TEMPLATE" ]; then
    error "Service template not found at ${SERVICE_TEMPLATE}"
    exit 1
fi

info "Generating service file from template..."
# Substitute pi placeholder
GENERATED_SERVICE="/tmp/FlightTracker.service"
sed \
    -e "s|/home/pi/|/home/${CURRENT_USER}/|g" \
    -e "s|^User=pi$|User=${CURRENT_USER}|" \
    "$SERVICE_TEMPLATE" > "$GENERATED_SERVICE"

info "Installing systemd service..."
sudo cp "$GENERATED_SERVICE" /etc/systemd/system/FlightTracker.service
rm -f "$GENERATED_SERVICE"
sudo systemctl daemon-reload
sudo systemctl enable FlightTracker.service

success "Service installed and enabled."

# ============================================================================
# STEP 5: Reboot
# ============================================================================

# Get the Pi's IP address
PI_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo ""
echo -e "${GREEN}${BOLD}========================================${NC}"
echo -e "${GREEN}${BOLD}  Everything installed successfully!${NC}"
echo -e "${GREEN}${BOLD}========================================${NC}"
echo ""

echo "After reboot, the FlightTracker service will start automatically."
echo "You can access the web interface at:"
if [ -n "$PI_IP" ]; then
    echo -e "  ${BOLD}http://${PI_IP}:8584/${NC}"
else
    echo -e "  ${BOLD}http://<your-pi-ip>:8584/${NC}"
fi
echo ""
warn "It may take a few minutes after reboot before the web interface loads."
warn "Be patient - the Pi needs time to boot and start the service."
echo ""
echo "Check service logs with:"
echo "  journalctl -u FlightTracker.service -f"
echo ""

if [ "$NEEDS_RELOGIN" -eq 1 ]; then
    warn "You were added to the 'gpio' group. A reboot is required for this"
    warn "to take effect - the service will still work (it runs as your user"
    warn "with the new group membership after reboot)."
    echo ""
fi

if confirm "Reboot now?"; then
    sync
    success "Rebooting..."
    sudo reboot
else
    echo ""
    info "Reboot later with: sudo reboot"
    echo ""
    echo "To start the service now without rebooting:"
    echo "  sudo systemctl start FlightTracker.service"
fi

echo ""
info "Done!"
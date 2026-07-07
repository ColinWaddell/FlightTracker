#!/bin/bash
#
# FlightTracker Install Script
# For Raspberry Pi (3B, 4B, Zero 2 W, Zero W) running Raspbian Trixie
#
# Usage:
#   curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/master/platforms/pi/install.sh | bash
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

# Git branch to clone (change to "master" when merged)
BRANCH="feature/feature-upgrade"

# Pinned commit of hzeller/rpi-rgb-led-matrix (same as Adafruit installer)
RGB_MATRIX_REPO="https://github.com/hzeller/rpi-rgb-led-matrix"
RGB_MATRIX_COMMIT="7a503494378a67f3baa4ac680cecbae2703cc58f"

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

# Given a list of strings representing options, display each option
# preceded by a number (1 to N), display a prompt, check input until
# a valid number within the selection range is entered.
selectN() {
    local args=("$@")
    local i
    for ((i=0; i<${#args[@]}; i++)); do
        echo "  $((i+1)). ${args[$i]}"
    done
    echo ""
    local reply=""
    local last=${#args[@]}
    while :; do
        read -p "SELECT 1-$last: " reply
        if [[ "$reply" =~ ^[0-9]+$ ]] && [ "$reply" -ge 1 ] && [ "$reply" -le "$last" ]; then
            return $((reply - 1))
        fi
    done
}

# Given a filename, a regex pattern to match and a replacement string,
# perform replacement if found, else append replacement to end of file.
reconfig() {
    # $1 = filename, $2 = pattern to match, $3 = replacement
    if grep "$2" "$1" >/dev/null 2>&1; then
        # Pattern found; replace in file
        sudo sed -i "s/$2/$3/g" "$1" >/dev/null
    else
        # Not found; append
        echo "$3" | sudo tee -a "$1" >/dev/null
    fi
}

# ============================================================================
# SYSTEM DETECTION
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

# Redirect Pi 5 users to the Pi 5 installer
if echo "$PI_MODEL" | grep -q "Raspberry Pi 5"; then
    error "This script is for Pi 3/4/Zero. Detected: ${PI_MODEL}"
    error "For Pi 5, use the Pi 5 installer instead:"
    error "  curl -sSL https://raw.githubusercontent.com/ColinWaddell/FlightTracker/master/platforms/pi5/install.sh | bash"
    exit 1
fi

# Detect number of CPU cores
NUM_CORES=$(nproc --all)

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

# Warn Pi Zero W users about long compile times
if echo "$PI_MODEL" | grep -q "Zero W" && ! echo "$PI_MODEL" | grep -q "Zero 2"; then
    echo ""
    warn "Pi Zero W detected. Compilation steps will be slow (single-core ARMv6)."
    warn "If running over SSH, the connection may drop during long builds."
    warn "Consider using screen/tmux, or just re-run the script if this happens."
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
RGB_MATRIX_DIR="${CURRENT_HOME}/rpi-rgb-led-matrix"

# ============================================================================
# EXISTING INSTALLATION CHECK
# ============================================================================

if [ -d "$INSTALL_DIR" ] || [ -d "$RGB_MATRIX_DIR" ]; then
    echo ""
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

        # Remove sound blacklist (our install creates it)
        if [ -f /etc/modprobe.d/blacklist-rgb-matrix.conf ]; then
            sudo rm -f /etc/modprobe.d/blacklist-rgb-matrix.conf
            success "Removed sound blacklist"
        fi

        # Remove isolcpus from cmdline.txt (best effort)
        CMDLINE_FILE=/boot/firmware/cmdline.txt
        if [ ! -f "$CMDLINE_FILE" ]; then
            CMDLINE_FILE=/boot/cmdline.txt
        fi
        if [ -f "$CMDLINE_FILE" ]; then
            sudo sed -i -E -e 's/(^| )isolcpus=[0-9]+( |$)/\1\2/g' -e 's/  +/ /g' -e 's/ $//' "$CMDLINE_FILE" 2>/dev/null || true
            success "Removed isolcpus from cmdline (if present)"
        fi

        warn "Some system-level changes may remain in /boot/firmware/config.txt"
        warn "and installed apt packages."
        echo ""
        success "Uninstall complete. Re-run this script to perform a fresh install."
        exit 0
    else
        error "Cannot proceed with existing installation in place."
        exit 1
    fi
fi

# ============================================================================
# ALL QUESTIONS - Answer these, then walk away
# ============================================================================

echo ""
echo -e "${BOLD}========================================${NC}"
echo -e "${BOLD}  Configuration${NC}"
echo -e "${BOLD}========================================${NC}"
echo ""

warn "This script is designed for fresh Raspbian installs."
warn "No responsibility is taken for installed software on deployed hardware."
echo ""

if ! confirm "Ready to begin installation?"; then
    info "Aborted by user."
    exit 0
fi

echo ""
echo "You need to configure the RGB Matrix driver for your hardware."
echo ""

# Interface type
INTERFACES=(
    "Adafruit RGB Matrix Bonnet"
    "Adafruit RGB Matrix HAT + RTC"
)
echo "Select interface board type:"
selectN "${INTERFACES[@]}"
INTERFACE_TYPE=$?

# RTC setup (only for HAT)
INSTALL_RTC=0
if [ "$INTERFACE_TYPE" -eq 1 ]; then
    echo ""
    if confirm "Install realtime clock support?"; then
        INSTALL_RTC=1
    fi
fi

# Quality vs Convenience
QUALITY_OPTS=(
    "Quality (disables sound, requires soldering on single matrix Bonnet/HAT)"
    "Convenience (sound on, no soldering)"
)
echo ""
echo "Now you must choose between QUALITY and CONVENIENCE."
echo ""
echo "QUALITY: best output from the LED matrix requires commandeering hardware"
echo "normally used for sound, plus some soldering on the single matrix Bonnet/HAT."
echo "If you choose this option, there will be NO sound from the audio jack or"
echo "HDMI (USB audio adapters will work and sound best anyway), AND you must"
echo "SOLDER a wire between GPIO4 and GPIO18 on the single matrix Bonnet or HAT"
echo "board. For the Triple LED Matrix Bonnet choose QUALITY, and no soldering"
echo "is required."
echo ""
echo "CONVENIENCE: sound works normally, no extra soldering. Images on the LED"
echo "matrix are not quite as steady, but maybe OK for most uses. If eager to"
echo "get started, use CONVENIENCE for now, you can make the change and reinstall"
echo "later!"
echo ""
echo "What is thy bidding?"
selectN "${QUALITY_OPTS[@]}"
QUALITY_MOD=$?

# CPU isolation (only on multi-core)
ISOL_CPU=0
if [ "$NUM_CORES" -ge 2 ]; then
    ISOLCPUS_OPTS=(
        "Do not reserve a core for driving the display"
        "Reserve a core for driving the display (recommended)"
    )
    echo ""
    echo "Your Pi has ${NUM_CORES} CPU cores. You can dedicate one to driving the"
    echo "display. This reduces flicker when the system is busy with other work,"
    echo "at the cost of one core being unavailable for general use. This is the"
    echo "upstream recommendation from hzeller/rpi-rgb-led-matrix."
    selectN "${ISOLCPUS_OPTS[@]}"
    ISOL_CPU=$?
fi

# Verify selections
echo ""
echo -e "${BOLD}Configuration summary:${NC}"
echo "  Interface: ${INTERFACES[$INTERFACE_TYPE]}"
if [ "$INTERFACE_TYPE" -eq 1 ]; then
    echo "  RTC support: $([ "$INSTALL_RTC" -eq 1 ] && echo 'Yes' || echo 'No')"
fi
echo "  Optimize: ${QUALITY_OPTS[$QUALITY_MOD]}"
if [ "$QUALITY_MOD" -eq 0 ]; then
    warn "  Reminder: you must SOLDER a wire between GPIO4 and GPIO18, and internal sound is DISABLED!"
fi
if [ "$NUM_CORES" -ge 2 ]; then
    echo "  Isolate CPU for display driving: ${ISOLCPUS_OPTS[$ISOL_CPU]}"
fi
echo ""

if ! confirm "Continue with these settings?"; then
    info "Aborted by user."
    exit 0
fi

echo ""
echo -e "${BOLD}========================================${NC}"
echo -e "${BOLD}  Installation - you can walk away now${NC}"
echo -e "${BOLD}========================================${NC}"
echo ""

# ============================================================================
# STEP 1: System Update
# ============================================================================

echo -e "${BOLD}--- Step 1: System Update ---${NC}"
echo ""

info "Updating system packages. This may take a while, especially on Pi Zero W..."
sudo apt-get update
run_quiet "Upgrading system packages" sudo DEBIAN_FRONTEND=noninteractive apt-get dist-upgrade -y

info "Installing required packages..."
run_quiet "Installing required packages" sudo DEBIAN_FRONTEND=noninteractive apt-get install -y \
    git \
    curl \
    python3 \
    python3-venv \
    python3-pip \
    python3-dev \
    python3-pillow \
    cython3 \
    python3-setuptools \
    libcap2-bin \
    unzip

success "System update complete."

# ============================================================================
# STEP 2: Clone FlightTracker Repo
# ============================================================================

echo ""
echo -e "${BOLD}--- Step 2: Clone FlightTracker ---${NC}"
echo ""

run_quiet "Cloning FlightTracker (branch: ${BRANCH})" git clone --depth 1 --branch "${BRANCH}" https://github.com/ColinWaddell/FlightTracker

if [ ! -d "$INSTALL_DIR" ]; then
    error "Failed to clone FlightTracker repository."
    exit 1
fi
success "FlightTracker cloned to ${INSTALL_DIR}"

# ============================================================================
# STEP 3: Download & Build RGB Matrix Library
# ============================================================================

echo ""
echo -e "${BOLD}--- Step 3: Build RGB Matrix Driver ---${NC}"
echo ""

info "Downloading RGB matrix library (pinned commit ${RGB_MATRIX_COMMIT})..."
cd "$CURRENT_HOME"
run_quiet "Downloading RGB matrix library" curl -L "${RGB_MATRIX_REPO}/archive/${RGB_MATRIX_COMMIT}.zip" -o "rpi-rgb-led-matrix-${RGB_MATRIX_COMMIT}.zip"
unzip -q "rpi-rgb-led-matrix-${RGB_MATRIX_COMMIT}.zip"
rm "rpi-rgb-led-matrix-${RGB_MATRIX_COMMIT}.zip"
mv "rpi-rgb-led-matrix-${RGB_MATRIX_COMMIT}" "rpi-rgb-led-matrix"

if [ ! -d "$RGB_MATRIX_DIR" ]; then
    error "Failed to download RGB matrix library."
    exit 1
fi
success "RGB matrix library downloaded."

info "Building RGB matrix library..."
warn "This takes a while - especially on Pi Zero W."
echo ""

cd "$RGB_MATRIX_DIR"

# Build with Quality mode flag if selected
USER_DEFINES=""
if [ "$QUALITY_MOD" -eq 1 ]; then
    USER_DEFINES+=" -DDISABLE_HARDWARE_PULSES"
fi

run_quiet "Building RGB matrix library" make clean
run_quiet "Compiling RGB matrix library" make build-python USER_DEFINES="$USER_DEFINES"

# ============================================================================
# STEP 4: Install Python Dependencies
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

# /tmp is tmpfs (RAM) on Raspberry Pi and defaults to ~200MB on Pi Zero W.
# This is too small for building packages like curl_cffi. Resize the tmpfs
# to give more headroom. This is temporary (until reboot) and only increases
# the size - it doesn't consume RAM until actually used.
TMP_SIZE="512M"
info "Resizing /tmp tmpfs to ${TMP_SIZE} (needed for pip builds)..."
sudo mount -o remount,size=${TMP_SIZE} /tmp

# Also set TMPDIR to disk as a secondary measure
PIP_TMPDIR="${CURRENT_HOME}/.pip-tmp"
mkdir -p "$PIP_TMPDIR"

info "Installing Python dependencies (this may take a while)..."
echo ""

run_quiet "Upgrading pip" env TMPDIR="$PIP_TMPDIR" ./env/bin/pip install --upgrade pip
run_quiet "Installing Python requirements" env TMPDIR="$PIP_TMPDIR" ./env/bin/pip install -r platforms/pi/requirements.txt

# Install RGB Matrix Python bindings by copying the pre-built .so files
# directly into the venv's site-packages. The setup.py uses distutils which
# was removed in Python 3.12+, so pip install . fails on Trixie (Python 3.13).
# The `make build-python` step already compiled the .so files, so we just
# copy the package directory.
info "Installing RGB Matrix Python bindings..."
SITE_PACKAGES="${INSTALL_DIR}/env/lib/python$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')/site-packages"
cp -r "${RGB_MATRIX_DIR}/bindings/python/rgbmatrix" "${SITE_PACKAGES}/"

# Verify the import works
if ! "${INSTALL_DIR}/env/bin/python" -c 'from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics' 2>/dev/null; then
    error "Failed to import rgbmatrix. The build may have failed."
    exit 1
fi

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
# STEP 7: Apply Boot Configuration
# ============================================================================

echo ""
echo -e "${BOLD}--- Step 7: Apply Boot Configuration ---${NC}"
echo ""

# Boot config locations. Trixie and later use /boot/firmware/;
# older releases use /boot/.
CMDLINE_FILE=/boot/firmware/cmdline.txt
if [ ! -f "$CMDLINE_FILE" ]; then
    CMDLINE_FILE=/boot/cmdline.txt
fi

# RTC setup (for HAT + RTC)
if [ "$INSTALL_RTC" -ne 0 ]; then
    info "Enabling I2C for RTC..."
    sudo raspi-config nonint do_i2c 0
    reconfig /boot/firmware/config.txt "^.*dtoverlay=i2c-rtc.*$" "dtoverlay=i2c-rtc,ds1307"
    sudo apt-get -y remove fake-hwclock 2>/dev/null || true
    sudo update-rc.d -f fake-hwclock remove 2>/dev/null || true
    sudo sed --in-place '/if \[ -e \/run\/systemd\/system \] ; then/,+2 s/^#*/#/' /lib/udev/hwclock-set 2>/dev/null || true
    success "RTC support configured."
fi

# Sound blacklist (Quality mode disables sound)
if [ "$QUALITY_MOD" -eq 0 ]; then
    info "Disabling internal sound (Quality mode)..."
    echo "blacklist snd_bcm2835" | sudo tee /etc/modprobe.d/blacklist-rgb-matrix.conf >/dev/null
    success "Sound blacklisted."
else
    # Remove blacklist if it exists (Convenience mode)
    sudo rm -f /etc/modprobe.d/blacklist-rgb-matrix.conf 2>/dev/null || true
fi

# CPU isolation (only on multi-core, if selected)
if [ "$NUM_CORES" -ge 2 ] && [ "$ISOL_CPU" -eq 1 ]; then
    info "Reserving CPU core for display driving..."
    ISOLCPU_CMD="isolcpus=$((NUM_CORES - 1))"
    # Strip any previously-added isolcpus=N token first (idempotent)
    sudo sed -i -E -e 's/(^| )isolcpus=[0-9]+( |$)/\1\2/g' -e 's/  +/ /g' -e 's/ $//' "$CMDLINE_FILE"
    # Append isolcpus token
    sudo sed -i "s/$/ ${ISOLCPU_CMD}/" "$CMDLINE_FILE"
    success "CPU core reserved (isolcpus=$((NUM_CORES - 1)))."
fi

# ============================================================================
# STEP 8: Reboot
# ============================================================================

# Get the Pi's IP address
PI_IP=$(hostname -I 2>/dev/null | awk '{print $1}')

echo ""
echo -e "${GREEN}${BOLD}========================================${NC}"
echo -e "${GREEN}${BOLD}  Everything installed successfully!${NC}"
echo -e "${GREEN}${BOLD}========================================${NC}"
echo ""

echo "The RGB Matrix driver needs a reboot to take effect - sound blacklist,"
echo "boot config changes, etc."
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
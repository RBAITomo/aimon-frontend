#!/usr/bin/env bash
# Setup script for AI-MON frontend on Raspberry Pi OS
set -euo pipefail

echo "=== AI-MON Frontend Setup ==="

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REBOOT_NEEDED=false

# ── 1. Whisplay HAT driver (WM8960 audio + LCD + LED + button) ──────
# Installs kernel drivers, device-tree overlays, systemd service, and
# system packages: alsa-utils, i2c-tools, dkms, libasound2-plugins,
#   python3-libgpiod, python3-spidev, python3-pil, python3-pygame
# Reference: https://github.com/PiSugar/whisplay
WHISPLAY_DIR="/opt/whisplay"
if [ ! -d "$WHISPLAY_DIR" ]; then
    echo "Cloning Whisplay HAT driver..."
    sudo git clone https://github.com/PiSugar/whisplay.git --depth 1 "$WHISPLAY_DIR"
fi
echo "Installing Whisplay HAT driver..."
(cd "$WHISPLAY_DIR/Driver" && sudo bash install_wm8960_drive.sh)
REBOOT_NEEDED=true

# ── 2. Additional system packages (not covered by Whisplay) ─────────
echo "Installing additional system packages..."
sudo apt-get update
sudo apt-get install -y \
    python3-pip python3-venv python3-dev \
    portaudio19-dev \
    libopus-dev libopus0 \
    libasound2-dev \
    python3-rpi-lgpio \
    rpicam-apps \
    libzbar0

# ── 3. Python virtual environment ───────────────────────────────────
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR" --system-site-packages
fi
echo "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

# ── 4. Data directory for SQLite ─────────────────────────────────────
mkdir -p "$SCRIPT_DIR/data"

# ── 5. NetworkManager permissions (WiFi hotspot / captive portal) ────
AIMON_USER="${SUDO_USER:-$(whoami)}"
echo "Configuring NetworkManager permissions for $AIMON_USER user..."
sudo usermod -aG netdev "$AIMON_USER" 2>/dev/null || true
POLKIT_RULE="/etc/polkit-1/localauthority/50-local.d/10-aimon-network.pkla"
echo "Installing NetworkManager polkit rule..."
sudo bash -c "cat > $POLKIT_RULE" <<PKLA
[Allow $AIMON_USER to manage NetworkManager WiFi]
Identity=unix-user:$AIMON_USER
Action=org.freedesktop.NetworkManager.*
ResultAny=yes
ResultInactive=yes
ResultActive=yes
PKLA

# ── 6. Boot config (SPI + camera) ───────────────────────────────────
# Whisplay driver already enables I2C, I2S, and WM8960 overlay.
# We still need SPI (LCD via spidev) and camera auto-detect.
CONFIG_FILE="/boot/firmware/config.txt"
if [ ! -f "$CONFIG_FILE" ]; then
    CONFIG_FILE="/boot/config.txt"
fi

if [ -f "$CONFIG_FILE" ] && ! sudo grep -q "^dtparam=spi=on" "$CONFIG_FILE" 2>/dev/null; then
    echo "Enabling SPI interface..."
    sudo bash -c "echo 'dtparam=spi=on' >> $CONFIG_FILE"
    REBOOT_NEEDED=true
fi

# OV5647 camera via CSI; rpicam-apps (Bookworm) replaces legacy libcamera-apps
if [ -f "$CONFIG_FILE" ] && ! sudo grep -q "^camera_auto_detect=1" "$CONFIG_FILE" 2>/dev/null; then
    echo "Enabling camera auto-detect..."
    sudo bash -c "echo 'camera_auto_detect=1' >> $CONFIG_FILE"
    REBOOT_NEEDED=true
fi

echo ""
echo "✅ Setup complete!"
echo ""
if [ "$REBOOT_NEEDED" = "true" ]; then
    echo "⚠️  REBOOT REQUIRED for hardware changes to take effect."
    echo "   Run: sudo reboot"
    echo ""
fi
echo "After reboot, verify hardware:"
echo "   cd $WHISPLAY_DIR/example && sudo bash run_test.sh  # Whisplay HAT"
echo "   rpicam-hello --list-cameras        # verify OV5647 detected"
echo "   rpicam-still --nopreview -o test.jpg  # capture a test photo"
echo ""
echo "Next steps:"
echo "1. Configure backend URL: export BACKEND_WS_URL='ws://192.168.1.52:8080'"
echo "2. Set robot ID: export ROBOT_ID='aimon-001'"
echo "3. Run the frontend: ./run.sh"
echo ""

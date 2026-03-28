#!/usr/bin/env bash
# Setup script for AI-MON frontend on Raspberry Pi OS
set -euo pipefail

echo "=== AI-MON Frontend Setup ==="

# System dependencies
echo "Installing system packages..."
sudo apt-get update
sudo apt-get install -y \
    python3-pip python3-venv python3-dev \
    python3-pygame \
    portaudio19-dev \
    libopus-dev libopus0 \
    libasound2-dev \
    python3-rpi-lgpio \
    i2c-tools \
    rpicam-apps \
    libzbar0

# Create virtual environment
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR" --system-site-packages
fi

echo "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

# Create data directory for SQLite
mkdir -p "$SCRIPT_DIR/data"

# Allow service user to manage WiFi (hotspot creation for captive portal setup)
# Detect current user (typically 'aimon' or 'pi')
AIMON_USER="${SUDO_USER:-$(whoami)}"
echo "Configuring NetworkManager permissions for $AIMON_USER user..."
sudo usermod -aG netdev "$AIMON_USER" 2>/dev/null || true
# Polkit rule to authorize WiFi hotspot without root
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

# Enable SPI if not already enabled
CONFIG_FILE="/boot/firmware/config.txt"
if [ ! -f "$CONFIG_FILE" ]; then
    CONFIG_FILE="/boot/config.txt"
fi

if [ -f "$CONFIG_FILE" ] && ! sudo grep -q "^dtparam=spi=on" "$CONFIG_FILE" 2>/dev/null; then
    echo "Enabling SPI interface..."
    sudo bash -c "echo 'dtparam=spi=on' >> $CONFIG_FILE"
    echo "⚠️  SPI enabled. Reboot required for changes to take effect."
    REBOOT_NEEDED=true
fi

# Enable I2C if not already enabled (for audio codec)
if [ -f "$CONFIG_FILE" ] && ! sudo grep -q "^dtparam=i2c_arm=on" "$CONFIG_FILE" 2>/dev/null; then
    echo "Enabling I2C interface..."
    sudo bash -c "echo 'dtparam=i2c_arm=on' >> $CONFIG_FILE"
    echo "⚠️  I2C enabled. Reboot required for changes to take effect."
    REBOOT_NEEDED=true
fi

# Enable camera if not already enabled (OV5647 via CSI)
# Note: camera_auto_detect=1 is usually present on Bookworm by default.
# rpicam-apps (Bookworm) replaces legacy libcamera-apps; use rpicam-still/rpicam-hello.
if [ -f "$CONFIG_FILE" ] && ! sudo grep -q "^camera_auto_detect=1" "$CONFIG_FILE" 2>/dev/null; then
    echo "Enabling camera auto-detect..."
    sudo bash -c "echo 'camera_auto_detect=1' >> $CONFIG_FILE"
    echo "⚠️  Camera enabled. Reboot required for changes to take effect."
    REBOOT_NEEDED=true
fi

echo ""
echo "✅ Setup complete!"
echo ""
if [ "${REBOOT_NEEDED:-false}" = "true" ]; then
    echo "⚠️  REBOOT REQUIRED: interfaces enabled (SPI/I2C/Camera)"
    echo "   Run: sudo reboot"
    echo ""
fi
echo "Camera test (after reboot):"
echo "   rpicam-hello --list-cameras        # verify OV5647 detected"
echo "   rpicam-still --nopreview -o test.jpg  # capture a test photo"
echo ""
echo "Next steps:"
echo "1. Configure backend URL: export BACKEND_WS_URL='ws://192.168.1.52:8080'"
echo "2. Set robot ID: export ROBOT_ID='aimon-001'"
echo "3. Run the frontend: ./run.sh"
echo ""

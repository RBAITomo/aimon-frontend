#!/usr/bin/env bash
# Start AI-MON frontend on Raspberry Pi
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# LCD is driven via SPI (not framebuffer). Use SDL dummy driver so
# pygame works headless. Override with SDL_VIDEODRIVER=fbcon if you
# ever connect an HDMI display.
export SDL_VIDEODRIVER="${SDL_VIDEODRIVER:-dummy}"

# Backend connection defaults are in .env and config.py.
# Override here only if you need to bypass .env:
#   BACKEND_WS_URL=ws://192.168.1.52:8080 ./run.sh

# Set wm8960 soundcard (card 1) volumes to 100%
if command -v amixer &>/dev/null; then
    for ctl in 'Headphone' 'Speaker' 'Speaker AC' 'Speaker DC'; do
        amixer -c 1 sset "$ctl" 100% 2>/dev/null || true
    done
fi

cd "$SCRIPT_DIR"
exec python3 main.py "$@"

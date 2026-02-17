# AI-MON Frontend - Quick Start

Ultra-fast setup guide for AI-MON frontend on Raspberry Pi.

## 🚀 30-Second Setup

```bash
cd ~
git clone <repo-url> aimon-frontend
cd aimon-frontend
./setup.sh
export BACKEND_WS_URL="ws://192.168.1.100:8080"
./run.sh
```

## 📝 Prerequisites

- ✅ Raspberry Pi Zero 2 / Pi 3 / Pi 4 / Pi 5
- ✅ Whisplay HAT (ST7789 LCD + WM8960 audio)
- ✅ Raspberry Pi OS (Bookworm recommended)
- ✅ SPI enabled: `sudo raspi-config` → Interface → SPI → Yes
- ✅ Backend running at `ws://backend-ip:8080`

## 📦 What Gets Installed

```bash
./setup.sh installs:
├── Python packages (pygame, websockets, pyaudio, opuslib)
├── System packages (portaudio, opus, alsa, spidev)
├── Virtual environment (.venv/)
└── Data directory (data/)
```

## 🎯 Usage

### Run Interactively

```bash
./run.sh
# Press Ctrl+C to stop
```

### Run as Service

```bash
sudo cp aimon-frontend.service /etc/systemd/system/
sudo systemctl enable aimon-frontend
sudo systemctl start aimon-frontend
```

### Check Status

```bash
sudo systemctl status aimon-frontend
sudo journalctl -u aimon-frontend -f
```

## 🔧 Configuration

**Change backend URL:**
```bash
export BACKEND_WS_URL="ws://192.168.1.100:8080"
```

**Change robot ID:**
```bash
export ROBOT_ID="my-robot-001"
```

**Or edit service file:**
```bash
sudo nano /etc/systemd/system/aimon-frontend.service
```

## 🎨 LED Colors

| Color | State | What It Means |
|-------|-------|---------------|
| 🔵 Blue | IDLE | Ready - press button |
| 🟢 Green | LISTENING | Recording your voice |
| 🟡 Yellow | ASR | Processing speech |
| 🔵 Cyan | ANSWER | Playing response |
| 🟡 Yellow | EMOTION | Showing emotion |
| 🔴 Red | OFFLINE | Can't connect to backend |

## 🔄 How It Works

```
1. Press & hold button    → Start recording (mic ON)
2. Release button         → Send audio to backend
3. Backend processes      → ASR → LLM → TTS
4. Display + audio        → Show text, play audio (mic OFF)
5. Show emotion           → Display animation
6. Return to idle         → Ready for next input
```

## 🐛 Troubleshooting

**Can't connect to backend:**
```bash
curl http://backend-ip:8080/q/health
```

**No audio:**
```bash
aplay -l | grep wm8960
speaker-test -c 1 -D hw:1,0
```

**Display not working:**
```bash
ls -l /dev/spidev0.0  # SPI should exist
ls -l /dev/fb0        # Framebuffer should exist
```

**Permission errors:**
```bash
sudo usermod -a -G spi,gpio,audio pi
sudo reboot
```

## 📚 Documentation

- Full README: [README.md](README.md)
- Deployment Guide: [DEPLOYMENT.md](DEPLOYMENT.md)
- Testing Guide: [TESTING.md](TESTING.md)
- Test Suite: [tests/README.md](tests/README.md)

## 🆘 Need Help?

**Check logs:**
```bash
sudo journalctl -u aimon-frontend -n 50
```

**Run diagnostics:**
```bash
cd ~/aimon-frontend
python3 -c "
import sys
print('Python:', sys.version)
try:
    import pygame; print('pygame:', pygame.version.ver)
except: print('pygame: NOT INSTALLED')
try:
    import websockets; print('websockets: OK')
except: print('websockets: NOT INSTALLED')
try:
    import pyaudio; print('pyaudio: OK')
except: print('pyaudio: NOT INSTALLED')
try:
    import opuslib; print('opuslib: OK')
except: print('opuslib: NOT INSTALLED')
"
```

## ⚡ Common Commands

```bash
# Start service
sudo systemctl start aimon-frontend

# Stop service
sudo systemctl stop aimon-frontend

# Restart service
sudo systemctl restart aimon-frontend

# View logs
sudo journalctl -u aimon-frontend -f

# Update code
cd ~/aimon-frontend && git pull
sudo systemctl restart aimon-frontend

# Clear database
rm data/turns.db
sudo systemctl restart aimon-frontend
```

---

**Setup Time:** < 10 minutes  
**Hardware Cost:** ~$60 (Pi Zero 2 + Whisplay HAT)  
**Python Version:** 3.11+

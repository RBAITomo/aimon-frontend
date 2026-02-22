# aimon-frontend

Thin client frontend for AI-MON v0.2 — Pygame-based UI running on Raspberry Pi Zero 2 with Whisplay HAT (ST7789 LCD + WM8960 audio + button).

**Architecture:** Frontend is a **console**, backend is the **brain**. All AI intelligence (ASR, LLM, RAG, TTS, memory) lives in the backend.

## Features

- **Push-to-Talk UI:** Button-driven voice interaction
- **Half-Duplex Audio:** Mic OFF during playback (echo-safe)
- **OPUS Streaming:** Efficient audio encoding (16kHz → 48kHz)
- **WebSocket v4 Protocol:** Real-time bidirectional communication
- **State Machine:** IDLE → LISTENING → ASR → ANSWER → EMOTION
- **Local Turn Logging:** SQLite storage (200 turns max)
- **Sprite Animation:** Emotion-based character rendering
- **RGB LED Feedback:** State-driven color indicators
- **Auto-Reconnect:** Exponential backoff (2s→60s cap)
- **WiFi QR Manager:** Long-press to scan WiFi credentials in offline mode

## Hardware Requirements

### Required
- **Raspberry Pi Zero 2** (or Pi 3/4/5)
- **Whisplay HAT:**
  - ST7789 240×280 LCD (SPI)
  - WM8960 audio codec (I2S)
  - Push button (GPIO)
  - RGB LED (PWM)

### Pinout (BOARD Numbering)
```
Button:     GPIO 11
DC (LCD):   GPIO 13
RST (LCD):  GPIO 7
Backlight:  GPIO 15
LED Red:    GPIO 22
LED Green:  GPIO 18
LED Blue:   GPIO 16
SPI:        Bus 0, Device 0
Audio:      hw:1,0 (WM8960)
```

## Architecture

```
[User] → Button Press
           ↓
[Frontend: main.py]
  ├─ StateMachine → State transitions
  ├─ AudioCapture → OPUS encoding
  ├─ AudioPlayback → PCM16 playback
  ├─ WSClient → Protocol v4
  ├─ TurnLogger → SQLite (200 turns)
  └─ DisplayEngine → Pygame → ST7789 LCD
           ↓
[Backend: WebSocket]
  → ASR → LLM → Memory → TTS
           ↓
[Frontend] → Display + Audio
```

## Tech Stack

- **Runtime:** Python 3.11+
- **UI:** Pygame (framebuffer mode, no X11)
- **Audio:** PyAudio (ALSA) + opuslib
- **Hardware:** RPi.GPIO, spidev
- **Protocol:** WebSocket (websockets library)
- **Storage:** SQLite3

## Quick Start

**📖 For fastest setup, see [QUICKSTART.md](QUICKSTART.md)**  
**🚀 For production deployment, see [DEPLOYMENT.md](DEPLOYMENT.md)**

### Prerequisites

```bash
# Raspberry Pi OS Lite (Bookworm recommended)
# Enable SPI: sudo raspi-config → Interface Options → SPI → Yes
# Backend must be running: ws://backend-host:8080
```

### Installation

```bash
# Clone repository
cd ~
git clone https://github.com/your-org/aimon-frontend.git
cd aimon-frontend

# Run setup script (installs dependencies)
./setup.sh

# Configure backend connection
export BACKEND_WS_URL="ws://192.168.1.100:8080"
export ROBOT_ID="robot001"

# Run frontend
./run.sh
```

### First Run Test

1. **Button press & hold** → LED turns GREEN → Mic recording
2. **Button release** → LED turns YELLOW → Processing
3. **Backend response** → LED turns CYAN → Audio playback
4. **Animation** → LED turns YELLOW → Emotion display
5. **Return to idle** → LED turns BLUE → Ready

## Installation (Detailed)

### Step 1: System Dependencies

```bash
sudo apt-get update
sudo apt-get install -y \
    python3-pip python3-venv python3-dev \
    python3-pygame \
    portaudio19-dev \
    libopus-dev libopus0 \
    libasound2-dev \
    libspidev-dev \
    python3-rpi-lgpio \
    libzbar0
```
### Step 2: Enable SPI

```bash
sudo raspi-config
# → Interface Options → SPI → Yes → Finish → Reboot
```

Verify:
```bash
ls -l /dev/spidev0.0  # Should exist
```

### Step 3: Python Environment

```bash
cd ~/aimon-frontend

# Create virtual environment
python3 -m venv .venv --system-site-packages

# Activate
source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 4: Configure Audio

Check WM8960 device:
```bash
aplay -l
# Should show: card 1: wm8960soundcard [wm8960-soundcard]
```

Test microphone:
```bash
arecord -D hw:1,0 -f S16_LE -r 16000 -c 1 -d 5 test.wav
aplay test.wav
```

### Step 5: Configuration

Create `.env` file (optional):
```bash
cat > .env << EOF
BACKEND_WS_URL=ws://192.168.1.100:8080
ROBOT_ID=robot001
TURN_DB_PATH=/home/pi/aimon-frontend/data/turns.db
EOF
```

Or use environment variables:
```bash
export BACKEND_WS_URL="ws://192.168.1.100:8080"
export ROBOT_ID="robot001"
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_WS_URL` | `ws://localhost:8080` | Backend WebSocket endpoint |
| `ROBOT_ID` | `robot001` | Unique device identifier |
| `TURN_DB_PATH` | `./data/turns.db` | SQLite database path |
| `SDL_VIDEODRIVER` | `fbcon` | Pygame video driver (framebuffer) |
| `SDL_FBDEV` | `/dev/fb0` | Framebuffer device |

### Hardware Configuration

Edit `config.py` to customize:
- Audio sample rates
- LCD dimensions & FPS
- GPIO pin assignments
- LED colors per state
- SPI speed & bus

### Audio Settings

```python
AUDIO_SAMPLE_RATE_CAPTURE = 16000  # Mic input
AUDIO_SAMPLE_RATE_OPUS = 48000     # OPUS encoding
OPUS_FRAME_DURATION_MS = 20        # Frame size
OPUS_BITRATE = 24000               # Low bitrate for speech
```

## Running

### Interactive Mode

```bash
cd ~/aimon-frontend
source .venv/bin/activate
./run.sh
```

Logs will display in terminal. Press `Ctrl+C` to stop.

### Background Mode

```bash
nohup ./run.sh > aimon.log 2>&1 &
```

View logs:
```bash
tail -f aimon.log
```

Stop:
```bash
pkill -f main.py
```

## Deployment (Systemd Service)

### Step 1: Copy Service File

```bash
sudo cp aimon-frontend.service /etc/systemd/system/
```

### Step 2: Edit Service (if needed)

```bash
sudo nano /etc/systemd/system/aimon-frontend.service
```

Update paths and environment variables:
```ini
[Service]
User=pi
WorkingDirectory=/home/pi/aimon-frontend
Environment=BACKEND_WS_URL=ws://192.168.1.100:8080
Environment=ROBOT_ID=robot001
ExecStart=/home/pi/aimon-frontend/.venv/bin/python3 main.py
```

### Step 3: Enable & Start

```bash
# Reload systemd
sudo systemctl daemon-reload

# Enable auto-start on boot
sudo systemctl enable aimon-frontend

# Start service
sudo systemctl start aimon-frontend

# Check status
sudo systemctl status aimon-frontend
```

### Step 4: Manage Service

```bash
# View logs
sudo journalctl -u aimon-frontend -f

# Restart service
sudo systemctl restart aimon-frontend

# Stop service
sudo systemctl stop aimon-frontend

# Disable auto-start
sudo systemctl disable aimon-frontend
```

## Development

### Project Structure

```
aimon-frontend/
├── main.py                      # Entry point
├── config.py                    # Configuration
├── requirements.txt             # Python dependencies
├── setup.sh                     # Setup script
├── run.sh                       # Run script
├── pytest.ini                   # Test configuration
├── TESTING.md                   # Test documentation
├── audio/
│   ├── audio_capture.py         # Mic recording + OPUS encoding
│   └── audio_playback.py        # PCM16 playback
├── display/
│   ├── display_engine.py        # Pygame rendering
│   └── sprite_manager.py        # Animation loader
├── hardware/
│   └── whisplay_hat.py          # ST7789 LCD + GPIO + LED
├── network/
│   └── ws_client.py             # WebSocket v4 client
├── state/
│   └── state_machine.py         # IDLE→LISTENING→ASR→ANSWER→EMOTION
├── storage/
│   └── turn_logger.py           # SQLite turn logging
├── sprites/                     # Emotion animations
├── tests/                       # Unit tests (140+ tests)
└── data/                        # SQLite database
```

### Running Tests

```bash
# Install test dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific test file
pytest tests/test_state_machine.py

# View coverage report
open htmlcov/index.html
```

See [TESTING.md](TESTING.md) for detailed testing guide.

### Local Development (without Pi)

Tests can run on any system (hardware is mocked):

```bash
# On macOS/Linux/Windows
cd aimon-frontend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
pytest
```

### Code Quality

```bash
# Type checking (optional)
pip install mypy
mypy main.py state/ network/ storage/

# Linting (optional)
pip install pylint
pylint main.py state/ network/ storage/

# Format code (optional)
pip install black
black .
```

## Troubleshooting

### Connection Issues

**Problem:** "WebSocket connection failed"

```bash
# Check backend is running
curl http://backend-host:8080/q/health

# Test WebSocket connection
websocat ws://backend-host:8080/ws/audio/robot001

# Check firewall
sudo ufw status
sudo ufw allow 8080/tcp
```

### Audio Issues

**Problem:** "No audio device found"

```bash
# List audio devices
aplay -l
arecord -l

# Test playback
speaker-test -c 1 -r 16000

# Test recording
arecord -D hw:1,0 -f S16_LE -r 16000 -c 1 -d 5 test.wav
```

**Problem:** "PyAudio errors"

```bash
# Reinstall PyAudio
pip uninstall pyaudio
sudo apt-get install --reinstall portaudio19-dev
pip install --no-cache-dir pyaudio
```

### Display Issues

**Problem:** "Pygame cannot access framebuffer"

```bash
# Check framebuffer exists
ls -l /dev/fb0

# Run with sudo (if needed)
sudo ./run.sh

# Alternative: Use dummy video driver (no display)
export SDL_VIDEODRIVER=dummy
./run.sh
```

**Problem:** "SPI permission denied"

```bash
# Add user to spi group
sudo usermod -a -G spi,gpio,audio pi

# Reboot
sudo reboot
```

### System Issues

**Problem:** "Module not found"

```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

**Problem:** "High CPU usage"

```bash
# Reduce LCD FPS in config.py
LCD_FPS = 15  # Default: 30

# Check for infinite loops
sudo journalctl -u aimon-frontend -f
```

### Debugging

**Enable verbose logging:**

Edit `main.py`:
```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO to DEBUG
    ...
)
```

**Monitor system resources:**
```bash
# CPU & memory
htop

# Disk usage
df -h

# SQLite size
ls -lh data/turns.db
```

## LED Status Indicators

| Color | State | Meaning |
|-------|-------|---------|
| 🔵 Soft Blue | IDLE | Ready for input |
| 🟢 Green | LISTENING | Recording audio |
| 🟡 Yellow | ASR | Processing speech |
| 🔵 Cyan | ANSWER | Playing response |
| 🟡 Warm Yellow | EMOTION | Showing emotion |
| 🟣 Purple | CAMERA | Capturing vision |
| 🟦 Cyan (bright) | WIFI_SCAN | Scanning WiFi QR code |
| 🟨 Amber | OFFLINE | Offline mode (tamagotchi gameplay) |
| 🔴 Red | ERROR | Backend disconnected |

## WiFi QR Manager

### Offline WiFi Setup

When the Pi loses WiFi connectivity, you can reconnect using an embedded WiFi QR scanner:

**How to use:**
1. Hold the button for ≥1.5 seconds (long-press) in offline mode
2. LED turns bright cyan — WiFi QR scan in progress
3. Point camera at WiFi QR code (standard `WIFI:S:...;T:...;P:...;` format)
4. Scanner decodes SSID, password, and security type
5. Auto-connects via `nmcli` network manager
6. Profile saved to `data/wifi-profiles.json` for quick reconnect

**Supported QR Format:**
- Standard WiFi QR format with SSID, password, and encryption type
- Compatible with most WiFi QR generators

**Profile Storage:**
- Profiles persisted locally (JSON format)
- Enables seamless reconnection without re-scanning
- Deduplicated by SSID — password updated if rescanned

**Hardware Requirements:**
- OV5647 CSI camera (integrated on Pi Zero 2)
- `libzbar0` library (installed via setup.sh)
- NetworkManager (`nmcli` command)

## Performance

### Resource Usage (Pi Zero 2)

- **CPU:** ~40% (30 FPS), ~20% (15 FPS)
- **RAM:** ~80 MB
- **Storage:** ~50 MB + SQLite (~2 MB for 200 turns)
- **Network:** ~24 Kbps (OPUS audio streaming)

### Optimization Tips

1. **Reduce LCD FPS:** Set `LCD_FPS = 15` in `config.py`
2. **Lower OPUS bitrate:** Set `OPUS_BITRATE = 16000`
3. **Disable animations:** Use static sprites
4. **Limit turn logging:** Reduce `TURN_MAX_COUNT = 50`

## Security

### Network Security

- Use TLS/WSS for production: `wss://backend-host:8443`
- Restrict backend access with firewall rules
- Use VPN for remote access

### File Permissions

```bash
# Protect configuration
chmod 600 .env

# Restrict database access
chmod 600 data/turns.db
```

### No Sensitive Data

- ❌ No API keys stored (backend handles all AI services)
- ❌ No raw audio stored (only transcripts)
- ✅ Local SQLite database only

## Updates

### Update Frontend

```bash
cd ~/aimon-frontend
git pull origin main

# Reinstall dependencies
source .venv/bin/activate
pip install -r requirements.txt --upgrade

# Restart service
sudo systemctl restart aimon-frontend
```

### Backup Data

```bash
# Backup turn logs
cp data/turns.db data/turns-backup-$(date +%Y%m%d).db

# Backup configuration
cp .env .env.backup
```

## Project Status

- **Version:** 0.2.0
- **Status:** Production Ready
- **Test Coverage:** 90%+ (140+ unit tests)
- **Python:** 3.11+
- **Platform:** Raspberry Pi OS (Bookworm)

## Related Repositories

- **Backend:** [aimon-backend](../aimon-backend/) - Java/Quarkus backend with AI intelligence
- **Design Docs:** [AI-MON_Technical_Design_v0.2.md](../AI-MON_Technical_Design_v0.2.md)

## Support

### Documentation

- **[QUICKSTART.md](QUICKSTART.md)** - 30-second setup guide
- **[DEPLOYMENT.md](DEPLOYMENT.md)** - Production deployment guide
- **[TESTING.md](TESTING.md)** - Test suite documentation
- [tests/README.md](tests/README.md) - Test development guide
- [Design Compliance Review](../plans/reports/aimon-frontend-design-compliance-review.md)
- [Technical Design](../AI-MON_Technical_Design_v0.2.md) - Full system specification

### Issues

Report issues with:
- Raspberry Pi model & OS version
- Python version: `python3 --version`
- Backend URL & status
- Full logs: `sudo journalctl -u aimon-frontend --since today`

## License

[Your License Here]

## Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/my-feature`
3. Write tests: Add to `tests/`
4. Run tests: `pytest`
5. Commit changes: `git commit -am 'Add feature'`
6. Push: `git push origin feature/my-feature`
7. Submit PR

---

**Created:** February 15, 2026  
**Raspberry Pi Setup:** ~10 minutes  
**Hardware Cost:** ~$60 (Pi Zero 2 + Whisplay HAT)

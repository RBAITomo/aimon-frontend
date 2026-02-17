# AI-MON Frontend Deployment Guide

Quick deployment guide for production Raspberry Pi setup.

## ⚡ Quick Deploy (5 Minutes)

### Prerequisites Check

```bash
# 1. Check Pi model
cat /proc/cpuinfo | grep Model

# 2. Check OS version
cat /etc/os-release

# 3. Check SPI enabled
ls -l /dev/spidev0.0

# 4. Check audio device
aplay -l | grep wm8960
```

### One-Command Setup

```bash
# Clone, setup, and configure
cd ~
git clone <repo-url> aimon-frontend
cd aimon-frontend
./setup.sh
export BACKEND_WS_URL="ws://192.168.1.100:8080"
export ROBOT_ID="robot001"
./run.sh
```

## 📦 Production Deployment

### Step 1: Initial Setup (One-Time)

```bash
# SSH into Raspberry Pi
ssh pi@raspberrypi.local

# Update system
sudo apt-get update && sudo apt-get upgrade -y

# Clone repository
cd ~
git clone <repo-url> aimon-frontend
cd aimon-frontend

# Run setup script
./setup.sh

# Enable SPI if prompted
sudo raspi-config
# → Interface Options → SPI → Yes
sudo reboot
```

### Step 2: Configure Backend Connection

```bash
cd ~/aimon-frontend

# Option A: Environment file
cat > .env << EOF
BACKEND_WS_URL=ws://192.168.1.100:8080
ROBOT_ID=pi-zero-001
EOF

# Option B: Direct export
export BACKEND_WS_URL="ws://192.168.1.100:8080"
export ROBOT_ID="pi-zero-001"
```

### Step 3: Test Run

```bash
cd ~/aimon-frontend
./run.sh
```

**Expected behavior:**
1. LED turns BLUE (IDLE state)
2. Press button → LED turns GREEN (recording)
3. Release button → LED turns YELLOW (processing)
4. Backend responds → LED turns CYAN (playing)
5. Animation → LED turns YELLOW (emotion)
6. Back to BLUE (idle)

Press `Ctrl+C` to stop.

### Step 4: Install as Service

```bash
# Edit service file with correct paths
sudo nano /etc/systemd/system/aimon-frontend.service
```

Update these lines:
```ini
User=pi
WorkingDirectory=/home/pi/aimon-frontend
Environment=BACKEND_WS_URL=ws://192.168.1.100:8080
Environment=ROBOT_ID=pi-zero-001
ExecStart=/home/pi/aimon-frontend/.venv/bin/python3 main.py
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable aimon-frontend
sudo systemctl start aimon-frontend
sudo systemctl status aimon-frontend
```

### Step 5: Verify Deployment

```bash
# Check service status
sudo systemctl status aimon-frontend

# Check logs
sudo journalctl -u aimon-frontend -f

# Test button press
# Should see: "State: idle → listening"

# Check database
ls -lh data/turns.db

# Check network connection
netstat -an | grep 8080
```

## 🔧 Configuration

### Network Configuration

**Local Backend (Same Pi):**
```bash
BACKEND_WS_URL=ws://localhost:8080
```

**Network Backend:**
```bash
BACKEND_WS_URL=ws://192.168.1.100:8080
```

**Remote Backend (with TLS):**
```bash
BACKEND_WS_URL=wss://aimon.example.com:8443
```

### Performance Tuning

Edit `config.py`:

**For Pi Zero 2 (optimize for low CPU):**
```python
LCD_FPS = 15                    # Reduce from 30
OPUS_BITRATE = 16000            # Reduce from 24000
```

**For Pi 4/5 (maximize quality):**
```python
LCD_FPS = 30                    # Default
OPUS_BITRATE = 32000            # Increase quality
```

### Multiple Devices

Deploy multiple Pi devices with unique IDs:

**Device 1:**
```bash
ROBOT_ID=kitchen-pi
```

**Device 2:**
```bash
ROBOT_ID=bedroom-pi
```

**Device 3:**
```bash
ROBOT_ID=living-room-pi
```

## 📊 Monitoring

### Health Checks

**Service status:**
```bash
sudo systemctl is-active aimon-frontend
# Expected: active
```

**Connection status:**
```bash
sudo journalctl -u aimon-frontend -n 50 | grep "Session established"
# Should show recent session ID
```

**Audio device:**
```bash
aplay -l | grep wm8960
# Should show: card 1: wm8960soundcard
```

### Log Monitoring

**Real-time logs:**
```bash
sudo journalctl -u aimon-frontend -f
```

**Recent errors:**
```bash
sudo journalctl -u aimon-frontend -p err -n 100
```

**Connection logs:**
```bash
sudo journalctl -u aimon-frontend | grep "WebSocket"
```

**State transitions:**
```bash
sudo journalctl -u aimon-frontend | grep "State:"
```

### Performance Monitoring

**CPU usage:**
```bash
top -p $(pgrep -f main.py)
```

**Memory usage:**
```bash
ps aux | grep main.py
```

**Database size:**
```bash
ls -lh ~/aimon-frontend/data/turns.db
```

**Turn count:**
```bash
sqlite3 ~/aimon-frontend/data/turns.db "SELECT COUNT(*) FROM turns;"
```

## 🚀 Updates & Maintenance

### Update Frontend Code

```bash
cd ~/aimon-frontend
git pull origin main
source .venv/bin/activate
pip install -r requirements.txt --upgrade
sudo systemctl restart aimon-frontend
```

### Update Backend URL

```bash
# Edit service file
sudo nano /etc/systemd/system/aimon-frontend.service

# Update BACKEND_WS_URL line
Environment=BACKEND_WS_URL=ws://new-backend:8080

# Reload and restart
sudo systemctl daemon-reload
sudo systemctl restart aimon-frontend
```

### Backup & Restore

**Backup:**
```bash
# Backup turn logs
cp ~/aimon-frontend/data/turns.db \
   ~/backups/turns-$(date +%Y%m%d).db

# Backup configuration
cp ~/aimon-frontend/.env ~/backups/.env-$(date +%Y%m%d)
```

**Restore:**
```bash
# Restore turn logs
cp ~/backups/turns-20260215.db \
   ~/aimon-frontend/data/turns.db

# Restart service
sudo systemctl restart aimon-frontend
```

### Clear Old Data

```bash
# Clear turn logs
rm ~/aimon-frontend/data/turns.db
sudo systemctl restart aimon-frontend
# New database will be created
```

### Reinstall from Scratch

```bash
# Stop service
sudo systemctl stop aimon-frontend
sudo systemctl disable aimon-frontend

# Remove installation
rm -rf ~/aimon-frontend

# Remove service file
sudo rm /etc/systemd/system/aimon-frontend.service
sudo systemctl daemon-reload

# Follow "Step 1: Initial Setup" again
```

## 🔥 Critical Troubleshooting

### Frontend Won't Start

**Check logs:**
```bash
sudo journalctl -u aimon-frontend -n 100
```

**Common fixes:**
```bash
# Fix permissions
sudo chown -R pi:pi ~/aimon-frontend

# Reinstall dependencies
cd ~/aimon-frontend
source .venv/bin/activate
pip install -r requirements.txt --force-reinstall

# Reset service
sudo systemctl daemon-reload
sudo systemctl restart aimon-frontend
```

### Backend Connection Failed

**Test backend:**
```bash
curl http://backend-ip:8080/q/health
```

**Test WebSocket:**
```bash
# Install websocat
sudo apt-get install websocat

# Test connection
websocat ws://backend-ip:8080/ws/audio/test123
```

**Check firewall:**
```bash
# On backend server
sudo ufw allow 8080/tcp
```

### No Audio

**Test speaker:**
```bash
speaker-test -c 1 -r 16000 -D hw:1,0
```

**Test microphone:**
```bash
arecord -D hw:1,0 -f S16_LE -r 16000 -c 1 -d 5 test.wav
aplay test.wav
```

**Reinstall audio drivers:**
```bash
sudo apt-get install --reinstall alsa-utils libasound2
sudo reboot
```

### Display Issues

**Check framebuffer:**
```bash
ls -l /dev/fb0
```

**Test with sudo:**
```bash
sudo systemctl stop aimon-frontend
cd ~/aimon-frontend
sudo ./run.sh
```

**Check SPI:**
```bash
ls -l /dev/spidev0.0
```

### High CPU Usage

**Check FPS:**
```bash
grep LCD_FPS ~/aimon-frontend/config.py
```

**Reduce FPS:**
```bash
nano ~/aimon-frontend/config.py
# Change: LCD_FPS = 15
sudo systemctl restart aimon-frontend
```

## 📋 Deployment Checklist

**Pre-deployment:**
- [ ] Backend is running and accessible
- [ ] SPI enabled: `ls /dev/spidev0.0`
- [ ] Audio device detected: `aplay -l | grep wm8960`
- [ ] Network connectivity: `ping backend-ip`

**Initial setup:**
- [ ] Repository cloned
- [ ] `setup.sh` completed successfully
- [ ] Dependencies installed: `pip list | grep pygame`
- [ ] Virtual environment created: `ls .venv/`

**Configuration:**
- [ ] `BACKEND_WS_URL` configured
- [ ] `ROBOT_ID` set (unique per device)
- [ ] `.env` file created (if using)

**Testing:**
- [ ] Test run successful: `./run.sh`
- [ ] Button press triggers recording
- [ ] Audio playback works
- [ ] Display shows animations
- [ ] LED colors change per state

**Service deployment:**
- [ ] Service file copied: `ls /etc/systemd/system/aimon-frontend.service`
- [ ] Service enabled: `systemctl is-enabled aimon-frontend`
- [ ] Service running: `systemctl is-active aimon-frontend`
- [ ] Logs show connection: `journalctl -u aimon-frontend -n 20`

**Post-deployment:**
- [ ] Service survives reboot
- [ ] Auto-reconnect works after backend restart
- [ ] Turn logs being created: `ls -l data/turns.db`
- [ ] No errors in logs: `journalctl -u aimon-frontend -p err`

## 🆘 Support

**Quick diagnostics script:**

```bash
#!/bin/bash
echo "=== AI-MON Frontend Diagnostics ==="
echo "Pi Model: $(cat /proc/cpuinfo | grep Model | cut -d: -f2)"
echo "OS: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)"
echo "Python: $(python3 --version)"
echo "SPI: $(ls /dev/spidev0.0 2>/dev/null && echo 'OK' || echo 'MISSING')"
echo "Audio: $(aplay -l | grep wm8960 && echo 'OK' || echo 'MISSING')"
echo "Service: $(systemctl is-active aimon-frontend)"
echo "Backend: $BACKEND_WS_URL"
echo "Recent logs:"
sudo journalctl -u aimon-frontend -n 10 --no-pager
```

Save as `diagnose.sh`, run with: `bash diagnose.sh`

---

**Deployment Time:** ~10 minutes  
**Tested On:** Raspberry Pi Zero 2 W, Pi 4 Model B  
**OS:** Raspberry Pi OS Bookworm (Lite)

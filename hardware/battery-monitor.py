"""Battery monitor for Waveshare UPS HAT (C) via INA219 at I2C address 0x43.

Reads battery voltage from the INA219 bus voltage register, converts to
percentage using a piecewise LiPo discharge curve. Polls in a background
daemon thread; exposes `battery_pct` property (0-100, or -1 if unavailable).

Usage:
    monitor = BatteryMonitor()
    pct = monitor.battery_pct  # int 0-100 or -1
    monitor.stop()             # call on shutdown
"""

import logging
import threading
import time

log = logging.getLogger(__name__)

_INA219_ADDR = 0x43
_BUS_VOLTAGE_REG = 0x02

# Piecewise LiPo discharge curve: (min_voltage, percentage) sorted descending.
# Interpolates linearly between breakpoints. Based on standard 18650 discharge.
_DISCHARGE_CURVE = [
    (4.20, 100),
    (4.10, 90),
    (4.00, 80),
    (3.90, 70),
    (3.80, 60),
    (3.70, 50),
    (3.60, 35),
    (3.50, 20),
    (3.40, 10),
    (3.30, 3),
    (3.20, 0),
]


def _voltage_to_pct(volts: float) -> int:
    """Convert LiPo cell voltage to estimated capacity percentage (0-100)."""
    for i, (v, p) in enumerate(_DISCHARGE_CURVE):
        if volts >= v:
            if i == 0:
                return p
            v_prev, p_prev = _DISCHARGE_CURVE[i - 1]
            frac = (volts - v) / (v_prev - v)
            return int(p + (p_prev - p) * frac)
    return 0


class BatteryMonitor:
    """Reads INA219 battery voltage in background; exposes battery_pct."""

    def __init__(self, poll_interval_s: int = 60):
        self._interval = poll_interval_s
        self._pct = -1  # -1 = unavailable
        self._lock = threading.Lock()
        self._running = False
        self._bus = None

        try:
            import smbus2
            self._bus = smbus2.SMBus(1)
            # Synchronous first read so UI shows battery immediately
            self._pct = self._read_pct()
            log.info("BatteryMonitor: %.2fV → %d%%", self._read_raw_volts(), self._pct)
            self._running = True
            t = threading.Thread(target=self._loop, daemon=True, name="battery-monitor")
            t.start()
        except ImportError:
            log.warning("BatteryMonitor: smbus2 not installed; battery display disabled")
        except Exception as e:
            log.warning("BatteryMonitor: init failed (%s); battery display disabled", e)

    @property
    def battery_pct(self) -> int:
        """Current battery percentage (0-100) or -1 if unavailable."""
        with self._lock:
            return self._pct

    def stop(self):
        """Signal background thread to stop."""
        self._running = False

    # --- Private ---

    def _read_raw_volts(self) -> float:
        """Read INA219 bus voltage register and return voltage in V."""
        raw = self._bus.read_word_data(_INA219_ADDR, _BUS_VOLTAGE_REG)
        # INA219 is big-endian; smbus2 returns little-endian — swap bytes
        raw = ((raw & 0xFF) << 8) | ((raw >> 8) & 0xFF)
        return (raw >> 3) * 0.004  # bits[15:3], 4mV per LSB

    def _read_pct(self) -> int:
        try:
            return _voltage_to_pct(self._read_raw_volts())
        except Exception as e:
            log.debug("BatteryMonitor: read error: %s", e)
            return -1

    def _loop(self):
        while self._running:
            time.sleep(self._interval)
            pct = self._read_pct()
            with self._lock:
                self._pct = pct
            if pct >= 0:
                log.debug("Battery: %d%%", pct)

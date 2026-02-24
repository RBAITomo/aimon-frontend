"""Camera capture service for OV5647 via picamera2.

Captures JPEG to memory (no disk I/O), returns raw bytes.
Power-gated: Picamera2 is opened, captured, then immediately closed on
each call so the ISP draws no current between captures (~150–250 mA saving).
Graceful fallback on non-Pi platforms (returns None).
"""

import io
import logging
import time

log = logging.getLogger(__name__)


class CameraCaptureService:
    """OV5647 CSI camera capture with rate limiting and per-capture power gating."""

    def __init__(self, min_interval_s=30):
        self._last_capture = 0.0
        self._min_interval = min_interval_s
        self._initialized = False

    def initialize(self):
        """Test camera availability without keeping it open (power-save).

        Sets self._initialized so available property works. Does not hold
        the camera open — each capture call opens/closes its own instance.
        """
        try:
            from picamera2 import Picamera2
            cam = Picamera2()
            cam.close()
            self._initialized = True
            log.info("Camera available (640x480, power-gated per capture)")
        except Exception as e:
            log.warning("Camera init failed (expected on non-Pi): %s", e)
            self._initialized = False

    @property
    def available(self):
        """Whether camera hardware is present and picamera2 is importable."""
        return self._initialized

    @property
    def rate_limited(self):
        """Whether capture is currently rate-limited."""
        return time.time() - self._last_capture < self._min_interval

    def capture_bytes(self, bypass_rate_limit=False):
        """Capture photo, return raw JPEG bytes or None.

        Opens Picamera2 → captures → closes on each call to power-gate
        the sensor and ISP between captures.
        """
        if not self._initialized:
            return None

        now = time.time()
        if not bypass_rate_limit and now - self._last_capture < self._min_interval:
            remaining = int(self._min_interval - (now - self._last_capture))
            log.info("Camera rate-limited, wait %ds", remaining)
            return None

        cam = None
        try:
            from picamera2 import Picamera2
            cam = Picamera2()
            cfg = cam.create_still_configuration(
                main={"size": (640, 480), "format": "RGB888"}
            )
            cam.configure(cfg)
            cam.start()
            stream = io.BytesIO()
            cam.capture_file(stream, format="jpeg")
            stream.seek(0)
            data = stream.read()
            self._last_capture = now
            log.info("Photo captured (%d bytes)", len(data))
            return data
        except Exception as e:
            log.error("Camera capture failed: %s", e)
            return None
        finally:
            if cam is not None:
                try:
                    cam.stop()
                except Exception:
                    pass
                try:
                    cam.close()
                except Exception:
                    pass

    def cleanup(self):
        """No-op: camera is already closed after each capture."""
        self._initialized = False

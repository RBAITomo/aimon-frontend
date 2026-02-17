"""Camera capture service for OV5647 via picamera2.

Captures JPEG to memory (no disk I/O), returns base64 string.
Graceful fallback on non-Pi platforms (returns None).
"""

import base64
import io
import logging
import time

log = logging.getLogger(__name__)


class CameraCaptureService:
    """OV5647 CSI camera capture with rate limiting."""

    def __init__(self, min_interval_s=30):
        self._camera = None
        self._last_capture = 0.0
        self._min_interval = min_interval_s
        self._initialized = False

    def initialize(self):
        """Initialize picamera2. Call once at startup."""
        try:
            from picamera2 import Picamera2
            self._camera = Picamera2()
            config = self._camera.create_still_configuration(
                main={"size": (640, 480), "format": "RGB888"}
            )
            self._camera.configure(config)
            self._camera.start()
            self._initialized = True
            log.info("Camera initialized (640x480 JPEG)")
        except Exception as e:
            log.warning("Camera init failed (expected on non-Pi): %s", e)
            self._initialized = False

    @property
    def available(self):
        """Whether camera is initialized and ready."""
        return self._initialized

    @property
    def rate_limited(self):
        """Whether capture is currently rate-limited."""
        return time.time() - self._last_capture < self._min_interval

    def capture_base64(self):
        """Capture photo, return (base64_string, 'jpeg') or (None, None).

        Returns None if not initialized, rate-limited, or capture fails.
        """
        if not self._initialized:
            return None, None

        now = time.time()
        if now - self._last_capture < self._min_interval:
            remaining = int(self._min_interval - (now - self._last_capture))
            log.info("Camera rate-limited, wait %ds", remaining)
            return None, None

        try:
            stream = io.BytesIO()
            self._camera.capture_file(stream, format="jpeg")
            stream.seek(0)
            b64 = base64.b64encode(stream.read()).decode("utf-8")
            self._last_capture = now
            log.info("Photo captured (%d bytes base64)", len(b64))
            return b64, "jpeg"
        except Exception as e:
            log.error("Camera capture failed: %s", e)
            return None, None

    def capture_bytes(self):
        """Capture photo, return raw JPEG bytes or None."""
        if not self._initialized:
            return None

        now = time.time()
        if now - self._last_capture < self._min_interval:
            remaining = int(self._min_interval - (now - self._last_capture))
            log.info("Camera rate-limited, wait %ds", remaining)
            return None

        try:
            stream = io.BytesIO()
            self._camera.capture_file(stream, format="jpeg")
            stream.seek(0)
            data = stream.read()
            self._last_capture = now
            log.info("Photo captured (%d bytes)", len(data))
            return data
        except Exception as e:
            log.error("Camera capture failed: %s", e)
            return None

    def cleanup(self):
        """Stop camera. Call on shutdown."""
        if self._camera:
            try:
                self._camera.stop()
            except Exception:
                pass
            self._camera = None
            self._initialized = False

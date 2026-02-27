"""Vision analysis service calling backend API for food detection.

Sends JPEG images to the backend's /api/vision/analyze endpoint,
which routes to Moondream2 sidecar (primary) or cloud fallback.
"""

import io
import json
import logging
import os
import random
import re
import time

import requests

import config

log = logging.getLogger(__name__)


class VisionAnalysisService:
    """Calls backend vision API for food detection."""

    def __init__(self):
        self._available = False
        self._last_call = 0.0
        self._min_interval = config.CAMERA_RATE_LIMIT_S
        self._sprite_keys = self._scan_sprite_keys()
        self._initialize()

    def _initialize(self):
        """Check backend URL is configured."""
        if not config.BACKEND_HTTP_URL:
            log.warning("BACKEND_HTTP_URL not set, vision disabled")
            return
        self._available = config.CAMERA_ENABLED
        if self._available:
            log.info("Vision analysis service initialized (backend=%s)", config.BACKEND_HTTP_URL)

    def _scan_sprite_keys(self):
        """Scan assets/food/ directory for available sprite filenames (without .png)."""
        food_dir = os.path.join(config.ASSET_DIR, "food")
        keys = []
        if not os.path.isdir(food_dir):
            log.warning("Food sprite directory not found: %s", food_dir)
            return keys
        for f in os.listdir(food_dir):
            if f.lower().endswith(".png"):
                keys.append(os.path.splitext(f)[0])
        log.info("Loaded %d food sprite keys", len(keys))
        return keys

    def _validate_sprite_key(self, key):
        """Validate sprite_key: must be alphanumeric/underscore/space and exist in sprite list."""
        if not key or not isinstance(key, str):
            return random.choice(["default", "default2"])
        sanitized = re.sub(r"[^a-zA-Z0-9_ ]", "", key)
        if sanitized in self._sprite_keys:
            return sanitized
        # Try case-insensitive match
        lower = sanitized.lower()
        for k in self._sprite_keys:
            if k.lower() == lower:
                return k
        return random.choice(["default", "default2"])

    @property
    def available(self):
        return self._available

    @property
    def rate_limited(self):
        return time.time() - self._last_call < self._min_interval

    def _compress_image(self, jpeg_bytes, max_dim=512, quality=70):
        """Resize and recompress JPEG to reduce upload size."""
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(jpeg_bytes))
            w, h = img.size
            if max(w, h) > max_dim:
                ratio = max_dim / max(w, h)
                img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality)
            compressed = buf.getvalue()
            log.info("Image compressed: %d -> %d bytes", len(jpeg_bytes), len(compressed))
            return compressed
        except Exception as e:
            log.warning("Image compression skipped: %s", e)
            return jpeg_bytes

    def analyze(self, jpeg_bytes):
        """Analyze JPEG image bytes via backend API.

        Returns dict with is_food, food_name, sprite_key, description.
        Returns None if unavailable, rate-limited, or on error.
        """
        if not self._available:
            return None

        if self.rate_limited:
            remaining = int(self._min_interval - (time.time() - self._last_call))
            log.info("Vision rate-limited, wait %ds", remaining)
            return None

        self._last_call = time.time()

        try:
            jpeg_bytes = self._compress_image(jpeg_bytes)

            t0 = time.time()
            url = f"{config.BACKEND_HTTP_URL}/api/vision/analyze"
            resp = requests.post(
                url,
                files={"image": ("photo.jpg", jpeg_bytes, "image/jpeg")},
                timeout=10,
            )
            resp.raise_for_status()
            result = resp.json()

            log.info(
                "Backend vision API took %.1fs (source=%s, %d bytes sent)",
                time.time() - t0,
                result.get("source", "unknown"),
                len(jpeg_bytes),
            )

            # Validate sprite_key locally (backend also validates, but double-check)
            if result.get("is_food"):
                result["sprite_key"] = self._validate_sprite_key(result.get("sprite_key"))

            log.info(
                "Vision result: is_food=%s, food=%s, sprite=%s",
                result.get("is_food"),
                result.get("food_name"),
                result.get("sprite_key"),
            )
            return result

        except Exception as e:
            log.error("Vision analysis failed: %s", e)
            # Short penalty to prevent rapid retry on errors
            self._last_call = time.time() - self._min_interval + 10
            return None

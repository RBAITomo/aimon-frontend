"""Vision analysis service calling Gemini API directly from Pi.

Uses google-genai SDK to send JPEG images to Gemini 2.5 Flash
for food detection and scene description.
"""

import json
import logging
import os
import random
import re
import time

import config

log = logging.getLogger(__name__)

VISION_PROMPT_TEMPLATE = (
    "Analyze this image taken by a child's AI companion toy.\n"
    "Rules:\n"
    '1. If food, respond JSON: {{"is_food": true, "food_name": "<Vietnamese name>", "sprite_key": "<key>", "description": "<brief>"}}\n'
    '2. If not food, respond JSON: {{"is_food": false, "food_name": null, "sprite_key": null, "description": "<Vietnamese, child-friendly>"}}\n'
    "3. Keep descriptions under 50 words.\n"
    "4. Be child-appropriate and positive.\n"
    "5. Respond ONLY with JSON, no markdown fences.\n"
    "6. For sprite_key, pick the closest match from this list: [{sprite_keys}]. Use 'default' if none match."
)


class VisionAnalysisService:
    """Calls Gemini Vision API directly for food detection."""

    def __init__(self):
        self._client = None
        self._available = False
        self._last_call = 0.0
        self._min_interval = config.CAMERA_RATE_LIMIT_S
        self._sprite_keys = self._scan_sprite_keys()
        self._initialize()

    def _initialize(self):
        """Initialize google-genai client."""
        if not config.GEMINI_API_KEY:
            log.warning("GEMINI_API_KEY not set, vision disabled")
            return
        try:
            from google import genai
            self._client = genai.Client(api_key=config.GEMINI_API_KEY)
            self._available = True
            log.info("Vision analysis service initialized (model=%s)", config.GEMINI_MODEL)
        except Exception as e:
            log.warning("Vision init failed: %s", e)

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
            import io
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
        """Analyze JPEG image bytes. Returns dict with is_food, food_name, description.

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
            from google.genai import types

            # Downscale image to reduce upload time from Pi
            jpeg_bytes = self._compress_image(jpeg_bytes)

            prompt = VISION_PROMPT_TEMPLATE.format(
                sprite_keys=", ".join(self._sprite_keys[:100])
            )

            t0 = time.time()
            response = self._client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
                            types.Part.from_text(text=prompt),
                        ]
                    )
                ],
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(thinking_budget=128),
                ),
            )

            log.info("Gemini API call took %.1fs (%d bytes sent)", time.time() - t0, len(jpeg_bytes))
            text = response.text.strip()
            # Strip markdown fences if present
            if text.startswith("```"):
                first_nl = text.index("\n")
                last_fence = text.rfind("```")
                if first_nl > 0 and last_fence > first_nl:
                    text = text[first_nl + 1 : last_fence].strip()

            result = json.loads(text)
            # Validate and set sprite_key
            if result.get("is_food"):
                result["sprite_key"] = self._validate_sprite_key(result.get("sprite_key"))
            log.info("Vision result: is_food=%s, food=%s, sprite=%s",
                     result.get("is_food"), result.get("food_name"), result.get("sprite_key"))
            return result

        except Exception as e:
            log.error("Vision analysis failed: %s", e)
            # Short penalty to prevent rapid retry on errors
            self._last_call = time.time() - self._min_interval + 10
            return None

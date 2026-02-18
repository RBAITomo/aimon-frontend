"""Vision analysis service calling Gemini API directly from Pi.

Uses google-genai SDK to send JPEG images to Gemini 2.5 Flash
for food detection and scene description.
"""

import json
import logging
import time

import config

log = logging.getLogger(__name__)

VISION_PROMPT = (
    "Analyze this image taken by a child's AI companion toy.\n"
    "Rules:\n"
    '1. If food, respond JSON: {"is_food": true, "food_name": "<Vietnamese name>", "description": "<brief>"}\n'
    '2. If not food, respond JSON: {"is_food": false, "food_name": null, "description": "<Vietnamese, child-friendly>"}\n'
    "3. Keep descriptions under 50 words.\n"
    "4. Be child-appropriate and positive.\n"
    "5. Respond ONLY with JSON, no markdown fences."
)


class VisionAnalysisService:
    """Calls Gemini Vision API directly for food detection."""

    def __init__(self):
        self._client = None
        self._available = False
        self._last_call = 0.0
        self._min_interval = config.CAMERA_RATE_LIMIT_S
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

    @property
    def available(self):
        return self._available

    @property
    def rate_limited(self):
        return time.time() - self._last_call < self._min_interval

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

            response = self._client.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
                            types.Part.from_text(text=VISION_PROMPT),
                        ]
                    )
                ],
            )

            text = response.text.strip()
            # Strip markdown fences if present
            if text.startswith("```"):
                first_nl = text.index("\n")
                last_fence = text.rfind("```")
                if first_nl > 0 and last_fence > first_nl:
                    text = text[first_nl + 1 : last_fence].strip()

            result = json.loads(text)
            log.info("Vision result: is_food=%s, food=%s", result.get("is_food"), result.get("food_name"))
            return result

        except Exception as e:
            log.error("Vision analysis failed: %s", e)
            # Short penalty to prevent rapid retry on errors
            self._last_call = time.time() - self._min_interval + 10
            return None

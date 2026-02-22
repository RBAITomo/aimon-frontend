"""Offline response bank for Vietnamese text feedback.

Loads curated Vietnamese phrases from JSON and serves them with
no-repeat-until-exhausted selection logic per category.
"""

import json
import logging
import os
import random
import threading

log = logging.getLogger(__name__)

_RESPONSES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "offline-responses.json"
)


class OfflineResponseBank:
    """Vietnamese response phrases with no-repeat selection."""

    def __init__(self, path=None):
        self._path = path or _RESPONSES_PATH
        self._responses = {}
        self._used_indices = {}  # category -> set of used indices
        self._lock = threading.Lock()
        self._load()

    def _load(self):
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                self._responses = json.load(f)
            for category in self._responses:
                self._used_indices[category] = set()
            log.info("Loaded %d response categories", len(self._responses))
        except (FileNotFoundError, json.JSONDecodeError) as e:
            log.error("Failed to load offline responses: %s", e)
            self._responses = {"neutral": ["Tớ ở đây nè!"]}
            self._used_indices = {"neutral": set()}

    def get_response(self, condition: str) -> str:
        """Pick a random unused phrase for the given condition (thread-safe)."""
        with self._lock:
            if condition not in self._responses:
                condition = "neutral"

            phrases = self._responses[condition]
            used = self._used_indices.get(condition, set())

            # Reset if all exhausted
            if len(used) >= len(phrases):
                used = set()
                self._used_indices[condition] = used

            available = [i for i in range(len(phrases)) if i not in used]
            idx = random.choice(available)
            used.add(idx)
            return phrases[idx]

    @staticmethod
    def determine_condition(hunger: int, energy: int, happiness: int) -> str:
        """Return dominant stat condition key."""
        if hunger >= 80 or energy <= 20:
            return "critical"
        if hunger >= 60:
            return "hungry_high"
        if energy <= 40:
            return "energy_low"
        if happiness >= 70:
            return "happy_high"
        return "neutral"

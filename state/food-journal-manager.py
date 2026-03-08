"""Persistent food journal for cookbook collection. Deduplicates by sprite_key."""

import json
import logging
import os
import tempfile
import threading
from datetime import datetime

import config

log = logging.getLogger(__name__)


class FoodJournalManager:
    """Records unique foods photographed. Thread-safe, atomic JSON persistence."""

    def __init__(self, path=None, region_map_path=None):
        self._path = path or config.FOOD_JOURNAL_PATH
        self._region_map_path = region_map_path or config.FOOD_REGION_MAP_PATH
        self._journal = {}  # sprite_key -> entry dict
        self._region_map = {}
        self._lock = threading.Lock()
        self._load_region_map()
        self._load()

    def record(self, food_name: str, sprite_key: str) -> bool:
        """Record food in journal. Returns True if new (first discovery)."""
        with self._lock:
            if sprite_key in self._journal:
                self._journal[sprite_key]["count"] += 1
                self._save()
                log.debug("Journal: %s count -> %d", sprite_key, self._journal[sprite_key]["count"])
                return False
            self._journal[sprite_key] = {
                "name_vi": food_name,
                "sprite_key": sprite_key,
                "first_seen": datetime.now().isoformat(timespec="seconds"),
                "count": 1,
                "region_hint": self._resolve_region(sprite_key),
            }
            self._save()
            log.info("Journal: NEW food %s (%d unique)", sprite_key, len(self._journal))
            return True

    def get_all(self) -> dict:
        """Return copy of journal dict."""
        with self._lock:
            return dict(self._journal)

    def get_entry(self, sprite_key: str):
        """Single entry lookup. Returns dict or None."""
        with self._lock:
            return self._journal.get(sprite_key)

    def unique_count(self) -> int:
        """Total unique foods discovered."""
        with self._lock:
            return len(self._journal)

    def _resolve_region(self, sprite_key: str) -> str:
        """Lookup region from map. Supports wildcard prefix matching."""
        # Direct match first
        if sprite_key in self._region_map:
            return self._region_map[sprite_key]
        # Wildcard prefix match (e.g., "fruit_*" matches "fruit_cherry")
        for pattern, region in self._region_map.items():
            if pattern.endswith("*") and sprite_key.startswith(pattern[:-1]):
                return region
        return self._region_map.get("_default", "Whipcream Spire")

    def _load_region_map(self):
        """Load static region mapping from JSON."""
        if not os.path.exists(self._region_map_path):
            log.warning("Region map not found: %s", self._region_map_path)
            return
        try:
            with open(self._region_map_path, "r", encoding="utf-8") as f:
                self._region_map = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Failed to load region map: %s", e)

    def _load(self):
        """Load journal from JSON file. Handles missing/corrupt files."""
        if not os.path.exists(self._path):
            self._journal = {}
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                self._journal = data
            else:
                log.warning("Invalid journal format, resetting")
                self._journal = {}
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Failed to load journal: %s", e)
            self._journal = {}

    def _save(self):
        """Atomic write: write to temp file, then rename."""
        dir_path = os.path.dirname(self._path)
        os.makedirs(dir_path, exist_ok=True)
        try:
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._journal, f, ensure_ascii=False)
            os.replace(tmp_path, self._path)
        except OSError as e:
            log.error("Failed to save journal: %s", e)

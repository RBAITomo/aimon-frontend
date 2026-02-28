"""Persistent food inventory with JSON storage. FIFO eviction at max capacity."""

import json
import logging
import os
import tempfile
import threading
import time

import config

log = logging.getLogger(__name__)


class FoodInventoryManager:
    """Manages stored food items with JSON file persistence. Thread-safe."""

    def __init__(self, path=None, max_items=None):
        self._path = path or config.FOOD_INVENTORY_PATH
        self._max = max_items or config.FOOD_INVENTORY_MAX
        self._items = []
        self._lock = threading.Lock()
        self._load()

    def add(self, food_name: str, sprite_key: str) -> bool:
        """Add food item to inventory. Evicts oldest if full."""
        with self._lock:
            if len(self._items) >= self._max:
                evicted = self._items.pop(0)
                log.debug("Evicted oldest food: %s", evicted["food_name"])
            self._items.append({
                "food_name": food_name,
                "sprite_key": sprite_key,
                "captured_at": time.time(),
            })
            self._save()
            log.info("Food added to inventory: %s (%d/%d)", food_name, len(self._items), self._max)
        return True

    def pop(self):
        """Remove and return oldest food item (FIFO). Returns None if empty."""
        with self._lock:
            if not self._items:
                return None
            item = self._items.pop(0)
            self._save()
            log.info("Food popped from inventory: %s (%d remaining)", item["food_name"], len(self._items))
            return item

    def get_all(self) -> list:
        """Return copy of all inventory items."""
        with self._lock:
            return list(self._items)

    def count(self) -> int:
        return len(self._items)

    def _load(self):
        """Load inventory from JSON file. Handles missing/corrupt files."""
        if not os.path.exists(self._path):
            self._items = []
            return
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                self._items = data[:self._max]
            else:
                log.warning("Invalid inventory format, resetting")
                self._items = []
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Failed to load inventory: %s", e)
            self._items = []

    def _save(self):
        """Atomic write: write to temp file, then rename."""
        dir_path = os.path.dirname(self._path)
        os.makedirs(dir_path, exist_ok=True)
        try:
            fd, tmp_path = tempfile.mkstemp(dir=dir_path, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._items, f, ensure_ascii=False)
            os.replace(tmp_path, self._path)
        except OSError as e:
            log.error("Failed to save inventory: %s", e)

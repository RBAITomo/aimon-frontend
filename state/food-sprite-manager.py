"""Food sprite manager: on-screen food items with tween eat animation.

Manages food sprites detected by camera/Gemini. Supports immediate eat
(tween to pet center), storing up to 3 items when pet is full, and
auto-eating oldest stored food when hunger increases.
"""

import logging
import os
import random
import threading
from collections import deque
from dataclasses import dataclass, field

import pygame

import config

log = logging.getLogger(__name__)


@dataclass
class FoodItem:
    """Single food sprite on screen."""
    sprite_key: str
    food_name: str
    surface: pygame.Surface = field(repr=False)
    x: float = 0.0
    y: float = 0.0
    state: str = "idle"  # idle | tweening | done
    tween_tick: int = 0
    tween_start_x: float = 0.0
    tween_start_y: float = 0.0
    slot_index: int = -1


class FoodSpriteManager:
    """Manages on-screen food sprites with tween animation and FIFO queue."""

    def __init__(self):
        self._items: deque[FoodItem] = deque()
        self._sprite_cache: dict[str, pygame.Surface] = {}
        self._lock = threading.Lock()
        self._food_dir = os.path.join(config.ASSET_DIR, "food")

    def _load_sprite(self, sprite_key: str) -> pygame.Surface:
        """Load and cache a food sprite, scaled to FOOD_SPRITE_SIZE."""
        if sprite_key in self._sprite_cache:
            return self._sprite_cache[sprite_key]

        path = os.path.join(self._food_dir, f"{sprite_key}.png")
        try:
            surf = pygame.image.load(path).convert_alpha()
        except (pygame.error, FileNotFoundError):
            fallback = random.choice(["default", "default2"])
            path = os.path.join(self._food_dir, f"{fallback}.png")
            try:
                surf = pygame.image.load(path).convert_alpha()
            except (pygame.error, FileNotFoundError):
                surf = pygame.Surface((config.FOOD_SPRITE_SIZE, config.FOOD_SPRITE_SIZE), pygame.SRCALPHA)
                surf.fill((255, 200, 100, 200))

        size = config.FOOD_SPRITE_SIZE
        surf = pygame.transform.smoothscale(surf, (size, size))
        self._sprite_cache[sprite_key] = surf
        return surf

    def _find_free_slot(self) -> int:
        """Find first unused slot index (0-2)."""
        used = {item.slot_index for item in self._items if item.state == "idle"}
        for i in range(config.FOOD_SPRITE_MAX):
            if i not in used:
                return i
        return 0  # fallback

    def add(self, sprite_key: str, food_name: str, eat_immediately: bool = False) -> FoodItem:
        """Add a food item. If eat_immediately, start tween to pet center."""
        surface = self._load_sprite(sprite_key)
        slot = self._find_free_slot()
        sx, sy = config.FOOD_SLOT_POSITIONS[slot]

        item = FoodItem(
            sprite_key=sprite_key,
            food_name=food_name,
            surface=surface,
            x=sx, y=sy,
            slot_index=slot,
            tween_start_x=sx,
            tween_start_y=sy,
        )

        with self._lock:
            # Evict oldest idle if at max
            idle_count = sum(1 for it in self._items if it.state == "idle")
            if idle_count >= config.FOOD_SPRITE_MAX:
                self._evict_oldest()
            if eat_immediately:
                item.state = "tweening"
                item.tween_tick = 0
            self._items.append(item)

        return item

    def _evict_oldest(self):
        """Remove oldest idle item (no lock, caller must hold lock)."""
        for i, item in enumerate(self._items):
            if item.state == "idle":
                del self._items[i]
                return

    def eat_oldest(self) -> bool:
        """Start tween on oldest idle item. Returns True if item found."""
        with self._lock:
            for item in self._items:
                if item.state == "idle":
                    item.state = "tweening"
                    item.tween_tick = 0
                    item.tween_start_x = item.x
                    item.tween_start_y = item.y
                    return True
        return False

    def tick(self) -> list[FoodItem]:
        """Advance tweens. Returns list of items that completed eating this tick."""
        completed = []
        with self._lock:
            for item in self._items:
                if item.state != "tweening":
                    continue
                item.tween_tick += 1
                t = min(item.tween_tick / config.FOOD_TWEEN_FRAMES, 1.0)
                # Lerp toward pet center
                tx, ty = config.FOOD_PET_CENTER
                item.x = item.tween_start_x + (tx - item.tween_start_x) * t
                item.y = item.tween_start_y + (ty - item.tween_start_y) * t
                if t >= 1.0:
                    item.state = "done"
                    completed.append(item)
            # Remove done items
            self._items = deque(item for item in self._items if item.state != "done")
        return completed

    def render(self, surface: pygame.Surface):
        """Blit all visible food items onto surface."""
        with self._lock:
            for item in self._items:
                if item.state == "done":
                    continue
                # Scale down during tween
                if item.state == "tweening" and config.FOOD_TWEEN_FRAMES > 0:
                    t = min(item.tween_tick / config.FOOD_TWEEN_FRAMES, 1.0)
                    scale = max(1.0 - t * 0.7, 0.3)
                    size = int(config.FOOD_SPRITE_SIZE * scale)
                    if size < 2:
                        continue
                    scaled = pygame.transform.smoothscale(item.surface, (size, size))
                    surface.blit(scaled, (int(item.x), int(item.y)))
                else:
                    surface.blit(item.surface, (int(item.x), int(item.y)))

    def check_auto_eat(self, hunger: int, on_eaten_callback) -> bool:
        """If hunger > 0 and idle food exists, eat oldest and invoke callback."""
        if hunger <= 0:
            return False
        with self._lock:
            target = None
            for item in self._items:
                if item.state == "idle":
                    target = item
                    break
            if not target:
                return False
            target.state = "tweening"
            target.tween_tick = 0
            target.tween_start_x = target.x
            target.tween_start_y = target.y
            food_name = target.food_name
            sprite_key = target.sprite_key

        if on_eaten_callback:
            on_eaten_callback(food_name, sprite_key)
        return True

    @property
    def has_stored_food(self) -> bool:
        with self._lock:
            return any(item.state == "idle" for item in self._items)

    def clear(self):
        with self._lock:
            self._items.clear()

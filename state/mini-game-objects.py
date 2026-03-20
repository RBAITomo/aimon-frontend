"""Mini-game objects: FallingItem, Player, ItemSpawner, collision detection.

Designed for Pi Zero 2 constraints: max 8 items, rect collision only, 30 FPS.
"""

import dataclasses
import random
import logging

import pygame

import config

log = logging.getLogger(__name__)

# Food sprite keys (must match assets/food/*.png filenames without extension)
FOOD_SPRITES = [
    "cookies", "donut", "icecream", "chocolate", "pancakes",
    "waffle", "gummybear", "pudding", "strawberrycake", "fruitcake",
    "cotton-candy",
]

# Hazard sprites — use colored rects as fallback (no dedicated hazard assets)
HAZARD_SPRITES = ["hazard_rock", "hazard_trash"]

# Difficulty tiers: (fall_speed_px_per_frame, spawn_interval_frames, food_ratio)
TIER_CONFIG = [
    (2.0, 30, 0.30),   # 0-30s: slow, ~1/sec, 30% food / 70% hazards
    (3.0, 20, 0.30),   # 30-60s: medium, ~1.5/sec
    (4.0, 15, 0.30),   # 60-90s: fast, ~2/sec
]

MAX_ITEMS = 8
ITEM_SIZE = 32  # px, slightly smaller than FOOD_SPRITE_SIZE for game


@dataclasses.dataclass
class FallingItem:
    """Single falling food or hazard object."""
    item_type: str          # "food" or "hazard"
    sprite_key: str
    surface: pygame.Surface
    x: float
    y: float
    speed: float
    width: int = ITEM_SIZE
    height: int = ITEM_SIZE

    def update(self):
        self.y += self.speed

    def is_off_screen(self, bottom: int = 240) -> bool:
        return self.y > bottom

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), int(self.y), self.width, self.height)


class Player:
    """Player-controlled Mon catching food at bottom of screen."""

    MOVE_SPEED = 6
    WIDTH = 48
    HEIGHT = 48
    STUN_DURATION = 45  # frames (1.5s at 30fps)

    def __init__(self, play_area_width: int = config.LCD_WIDTH,
                 play_area_bottom: int = config.LCD_HEIGHT):
        self._area_w = play_area_width
        self.x = (play_area_width - self.WIDTH) // 2
        self.y_pos = play_area_bottom - self.HEIGHT - 4  # 4px padding from bottom
        self.stun_timer = 0
        self.moving = None  # None=idle, "left", "right"

    def move_left(self):
        if not self.is_stunned:
            self.x = max(0, self.x - self.MOVE_SPEED)
            self.moving = "left"

    def move_right(self):
        if not self.is_stunned:
            self.x = min(self._area_w - self.WIDTH, self.x + self.MOVE_SPEED)
            self.moving = "right"

    def stun(self):
        self.stun_timer = self.STUN_DURATION

    def update(self):
        if self.stun_timer > 0:
            self.stun_timer -= 1

    @property
    def is_stunned(self) -> bool:
        return self.stun_timer > 0

    @property
    def rect(self) -> pygame.Rect:
        return pygame.Rect(int(self.x), self.y_pos, self.WIDTH, self.HEIGHT)

    def reset(self):
        self.x = (self._area_w - self.WIDTH) // 2
        self.stun_timer = 0
        self.moving = None


class ItemSpawner:
    """Manages spawning falling items with difficulty progression."""

    def __init__(self, load_sprite_fn):
        """load_sprite_fn: callable(sprite_key) -> pygame.Surface"""
        self._load_sprite = load_sprite_fn
        self.items: list[FallingItem] = []
        self._spawn_timer = 0
        self._tier = 0

    def set_tier(self, tier: int):
        self._tier = min(tier, len(TIER_CONFIG) - 1)

    def tick(self, play_width: int = config.LCD_WIDTH):
        """Spawn new items and update existing ones. Call once per frame."""
        speed, interval, food_ratio = TIER_CONFIG[self._tier]

        # Spawn
        self._spawn_timer += 1
        if self._spawn_timer >= interval and len(self.items) < MAX_ITEMS:
            self._spawn_timer = 0
            self._spawn_item(speed, food_ratio, play_width)

        # Update positions
        for item in self.items:
            item.update()

        # Remove off-screen
        self.items = [i for i in self.items if not i.is_off_screen()]

    def _spawn_item(self, speed: float, food_ratio: float, play_width: int):
        is_food = random.random() < food_ratio
        if is_food:
            sprite_key = random.choice(FOOD_SPRITES)
            item_type = "food"
        else:
            sprite_key = random.choice(HAZARD_SPRITES)
            item_type = "hazard"

        surface = self._load_sprite(sprite_key)
        x = random.randint(0, max(0, play_width - ITEM_SIZE))

        self.items.append(FallingItem(
            item_type=item_type,
            sprite_key=sprite_key,
            surface=surface,
            x=x,
            y=-ITEM_SIZE,  # start above screen
            speed=speed,
        ))

    def reset(self):
        self.items.clear()
        self._spawn_timer = 0
        self._tier = 0


def check_collision(player: Player, item: FallingItem) -> bool:
    """Simple rect overlap collision check."""
    return player.rect.colliderect(item.rect)

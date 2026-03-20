"""Cookbook screen: grid of discovered food sprites with paging."""

import logging
import os

import pygame

import config

log = logging.getLogger(__name__)

# All food sprite filenames (excluding defaults), sorted alphabetically
_FOOD_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "food")
_EXCLUDE = {"default.png", "default2.png", "hazard_rock.png", "hazard_trash.png"}


def _scan_all_sprites():
    """List all food sprite keys from assets/food/ directory."""
    if not os.path.isdir(_FOOD_DIR):
        return []
    files = sorted(f for f in os.listdir(_FOOD_DIR) if f.endswith(".png") and f not in _EXCLUDE)
    return [os.path.splitext(f)[0] for f in files]


class CookbookScreenRenderer:
    """Renders food cookbook grid with paging. Discovered foods colored, others grey."""

    def __init__(self):
        self._font_title = pygame.font.SysFont("dejavusans", 16, bold=True)
        self._font_name = pygame.font.SysFont("dejavusans", 9)
        self._font_hint = pygame.font.SysFont("dejavusans", 11)
        self._page = 0
        self._sprite_cache = {}  # sprite_key -> scaled Surface
        self._all_keys = _scan_all_sprites()
        self._per_page = config.COOKBOOK_GRID_COLS * config.COOKBOOK_GRID_ROWS
        self._total_pages = max(1, (len(self._all_keys) + self._per_page - 1) // self._per_page)

    @property
    def page(self):
        return self._page

    def next_page(self):
        if self._page < self._total_pages - 1:
            self._page += 1
            self._sprite_cache.clear()

    def prev_page(self):
        if self._page > 0:
            self._page -= 1
            self._sprite_cache.clear()

    def render(self, surface, food_journal=None, **kwargs):
        """Render cookbook grid onto surface."""
        journal = food_journal.get_all() if food_journal else {}
        unique = len(journal)
        total = len(self._all_keys)

        # Title
        title = self._font_title.render(f"Sách Nấu Ăn", True, (255, 255, 255))
        surface.blit(title, (config.LCD_WIDTH // 2 - title.get_width() // 2, 8))

        # Counter + page
        counter_text = f"{unique}/{total} món | Trang {self._page + 1}/{self._total_pages}"
        counter = self._font_hint.render(counter_text, True, (180, 180, 180))
        surface.blit(counter, (config.LCD_WIDTH // 2 - counter.get_width() // 2, 30))

        # Grid
        start = self._page * self._per_page
        page_keys = self._all_keys[start:start + self._per_page]
        sz = config.COOKBOOK_SPRITE_SIZE
        cell_w = config.COOKBOOK_CELL_SIZE
        cell_h = cell_w + 12  # extra space for name text

        for i, key in enumerate(page_keys):
            col = i % config.COOKBOOK_GRID_COLS
            row = i // config.COOKBOOK_GRID_COLS
            x = config.COOKBOOK_GRID_START_X + col * cell_w
            y = config.COOKBOOK_GRID_START_Y + row * cell_h

            if key in journal:
                # Discovered: load colored sprite
                spr = self._load_sprite(key, sz)
                if spr:
                    sx = x + (cell_w - sz) // 2
                    surface.blit(spr, (sx, y))
                # Name below sprite
                name = journal[key].get("name_vi", key)[:8]
                name_surf = self._font_name.render(name, True, (220, 220, 220))
                surface.blit(name_surf, (x + (cell_w - name_surf.get_width()) // 2, y + sz + 1))
            else:
                # Undiscovered: grey placeholder
                sx = x + (cell_w - sz) // 2
                pygame.draw.rect(surface, (50, 50, 60), (sx, y, sz, sz), border_radius=4)
                pygame.draw.rect(surface, (70, 70, 80), (sx, y, sz, sz), 1, border_radius=4)

        # Navigation hints
        hint = self._font_hint.render("A:< D:> C:đóng", True, (100, 100, 100))
        surface.blit(hint, (config.LCD_WIDTH // 2 - hint.get_width() // 2, config.LCD_HEIGHT - 18))

    def _load_sprite(self, sprite_key, size):
        """Load and cache scaled food sprite."""
        if sprite_key in self._sprite_cache:
            return self._sprite_cache[sprite_key]
        path = os.path.join(_FOOD_DIR, f"{sprite_key}.png")
        if not os.path.exists(path):
            return None
        try:
            img = pygame.image.load(path).convert_alpha()
            img = pygame.transform.smoothscale(img, (size, size))
            self._sprite_cache[sprite_key] = img
            return img
        except pygame.error as e:
            log.warning("Failed to load sprite %s: %s", sprite_key, e)
            return None

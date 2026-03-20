"""Food inventory screen: list of stored food items for menu overlay."""

import logging

import pygame

import config

log = logging.getLogger(__name__)


class InventoryScreenRenderer:
    """Renders food inventory list within menu screen view."""

    def __init__(self):
        self._font_title = pygame.font.SysFont("dejavusans", 18)
        self._font = pygame.font.SysFont("dejavusans", 14)
        self._max_visible = 8  # max items visible at once

    def render(self, surface, food_inventory=None, **kwargs):
        """Render inventory list onto surface."""
        y = 30
        title = self._font_title.render("Kho do an", True, (255, 255, 255))
        surface.blit(title, (config.LCD_WIDTH // 2 - title.get_width() // 2, y))
        y += 30

        if not food_inventory:
            empty = self._font.render("Trong! Chup anh de them do an.", True, (140, 140, 140))
            surface.blit(empty, (config.LCD_WIDTH // 2 - empty.get_width() // 2, y + 40))
            return

        items = food_inventory.get_all() if hasattr(food_inventory, 'get_all') else food_inventory
        if not items:
            empty = self._font.render("Trong! Chup anh de them do an.", True, (140, 140, 140))
            surface.blit(empty, (config.LCD_WIDTH // 2 - empty.get_width() // 2, y + 40))
            return

        count = len(items)
        header = self._font.render(f"{count}/{config.FOOD_INVENTORY_MAX} mon", True, (160, 160, 160))
        surface.blit(header, (config.LCD_WIDTH // 2 - header.get_width() // 2, y))
        y += 22

        for i, item in enumerate(items[:self._max_visible]):
            name = item.get("food_name", "???")
            text = self._font.render(f"  {i+1}. {name}", True, (200, 200, 200))
            surface.blit(text, (20, y))
            y += 18

        if count > self._max_visible:
            more = self._font.render(f"  ... va {count - self._max_visible} mon nua", True, (120, 120, 120))
            surface.blit(more, (20, y))

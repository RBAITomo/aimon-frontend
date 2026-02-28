"""Menu overlay renderer: dark overlay + item select carousel or sub-screen."""

import importlib
import logging

import pygame

import config

log = logging.getLogger(__name__)

_menu_mod = importlib.import_module("state.menu-overlay-controller")
MenuItem = _menu_mod.MenuItem

_pet_screen_mod = importlib.import_module("display.pet-status-screen-renderer")
PetStatusScreenRenderer = _pet_screen_mod.PetStatusScreenRenderer

_inv_screen_mod = importlib.import_module("display.inventory-screen-renderer")
InventoryScreenRenderer = _inv_screen_mod.InventoryScreenRenderer

_badge_screen_mod = importlib.import_module("display.badges-screen-renderer")
BadgesScreenRenderer = _badge_screen_mod.BadgesScreenRenderer

_map_screen_mod = importlib.import_module("display.map-screen-renderer")
MapScreenRenderer = _map_screen_mod.MapScreenRenderer


class MenuOverlayRenderer:
    """Renders menu overlay on top of compositor output."""

    def __init__(self):
        self._font = pygame.font.SysFont("dejavusans", config.MENU_LABEL_FONT_SIZE)
        self._font_small = pygame.font.SysFont("dejavusans", 14)
        self._overlay = pygame.Surface((config.LCD_WIDTH, config.LCD_HEIGHT), pygame.SRCALPHA)
        self._pet_screen = PetStatusScreenRenderer()
        self._inv_screen = InventoryScreenRenderer()
        self._badge_screen = BadgesScreenRenderer()
        self._map_screen = MapScreenRenderer()
        self._screen_map = {
            MenuItem.PET_STATUS: self._pet_screen,
            MenuItem.FOOD_INVENTORY: self._inv_screen,
            MenuItem.BADGES: self._badge_screen,
            MenuItem.MAP: self._map_screen,
        }

    def render(self, surface, controller, pet_state=None, food_inventory=None):
        """Render menu overlay onto surface."""
        # Draw dark semi-transparent overlay
        self._overlay.fill((0, 0, 0, config.MENU_OVERLAY_ALPHA))
        surface.blit(self._overlay, (0, 0))

        if controller.in_screen:
            self._render_screen(surface, controller.current_item, pet_state, food_inventory)
        else:
            self._render_item_select(surface, controller.current_item)

    def _render_item_select(self, surface, current_item):
        """Render item carousel: centered label with navigation hints."""
        idx = current_item.value
        name = config.MENU_ITEM_NAMES[idx]
        cx, cy = config.LCD_WIDTH // 2, config.LCD_HEIGHT // 2

        # Draw current item name centered
        text_surf = self._font.render(name, True, (255, 255, 255))
        surface.blit(text_surf, (cx - text_surf.get_width() // 2, cy - text_surf.get_height() // 2))

        # Draw left/right arrows
        arrow_l = self._font.render("<", True, (180, 180, 180))
        arrow_r = self._font.render(">", True, (180, 180, 180))
        surface.blit(arrow_l, (30, cy - arrow_l.get_height() // 2))
        surface.blit(arrow_r, (config.LCD_WIDTH - 50, cy - arrow_r.get_height() // 2))

        # Item counter
        counter = self._font_small.render(f"{idx + 1}/{len(config.MENU_ITEM_NAMES)}", True, (140, 140, 140))
        surface.blit(counter, (cx - counter.get_width() // 2, cy + 30))

        # Hint text
        hint = self._font_small.render("A/D: chon | B: vao | C: dong", True, (100, 100, 100))
        surface.blit(hint, (cx - hint.get_width() // 2, config.LCD_HEIGHT - 25))

    def _render_screen(self, surface, item, pet_state, food_inventory):
        """Delegate to appropriate sub-screen renderer."""
        renderer = self._screen_map.get(item)
        if renderer:
            renderer.render(surface, pet_state=pet_state, food_inventory=food_inventory)

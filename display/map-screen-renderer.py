"""Map screen: placeholder for V2 menu overlay."""

import logging
import os

import pygame

import config

log = logging.getLogger(__name__)


class MapScreenRenderer:
    """Placeholder map screen — shows pin type decoration and 'Coming soon' message."""

    def __init__(self):
        self._font_title = pygame.font.SysFont("dejavusans", 18)
        self._font = pygame.font.SysFont("dejavusans", 14)
        self._font_small = pygame.font.SysFont("dejavusans", 10)
        # Load 32x32 map pin icons (native size)
        self._pins = {}
        for pin_type in ("current", "unlocked", "locked"):
            path = os.path.join(config.UI_ASSETS_PATH, f"map-pin-{pin_type}.png")
            try:
                self._pins[pin_type] = pygame.image.load(path).convert_alpha()
            except (pygame.error, FileNotFoundError):
                self._pins[pin_type] = None

    def render(self, surface, **kwargs):
        cx = config.LCD_WIDTH // 2

        # Title
        title = self._font_title.render("Ban do", True, (255, 255, 255))
        surface.blit(title, (cx - title.get_width() // 2, 30))

        # Decorative pin row: 3 pin types horizontally centered
        pin_y = 80
        pin_types = [("current", "Hien tai"), ("unlocked", "Mo khoa"), ("locked", "Chua mo")]
        start_x = cx - 75  # 3 pins × 50px spacing, centered

        for i, (pin_type, label) in enumerate(pin_types):
            px = start_x + i * 50
            pin = self._pins.get(pin_type)
            if pin:
                surface.blit(pin, (px, pin_y))
            else:
                pygame.draw.circle(surface, (100, 100, 120), (px + 16, pin_y + 16), 12)
            # Label below pin
            lbl = self._font_small.render(label, True, (160, 160, 170))
            surface.blit(lbl, (px + 16 - lbl.get_width() // 2, pin_y + 36))

        # Coming soon placeholder
        placeholder = self._font.render("Sap ra mat!", True, (140, 140, 140))
        surface.blit(placeholder, (cx - placeholder.get_width() // 2, 160))

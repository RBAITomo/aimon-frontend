"""Badges screen: placeholder for V2 menu overlay."""

import logging

import pygame

import config

log = logging.getLogger(__name__)


class BadgesScreenRenderer:
    """Placeholder badges screen — shows 'Coming soon' message."""

    def __init__(self):
        self._font_title = pygame.font.SysFont("dejavusans", 18)
        self._font = pygame.font.SysFont("dejavusans", 14)

    def render(self, surface, **kwargs):
        y = 30
        title = self._font_title.render("Huy hieu", True, (255, 255, 255))
        surface.blit(title, (config.LCD_WIDTH // 2 - title.get_width() // 2, y))

        placeholder = self._font.render("Sap ra mat!", True, (140, 140, 140))
        surface.blit(placeholder, (config.LCD_WIDTH // 2 - placeholder.get_width() // 2, config.LCD_HEIGHT // 2))

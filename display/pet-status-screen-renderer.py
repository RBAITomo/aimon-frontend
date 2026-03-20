"""Pet status screen: detailed stats display for menu overlay."""

import logging

import pygame

import config

log = logging.getLogger(__name__)


class PetStatusScreenRenderer:
    """Renders detailed pet stats within menu screen view."""

    def __init__(self):
        self._font_title = pygame.font.SysFont("dejavusans", 18)
        self._font = pygame.font.SysFont("dejavusans", 14)
        self._bar_width = 120
        self._bar_height = 10

    def render(self, surface, pet_state=None, **kwargs):
        """Render pet status screen onto surface."""
        if not pet_state:
            self._draw_centered(surface, "Khong co du lieu", 120)
            return

        x_start = 20
        y = 30

        # Title
        title = self._font_title.render("Trang thai thu cung", True, (255, 255, 255))
        surface.blit(title, (config.LCD_WIDTH // 2 - title.get_width() // 2, y))
        y += 30

        # Stage & Level
        stage_text = f"Giai doan: {pet_state.stage}  |  Level: {pet_state.level}"
        surface.blit(self._font.render(stage_text, True, (200, 200, 200)), (x_start, y))
        y += 22

        # Stat bars
        stats = [
            ("Do doi", pet_state.hunger, (220, 80, 80)),
            ("Nang luong", pet_state.energy, (80, 180, 220)),
            ("Hanh phuc", pet_state.happiness, (220, 200, 80)),
        ]
        for label, value, color in stats:
            surface.blit(self._font.render(f"{label}: {value}", True, (180, 180, 180)), (x_start, y))
            # Bar background
            bar_x = x_start + 100
            pygame.draw.rect(surface, (60, 60, 60), (bar_x, y + 2, self._bar_width, self._bar_height))
            # Bar fill (value is 0-100)
            fill_w = max(0, min(self._bar_width, int(self._bar_width * value / 100)))
            pygame.draw.rect(surface, color, (bar_x, y + 2, fill_w, self._bar_height))
            y += 20

        # XP
        xp_text = f"XP: {pet_state.xp}/{pet_state.xp_for_next}"
        surface.blit(self._font.render(xp_text, True, (180, 180, 180)), (x_start, y))
        y += 22

        # Battery
        if pet_state.battery_pct >= 0:
            bat_text = f"Pin: {pet_state.battery_pct}%"
            surface.blit(self._font.render(bat_text, True, (140, 140, 140)), (x_start, y))

    def _draw_centered(self, surface, text, y):
        surf = self._font.render(text, True, (180, 180, 180))
        surface.blit(surf, (config.LCD_WIDTH // 2 - surf.get_width() // 2, y))

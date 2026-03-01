"""Volume screen renderer: horizontal bar with A/D adjust hints."""

import logging
import pygame
import config

log = logging.getLogger(__name__)


class VolumeScreenRenderer:
    """Renders volume adjustment screen with a visual bar."""

    def __init__(self):
        self._font = pygame.font.SysFont("dejavusans", 22)
        self._font_small = pygame.font.SysFont("dejavusans", 14)

    def render(self, surface, volume_pct=80, **_kwargs):
        """Draw volume bar and hints.

        Args:
            surface: pygame surface to draw on.
            volume_pct: current volume percentage (0-100).
        """
        cx, cy = config.LCD_WIDTH // 2, config.LCD_HEIGHT // 2

        # Title
        title = self._font.render(f"Am luong: {volume_pct}%", True, (255, 255, 255))
        surface.blit(title, (cx - title.get_width() // 2, cy - 40))

        # Volume bar background
        bar_w, bar_h = 180, 16
        bar_x = cx - bar_w // 2
        bar_y = cy
        pygame.draw.rect(surface, (80, 80, 80), (bar_x, bar_y, bar_w, bar_h), border_radius=4)

        # Volume bar fill
        fill_w = int(bar_w * volume_pct / 100)
        if fill_w > 0:
            color = (80, 200, 80) if volume_pct <= 80 else (255, 180, 50)
            pygame.draw.rect(surface, color, (bar_x, bar_y, fill_w, bar_h), border_radius=4)

        # Hints
        hint = self._font_small.render("D: giam | A: tang | C: quay lai", True, (140, 140, 140))
        surface.blit(hint, (cx - hint.get_width() // 2, cy + 35))

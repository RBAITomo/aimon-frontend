"""Badge popup renderer: temporary overlay banner for badge notifications.

Shows badge name + description at top of content area for BADGE_POPUP_FRAMES.
Semi-transparent dark banner with gold text for badge name.
"""

import logging

import pygame

import config

log = logging.getLogger(__name__)


class BadgePopupRenderer:
    """Renders temporary badge notification popup overlay."""

    def __init__(self):
        self._font_name = pygame.font.SysFont("dejavusans", 14, bold=True)
        self._font_desc = pygame.font.SysFont("dejavusans", 12)
        self._active = False
        self._remaining_frames = 0
        self._badge_name = ""
        self._badge_desc = ""

    def show(self, badge_name, description=""):
        """Trigger popup display for BADGE_POPUP_FRAMES."""
        self._badge_name = badge_name
        self._badge_desc = description
        self._remaining_frames = config.BADGE_POPUP_FRAMES
        self._active = True
        log.info("Badge popup: %s", badge_name)

    def render(self, surface, tick):
        """Render popup if active. Call every frame."""
        if not self._active:
            return
        self._remaining_frames -= 1
        if self._remaining_frames <= 0:
            self._active = False
            return

        # Semi-transparent banner at top of content area
        banner_h = 38
        banner_y = config.CONTENT_Y_START + 4
        banner_surf = pygame.Surface((config.LCD_WIDTH - 16, banner_h))
        banner_surf.fill((30, 30, 50))
        banner_surf.set_alpha(210)
        surface.blit(banner_surf, (8, banner_y))

        # Badge name (gold) + description (light gray)
        name_surf = self._font_name.render(self._badge_name, True, (255, 220, 80))
        surface.blit(name_surf, (14, banner_y + 3))
        if self._badge_desc:
            desc_surf = self._font_desc.render(self._badge_desc, True, (190, 190, 200))
            surface.blit(desc_surf, (14, banner_y + 20))

    @property
    def is_active(self):
        return self._active

"""Pygame display engine: thin wrapper over LayerCompositor.

Delegates pet UI rendering to the 4-layer compositor. Keeps offline/error
screens as direct renders (no compositor needed for those).
All rendering targets a Pygame surface converted to RGB565 for ST7789 LCD.
"""

import importlib
import logging
import math

import pygame

import config

log = logging.getLogger(__name__)

# Import kebab-case compositor module
_compositor_mod = importlib.import_module("display.layer-compositor")
LayerCompositor = _compositor_mod.LayerCompositor

# Colors for non-compositor screens
_COL_BG = (10, 10, 20)
_COL_DIM = (100, 100, 120)


class DisplayEngine:
    """Renders state-driven UI to Pygame surface and blits to LCD."""

    def __init__(self, hat):
        """Initialize display with compositor and LCD output.

        Args:
            hat: WhisplayHAT instance for LCD output.
        """
        self._hat = hat
        self._surface = pygame.Surface(
            (config.LCD_WIDTH, config.LCD_HEIGHT), depth=24
        )
        self._compositor = LayerCompositor()
        self._font_large = pygame.font.SysFont("dejavusans", 22)
        self._font_small = pygame.font.SysFont("dejavusans", 16)

        log.info("DisplayEngine initialized (%dx%d)", config.LCD_WIDTH, config.LCD_HEIGHT)

    def render(self, tick, pet_state, text=None, badge_popup=None):
        """Main render call — delegates to compositor.

        Args:
            tick: Animation tick counter.
            pet_state: PetState dataclass with all rendering data.
            text: Optional speech bubble text.
            badge_popup: Optional BadgePopupRenderer to overlay on top.

        Returns:
            bool: True if current animation finished.
        """
        done = self._compositor.render_frame(
            self._surface, tick, pet_state, text
        )
        if badge_popup:
            badge_popup.render(self._surface, tick)
        self._blit_to_lcd()
        return done

    def render_offline(self, tick):
        """Render offline/disconnected screen (no compositor)."""
        self._surface.fill(_COL_BG)
        alpha = int(128 + 127 * math.sin(tick * 0.1))
        col = (alpha, 40, 40)
        self._draw_centered_text("Offline", self._font_large, col, y=120)
        self._draw_centered_text(
            "Reconnecting...", self._font_small, _COL_DIM, y=160
        )
        self._blit_to_lcd()

    def render_error(self, message):
        """Render error message screen (no compositor)."""
        self._surface.fill(_COL_BG)
        self._draw_centered_text("Error", self._font_large, (200, 60, 60), y=100)
        words = message.split(" ")
        lines, current = [], ""
        for word in words:
            test = f"{current} {word}".strip() if current else word
            if self._font_small.size(test)[0] <= config.LCD_WIDTH - 20:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        y = 140
        for line in lines[:4]:
            self._draw_centered_text(line, self._font_small, _COL_DIM, y=y)
            y += 22
        self._blit_to_lcd()

    def render_evolution(self, tick, pet_state):
        """Render evolution flash sequence on top of compositor frame.

        3 white flash pulses over 90 frames (3s at 30fps).
        Returns True when the flash is complete (transition to hold phase).
        """
        FLASH_DURATION = 90
        self._compositor.render_frame(self._surface, tick, pet_state, None)

        if tick <= FLASH_DURATION:
            # sin-wave alpha per 30-frame pulse: 0 → 220 → 0
            pulse_tick = tick % 30
            alpha = int(220 * math.sin(pulse_tick / 30.0 * math.pi))
            if alpha > 0:
                flash = pygame.Surface((config.LCD_WIDTH, config.LCD_HEIGHT))
                flash.fill((255, 255, 255))
                flash.set_alpha(alpha)
                self._surface.blit(flash, (0, 0))

        self._blit_to_lcd()
        return tick >= FLASH_DURATION

    def preload_stage(self, stage):
        """Preload sprites for a stage without switching to it yet."""
        self._compositor.preload_stage(stage)

    def set_black_background(self):
        """Black out display for evolution sequence."""
        self._compositor.set_black_background()

    def clear_black_background(self):
        """Restore normal background rendering after evolution."""
        self._compositor.clear_black_background()

    def reset_scroll(self):
        """Reset speech bubble scroll position."""
        self._compositor.reset_bubble()

    def set_background(self, bg_name):
        """Set background image by filename from backgrounds/ directory."""
        self._compositor.set_background(bg_name)

    def on_stats_changed(self):
        """Notify compositor that stats changed (forces base rebuild)."""
        self._compositor.mark_dirty()

    def _draw_centered_text(self, text, font, color, y):
        """Draw horizontally centered text at given y position."""
        surf = font.render(text, True, color)
        x = (config.LCD_WIDTH - surf.get_width()) // 2
        self._surface.blit(surf, (x, y))

    def _blit_to_lcd(self):
        """Convert Pygame surface to RGB565 and send to LCD via SPI."""
        from hardware.whisplay_hat import surface_to_rgb565
        rgb565_data = surface_to_rgb565(self._surface)
        self._hat.draw_frame(rgb565_data)

"""Renders speech bubble with word-wrapped text and auto-scroll.

Draws a semi-transparent rounded rectangle below the character sprite,
with auto-scrolling text that follows streaming LLM output.
Hidden when no text is active.
"""

import pygame

import config

_BG_COLOR = (30, 30, 45)
_BG_ALPHA = 200
_TEXT_COLOR = (220, 220, 230)
_BORDER_COLOR = (80, 200, 180)
_PADDING = 8
_BORDER_RADIUS = 8


class SpeechBubbleRenderer:
    """Draws speech bubble overlay with wrapped, scrolling text."""

    def __init__(self):
        self._font = pygame.font.SysFont("dejavusans", 13)
        self._line_height = self._font.get_linesize()
        self._scroll_offset = 0
        # Pre-create alpha surface for bubble background
        self._bubble_surf = pygame.Surface(
            (config.BUBBLE_WIDTH, config.BUBBLE_HEIGHT), pygame.SRCALPHA
        )

    def render(self, surface, text, tick):
        """Draw speech bubble with text at BUBBLE_Y position.

        Args:
            surface: Target render surface.
            text: Text string to display (may be partial streaming).
            tick: Current frame tick (unused now, reserved for animations).
        """
        if not text:
            return

        # Draw semi-transparent bubble background
        self._bubble_surf.fill((0, 0, 0, 0))
        pygame.draw.rect(
            self._bubble_surf, (*_BG_COLOR, _BG_ALPHA),
            (0, 0, config.BUBBLE_WIDTH, config.BUBBLE_HEIGHT),
            border_radius=_BORDER_RADIUS,
        )
        pygame.draw.rect(
            self._bubble_surf, (*_BORDER_COLOR, 180),
            (0, 0, config.BUBBLE_WIDTH, config.BUBBLE_HEIGHT),
            1, border_radius=_BORDER_RADIUS,
        )
        surface.blit(self._bubble_surf, (config.BUBBLE_X, config.BUBBLE_Y))

        # Wrap and render text lines
        max_text_w = config.BUBBLE_WIDTH - _PADDING * 2
        lines = self._wrap_text(text, max_text_w)

        # Calculate visible area
        visible_h = config.BUBBLE_HEIGHT - _PADDING * 2
        total_h = len(lines) * self._line_height

        # Auto-scroll to bottom
        if total_h > visible_h:
            self._scroll_offset = total_h - visible_h

        # Render visible lines with clipping
        clip_rect = pygame.Rect(
            config.BUBBLE_X + _PADDING,
            config.BUBBLE_Y + _PADDING,
            max_text_w,
            visible_h,
        )
        old_clip = surface.get_clip()
        surface.set_clip(clip_rect)

        y = config.BUBBLE_Y + _PADDING - self._scroll_offset
        for line in lines:
            if y + self._line_height > config.BUBBLE_Y and y < config.BUBBLE_Y + config.BUBBLE_HEIGHT:
                line_surf = self._font.render(line, True, _TEXT_COLOR)
                surface.blit(line_surf, (config.BUBBLE_X + _PADDING, y))
            y += self._line_height

        surface.set_clip(old_clip)

    def reset(self):
        """Reset scroll position (call on state change)."""
        self._scroll_offset = 0

    def _wrap_text(self, text, max_width):
        """Word-wrap text to fit within max_width pixels."""
        words = text.split(" ")
        lines = []
        current = ""
        for word in words:
            test = f"{current} {word}".strip() if current else word
            if self._font.size(test)[0] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        return lines if lines else [""]

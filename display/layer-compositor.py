"""4-layer compositor for pet UI rendering on 240x280 LCD.

Layer stack (bottom to top):
  1. Background (static scene, cached)
  2. Status bars (hunger/energy/happiness + XP, cached until dirty)
  3. Character sprite (per-frame blit)
  4. Speech bubble (per-frame, only when text active)

Pre-composites layers 1-2 into a base surface that only redraws when
stats change, keeping per-frame blits to 2-3 for Pi Zero 2 performance.
"""

import os
import logging

import pygame

import importlib

import config

# Import kebab-case modules via importlib
_sprite_mod = importlib.import_module("display.sprite-sheet-manager")
_stat_mod = importlib.import_module("display.stat-bar-renderer")
_bubble_mod = importlib.import_module("display.speech-bubble-renderer")
SpriteSheetManager = _sprite_mod.SpriteSheetManager
StatBarRenderer = _stat_mod.StatBarRenderer
SpeechBubbleRenderer = _bubble_mod.SpeechBubbleRenderer

log = logging.getLogger(__name__)

_COL_BG = (10, 10, 20)


class LayerCompositor:
    """Composites 4 layers: background, status, character, speech bubble."""

    def __init__(self):
        self._sprite_mgr = SpriteSheetManager()
        self._stat_renderer = StatBarRenderer()
        self._bubble_renderer = SpeechBubbleRenderer()

        # Pre-composited base surface (background + stat bars + XP bar)
        self._base_surface = pygame.Surface(
            (config.LCD_WIDTH, config.LCD_HEIGHT), depth=24
        )
        self._base_dirty = True
        self._current_bg = None
        self._current_stage = None

        # Cache last stat values to detect changes
        self._last_stats = None

        # Evolution mode: solid black background, stat bars hidden
        self._evolution_mode = False

        # Current variant code (set alongside _current_stage when stage=="variant")
        self._current_variant = None

        # Background fade transition
        self._fade_alpha = 0          # 0 = no overlay, 255 = fully black
        self._fade_direction = 0      # 1 = fading out, -1 = fading in, 0 = idle
        self._fade_speed = 15         # alpha change per frame (~0.55s each way at 30fps)
        self._pending_bg_name = None  # background to load at peak fade
        self._fade_surface = pygame.Surface(
            (config.LCD_WIDTH, config.LCD_HEIGHT), pygame.SRCALPHA
        )

    def set_black_background(self):
        """Enter evolution mode: solid black canvas, stat bars suppressed."""
        self._evolution_mode = True
        self._base_dirty = True

    def clear_black_background(self):
        """Exit evolution mode: restore normal background + stat bars."""
        self._evolution_mode = False
        self._base_dirty = True

    def preload_stage(self, stage, variant_code=None):
        """Preload sprites for a stage without switching current stage."""
        self._sprite_mgr.load_stage(stage, variant_code=variant_code)

    def load_stage(self, stage, variant_code=None):
        """Load sprites for a new evolution stage."""
        if stage == self._current_stage and variant_code == self._current_variant:
            return
        # Unload previous stage to free RAM
        if self._current_stage:
            self._sprite_mgr.unload_stage(self._current_stage)
        self._current_stage = stage
        self._current_variant = variant_code
        self._sprite_mgr.load_stage(stage, variant_code=variant_code)
        self._base_dirty = True
        log.info("Compositor loaded stage: %s (variant: %s)", stage, variant_code)

    def set_background(self, bg_name):
        """Set background with fade transition.

        Fades screen to black, swaps background, then fades back in.
        If no current background (first load), swaps instantly.
        """
        if self._current_bg is None:
            # First load — no transition needed
            self._load_background(bg_name)
            return
        # Start fade-out; load new bg at peak darkness
        self._pending_bg_name = bg_name
        self._fade_direction = 1  # fade out
        self._fade_alpha = 0

    def _load_background(self, bg_name):
        """Load background image immediately (no transition)."""
        path = os.path.join(config.BACKGROUND_DIR, bg_name)
        if os.path.isfile(path):
            try:
                bg = pygame.image.load(path)
                self._current_bg = pygame.transform.scale(
                    bg, (config.LCD_WIDTH, config.CONTENT_HEIGHT)
                )
                self._base_dirty = True
            except pygame.error as e:
                log.warning("Failed to load background %s: %s", bg_name, e)
        else:
            log.warning("Background not found: %s", path)

    def render_frame(self, surface, tick, pet_state, text=None):
        """Composite all layers onto target surface.

        Args:
            surface: Target render surface (240x280).
            tick: Animation tick counter.
            pet_state: PetState dataclass with stage, animation, stats, etc.
            text: Optional speech text (None = bubble hidden).

        Returns:
            bool: True if current animation has finished (one-shot complete).
        """
        # Ensure correct stage + variant is loaded
        effective_variant = pet_state.variant if pet_state.stage == "variant" else None
        if pet_state.stage != self._current_stage or effective_variant != self._current_variant:
            self.load_stage(pet_state.stage, variant_code=effective_variant)

        # Check if stats changed (mark base dirty)
        current_stats = (
            pet_state.hunger, pet_state.energy, pet_state.happiness,
            pet_state.level, pet_state.xp, pet_state.xp_for_next,
            pet_state.battery_pct,
        )
        if current_stats != self._last_stats:
            self._base_dirty = True
            self._last_stats = current_stats

        # Layer 1+2: Background + status bars (cached base)
        if self._base_dirty:
            self._rebuild_base(pet_state)
        surface.blit(self._base_surface, (0, 0))

        # Layer 3: Character sprite (dynamic position for movable stages)
        frame, done = self._sprite_mgr.get_frame(
            pet_state.stage, pet_state.animation, tick, pet_state.direction
        )
        if frame:
            cx = pet_state.char_x if pet_state.char_x >= 0 else config.CHAR_SPRITE_X
            cy = pet_state.char_y if pet_state.char_y >= 0 else config.CHAR_SPRITE_Y
            surface.blit(frame, (cx, cy))

        # Layer 4: Speech bubble
        if text:
            self._bubble_renderer.render(surface, text, tick)

        # Layer 5: Fade transition overlay
        if self._fade_direction != 0:
            self._tick_fade()
            self._fade_surface.fill((0, 0, 0, self._fade_alpha))
            surface.blit(self._fade_surface, (0, 0))

        return done

    def _tick_fade(self):
        """Advance fade transition by one frame."""
        self._fade_alpha += self._fade_speed * self._fade_direction
        if self._fade_direction == 1 and self._fade_alpha >= 255:
            # Peak darkness — swap background and start fade-in
            self._fade_alpha = 255
            if self._pending_bg_name:
                self._load_background(self._pending_bg_name)
                self._pending_bg_name = None
            self._fade_direction = -1  # fade in
        elif self._fade_direction == -1 and self._fade_alpha <= 0:
            # Fade-in complete
            self._fade_alpha = 0
            self._fade_direction = 0

    def _rebuild_base(self, pet_state):
        """Rebuild cached base surface: background + stat bars + XP bar."""
        if self._evolution_mode:
            # Evolution mode: solid black, no stat bars
            self._base_surface.fill((0, 0, 0))
            self._base_dirty = False
            return

        self._base_surface.fill(_COL_BG)

        # Background image in content area
        if self._current_bg:
            self._base_surface.blit(
                self._current_bg, (0, config.CONTENT_Y_START)
            )

        # Top stat bars
        self._stat_renderer.render_stat_bars(
            self._base_surface,
            pet_state.hunger, pet_state.energy, pet_state.happiness,
        )

        # Battery icon (top-right corner)
        self._stat_renderer.render_battery_icon(
            self._base_surface, pet_state.battery_pct,
        )

        # Bottom XP bar
        self._stat_renderer.render_xp_bar(
            self._base_surface,
            pet_state.level, pet_state.xp, pet_state.xp_for_next,
        )

        self._base_dirty = False

    def mark_dirty(self):
        """Force base surface rebuild on next frame."""
        self._base_dirty = True

    def reset_bubble(self):
        """Reset speech bubble scroll position."""
        self._bubble_renderer.reset()

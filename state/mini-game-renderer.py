"""MiniGameRenderer: draws all game visuals as full-screen replacement.

Replaces compositor entirely during MINI_GAME state. Renders onto the
main surface directly (280x240). No alpha blending on falling items.
"""

import importlib
import logging
import os

import pygame

import config

log = logging.getLogger(__name__)

_ctrl_mod = importlib.import_module("state.mini-game-controller")
GameState = _ctrl_mod.GameState

# Colors
BG_COLOR = (200, 180, 220)          # soft purple (Marshmallow Meadow vibe)
TEXT_COLOR = (255, 255, 255)
SCORE_COLOR = (255, 255, 100)
TIMER_BAR_COLOR = (100, 200, 100)
TIMER_BAR_BG = (60, 60, 60)
HAZARD_COLOR = (180, 60, 60)        # red rect for hazard fallback
PLAYER_COLOR = (80, 200, 120)       # green rect placeholder

# Layout
HUD_HEIGHT = 20
TIMER_BAR_WIDTH = 100
TIMER_BAR_HEIGHT = 8
W = config.LCD_WIDTH   # 280
H = config.LCD_HEIGHT  # 240


class MiniGameRenderer:
    """Renders Food Catcher mini-game onto Pygame surface."""

    def __init__(self, controller, font: pygame.font.Font,
                 player_sprite=None, sprite_mgr=None, stage=None):
        self._ctrl = controller
        self._font = font
        self._sprite_mgr = sprite_mgr
        self._stage = stage
        # Smaller font for secondary text
        try:
            self._small_font = pygame.font.Font(font.name if hasattr(font, 'name') else None, 12)
        except Exception:
            self._small_font = pygame.font.SysFont("monospace", 12)
        self._frame = 0
        self._hazard_surface = self._make_hazard_surface()
        self._bg_image = self._load_background()
        # Scale Mon idle sprite as fallback
        self._player_sprite = None
        if player_sprite:
            pw = self._ctrl.player.WIDTH
            ph = self._ctrl.player.HEIGHT
            self._player_sprite = pygame.transform.scale(player_sprite, (pw, ph))
        # Load basket sprite as secondary fallback (when no pet sprite available)
        self._basket_sprite = None
        basket_path = os.path.join(config.UI_ASSETS_PATH, "mini-game-basket.png")
        try:
            basket_img = pygame.image.load(basket_path).convert_alpha()
            pw = self._ctrl.player.WIDTH   # 48
            ph = self._ctrl.player.HEIGHT  # 48
            self._basket_sprite = pygame.transform.smoothscale(basket_img, (pw, ph))
        except (pygame.error, FileNotFoundError):
            log.warning("Basket sprite not found: %s", basket_path)
        # Cache for scaled walking/idle frames
        self._sprite_cache = {}

    def _load_background(self):
        """Load Marshmallow Meadow background for mini-game, fallback to solid color."""
        bg_path = os.path.join(config.BACKGROUND_DIR, "mini-game-meadow.png")
        try:
            bg = pygame.image.load(bg_path).convert()
            return pygame.transform.scale(bg, (W, H))
        except (pygame.error, FileNotFoundError):
            log.warning("Mini-game background not found: %s", bg_path)
            return None

    def _make_hazard_surface(self) -> pygame.Surface:
        """Create a colored rect surface for hazard items (no sprite asset)."""
        _obj = importlib.import_module("state.mini-game-objects")
        s = pygame.Surface((_obj.ITEM_SIZE, _obj.ITEM_SIZE))
        s.fill(HAZARD_COLOR)
        # Draw X pattern
        sz = _obj.ITEM_SIZE
        pygame.draw.line(s, (255, 255, 255), (4, 4), (sz - 4, sz - 4), 2)
        pygame.draw.line(s, (255, 255, 255), (sz - 4, 4), (4, sz - 4), 2)
        return s

    def render(self, surface: pygame.Surface):
        """Render entire mini-game frame onto surface (full 280x240)."""
        self._frame += 1
        state = self._ctrl.state

        # Always clear full screen with background
        if self._bg_image:
            surface.blit(self._bg_image, (0, 0))
        else:
            surface.fill(BG_COLOR)

        if state == GameState.WAITING:
            self._render_waiting(surface)
        elif state == GameState.COUNTDOWN:
            self._render_countdown(surface)
        elif state == GameState.PLAYING:
            self._render_items(surface)
            self._render_player(surface)
            self._render_hud(surface)
        elif state == GameState.PAUSED:
            self._render_items(surface)
            self._render_player(surface)
            self._render_hud(surface)
            self._render_paused(surface)
        elif state == GameState.GAME_OVER:
            self._render_game_over(surface)

    def _render_hud(self, surface: pygame.Surface):
        # Score — top left
        score_text = self._font.render(f"{self._ctrl.score}", True, SCORE_COLOR)
        surface.blit(score_text, (4, 2))

        # High score — top center
        hi_text = self._small_font.render(f"HI:{self._ctrl.high_score}", True, TEXT_COLOR)
        surface.blit(hi_text, ((W - hi_text.get_width()) // 2, 4))

        # Lives — below score (left side)
        lives = self._ctrl.lives_remaining
        lives_text = self._small_font.render(f"x{lives}", True, (255, 100, 100))
        surface.blit(lives_text, (4, 18))

        # Timer bar — top right
        bar_x = W - TIMER_BAR_WIDTH - 4
        bar_y = 6
        pygame.draw.rect(surface, TIMER_BAR_BG, (bar_x, bar_y, TIMER_BAR_WIDTH, TIMER_BAR_HEIGHT))
        fill_w = int(TIMER_BAR_WIDTH * self._ctrl.timer_ratio)
        if fill_w > 0:
            pygame.draw.rect(surface, TIMER_BAR_COLOR, (bar_x, bar_y, fill_w, TIMER_BAR_HEIGHT))

    def _render_items(self, surface: pygame.Surface):
        for item in self._ctrl.items:
            # Use hazard fallback surface if sprite_key starts with "hazard_"
            if item.item_type == "hazard" and item.sprite_key.startswith("hazard_"):
                surface.blit(self._hazard_surface, (int(item.x), int(item.y)))
            else:
                surface.blit(item.surface, (int(item.x), int(item.y)))

    def _get_player_frame(self):
        """Get the appropriate animation frame based on player movement state."""
        player = self._ctrl.player
        pw, ph = player.WIDTH, player.HEIGHT

        if self._sprite_mgr and self._stage and player.moving:
            # Use walking animation when moving
            direction = "west" if player.moving == "left" else "east"
            frame, _ = self._sprite_mgr.get_frame(
                self._stage, "walking", self._frame, direction
            )
            cache_key = ("walking", direction, id(frame))
            if cache_key not in self._sprite_cache:
                self._sprite_cache[cache_key] = pygame.transform.scale(frame, (pw, ph))
            return self._sprite_cache[cache_key]

        return self._player_sprite or self._basket_sprite

    def _render_player(self, surface: pygame.Surface):
        player = self._ctrl.player
        # Stun flash: alternate visibility every 5 frames
        if player.is_stunned and (self._frame // 5) % 2 == 0:
            return

        sprite = self._get_player_frame()
        if sprite:
            surface.blit(sprite, (int(player.x), player.y_pos))
        else:
            # Fallback: basket PNG, or green rect if basket also missing
            if self._basket_sprite:
                surface.blit(self._basket_sprite, (int(player.x), player.y_pos))
            else:
                pygame.draw.rect(surface, PLAYER_COLOR,
                                 (int(player.x), player.y_pos, player.WIDTH, player.HEIGHT))

    def _render_countdown(self, surface: pygame.Surface):
        num = self._ctrl.countdown_number
        text = str(num) if num > 0 else "GO!"
        rendered = self._font.render(text, True, TEXT_COLOR)
        x = (W - rendered.get_width()) // 2
        y = (H - rendered.get_height()) // 2
        surface.blit(rendered, (x, y))

    def _render_paused(self, surface: pygame.Surface):
        # Semi-transparent dark overlay
        overlay = pygame.Surface((W, H))
        overlay.set_alpha(128)
        overlay.fill((0, 0, 0))
        surface.blit(overlay, (0, 0))

        text = self._font.render("PAUSED", True, TEXT_COLOR)
        surface.blit(text, ((W - text.get_width()) // 2, (H - text.get_height()) // 2))

    def _render_game_over(self, surface: pygame.Surface):
        cx = W // 2
        y = 30

        # Title
        title = self._font.render("GAME OVER", True, TEXT_COLOR)
        surface.blit(title, (cx - title.get_width() // 2, y))
        y += 30

        # Score
        score_text = self._font.render(f"Score: {self._ctrl.score}", True, SCORE_COLOR)
        surface.blit(score_text, (cx - score_text.get_width() // 2, y))
        y += 24

        # Cotton candy earned
        candy = self._ctrl.cotton_candy_earned
        candy_text = self._font.render(f"Cotton Candy: {candy}", True, TEXT_COLOR)
        surface.blit(candy_text, (cx - candy_text.get_width() // 2, y))
        y += 24

        # High score
        hi_text = self._font.render(f"High Score: {self._ctrl.high_score}", True, TEXT_COLOR)
        surface.blit(hi_text, (cx - hi_text.get_width() // 2, y))
        y += 36

        # Error message if start was rejected
        if self._ctrl.error_reason:
            err = self._ctrl.error_reason.replace("_", " ").title()
            err_text = self._small_font.render(err, True, (255, 100, 100))
            surface.blit(err_text, (cx - err_text.get_width() // 2, y))
            y += 20

        # Exit prompt
        exit_text = self._small_font.render("Press B to exit", True, TEXT_COLOR)
        surface.blit(exit_text, (cx - exit_text.get_width() // 2, y))

    def _render_waiting(self, surface: pygame.Surface):
        text = self._font.render("Loading...", True, TEXT_COLOR)
        surface.blit(text, ((W - text.get_width()) // 2, (H - text.get_height()) // 2))

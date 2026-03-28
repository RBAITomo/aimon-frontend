"""Badge screen: grid of badge sprites with earned/unearned states and detail view."""

import logging
import os

import pygame

import config

log = logging.getLogger(__name__)

_BADGE_DIR = config.BADGE_ASSETS_PATH
_BADGE_SIZE = 32
_CELL_SIZE = 48  # 32px sprite + 8px padding each side
_COLS = config.BADGE_GRID_COLS
_ROWS = config.BADGE_GRID_ROWS
_PER_PAGE = _COLS * _ROWS
_GRID_START_X = (config.LCD_WIDTH - _COLS * _CELL_SIZE) // 2
_GRID_START_Y = 50


class BadgeScreenRenderer:
    """Renders badge grid with sprites. Earned=color, unearned=grey+lock."""

    def __init__(self):
        self._font_title = pygame.font.SysFont("dejavusans", 16, bold=True)
        self._font_name = pygame.font.SysFont("dejavusans", 12, bold=True)
        self._font_desc = pygame.font.SysFont("dejavusans", 10)
        self._font_hint = pygame.font.SysFont("dejavusans", 11)
        self._page = 0
        self._selected = 0
        self._detail_mode = False
        self._sprite_cache = {}

    @property
    def page(self):
        return self._page

    @property
    def is_in_detail(self):
        """True when badge detail view is active."""
        return self._detail_mode

    def can_evolve_selected(self, badges_data, pet_stage):
        """Return variant_code if selected badge can trigger evolution, else None."""
        if not badges_data or self._selected >= len(badges_data):
            return None
        badge = badges_data[self._selected]
        if not badge.get("earned") or not badge.get("variant_code"):
            return None
        if pet_stage not in ("adult", "child"):
            return None
        return badge.get("variant_code")

    def trigger_evolve(self, badges_data):
        """Return badge code for evolution trigger, or None if not eligible."""
        if not badges_data or self._selected >= len(badges_data):
            return None
        badge = badges_data[self._selected]
        if badge.get("earned") and badge.get("variant_code"):
            return badge.get("code")
        return None

    def next_selection(self):
        """Move selection right/down."""
        self._selected += 1

    def prev_selection(self):
        """Move selection left/up."""
        self._selected -= 1

    def toggle_detail(self):
        """Toggle detail view for selected badge."""
        self._detail_mode = not self._detail_mode

    def back(self):
        """Exit detail mode, or signal to close screen."""
        if self._detail_mode:
            self._detail_mode = False
            return False  # handled internally
        return True  # let caller close screen

    def render(self, surface, badges_data=None, pet_stage="adult", **kwargs):
        """Render badge grid or detail view.
        badges_data=None means still loading; [] means loaded but no badges yet.
        pet_stage: current pet stage string (used to gate evolution hint in detail view).
        """
        if badges_data is None:
            self._render_loading(surface)
            return
        if len(badges_data) == 0:
            self._render_no_badges(surface)
            return
        badges = badges_data

        total = len(badges)
        total_pages = max(1, (total + _PER_PAGE - 1) // _PER_PAGE)
        self._page = max(0, min(self._page, total_pages - 1))
        self._selected = max(0, min(self._selected, total - 1))

        if self._detail_mode:
            self._render_detail(surface, badges[self._selected], pet_stage=pet_stage)
        else:
            self._render_grid(surface, badges, total_pages)

    def _render_loading(self, surface):
        title = self._font_title.render("Huy Hiệu", True, (255, 255, 255))
        surface.blit(title, (config.LCD_WIDTH // 2 - title.get_width() // 2, 8))
        msg = self._font_desc.render("Đang tải...", True, (140, 140, 140))
        surface.blit(msg, (config.LCD_WIDTH // 2 - msg.get_width() // 2, config.LCD_HEIGHT // 2))

    def _render_no_badges(self, surface):
        title = self._font_title.render("Huy Hiệu", True, (255, 255, 255))
        surface.blit(title, (config.LCD_WIDTH // 2 - title.get_width() // 2, 8))
        msg = self._font_desc.render("Chua co huy hieu nao", True, (140, 140, 140))
        surface.blit(msg, (config.LCD_WIDTH // 2 - msg.get_width() // 2, config.LCD_HEIGHT // 2))

    def _render_grid(self, surface, badges, total_pages):
        earned_count = sum(1 for b in badges if b.get("earned"))
        total = len(badges)

        # Title
        title = self._font_title.render(f"Huy Hiệu ({earned_count}/{total})", True, (255, 255, 255))
        surface.blit(title, (config.LCD_WIDTH // 2 - title.get_width() // 2, 8))

        # Page info
        if total_pages > 1:
            pg = self._font_hint.render(f"Trang {self._page + 1}/{total_pages}", True, (140, 140, 140))
            surface.blit(pg, (config.LCD_WIDTH // 2 - pg.get_width() // 2, 30))

        # Grid
        start = self._page * _PER_PAGE
        page_badges = badges[start:start + _PER_PAGE]

        for i, badge in enumerate(page_badges):
            col = i % _COLS
            row = i // _COLS
            x = _GRID_START_X + col * _CELL_SIZE
            y = _GRID_START_Y + row * (_CELL_SIZE + 4)
            global_idx = start + i
            is_selected = global_idx == self._selected

            # Selection highlight
            if is_selected:
                pygame.draw.rect(surface, (255, 220, 80), (x - 2, y - 2, _CELL_SIZE + 4, _CELL_SIZE + 4), 2, border_radius=6)

            code = badge.get("code", "")
            earned = badge.get("earned", False)
            sprite_x = x + (_CELL_SIZE - _BADGE_SIZE) // 2
            sprite_y = y + (_CELL_SIZE - _BADGE_SIZE) // 2

            if earned:
                spr = self._load_sprite(code)
                if spr:
                    surface.blit(spr, (sprite_x, sprite_y))
                else:
                    self._draw_fallback_circle(surface, sprite_x, sprite_y, code, (100, 200, 100))
            else:
                # Grey placeholder with lock
                self._draw_fallback_circle(surface, sprite_x, sprite_y, code, (60, 60, 70))
                lock = self._font_desc.render("🔒", True, (120, 120, 130))
                surface.blit(lock, (sprite_x + _BADGE_SIZE - 10, sprite_y + _BADGE_SIZE - 10))

        # Hints
        hint = self._font_hint.render("A/D:chon B:xem C:dong", True, (100, 100, 100))
        surface.blit(hint, (config.LCD_WIDTH // 2 - hint.get_width() // 2, config.LCD_HEIGHT - 18))

    def _render_detail(self, surface, badge, pet_stage="adult"):
        """Detail view for a single badge."""
        cx = config.LCD_WIDTH // 2
        y = 20

        # Badge sprite (larger)
        code = badge.get("code", "")
        spr = self._load_sprite(code)
        if spr:
            big = pygame.transform.smoothscale(spr, (48, 48))
            surface.blit(big, (cx - 24, y))
        else:
            earned = badge.get("earned", False)
            color = (100, 200, 100) if earned else (60, 60, 70)
            pygame.draw.circle(surface, color, (cx, y + 24), 24)
        y += 56

        # Name
        name = self._font_name.render(badge.get("name", code), True, (255, 220, 80))
        surface.blit(name, (cx - name.get_width() // 2, y))
        y += 22

        # Description
        desc = badge.get("description", "")
        if desc:
            desc_surf = self._font_desc.render(desc, True, (190, 190, 200))
            surface.blit(desc_surf, (cx - desc_surf.get_width() // 2, y))
        y += 20

        # Progress / earned status
        earned = badge.get("earned", False)
        if earned:
            status = self._font_desc.render("Da dat duoc!", True, (100, 255, 100))
            surface.blit(status, (cx - status.get_width() // 2, y))
            y += 18
            earned_at = badge.get("earned_at", "")
            if earned_at:
                date_surf = self._font_desc.render(f"Ngay: {earned_at[:10]}", True, (140, 140, 150))
                surface.blit(date_surf, (cx - date_surf.get_width() // 2, y))
        else:
            progress = badge.get("progress", 0)
            prog_text = f"Tien do: {progress}"
            prog_surf = self._font_desc.render(prog_text, True, (180, 180, 180))
            surface.blit(prog_surf, (cx - prog_surf.get_width() // 2, y))
        y += 22

        # XP reward
        xp = badge.get("xp_reward", 0)
        xp_surf = self._font_desc.render(f"+{xp} XP", True, (255, 220, 80))
        surface.blit(xp_surf, (cx - xp_surf.get_width() // 2, y))
        y += 22

        # Evolution section (when badge has evolution and pet is ADULT or CHILD)
        variant_code = badge.get("variant_code")
        if variant_code and badge.get("earned") and pet_stage in ("adult", "child"):
            evo_label = self._font_desc.render("* Co the tien hoa!", True, (255, 200, 50))
            surface.blit(evo_label, (cx - evo_label.get_width() // 2, y))
            hint_text = "A:tien hoa  C:quay lai"
        else:
            hint_text = "C: quay lai"

        hint = self._font_hint.render(hint_text, True, (100, 100, 100))
        surface.blit(hint, (cx - hint.get_width() // 2, config.LCD_HEIGHT - 18))

    def _load_sprite(self, badge_code):
        """Load badge sprite PNG, cache it."""
        if badge_code in self._sprite_cache:
            return self._sprite_cache[badge_code]
        path = os.path.join(_BADGE_DIR, f"{badge_code}.png")
        if not os.path.exists(path):
            self._sprite_cache[badge_code] = None
            return None
        try:
            img = pygame.image.load(path).convert_alpha()
            img = pygame.transform.smoothscale(img, (_BADGE_SIZE, _BADGE_SIZE))
            self._sprite_cache[badge_code] = img
            return img
        except pygame.error as e:
            log.warning("Failed to load badge sprite %s: %s", badge_code, e)
            self._sprite_cache[badge_code] = None
            return None

    def _draw_fallback_circle(self, surface, x, y, code, color):
        """Draw colored circle with first letter as fallback."""
        cx = x + _BADGE_SIZE // 2
        cy = y + _BADGE_SIZE // 2
        pygame.draw.circle(surface, color, (cx, cy), _BADGE_SIZE // 2)
        letter = code[0].upper() if code else "?"
        letter_surf = self._font_name.render(letter, True, (255, 255, 255))
        surface.blit(letter_surf, (cx - letter_surf.get_width() // 2, cy - letter_surf.get_height() // 2))

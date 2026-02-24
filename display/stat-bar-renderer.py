"""Renders pet stat bars (hunger/energy/happiness) and XP progress bar.

Uses pygame.draw.rect for performance on Pi Zero 2. Pre-renders static
labels at init to avoid per-frame font rendering.
"""

import pygame

import config

# Stat bar color pairs: (full_color, empty_color)
_HUNGER_FULL = (60, 180, 80)
_HUNGER_EMPTY = (200, 60, 60)
_ENERGY_FULL = (200, 190, 60)
_ENERGY_EMPTY = (100, 100, 110)
_HAPPINESS_FULL = (200, 120, 160)
_HAPPINESS_EMPTY = (100, 100, 110)

_BAR_BG = (40, 40, 55)
_XP_COLOR = (80, 200, 180)
_XP_BG = (40, 40, 55)
_LABEL_COLOR = (180, 180, 200)

# Battery icon colors
_BAT_HIGH = (60, 180, 80)    # green  >50%
_BAT_MID = (200, 180, 60)    # yellow 20-50%
_BAT_LOW = (200, 60, 60)     # red    <20%
_BAT_UNKNOWN = (100, 100, 110)  # grey  unavailable
_BAT_OUTLINE = (160, 160, 180)

# Battery icon geometry (top-right of stat bar region)
# Body: 21×6px outline; nub: 3×4px cap; fill: 19×4px inside body
_BAT_X = 213
_BAT_Y = 9   # same as STAT_BAR_Y
_BAT_BODY_W = 21
_BAT_BODY_H = 6
_BAT_NUB_W = 3
_BAT_NUB_H = 4
_BAT_FILL_MAX_W = 19  # max fill width inside body


class StatBarRenderer:
    """Draws stat bars in top region and XP bar in bottom region."""

    def __init__(self):
        self._font = pygame.font.SysFont("dejavusans", 10)
        self._level_font = pygame.font.SysFont("dejavusans", 11)
        # Pre-render stat icons as colored dots (cheaper than text labels)
        self._icons = {
            "hunger": _HUNGER_FULL,
            "energy": _ENERGY_FULL,
            "happiness": _HAPPINESS_FULL,
        }

    def render_stat_bars(self, surface, hunger, energy, happiness):
        """Draw 3 horizontal stat bars in the top 24px region.

        Args:
            surface: Target surface to draw on.
            hunger: 0-100 (high = bad, color inverts).
            energy: 0-100 (low = bad).
            happiness: 0-100 (low = bad).
        """
        # (name, value, full_color, empty_color, invert)
        # invert=True: high value = bad (hunger), bar fills red when high
        stats = [
            ("hunger", hunger, _HUNGER_FULL, _HUNGER_EMPTY, True),
            ("energy", energy, _ENERGY_FULL, _ENERGY_EMPTY, False),
            ("happiness", happiness, _HAPPINESS_FULL, _HAPPINESS_EMPTY, False),
        ]

        x = 8
        y = config.STAT_BAR_Y
        bar_w = config.STAT_BAR_WIDTH
        bar_h = config.STAT_BAR_THICKNESS

        for name, value, full_col, empty_col, invert in stats:
            # Icon dot
            icon_col = self._icons[name]
            pygame.draw.circle(surface, icon_col, (x + 3, y + bar_h // 2), 3)

            # Background track
            bx = x + 10
            pygame.draw.rect(surface, _BAR_BG, (bx, y, bar_w, bar_h))

            # Fill bar (invert: high hunger = red)
            fill_pct = max(0, min(100, value)) / 100.0
            if invert:
                fill_pct = 1.0 - fill_pct
            fill_w = int(bar_w * fill_pct)

            # Lerp color between full and empty
            col = self._lerp_color(full_col, empty_col, 1.0 - fill_pct)
            if fill_w > 0:
                pygame.draw.rect(surface, col, (bx, y, fill_w, bar_h))

            x += 10 + bar_w + config.STAT_BAR_GAP

    def render_xp_bar(self, surface, level, xp, xp_for_next):
        """Draw XP progress bar + level label in bottom 24px region.

        Args:
            surface: Target surface.
            level: Current pet level.
            xp: Current XP in this level.
            xp_for_next: XP needed to reach next level.
        """
        y = config.XP_BAR_Y
        bar_h = config.XP_BAR_HEIGHT_PX

        # Level label
        label = self._level_font.render(f"Lv.{level}", True, _LABEL_COLOR)
        surface.blit(label, (6, y - 1))

        # XP bar background
        bx = config.XP_BAR_X
        bw = config.XP_BAR_WIDTH
        pygame.draw.rect(surface, _XP_BG, (bx, y, bw, bar_h))

        # XP fill
        if xp_for_next > 0:
            fill_pct = max(0, min(1.0, xp / xp_for_next))
            fill_w = int(bw * fill_pct)
            if fill_w > 0:
                pygame.draw.rect(surface, _XP_COLOR, (bx, y, fill_w, bar_h))

    def render_battery_icon(self, surface, battery_pct: int):
        """Draw a small battery icon in the top-right corner of the stat bar region.

        Args:
            surface: Target surface.
            battery_pct: 0-100 percentage, or -1 if unavailable.
        """
        x, y = _BAT_X, _BAT_Y

        # Choose fill color by level
        if battery_pct < 0:
            fill_col = _BAT_UNKNOWN
            fill_w = 0
        elif battery_pct > 50:
            fill_col = _BAT_HIGH
            fill_w = int(_BAT_FILL_MAX_W * battery_pct / 100)
        elif battery_pct > 20:
            fill_col = _BAT_MID
            fill_w = int(_BAT_FILL_MAX_W * battery_pct / 100)
        else:
            fill_col = _BAT_LOW
            fill_w = max(1, int(_BAT_FILL_MAX_W * battery_pct / 100))

        # Body outline
        pygame.draw.rect(surface, _BAT_OUTLINE, (x, y, _BAT_BODY_W, _BAT_BODY_H), 1)

        # Fill inside body (1px inset from outline)
        if fill_w > 0:
            pygame.draw.rect(surface, fill_col, (x + 1, y + 1, fill_w, _BAT_BODY_H - 2))

        # Terminal nub (right side cap)
        nub_y = y + (_BAT_BODY_H - _BAT_NUB_H) // 2
        pygame.draw.rect(surface, _BAT_OUTLINE, (x + _BAT_BODY_W, nub_y, _BAT_NUB_W, _BAT_NUB_H))

    @staticmethod
    def _lerp_color(c1, c2, t):
        """Linear interpolate between two RGB colors. t=0 -> c1, t=1 -> c2."""
        t = max(0.0, min(1.0, t))
        return tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))

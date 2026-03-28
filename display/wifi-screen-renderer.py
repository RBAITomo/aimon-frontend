"""WiFi screen renderer: shows current connection status and saved profiles."""

import logging
import subprocess
import time

import pygame

import config

log = logging.getLogger(__name__)


class WifiScreenRenderer:
    """Renders WiFi status screen with active connection and saved profiles."""

    def __init__(self):
        self._font = pygame.font.SysFont("dejavusans", 20)
        self._font_small = pygame.font.SysFont("dejavusans", 14)
        self._font_title = pygame.font.SysFont("dejavusans", 22)
        self._cached_status = {"ssid": None, "signal": 0}
        self._last_refresh = 0.0
        self._refresh_interval = 5  # seconds between nmcli queries

    def render(self, surface, wifi_manager=None, **_kwargs):
        """Draw WiFi status screen.

        Args:
            surface: pygame surface to draw on.
            wifi_manager: WifiManager instance for saved profiles.
        """
        now = time.time()
        if now - self._last_refresh > self._refresh_interval:
            self._cached_status = self._get_wifi_status()
            self._last_refresh = now

        cx = config.LCD_WIDTH // 2
        y = 15

        # Title
        title = self._font_title.render("WiFi", True, (255, 255, 255))
        surface.blit(title, (cx - title.get_width() // 2, y))
        y += 35

        # Active connection
        ssid = self._cached_status["ssid"]
        signal = self._cached_status["signal"]
        if ssid:
            # Green dot + SSID
            pygame.draw.circle(surface, (80, 200, 80), (25, y + 8), 5)
            label = self._font.render(ssid, True, (80, 200, 80))
            surface.blit(label, (38, y - 2))
            # Signal bars on the right
            self._draw_signal_bars(surface, config.LCD_WIDTH - 55, y - 2, signal)
        else:
            pygame.draw.circle(surface, (200, 80, 80), (25, y + 8), 5)
            label = self._font.render("Khong ket noi", True, (200, 80, 80))
            surface.blit(label, (38, y - 2))
        y += 28

        # Separator
        pygame.draw.line(surface, (80, 80, 80), (15, y), (config.LCD_WIDTH - 15, y))
        y += 12

        # Saved profiles section
        header = self._font_small.render("Da luu:", True, (180, 180, 180))
        surface.blit(header, (15, y))
        y += 20

        try:
            profiles = wifi_manager.get_profiles() if wifi_manager else []
        except Exception:
            profiles = []
        if not profiles:
            empty = self._font_small.render("(chua co)", True, (100, 100, 100))
            surface.blit(empty, (25, y))
        else:
            # Show up to 5 profiles (screen height limit)
            for prof in profiles[:5]:
                p_ssid = prof.get("ssid", "?")
                is_active = ssid and p_ssid == ssid
                color = (80, 200, 80) if is_active else (200, 200, 200)
                prefix = "> " if is_active else "  "
                text = self._font_small.render(f"{prefix}{p_ssid}", True, color)
                surface.blit(text, (20, y))
                y += 18

        # Hint at bottom
        hint = self._font_small.render("A: them WiFi | C: quay lai", True, (100, 100, 100))
        surface.blit(hint, (cx - hint.get_width() // 2, config.LCD_HEIGHT - 22))

    def _draw_signal_bars(self, surface, x, y, signal):
        """Draw 5-bar signal strength indicator.

        Args:
            surface: pygame surface.
            x: top-left x of bar group.
            y: top-left y of bar group.
            signal: signal strength 0-100.
        """
        bar_count = max(1, min(5, (signal + 10) // 20))
        if signal <= 20:
            color = (200, 60, 60)
        elif signal <= 40:
            color = (220, 160, 40)
        elif signal <= 60:
            color = (220, 220, 60)
        else:
            color = (80, 200, 80)

        for i in range(5):
            bar_h = 4 + i * 3  # increasing height: 4, 7, 10, 13, 16
            bar_x = x + i * 8
            bar_y = y + 20 - bar_h
            bar_color = color if i < bar_count else (60, 60, 60)
            pygame.draw.rect(surface, bar_color, (bar_x, bar_y, 5, bar_h))

    @staticmethod
    def _get_wifi_status():
        """Query nmcli for active WiFi SSID and signal strength."""
        try:
            # Get active WiFi connection name
            r = subprocess.run(
                ["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active"],
                capture_output=True, text=True, timeout=3,
            )
            active_ssid = None
            for line in r.stdout.strip().split("\n"):
                # rsplit from right — TYPE is always last, SSID may contain colons
                parts = line.rsplit(":", 1)
                if len(parts) >= 2 and parts[1] == "802-11-wireless":
                    active_ssid = parts[0]
                    break

            # Get signal strength for active network
            signal = 0
            if active_ssid:
                r2 = subprocess.run(
                    ["nmcli", "-t", "-f", "SSID,SIGNAL", "dev", "wifi", "list"],
                    capture_output=True, text=True, timeout=3,
                )
                for line in r2.stdout.strip().split("\n"):
                    # rsplit from right — SIGNAL is always last, SSID may contain colons
                    parts = line.rsplit(":", 1)
                    if len(parts) >= 2 and parts[0] == active_ssid:
                        try:
                            signal = int(parts[1])
                        except ValueError:
                            pass
                        break

            return {"ssid": active_ssid, "signal": signal}
        except Exception as e:
            log.warning("Failed to query WiFi status: %s", e)
            return {"ssid": None, "signal": 0}

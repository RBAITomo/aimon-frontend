"""WiFi setup screen renderer: QR code display during captive portal setup.

Shows QR code encoding portal URL on the 280x240 LCD, with Vietnamese
instructions and dynamic status text. Used instead of the normal WiFi
status screen while captive portal setup is active.
"""

import io
import logging

import pygame

import config

log = logging.getLogger(__name__)

# Lazy-load qrcode to avoid import errors on dev machines
_qrcode = None


def _ensure_qrcode():
    global _qrcode
    if _qrcode is None:
        import qrcode as _qr
        _qrcode = _qr


class WifiSetupScreenRenderer:
    """Renders QR code + status during captive portal WiFi setup."""

    def __init__(self):
        self._font_title = pygame.font.SysFont("dejavusans", 20)
        self._font_body = pygame.font.SysFont("dejavusans", 14)
        self._font_hint = pygame.font.SysFont("dejavusans", 12)
        self._qr_surface = None
        self._status_text = ""
        self._portal_url = None

    def set_portal_url(self, url: str):
        """Generate QR code from URL and cache as pygame Surface."""
        try:
            _ensure_qrcode()
            self._portal_url = url
            qr = _qrcode.QRCode(version=None, box_size=5, border=2,
                                error_correction=_qrcode.constants.ERROR_CORRECT_M)
            qr.add_data(url)
            qr.make(fit=True)
            # White QR on black background for LCD contrast
            img = qr.make_image(fill_color="white", back_color="black")
            img = img.resize((140, 140))
            raw = img.convert("RGB").tobytes()
            self._qr_surface = pygame.image.frombuffer(raw, (140, 140), "RGB")
            log.info("QR code generated for %s", url)
        except Exception as e:
            log.error("QR generation failed: %s", e)
            self._qr_surface = None

    def set_status(self, text: str):
        """Update status line shown below QR code."""
        self._status_text = text

    def reset(self):
        """Clear all state for next use."""
        self._qr_surface = None
        self._status_text = ""
        self._portal_url = None

    def render(self, surface, **_kwargs):
        """Draw QR code + instructions + status onto surface."""
        cx = config.LCD_WIDTH // 2

        # Title: AP name
        title = self._font_title.render("AIMON-Setup", True, (0, 180, 216))
        surface.blit(title, (cx - title.get_width() // 2, 8))

        # Instruction text
        instr = self._font_body.render("Quét mẫ để kết nối WiFi", True, (180, 180, 180))
        surface.blit(instr, (cx - instr.get_width() // 2, 32))

        if self._qr_surface:
            # QR code centered
            qr_x = cx - 70  # 140/2
            surface.blit(self._qr_surface, (qr_x, 52))
        else:
            # Loading state: show status in center
            if self._status_text:
                loading = self._font_body.render(self._status_text, True, (0, 180, 216))
                surface.blit(loading, (cx - loading.get_width() // 2, 110))

        # Status text below QR
        if self._status_text and self._qr_surface:
            status = self._font_body.render(self._status_text, True, (0, 200, 255))
            surface.blit(status, (cx - status.get_width() // 2, 198))

        # Button hint at bottom
        hint = self._font_hint.render("C: huy", True, (100, 100, 100))
        surface.blit(hint, (cx - hint.get_width() // 2, config.LCD_HEIGHT - 20))

"""WiFi QR manager: decode QR codes, persist profiles, connect via nmcli.

Scan WiFi QR codes (standard WIFI:S:...;T:...;P:...; format),
save/dedup profiles to JSON, and connect using NetworkManager CLI.
"""

import io
import json
import logging
import os
import stat
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

def _parse_wifi_qr(raw: str) -> dict | None:
    """Parse WiFi QR string (field-order independent). Returns {ssid, type, password} or None."""
    if not raw.startswith("WIFI:"):
        return None
    fields = {}
    for part in raw[5:].rstrip(";").split(";"):
        if ":" in part:
            k, v = part.split(":", 1)
            fields[k] = v
    if "S" not in fields:
        return None
    return {"ssid": fields["S"], "type": fields.get("T", ""), "password": fields.get("P", "")}

# Lazy imports for hardware-only deps (pyzbar, PIL)
_pyzbar_decode = None
_PIL_Image = None


def _ensure_imports():
    """Lazy-load pyzbar and PIL so module imports don't fail on dev machines."""
    global _pyzbar_decode, _PIL_Image
    if _pyzbar_decode is None:
        from pyzbar.pyzbar import decode as _decode
        from PIL import Image as _Img

        _pyzbar_decode = _decode
        _PIL_Image = _Img


class WifiManager:
    """QR WiFi decode, profile persistence, and nmcli connection."""

    def __init__(self, profiles_path: str):
        self._path = Path(profiles_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    # -- Profile persistence --------------------------------------------------

    def _load(self) -> dict:
        if not self._path.exists():
            return {"profiles": [], "last_used": None}
        with open(self._path) as f:
            return json.load(f)

    def _save(self, data: dict):
        with open(self._path, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        os.chmod(self._path, stat.S_IRUSR | stat.S_IWUSR)  # 600

    def get_profiles(self) -> list:
        return self._load()["profiles"]

    def add_profile(self, ssid: str, password: str):
        """Save profile (dedup by SSID — update password if exists)."""
        data = self._load()
        for p in data["profiles"]:
            if p["ssid"] == ssid:
                p["password"] = password
                break
        else:
            data["profiles"].append({"ssid": ssid, "password": password})
        data["last_used"] = ssid
        self._save(data)
        log.info("WiFi profile saved: %s", ssid)

    # -- QR decode -------------------------------------------------------------

    def scan_qr_for_wifi(self, jpeg_bytes: bytes) -> dict | None:
        """Decode WiFi QR from JPEG bytes. Returns {ssid, password, type} or None."""
        try:
            _ensure_imports()
            img = _PIL_Image.open(io.BytesIO(jpeg_bytes))
            codes = _pyzbar_decode(img)
            for code in codes:
                raw = code.data.decode("utf-8", errors="ignore")
                result = _parse_wifi_qr(raw)
                if result:
                    return result
        except Exception as e:
            log.error("QR decode error: %s", e)
        return None

    # -- nmcli connection ------------------------------------------------------

    def connect_to_profile(self, ssid: str, password: str) -> bool:
        """Connect via nmcli. Returns True on success."""
        try:
            # Try existing NetworkManager connection first
            r = subprocess.run(
                ["nmcli", "connection", "up", ssid],
                capture_output=True,
                timeout=15,
            )
            if r.returncode == 0:
                log.info("Connected to existing NM profile: %s", ssid)
                return True
            # Add new connection and connect
            r = subprocess.run(
                ["nmcli", "device", "wifi", "connect", ssid, "password", password],
                capture_output=True,
                timeout=30,
            )
            success = r.returncode == 0
            log.info(
                "nmcli connect %s: %s",
                ssid,
                "OK" if success else f"FAILED (rc={r.returncode})",
            )
            return success
        except subprocess.TimeoutExpired:
            log.error("nmcli timeout connecting to %s", ssid)
            return False
        except Exception as e:
            log.error("nmcli error: %s", e)
            return False

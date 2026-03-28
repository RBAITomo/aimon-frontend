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

    # -- Network scanning -------------------------------------------------------

    @staticmethod
    def scan_available_networks() -> list[dict]:
        """Scan nearby WiFi networks via nmcli. Returns [{ssid, signal}] sorted by signal desc."""
        try:
            r = subprocess.run(
                ["nmcli", "-t", "-f", "SSID,SIGNAL", "dev", "wifi", "list", "--rescan", "yes"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode != 0:
                log.warning("nmcli wifi list failed: %s", r.stderr.strip())
                return []
            # Deduplicate SSIDs, keep highest signal
            seen = {}
            for line in r.stdout.strip().split("\n"):
                if not line:
                    continue
                parts = line.rsplit(":", 1)
                if len(parts) < 2:
                    continue
                ssid = parts[0].strip()
                if not ssid:
                    continue
                try:
                    signal = int(parts[1])
                except ValueError:
                    signal = 0
                if ssid not in seen or signal > seen[ssid]:
                    seen[ssid] = signal
            result = [{"ssid": s, "signal": sig} for s, sig in seen.items()]
            result.sort(key=lambda x: x["signal"], reverse=True)
            log.info("Scanned %d unique WiFi networks", len(result))
            return result
        except subprocess.TimeoutExpired:
            log.error("nmcli wifi scan timed out")
            return []
        except Exception as e:
            log.error("WiFi scan error: %s", e)
            return []

    # -- AP hotspot management --------------------------------------------------

    def create_hotspot(self, ap_ssid: str, ap_password: str, con_name: str) -> str | None:
        """Create WiFi AP via nmcli hotspot. Returns gateway IP or None on failure."""
        try:
            r = subprocess.run(
                ["nmcli", "device", "wifi", "hotspot", "ifname", "wlan0",
                 "con-name", con_name, "ssid", ap_ssid, "password", ap_password],
                capture_output=True, text=True, timeout=15,
            )
            if r.returncode != 0:
                log.error("Hotspot creation failed: %s", r.stderr.strip())
                return None
            # Extract gateway IP from connection
            r2 = subprocess.run(
                ["nmcli", "-t", "-f", "IP4.ADDRESS", "connection", "show", con_name],
                capture_output=True, text=True, timeout=5,
            )
            for line in r2.stdout.strip().split("\n"):
                if ":" in line:
                    addr = line.split(":", 1)[1].strip()
                    gateway_ip = addr.split("/")[0]  # "10.42.0.1/24" -> "10.42.0.1"
                    log.info("Hotspot created: ssid=%s, gateway=%s", ap_ssid, gateway_ip)
                    return gateway_ip
            # Fallback if IP parsing fails
            log.warning("Could not parse gateway IP, using default 10.42.0.1")
            return "10.42.0.1"
        except subprocess.TimeoutExpired:
            log.error("Hotspot creation timed out")
            return None
        except Exception as e:
            log.error("Hotspot error: %s", e)
            return None

    @staticmethod
    def teardown_hotspot(con_name: str):
        """Remove hotspot connection. Idempotent — safe if already gone."""
        try:
            subprocess.run(
                ["nmcli", "connection", "delete", con_name],
                capture_output=True, timeout=10,
            )
            log.info("Hotspot '%s' removed", con_name)
        except Exception as e:
            log.warning("Hotspot teardown error (may already be gone): %s", e)

    # -- Auto-connect to saved profiles -----------------------------------------

    def auto_connect_saved(self, available: list[dict]) -> str | None:
        """Try connecting to saved profiles that match available networks.

        Args:
            available: [{ssid, signal}] from scan_available_networks().

        Returns:
            Connected SSID on success, None if no match or all failed.
        """
        available_ssids = {n["ssid"] for n in available}
        profiles = self.get_profiles()
        # Try each saved profile that's in range, strongest signal first
        matches = [p for p in profiles if p["ssid"] in available_ssids]
        # Sort by signal strength (match with available list order)
        signal_map = {n["ssid"]: n["signal"] for n in available}
        matches.sort(key=lambda p: signal_map.get(p["ssid"], 0), reverse=True)

        for prof in matches:
            ssid = prof["ssid"]
            log.info("Auto-connect attempt: %s (signal=%d)", ssid, signal_map.get(ssid, 0))
            if self.connect_to_profile(ssid, prof["password"]):
                return ssid
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

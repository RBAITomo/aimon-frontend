"""Captive portal HTTP server: serves WiFi credentials form on local AP.

Lightweight server using stdlib http.server. Serves a mobile-friendly
HTML form for entering WiFi credentials. Runs in a daemon thread,
stoppable from another thread via stop().
"""

import html
import logging
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

log = logging.getLogger(__name__)


def _build_html(ssid_list: list[dict]) -> str:
    """Build self-contained HTML form with inline CSS. Vietnamese text."""
    # Build SSID <option> tags from scanned networks
    options = ""
    for net in ssid_list:
        ssid = net.get("ssid", "")
        signal = net.get("signal", 0)
        bars = min(4, max(1, signal // 25))
        label = f"{html.escape(ssid)} {'▰' * bars}{'▱' * (4 - bars)}"
        escaped = html.escape(ssid, quote=True)
        options += f'<option value="{escaped}">{label}</option>\n'

    return f"""<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIMON - Ket noi WiFi</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:system-ui,sans-serif;background:#1a1a2e;color:#e0e0e0;
  padding:20px;min-height:100vh;display:flex;flex-direction:column;align-items:center}}
h1{{color:#00b4d8;font-size:1.4rem;margin-bottom:18px;text-align:center}}
form{{width:100%;max-width:320px}}
label{{display:block;margin-bottom:6px;font-size:0.95rem;color:#b0b0b0}}
select,input[type=text],input[type=password]{{width:100%;padding:10px;
  border:1px solid #444;border-radius:6px;background:#2a2a3e;color:#fff;
  font-size:1rem;margin-bottom:14px}}
.pw-wrap{{position:relative}}
.pw-wrap input{{padding-right:44px}}
.pw-toggle{{position:absolute;right:8px;top:10px;background:none;border:none;
  color:#888;font-size:0.85rem;cursor:pointer}}
.hidden-wrap{{margin-bottom:14px}}
.hidden-wrap label{{display:inline;font-size:0.85rem;color:#888;cursor:pointer}}
.hidden-wrap input[type=checkbox]{{margin-right:6px}}
#manual-ssid{{display:none;margin-top:8px}}
button[type=submit]{{width:100%;padding:12px;background:#00b4d8;color:#fff;
  border:none;border-radius:6px;font-size:1.1rem;cursor:pointer;font-weight:bold}}
button[type=submit]:active{{background:#0096c7}}
.footer{{margin-top:24px;font-size:0.75rem;color:#555;text-align:center}}
</style>
</head>
<body>
<h1>AIMON - Ket noi WiFi</h1>
<form method="POST" action="/connect" onsubmit="return validate()">
  <label for="ssid-select">Chon mang WiFi:</label>
  <select id="ssid-select" name="ssid">
    {options}
  </select>
  <div class="hidden-wrap">
    <label><input type="checkbox" id="hidden-chk" onchange="toggleHidden()">Mang an (nhap ten)</label>
    <input type="text" id="manual-ssid" name="manual_ssid" placeholder="Ten WiFi">
  </div>
  <label for="password">Mat khau:</label>
  <div class="pw-wrap">
    <input type="password" id="password" name="password" placeholder="Nhap mat khau">
    <button type="button" class="pw-toggle" onclick="togglePw()">Hien</button>
  </div>
  <button type="submit">Ket noi WiFi</button>
</form>
<div class="footer">AIMON &copy; 2026</div>
<script>
function togglePw(){{
  var p=document.getElementById('password');
  var b=document.querySelector('.pw-toggle');
  if(p.type==='password'){{p.type='text';b.textContent='An'}}
  else{{p.type='password';b.textContent='Hien'}}
}}
function toggleHidden(){{
  var c=document.getElementById('hidden-chk');
  var m=document.getElementById('manual-ssid');
  var s=document.getElementById('ssid-select');
  m.style.display=c.checked?'block':'none';
  s.style.display=c.checked?'none':'block';
}}
function validate(){{
  var c=document.getElementById('hidden-chk');
  var ssid=c.checked?document.getElementById('manual-ssid').value
    :document.getElementById('ssid-select').value;
  if(!ssid){{alert('Vui long chon hoac nhap ten WiFi');return false}}
  return true;
}}
</script>
</body>
</html>"""


_CONNECTING_HTML = """<!DOCTYPE html>
<html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AIMON - Dang ket noi</title>
<style>
body{font-family:system-ui,sans-serif;background:#1a1a2e;color:#e0e0e0;
  display:flex;justify-content:center;align-items:center;min-height:100vh;
  text-align:center;padding:20px}
h2{color:#00b4d8;margin-bottom:12px}
p{color:#888;font-size:0.9rem}
</style></head><body>
<div><h2>Dang ket noi...</h2>
<p>Thiet bi dang ket noi WiFi.<br>Ban co the dong trang nay.</p></div>
</body></html>"""


class _Handler(BaseHTTPRequestHandler):
    """HTTP request handler for captive portal form."""

    def log_message(self, fmt, *args):
        """Route http.server logs through Python logging."""
        log.debug("portal-http: " + fmt, *args)

    def do_GET(self):
        """Serve WiFi credentials form."""
        html = _build_html(self.server.ssid_list)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode("utf-8"))

    def do_POST(self):
        """Handle credentials submission from form."""
        if self.path != "/connect":
            self.send_error(404)
            return
        # Parse form body (cap at 4KB to prevent OOM on Pi Zero)
        length = min(int(self.headers.get("Content-Length", 0)), 4096)
        body = self.rfile.read(length).decode("utf-8")
        params = urllib.parse.parse_qs(body)

        # Determine SSID: manual input takes priority if provided
        manual = params.get("manual_ssid", [""])[0].strip()
        select = params.get("ssid", [""])[0].strip()
        ssid = manual if manual else select
        password = params.get("password", [""])[0]

        # Send response before triggering callback
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(_CONNECTING_HTML.encode("utf-8"))

        if ssid and self.server.on_credentials:
            log.info("Portal received credentials for SSID: %s", ssid)
            self.server.on_credentials(ssid, password)


class CaptivePortalServer:
    """Manages captive portal HTTP server lifecycle in a daemon thread."""

    def __init__(self, ssid_list: list[dict], on_credentials: callable):
        """Init server.

        Args:
            ssid_list: [{ssid, signal}] from network scan.
            on_credentials: callback(ssid, password) when user submits form.
        """
        self._ssid_list = ssid_list
        self._on_credentials = on_credentials
        self._server = None
        self._thread = None

    def start(self, port: int = 80):
        """Start HTTP server in daemon thread."""
        self._server = HTTPServer(("0.0.0.0", port), _Handler)
        # Attach data to server instance so handler can access it
        self._server.ssid_list = self._ssid_list
        self._server.on_credentials = self._on_credentials
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        log.info("Captive portal started on port %d", port)

    def stop(self):
        """Shutdown server and join thread. Idempotent."""
        if self._server:
            self._server.shutdown()
            self._server = None
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
            log.info("Captive portal stopped")

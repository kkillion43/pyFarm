"""
Captive portal web app — served only while the Pi is in AP / provisioning mode.

Routes:
  GET  /          — mobile-friendly page with scanned SSID dropdown + password field
  POST /connect   — joins the selected network; on success triggers Tailscale enrolment
                    and starts the greenhouse service
  GET  /success   — confirmation page showing the Pi's Tailscale IP
  GET  /error     — retry page shown when connection fails
"""
import logging
import shutil
import subprocess
import time
from typing import Callable, Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from config_loader import cfg

logger = logging.getLogger(__name__)

app = FastAPI(docs_url=None, redoc_url=None)

_stop_hotspot_callback: Optional[Callable] = None
_tailscale_ip: str = ""


def set_stop_hotspot_callback(fn: Callable) -> None:
    global _stop_hotspot_callback
    _stop_hotspot_callback = fn


# ---------------------------------------------------------------------------
# HTML helpers
# ---------------------------------------------------------------------------

_BASE_STYLE = """
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body { font-family: sans-serif; max-width: 480px; margin: 40px auto; padding: 0 16px; }
  h1   { color: #2e7d32; }
  select, input[type=password], button {
    width: 100%; padding: 12px; margin: 8px 0; font-size: 16px;
    border: 1px solid #ccc; border-radius: 6px; box-sizing: border-box;
  }
  button { background: #2e7d32; color: #fff; border: none; cursor: pointer; }
  button:hover { background: #1b5e20; }
  .note { color: #666; font-size: 13px; }
</style>
"""


def _scan_ssids() -> list:
    result = subprocess.run(
        ["nmcli", "-t", "-f", "SSID", "device", "wifi", "list"],
        capture_output=True, text=True,
    )
    seen = set()
    ssids = []
    for line in result.stdout.splitlines():
        ssid = line.strip()
        if ssid and ssid not in seen:
            seen.add(ssid)
            ssids.append(ssid)
    return ssids


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
def index():
    ssids = _scan_ssids()
    options = "".join(f"<option value='{s}'>{s}</option>" for s in ssids)
    if not options:
        options = "<option value=''>No networks found — refresh to retry</option>"

    html = f"""<!DOCTYPE html>
<html>
<head><title>Greenhouse Setup</title>{_BASE_STYLE}</head>
<body>
  <h1>🌱 Greenhouse Setup</h1>
  <p>Connect your Pi to your home WiFi network.</p>
  <form method="post" action="/connect">
    <label>WiFi Network</label>
    <select name="ssid" required>{options}</select>
    <label>Password</label>
    <input type="password" name="password" placeholder="Leave blank for open networks">
    <button type="submit">Connect</button>
  </form>
  <p class="note">After connecting, Tailscale will be configured automatically.</p>
</body>
</html>"""
    return HTMLResponse(html)


@app.post("/connect", response_class=HTMLResponse)
async def connect(ssid: str = Form(...), password: str = Form(default="")):
    """Attempt to join the selected WiFi network."""
    # Basic input sanitisation — reject shell-special characters
    for char in (";", "&", "|", "`", "$", "(", ")", "<", ">", "\n", "\r"):
        if char in ssid or char in password:
            return RedirectResponse("/error?reason=invalid_input", status_code=303)

    logger.info("Attempting to join SSID: '%s'", ssid)

    cmd = ["nmcli", "device", "wifi", "connect", ssid]
    if password:
        cmd += ["password", password]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    if result.returncode != 0:
        logger.warning("WiFi connect failed: %s", result.stderr.strip())
        return RedirectResponse(
            f"/error?reason={result.stderr.strip()[:80]}", status_code=303
        )

    logger.info("Joined '%s' successfully", ssid)

    # Stop the hotspot
    if _stop_hotspot_callback:
        _stop_hotspot_callback()

    # Enrol with Tailscale
    ts_ip = _enrol_tailscale()

    # Start the greenhouse service
    subprocess.run(["systemctl", "start", "greenhouse"], capture_output=True)

    return RedirectResponse(f"/success?ip={ts_ip}", status_code=303)


@app.get("/success", response_class=HTMLResponse)
def success(ip: str = ""):
    access_line = (
        f"<p>Your greenhouse dashboard is available at:<br>"
        f"<strong>http://{ip}:8000/docs</strong> (FastAPI)<br>"
        f"<strong>http://{ip}:1880</strong> (Node-RED)</p>"
        if ip else
        "<p>Install Tailscale on your device to find your Pi's address.</p>"
    )
    html = f"""<!DOCTYPE html>
<html>
<head><title>Connected!</title>{_BASE_STYLE}</head>
<body>
  <h1>✅ Connected!</h1>
  <p>Your Pi has joined the network.</p>
  {access_line}
  <p class="note">You can disconnect from <strong>Greenhouse-Setup</strong> and rejoin your home WiFi.</p>
</body>
</html>"""
    return HTMLResponse(html)


@app.get("/error", response_class=HTMLResponse)
def error(reason: str = "Unknown error"):
    html = f"""<!DOCTYPE html>
<html>
<head><title>Connection Failed</title>{_BASE_STYLE}</head>
<body>
  <h1>❌ Connection Failed</h1>
  <p>{reason}</p>
  <a href="/"><button>Try Again</button></a>
</body>
</html>"""
    return HTMLResponse(html)


# ---------------------------------------------------------------------------
# Tailscale enrolment
# ---------------------------------------------------------------------------

def _enrol_tailscale() -> str:
    """
    Install Tailscale if absent, enrol with the pre-generated auth key,
    and return the assigned Tailscale IP.
    """
    ts_cfg = cfg.get("tailscale", {})
    auth_key = ts_cfg.get("auth_key", "")
    hostname = ts_cfg.get("hostname", "greenhouse-pi")

    if not auth_key or auth_key == "tskey-auth-REPLACE_ME":
        logger.warning("Tailscale auth_key not configured — skipping enrolment")
        return ""

    if not shutil.which("tailscale"):
        logger.info("Installing Tailscale…")
        subprocess.run(
            "curl -fsSL https://tailscale.com/install.sh | sh",
            shell=True, check=True,
        )

    logger.info("Enrolling with Tailscale (hostname=%s)", hostname)
    subprocess.run(
        [
            "tailscale", "up",
            f"--authkey={auth_key}",
            f"--hostname={hostname}",
            "--accept-routes",
        ],
        capture_output=True,
    )

    # Give Tailscale a moment to get an IP
    time.sleep(5)
    result = subprocess.run(
        ["tailscale", "ip", "-4"], capture_output=True, text=True,
    )
    ip = result.stdout.strip()
    logger.info("Tailscale IP: %s", ip)
    return ip

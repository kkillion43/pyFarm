"""
WiFi provisioning — runs at boot as a systemd oneshot service.

Checks if the Pi has internet connectivity via NetworkManager.
  - Connected → exits cleanly (greenhouse.service starts normally)
  - Not connected → starts an open WiFi hotspot and launches the
    captive portal web app so the user can configure WiFi from
    their phone.
"""
import logging
import subprocess
import sys
import time

import uvicorn

from config_loader import cfg

logging.basicConfig(
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

AP_SSID = cfg["wifi"]["ap_ssid"]
PORTAL_PORT = cfg["wifi"].get("portal_port", 80)
CONNECTIVITY_CHECK_RETRIES = 3
CONNECTIVITY_CHECK_DELAY = 5  # seconds between retries


def is_connected() -> bool:
    """Return True if NetworkManager reports full internet connectivity."""
    for _ in range(CONNECTIVITY_CHECK_RETRIES):
        result = subprocess.run(
            ["nmcli", "-t", "-f", "CONNECTIVITY", "general", "status"],
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip() == "full":
            return True
        time.sleep(CONNECTIVITY_CHECK_DELAY)
    return False


def start_hotspot() -> None:
    """Create an open WiFi hotspot named AP_SSID using NetworkManager."""
    logger.info("Starting hotspot '%s'", AP_SSID)
    result = subprocess.run(
        [
            "nmcli", "device", "wifi", "hotspot",
            "ifname", "wlan0",
            "ssid", AP_SSID,
            "band", "bg",
        ],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        logger.error("Failed to start hotspot: %s", result.stderr.strip())
        sys.exit(1)
    logger.info("Hotspot '%s' is live", AP_SSID)


def stop_hotspot() -> None:
    """Disconnect the hotspot connection profile."""
    subprocess.run(
        ["nmcli", "connection", "down", "Hotspot"],
        capture_output=True,
    )
    logger.info("Hotspot stopped")


def main() -> None:
    if is_connected():
        logger.info("Network connectivity confirmed — provisioning not required")
        sys.exit(0)

    logger.info("No network connectivity detected — entering provisioning mode")
    start_hotspot()

    # Import here so portal.py is only loaded when needed
    from wifi.portal import app as portal_app, set_stop_hotspot_callback

    set_stop_hotspot_callback(stop_hotspot)

    logger.info("Captive portal starting on port %d", PORTAL_PORT)
    uvicorn.run(portal_app, host="0.0.0.0", port=PORTAL_PORT, log_level="warning")


if __name__ == "__main__":
    main()

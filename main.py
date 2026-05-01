"""
Greenhouse Pi — main entry point.

Starts three concurrent services:
  1. WateringAutomation  — background threads reading sensors + controlling pump
  2. FastAPI / uvicorn   — HTTP + WebSocket API server
  3. (Tailscale is a system service — managed separately)

Run with:
    cd /home/pi/greenhouse
    venv/bin/python main.py
"""
import logging
import signal
import sys

import uvicorn

from config_loader import cfg
from logging_config import setup_logging
from database.db import init_db
from automation.watering import WateringAutomation
from api.main import app, set_relay_controller

setup_logging()
logger = logging.getLogger(__name__)

_MOCK = cfg.get("mock_mode", False)

if _MOCK:
    from sensors.mock_sensors import MockSoilSensor as SoilSensor, MockDHTSensor as DHTSensor
    from controllers.mock_relay import MockRelayController as RelayController
    logger.warning("*** MOCK MODE — no real hardware will be used ***")
else:
    from sensors.soil_sensor import SoilSensor
    from sensors.dht_sensor import DHTSensor
    from controllers.relay_controller import RelayController


def build_sensors() -> list:
    return [
        SoilSensor(address=s["address"], name=s["name"])
        for s in cfg["sensors"]["soil"]
    ]


def main() -> None:
    logger.info("========== Greenhouse Pi starting ==========")

    init_db()

    dht = DHTSensor()
    relay = RelayController()
    sensors = build_sensors()

    # In mock mode poll every 15 s so the dashboard fills quickly
    if _MOCK:
        from database.db import update_automation_config
        update_automation_config({"poll_interval_seconds": 15})

    automation = WateringAutomation(sensors=sensors, dht=dht, relay=relay)
    automation.start()

    # Wire relay controller into the API layer
    set_relay_controller(relay)

    # Graceful shutdown on SIGTERM / SIGINT
    def _shutdown(sig, _frame):
        logger.info("Shutdown signal received (%s)", signal.Signals(sig).name)
        automation.stop()
        relay.deactivate_all()
        dht.exit()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    api_cfg = cfg["api"]
    logger.info("Starting API server on %s:%d", api_cfg["host"], api_cfg["port"])
    uvicorn.run(
        app,
        host=api_cfg["host"],
        port=api_cfg["port"],
        log_level="warning",    # uvicorn access logs go to uvicorn.access logger
    )


if __name__ == "__main__":
    main()

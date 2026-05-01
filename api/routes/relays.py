"""
Relay control routes — activate, deactivate, pulse, and status.

Relay board positions 1–8
─────────────────────────
  Pos 1  p_pump_1        BCM  5   Pump 1
  Pos 2  p_pump_2        BCM 13   Pump 2
  Pos 3  main_water_pump BCM 20   Main Water Pump
  Pos 4  trashcan        BCM 26   Auto-watering relay
  Pos 5  relay_5         BCM TBD  Expansion (unassigned)
  Pos 6  relay_6         BCM TBD  Expansion (unassigned)
  Pos 7  relay_7         BCM TBD  Expansion (unassigned)
  Pos 8  relay_8         BCM TBD  Expansion (unassigned)
"""
import logging
import threading

from fastapi import APIRouter, HTTPException, Query

from database.db import insert_relay_event

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/relays", tags=["relays"])

# ---------------------------------------------------------------------------
# Relay board manifest — board position, BCM pin, description for each relay.
# Positions 5-8 are expansion slots; set bcm_pin and add to config.yaml when wired.
# ---------------------------------------------------------------------------
RELAY_MANIFEST = {
    "p_pump_1":        {"position": 1, "bcm_pin": 5,    "description": "Pump 1"},
    "p_pump_2":        {"position": 2, "bcm_pin": 13,   "description": "Pump 2"},
    "main_water_pump": {"position": 3, "bcm_pin": 20,   "description": "Main Water Pump"},
    "trashcan":        {"position": 4, "bcm_pin": 26,   "description": "Auto-watering relay"},
    "relay_5":         {"position": 5, "bcm_pin": None, "description": "Expansion (unassigned)"},
    "relay_6":         {"position": 6, "bcm_pin": None, "description": "Expansion (unassigned)"},
    "relay_7":         {"position": 7, "bcm_pin": None, "description": "Expansion (unassigned)"},
    "relay_8":         {"position": 8, "bcm_pin": None, "description": "Expansion (unassigned)"},
}

# Injected by api/main.py at startup
_relay_controller = None


def set_relay_controller(relay) -> None:
    global _relay_controller
    _relay_controller = relay


def _get_relay():
    if _relay_controller is None:
        raise HTTPException(status_code=503, detail="Relay controller not initialised")
    return _relay_controller


@router.get("/manifest", summary="Relay board manifest")
def get_relay_manifest():
    """
    Return the full relay board map — all 8 positions with name, BCM pin, and description.

    Positions 1–4 are active. Positions 5–8 are expansion slots (bcm_pin = null until wired
    and added to config.yaml).
    """
    return RELAY_MANIFEST


@router.get("", summary="Current relay states")
def get_relay_status():
    """
    Return the current on/off state of all **active** relays (positions 1–4).

    Use `GET /relays/manifest` to see all 8 board positions with BCM pin labels.
    """
    return _get_relay().status()


@router.post("/{name}/on", summary="Turn relay ON")
def relay_on(name: str):
    """
    Turn a relay ON by name.

    | Position | Name              | BCM | Description          |
    |----------|-------------------|-----|----------------------|
    | 1        | p_pump_1          |  5  | Pump 1               |
    | 2        | p_pump_2          | 13  | Pump 2               |
    | 3        | main_water_pump   | 20  | Main Water Pump      |
    | 4        | trashcan          | 26  | Auto-watering relay  |
    """
    relay = _get_relay()
    try:
        relay.activate(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    insert_relay_event(name, "on", triggered_by="api")
    return {"relay": name, "state": "on"}


@router.post("/{name}/off", summary="Turn relay OFF")
def relay_off(name: str):
    """
    Turn a relay OFF by name.

    | Position | Name              | BCM | Description          |
    |----------|-------------------|-----|----------------------|
    | 1        | p_pump_1          |  5  | Pump 1               |
    | 2        | p_pump_2          | 13  | Pump 2               |
    | 3        | main_water_pump   | 20  | Main Water Pump      |
    | 4        | trashcan          | 26  | Auto-watering relay  |
    """
    relay = _get_relay()
    try:
        relay.deactivate(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    insert_relay_event(name, "off", triggered_by="api")
    return {"relay": name, "state": "off"}


@router.post("/{name}/pulse", summary="Pulse relay ON then OFF")
def relay_pulse(
    name: str,
    duration: float = Query(default=15.0, ge=1.0, le=300.0, description="Pulse duration in seconds"),
):
    """
    Turn a relay ON for `duration` seconds, then OFF automatically.
    Returns immediately — the pulse runs in a background thread.

    | Position | Name              | BCM | Description          |
    |----------|-------------------|-----|----------------------|
    | 1        | p_pump_1          |  5  | Pump 1               |
    | 2        | p_pump_2          | 13  | Pump 2               |
    | 3        | main_water_pump   | 20  | Main Water Pump      |
    | 4        | trashcan          | 26  | Auto-watering relay  |
    """
    relay = _get_relay()
    try:
        relay._resolve(name)  # validate name before spawning thread
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    def _run():
        relay.pulse(name, duration=duration)

    threading.Thread(target=_run, daemon=True).start()
    insert_relay_event(name, "pulse", duration_seconds=duration, triggered_by="api")
    return {"relay": name, "state": "pulse", "duration_seconds": duration}

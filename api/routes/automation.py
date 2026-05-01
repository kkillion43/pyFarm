"""
Automation config and override routes.
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import Optional

from database.db import get_automation_config, update_automation_config

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/automation", tags=["automation"])


class AutomationConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    moisture_threshold: Optional[float] = Field(default=None, ge=0, le=100,
        description="Lower band — pump turns ON when moisture drops at or below this value")
    moisture_target: Optional[float] = Field(default=None, ge=0, le=100,
        description="Upper band — pump stays OFF until moisture rises above this value (hysteresis)")
    oscillate_readings: Optional[int] = Field(default=None, ge=1, le=50)
    water_duration_seconds: Optional[float] = Field(default=None, ge=1, le=300)
    poll_interval_seconds: Optional[int] = Field(default=None, ge=30, le=3600)


class OverrideRequest(BaseModel):
    active: bool
    note: Optional[str] = None


def _cfg_to_dict(row) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


@router.get("/config")
def get_config():
    """Return the current automation configuration."""
    return _cfg_to_dict(get_automation_config())


@router.put("/config")
def update_config(body: AutomationConfigUpdate):
    """Update automation thresholds and intervals."""
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields provided to update")
    row = update_automation_config(updates)
    return _cfg_to_dict(row)


@router.post("/override")
def set_override(body: OverrideRequest):
    """
    Enable or disable manual override.
    When active=True the automation engine will skip watering decisions
    and the API (or Node-RED) has full relay control.
    """
    updates = {"manual_override": body.active}
    if body.note is not None:
        updates["override_note"] = body.note
    row = update_automation_config(updates)
    state = "enabled" if body.active else "disabled"
    logger.info("Manual override %s. Note: %s", state, body.note)
    return {"manual_override": row.manual_override, "note": row.override_note}

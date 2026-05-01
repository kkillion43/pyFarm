"""
Sensor history and latest-reading routes.
"""
import datetime
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from database.db import get_latest_reading, get_reading_history

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/sensors", tags=["sensors"])


def _row_to_dict(row) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}


@router.get("/{sensor_id}/latest")
def latest_reading(sensor_id: int):
    """Return the most recent reading for a sensor."""
    row = get_latest_reading(sensor_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"No readings found for sensor {sensor_id}")
    return _row_to_dict(row)


@router.get("/{sensor_id}/history")
def reading_history(
    sensor_id: int,
    start: Optional[datetime.datetime] = Query(default=None),
    end: Optional[datetime.datetime] = Query(default=None),
    limit: int = Query(default=500, le=5000),
):
    """
    Return historical readings for a sensor.
    Optionally filter by ISO-8601 start / end datetimes.
    """
    rows = get_reading_history(sensor_id, start=start, end=end, limit=limit)
    return [_row_to_dict(r) for r in rows]

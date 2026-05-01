"""
Database engine, session factory, and typed CRUD helpers.
Call init_db() once at startup to create tables.
"""
import datetime
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from config_loader import cfg
from database.models import AutomationConfig, Base, RelayEvent, SensorReading

logger = logging.getLogger(__name__)

_db_path = Path(cfg["database"]["path"])
_db_path.parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(
    f"sqlite:///{_db_path}",
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    """Create all tables and seed a default AutomationConfig row if absent."""
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as session:
        if not session.get(AutomationConfig, 1):
            auto_cfg = cfg["automation"]
            session.add(
                AutomationConfig(
                    id=1,
                    enabled=auto_cfg["enabled"],
                    moisture_threshold=auto_cfg["moisture_threshold"],
                    moisture_target=auto_cfg["moisture_target"],
                    oscillate_readings=auto_cfg["oscillate_readings"],
                    water_duration_seconds=auto_cfg["water_duration_seconds"],
                    poll_interval_seconds=auto_cfg["poll_interval_seconds"],
                )
            )
            session.commit()
    logger.info("Database initialised at %s", _db_path)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context-manager session — always commits or rolls back cleanly."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# SensorReading helpers
# ---------------------------------------------------------------------------

def insert_reading(reading: dict) -> SensorReading:
    """Persist a sensor reading dict and return the ORM row."""
    row = SensorReading(**reading)
    with get_session() as session:
        session.add(row)
        session.flush()
        session.expunge(row)
    return row


def get_latest_reading(sensor_id: int) -> Optional[SensorReading]:
    with get_session() as session:
        row = (
            session.query(SensorReading)
            .filter(SensorReading.sensor_id == sensor_id)
            .order_by(SensorReading.timestamp.desc())
            .first()
        )
        if row:
            session.expunge(row)
        return row


def get_reading_history(
    sensor_id: int,
    start: Optional[datetime.datetime] = None,
    end: Optional[datetime.datetime] = None,
    limit: int = 500,
) -> List[SensorReading]:
    with get_session() as session:
        q = session.query(SensorReading).filter(SensorReading.sensor_id == sensor_id)
        if start:
            q = q.filter(SensorReading.timestamp >= start)
        if end:
            q = q.filter(SensorReading.timestamp <= end)
        rows = q.order_by(SensorReading.timestamp.desc()).limit(limit).all()
        for r in rows:
            session.expunge(r)
        return rows


# ---------------------------------------------------------------------------
# RelayEvent helpers
# ---------------------------------------------------------------------------

def insert_relay_event(
    relay_name: str,
    action: str,
    duration_seconds: Optional[float] = None,
    triggered_by: str = "automation",
) -> None:
    with get_session() as session:
        session.add(
            RelayEvent(
                relay_name=relay_name,
                action=action,
                duration_seconds=duration_seconds,
                triggered_by=triggered_by,
            )
        )


# ---------------------------------------------------------------------------
# AutomationConfig helpers
# ---------------------------------------------------------------------------

def get_automation_config() -> AutomationConfig:
    with get_session() as session:
        row = session.get(AutomationConfig, 1)
        session.expunge(row)
        return row


def update_automation_config(updates: dict) -> AutomationConfig:
    with get_session() as session:
        row = session.get(AutomationConfig, 1)
        for key, value in updates.items():
            if hasattr(row, key):
                setattr(row, key, value)
        session.flush()
        session.expunge(row)
        return row

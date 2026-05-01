"""
SQLAlchemy ORM models for the greenhouse database.
Three tables:
  - SensorReading : all soil + air readings per poll cycle
  - RelayEvent    : every relay activation/deactivation recorded
  - AutomationConfig : single-row config for the watering automation engine
"""
import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class SensorReading(Base):
    __tablename__ = "sensor_readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    sensor_id = Column(Integer, nullable=False, index=True)
    sensor_name = Column(String(64), nullable=True)

    # Soil readings (RS-485)
    soil_temp_f = Column(Float, nullable=True)
    soil_temp_c = Column(Float, nullable=True)
    ph = Column(Float, nullable=True)
    electrical_conductivity = Column(Float, nullable=True)
    moisture = Column(Float, nullable=True)
    nitrogen = Column(Float, nullable=True)
    phosphorus = Column(Float, nullable=True)
    potassium = Column(Float, nullable=True)

    # Air readings (DHT)
    air_temp_f = Column(Float, nullable=True)
    air_temp_c = Column(Float, nullable=True)
    humidity = Column(Float, nullable=True)
    vpd = Column(Float, nullable=True)

    # Automation state snapshot
    water_count = Column(Integer, default=0)


class RelayEvent(Base):
    __tablename__ = "relay_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False, index=True)
    relay_name = Column(String(64), nullable=False)
    action = Column(String(16), nullable=False)   # "on" | "off" | "pulse"
    duration_seconds = Column(Float, nullable=True)
    triggered_by = Column(String(32), default="automation")  # "automation" | "api"


class AutomationConfig(Base):
    __tablename__ = "automation_config"

    id = Column(Integer, primary_key=True, default=1)
    enabled = Column(Boolean, default=True)
    moisture_threshold = Column(Float, default=12.0)   # Lower band — pump ON when moisture <= this
    moisture_target = Column(Float, default=18.0)      # Upper band — pump stays OFF until moisture > this
    oscillate_readings = Column(Integer, default=6)
    water_duration_seconds = Column(Float, default=15.0)
    poll_interval_seconds = Column(Integer, default=300)
    manual_override = Column(Boolean, default=False)  # True = API has taken control
    override_note = Column(Text, nullable=True)        # Optional reason from API caller

"""
SoilSensor — reads pH, EC, moisture, NPK, and temperature from a
Modbus RS-485 soil sensor via minimalmodbus.

Supports multiple sensor addresses on the same serial bus.
Each sensor instance holds its own minimalmodbus.Instrument object.
"""
import logging
import time
from typing import Optional

import minimalmodbus as mm

from config_loader import cfg

logger = logging.getLogger(__name__)

_REGISTER_MAP = {
    "ph":                     0x06,
    "soil_moist":             0x12,
    "nitrogen":               0x1E,
    "potassium":              0x20,
    "phosphorus":             0x1F,
    "electrical_conductivity": 0x15,
    "temp":                   0x13,
}


class SoilSensor:
    """
    RS-485 Modbus soil sensor interface.

    Args:
        address: Modbus address of the sensor on the RS-485 bus (1–247).
        name: Human-readable label stored alongside readings.

    Example:
        sensor = SoilSensor(address=1, name="bed_1")
        data = sensor.read_all()
    """

    def __init__(self, address: int, name: str = "") -> None:
        sensor_cfg = cfg["sensors"]
        self.address = address
        self.name = name or f"sensor_{address}"

        self._instr = mm.Instrument(
            sensor_cfg["serial_port"],
            address,
            debug=False,
        )
        self._instr.serial.baudrate = sensor_cfg["baud_rate"]
        self._instr.serial.timeout = 1
        logger.info("SoilSensor '%s' initialised on address %d", self.name, address)

    # ------------------------------------------------------------------
    # Individual reads
    # ------------------------------------------------------------------

    def read_ph(self) -> Optional[float]:
        """Soil pH (unitless)."""
        return self._safe_read("ph", decimals=2)

    def read_moisture(self) -> Optional[float]:
        """Soil moisture in %."""
        return self._safe_read("soil_moist", decimals=1)

    def read_ec(self, as_ppm: bool = True) -> Optional[float]:
        """
        Electrical conductivity.
        Returns ppm by default (divide raw µS/cm by 1.58).
        Set as_ppm=False for raw µS/cm.
        """
        raw = self._safe_read("electrical_conductivity")
        if raw is None:
            return None
        return round(raw / 1.58, 2) if as_ppm else raw

    def read_temp(self, fahrenheit: bool = True) -> Optional[float]:
        """Soil temperature. Fahrenheit by default."""
        raw = self._safe_read("temp", decimals=1)
        if raw is None:
            return None
        if fahrenheit:
            return round(raw * 1.8 + 32, 2)
        return raw

    def read_npk(self) -> dict:
        """Returns nitrogen, phosphorus, potassium in mg/kg."""
        return {
            "nitrogen":   self._safe_read("nitrogen"),
            "phosphorus": self._safe_read("phosphorus"),
            "potassium":  self._safe_read("potassium"),
        }

    def read_all(self) -> dict:
        """
        Returns a flat dict of all readings suitable for inserting
        directly into a SensorReading row.
        """
        npk = self.read_npk()
        soil_temp_c = self._safe_read("temp", decimals=1)  # read once, convert both units
        soil_temp_f = round(soil_temp_c * 1.8 + 32, 2) if soil_temp_c is not None else None
        return {
            "sensor_id":              self.address,
            "sensor_name":            self.name,
            "soil_temp_f":            soil_temp_f,
            "soil_temp_c":            soil_temp_c,
            "ph":                     self.read_ph(),
            "electrical_conductivity": self.read_ec(as_ppm=True),
            "moisture":               self.read_moisture(),
            "nitrogen":               npk["nitrogen"],
            "phosphorus":             npk["phosphorus"],
            "potassium":              npk["potassium"],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _safe_read(self, register_key: str, decimals: int = 0) -> Optional[float]:
        """Read a single register, returning None on any communication error."""
        reg = _REGISTER_MAP[register_key]
        try:
            value = self._instr.read_register(reg, decimals)
            return value
        except mm.ModbusException as exc:
            logger.warning(
                "Modbus error reading '%s' from sensor %d: %s",
                register_key, self.address, exc,
            )
        except Exception as exc:
            logger.error(
                "Unexpected error reading '%s' from sensor %d: %s",
                register_key, self.address, exc,
            )
        return None

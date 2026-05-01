"""
DHTSensor — reads air temperature and relative humidity from a
DHT11 or DHT22 sensor using the adafruit-circuitpython-dht library.

VPD calculation is a pure function so it can be tested independently.
"""
import logging
import math
import threading
from typing import Optional, Tuple

import board
import adafruit_dht

from config_loader import cfg

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pure VPD calculation — no hardware dependency
# ---------------------------------------------------------------------------

def calculate_vpd(air_temp_c: float, humidity_pct: float, leaf_offset_c: float = 2.5) -> float:
    """
    Calculate Vapour Pressure Deficit in kPa.

    Uses the Magnus formula for saturation vapour pressure.
    Leaf temperature is estimated as air_temp_c - leaf_offset_c
    (typically 1–3 °C cooler than ambient).

    Args:
        air_temp_c:    Air temperature in Celsius.
        humidity_pct:  Relative humidity as a percentage (0–100).
        leaf_offset_c: Degrees C subtracted from air temp to estimate leaf temp.

    Returns:
        VPD in kPa, rounded to 3 decimal places.
    """
    leaf_temp = air_temp_c - leaf_offset_c
    svp = 610.78 * math.exp((17.2694 * leaf_temp) / (leaf_temp + 238.3)) / 1000
    return round(svp * (1 - humidity_pct / 100), 3)


# ---------------------------------------------------------------------------
# Sensor class
# ---------------------------------------------------------------------------

_BOARD_PIN_MAP = {
    4:  board.D4,
    17: board.D17,
    18: board.D18,
    24: board.D24,
    25: board.D25,
    27: board.D27,
}


class DHTSensor:
    """
    DHT11 / DHT22 air temperature and humidity sensor.

    Args:
        pin:  BCM GPIO pin number the data line is connected to.
        model: "DHT11" or "DHT22".

    Example:
        dht = DHTSensor(pin=24, model="DHT11")
        reading = dht.read()
    """

    def __init__(self, pin: Optional[int] = None, model: Optional[str] = None) -> None:
        dht_cfg = cfg["sensors"]["dht"]
        self._pin_num = pin or dht_cfg["pin"]
        self._model = (model or dht_cfg["model"]).upper()
        self._leaf_offset = dht_cfg.get("leaf_offset_c", 2.5)

        board_pin = _BOARD_PIN_MAP.get(self._pin_num)
        if board_pin is None:
            raise ValueError(
                f"BCM pin {self._pin_num} is not mapped. "
                f"Add it to _BOARD_PIN_MAP in dht_sensor.py."
            )

        if self._model == "DHT22":
            self._device = adafruit_dht.DHT22(board_pin)
        else:
            self._device = adafruit_dht.DHT11(board_pin)

        logger.info("DHTSensor initialised: %s on BCM pin %d", self._model, self._pin_num)

    def read(self) -> Optional[dict]:
        """
        Read temperature and humidity from the sensor.

        Returns a dict with keys:
            air_temp_c, air_temp_f, humidity, vpd
        Returns None if the sensor fails or times out.
        """
        result = [None]
        error  = [None]

        def _read():
            try:
                temp_c   = self._device.temperature
                humidity = self._device.humidity
                result[0] = (temp_c, humidity)
            except RuntimeError as exc:
                error[0] = exc
            except Exception as exc:
                error[0] = exc

        t = threading.Thread(target=_read, daemon=True)
        t.start()
        t.join(timeout=5)   # 5-second hard cap on hardware read

        if t.is_alive():
            # Hardware read hung — reinitialise device so next call starts fresh
            logger.warning("DHT read timed out — reinitialising sensor")
            try:
                self._device.exit()
            except Exception:
                pass
            board_pin = _BOARD_PIN_MAP[self._pin_num]
            if self._model == "DHT22":
                self._device = adafruit_dht.DHT22(board_pin)
            else:
                self._device = adafruit_dht.DHT11(board_pin)
            return None

        if error[0] is not None:
            if isinstance(error[0], RuntimeError):
                logger.warning("DHT read failed (transient): %s", error[0])
            else:
                logger.error("DHT read unexpected error: %s", error[0])
            return None

        temp_c, humidity = result[0]

        if temp_c is None or humidity is None:
            logger.warning("DHT sensor returned None values")
            return None

        temp_f = round(temp_c * 9 / 5 + 32, 2)
        vpd = calculate_vpd(temp_c, humidity, self._leaf_offset)

        return {
            "air_temp_c": round(temp_c, 1),
            "air_temp_f": temp_f,
            "humidity":   round(humidity, 1),
            "vpd":        vpd,
        }

    def exit(self) -> None:
        """Release the hardware resource. Call on shutdown."""
        try:
            self._device.exit()
        except Exception:
            pass

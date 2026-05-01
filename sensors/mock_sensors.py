"""
Mock sensor classes for testing without physical hardware.
Returns realistic, slowly-varying values so the dashboard looks live.
"""
import datetime
import math
import random


def _wave(base: float, amplitude: float, period_s: float = 3600) -> float:
    """Sine wave centred on base — simulates gradual environmental drift."""
    t = datetime.datetime.utcnow().timestamp()
    return round(base + amplitude * math.sin(2 * math.pi * t / period_s), 2)


class MockSoilSensor:
    def __init__(self, address: int = 1, name: str = "mock_bed_1") -> None:
        self.address = address
        self.name = name

    def read_ph(self):        return _wave(6.8, 0.3)
    def read_moisture(self):  return _wave(18.0, 5.0)
    def read_ec(self, **_):   return _wave(420.0, 30.0)
    def read_temp(self, fahrenheit=True):
        c = _wave(22.0, 3.0)
        return round(c * 1.8 + 32, 2) if fahrenheit else c
    def read_npk(self):
        return {
            "nitrogen":   _wave(35, 5),
            "phosphorus": _wave(22, 3),
            "potassium":  _wave(28, 4),
        }

    def read_all(self) -> dict:
        npk = self.read_npk()
        return {
            "sensor_id":               self.address,
            "sensor_name":             self.name,
            "soil_temp_f":             self.read_temp(fahrenheit=True),
            "soil_temp_c":             self.read_temp(fahrenheit=False),
            "ph":                      self.read_ph(),
            "electrical_conductivity": self.read_ec(),
            "moisture":                self.read_moisture(),
            "nitrogen":                npk["nitrogen"],
            "phosphorus":              npk["phosphorus"],
            "potassium":               npk["potassium"],
        }


class MockDHTSensor:
    def __init__(self, **_) -> None:
        pass

    def read(self) -> dict:
        temp_c = _wave(24.0, 4.0)
        humidity = _wave(58.0, 10.0)
        from sensors.dht_sensor import calculate_vpd
        return {
            "air_temp_c": round(temp_c, 1),
            "air_temp_f": round(temp_c * 1.8 + 32, 2),
            "humidity":   round(humidity, 1),
            "vpd":        calculate_vpd(temp_c, humidity),
        }

    def exit(self) -> None:
        pass

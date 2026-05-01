"""
Mock relay controller for testing without physical GPIO.
"""
import logging
import threading
import time
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class MockRelayController:
    def __init__(self, pin_map: Optional[Dict[str, int]] = None) -> None:
        from config_loader import cfg
        self._pin_map = pin_map or cfg["relays"]
        self._state = {name: False for name in self._pin_map}
        self._lock = threading.Lock()
        logger.info("MockRelayController ready (no GPIO) with relays: %s", list(self._pin_map))

    def activate(self, name: str) -> None:
        self._set(name, True)

    def deactivate(self, name: str) -> None:
        self._set(name, False)

    def pulse(self, name: str, duration: float) -> None:
        self._resolve(name)
        with self._lock:
            self._state[name] = True
        logger.info("MockRelay '%s' ON (pulse %.1fs)", name, duration)
        time.sleep(min(duration, 2))          # cap sleep to 2s in mock mode
        with self._lock:
            self._state[name] = False
        logger.info("MockRelay '%s' OFF (pulse complete)", name)

    def status(self) -> Dict[str, bool]:
        with self._lock:
            return dict(self._state)

    def deactivate_all(self) -> None:
        for name in self._pin_map:
            self._set(name, False)

    def __enter__(self): return self
    def __exit__(self, *_): self.deactivate_all()

    def _set(self, name: str, on: bool) -> None:
        self._resolve(name)
        with self._lock:
            self._state[name] = on
        logger.info("MockRelay '%s' -> %s", name, "ON" if on else "OFF")

    def _resolve(self, name: str) -> int:
        if name not in self._pin_map:
            raise KeyError(f"Unknown relay '{name}'. Available: {list(self._pin_map)}")
        return self._pin_map[name]

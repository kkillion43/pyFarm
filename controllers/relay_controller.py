"""
RelayController — manages all GPIO relay outputs.

GPIO is initialised once at construction. Supports individual activate /
deactivate, timed pulse, and full status reporting. Implements the
context manager protocol for clean GPIO cleanup on shutdown.

Usage:
    from config_loader import cfg
    relay = RelayController(cfg["relays"])
    relay.activate("main_water_pump")
    relay.pulse("p_pump_1", duration=15)
    relay.deactivate("main_water_pump")
"""
import logging
import threading
import time
from typing import Dict, Optional

import RPi.GPIO as GPIO

from config_loader import cfg

logger = logging.getLogger(__name__)


class RelayController:
    """
    Controls a bank of GPIO-driven relays.

    Args:
        pin_map: Dict mapping relay name → BCM pin number.
                 Defaults to cfg["relays"] if not provided.

    Relay logic:
        Most relay boards are active-LOW: GPIO.LOW = relay ON.
        Set _active_low = False in subclass if your board is active-HIGH.
    """

    _active_low: bool = True  # Set False for active-HIGH relay boards

    def __init__(self, pin_map: Optional[Dict[str, int]] = None) -> None:
        self._pin_map: Dict[str, int] = pin_map or cfg["relays"]
        self._state: Dict[str, bool] = {name: False for name in self._pin_map}
        self._lock = threading.Lock()

        GPIO.setmode(GPIO.BCM)
        GPIO.setwarnings(False)

        for name, pin in self._pin_map.items():
            GPIO.setup(pin, GPIO.OUT)
            # Ensure all relays start in the OFF state
            GPIO.output(pin, GPIO.LOW if self._active_low else GPIO.HIGH)
            logger.debug("Relay '%s' initialised on BCM pin %d (OFF)", name, pin)

        logger.info("RelayController ready with %d relay(s): %s",
                    len(self._pin_map), list(self._pin_map))

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def activate(self, name: str) -> None:
        """Turn a relay ON."""
        self._set(name, on=True)

    def deactivate(self, name: str) -> None:
        """Turn a relay OFF."""
        self._set(name, on=False)

    def pulse(self, name: str, duration: float) -> None:
        """
        Turn a relay ON for `duration` seconds, then OFF.
        Blocks the calling thread for the duration.
        """
        pin = self._resolve(name)
        with self._lock:
            self._gpio_on(pin)
            self._state[name] = True
        logger.info("Relay '%s' ON (pulse %.1fs)", name, duration)

        time.sleep(duration)

        with self._lock:
            self._gpio_off(pin)
            self._state[name] = False
        logger.info("Relay '%s' OFF (pulse complete)", name)

    def status(self) -> Dict[str, bool]:
        """Returns a snapshot dict of relay_name → is_on."""
        with self._lock:
            return dict(self._state)

    def deactivate_all(self) -> None:
        """Turn every relay OFF — called on shutdown."""
        for name in self._pin_map:
            self._set(name, on=False)
        logger.info("All relays deactivated")

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> "RelayController":
        return self

    def __exit__(self, *_) -> None:
        self.deactivate_all()
        GPIO.cleanup()
        logger.info("GPIO cleaned up")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _set(self, name: str, on: bool) -> None:
        pin = self._resolve(name)
        with self._lock:
            if on:
                self._gpio_on(pin)
            else:
                self._gpio_off(pin)
            self._state[name] = on
        logger.info("Relay '%s' (pin %d) -> %s", name, pin, "ON" if on else "OFF")

    def _gpio_on(self, pin: int) -> None:
        GPIO.output(pin, GPIO.LOW if self._active_low else GPIO.HIGH)

    def _gpio_off(self, pin: int) -> None:
        GPIO.output(pin, GPIO.HIGH if self._active_low else GPIO.LOW)

    def _resolve(self, name: str) -> int:
        if name not in self._pin_map:
            raise KeyError(
                f"Unknown relay '{name}'. "
                f"Available relays: {list(self._pin_map)}"
            )
        return self._pin_map[name]

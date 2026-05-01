"""
WateringAutomation — background thread that periodically reads soil
sensors and triggers the pump if moisture drops below the configured
threshold.

The automation respects a manual_override flag stored in the database.
When override is True the automation loop skips watering decisions so
the API has full control. The loop continues polling and logging data
regardless of the override state.
"""
import datetime
import logging
import threading
import time
from typing import List

from config_loader import cfg
from controllers.relay_controller import RelayController
from database.db import (
    get_automation_config,
    insert_reading,
    insert_relay_event,
)
from sensors.dht_sensor import DHTSensor
from sensors.soil_sensor import SoilSensor

logger = logging.getLogger(__name__)


class WateringAutomation:
    """
    Runs one background thread per sensor that:
      1. Reads all soil + air values on each poll interval
      2. Persists readings to the database
      3. Checks moisture against the configured threshold
         (using an oscillate window to avoid reacting to single noisy reads)
      4. Activates the trashcan pump if watering is needed and
         override is not active

    Args:
        sensors:  List of SoilSensor instances (one per bed).
        dht:      Single DHTSensor shared by all sensors.
        relay:    RelayController instance.
    """

    def __init__(
        self,
        sensors: List[SoilSensor],
        dht: DHTSensor,
        relay: RelayController,
    ) -> None:
        self._sensors = sensors
        self._dht = dht
        self._relay = relay
        self._stop_event = threading.Event()
        self._water_counts = {s.address: 0 for s in sensors}
        self._moisture_history: dict = {s.address: [] for s in sensors}
        # Hysteresis state — True means the pump is in an active watering cycle
        # (moisture dropped below threshold and hasn't recovered above target yet)
        self._watering_active: dict = {s.address: False for s in sensors}
        self._threads: List[threading.Thread] = []

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start one polling thread per sensor."""
        for sensor in self._sensors:
            t = threading.Thread(
                target=self._poll_loop,
                args=(sensor,),
                name=f"automation-{sensor.name}",
                daemon=True,
            )
            t.start()
            self._threads.append(t)
            logger.info("Automation thread started for sensor '%s'", sensor.name)

    def stop(self) -> None:
        """Signal all threads to stop and wait for them to finish."""
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=10)
        logger.info("Automation stopped")

    # ------------------------------------------------------------------
    # Core polling loop
    # ------------------------------------------------------------------

    def _poll_loop(self, sensor: SoilSensor) -> None:
        while not self._stop_event.is_set():
            try:
                self._poll_once(sensor)
            except Exception:
                logger.exception("Unhandled error in automation loop for '%s'", sensor.name)

            auto_cfg = get_automation_config()
            self._stop_event.wait(timeout=auto_cfg.poll_interval_seconds)

    def _poll_once(self, sensor: SoilSensor) -> None:
        auto_cfg = get_automation_config()

        # --- Read sensors ---
        soil_data = sensor.read_all()
        air_data = self._dht.read() or {}

        reading = {
            **soil_data,
            **air_data,
            "timestamp":   datetime.datetime.utcnow(),
            "water_count": self._water_counts[sensor.address],
        }
        insert_reading(reading)
        logger.info(
            "[%s] moisture=%.1f  temp_f=%.1f  humidity=%.1f  vpd=%.3f",
            sensor.name,
            soil_data.get("moisture") or 0,
            air_data.get("air_temp_f") or 0,
            air_data.get("humidity") or 0,
            air_data.get("vpd") or 0,
        )

        # --- Watering decision ---
        if not auto_cfg.enabled:
            return

        if auto_cfg.manual_override:
            logger.debug("[%s] Manual override active — skipping watering check", sensor.name)
            return

        moisture = soil_data.get("moisture")
        if moisture is None:
            logger.warning("[%s] No moisture reading — skipping watering check", sensor.name)
            return

        # Track rolling moisture history for oscillate window
        history = self._moisture_history[sensor.address]
        history.append(moisture)
        if len(history) > auto_cfg.oscillate_readings:
            history.pop(0)

        # Use the oldest reading in the window as the reference point
        ref_moisture = history[0]

        # --- Hysteresis band ---
        # Once moisture drops to/below threshold → start watering cycle (_watering_active = True)
        # Keep watering each poll until moisture rises above moisture_target → end cycle
        currently_watering = self._watering_active[sensor.address]

        if not currently_watering and ref_moisture <= auto_cfg.moisture_threshold:
            logger.info(
                "[%s] Moisture %.1f <= threshold %.1f — starting watering cycle (target: %.1f)",
                sensor.name, ref_moisture, auto_cfg.moisture_threshold, auto_cfg.moisture_target,
            )
            self._watering_active[sensor.address] = True
            currently_watering = True

        if currently_watering:
            if moisture > auto_cfg.moisture_target:
                logger.info(
                    "[%s] Moisture %.1f exceeded target %.1f — watering cycle complete",
                    sensor.name, moisture, auto_cfg.moisture_target,
                )
                self._watering_active[sensor.address] = False
            else:
                logger.debug(
                    "[%s] Watering cycle active — moisture %.1f, target %.1f",
                    sensor.name, moisture, auto_cfg.moisture_target,
                )
                self._water(sensor, auto_cfg.water_duration_seconds)

    def _water(self, sensor: SoilSensor, duration: float) -> None:
        """Run the pump and record the event."""
        relay_name = cfg.get("automation", {}).get("water_relay", "trashcan")
        try:
            self._relay.pulse(relay_name, duration=duration)
            self._water_counts[sensor.address] += 1
            insert_relay_event(
                relay_name=relay_name,
                action="pulse",
                duration_seconds=duration,
                triggered_by="automation",
            )
            logger.info(
                "[%s] Watering complete (cycle #%d, %.1fs)",
                sensor.name,
                self._water_counts[sensor.address],
                duration,
            )
        except Exception:
            logger.exception("[%s] Pump activation failed", sensor.name)

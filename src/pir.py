"""PIR motion sensor handler with cooldown suppression."""

import time
from datetime import datetime

import os
os.environ.setdefault("JETSON_MODEL_NAME", "JETSON_ORIN_NANO")  # Orin Nano "Engineering Reference" model not auto-detected
import Jetson.GPIO as GPIO

from config import PIR_COOLDOWN_SEC


class PirInput:
    """Handles HW-MS03 PIR sensor. HIGH = motion detected."""

    def __init__(self, pin: int):
        self.pin = pin
        self._last_trigger: float = 0.0
        self.on_motion = None

        GPIO.setup(pin, GPIO.IN)

    def start(self):
        GPIO.add_event_detect(
            self.pin,
            GPIO.RISING,
            callback=self._callback,
        )

    def stop(self):
        GPIO.remove_event_detect(self.pin)

    def _callback(self, channel):
        now = time.time()
        if now - self._last_trigger < PIR_COOLDOWN_SEC:
            return

        self._last_trigger = now
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] PIR      MOTION DETECTED")
        if self.on_motion:
            self.on_motion()

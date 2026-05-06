"""Button input handler with press/release detection and duration tracking."""

import time
from datetime import datetime

import os
os.environ.setdefault("JETSON_MODEL_NAME", "JETSON_ORIN_NANO")  # Orin Nano "Engineering Reference" model not auto-detected
import Jetson.GPIO as GPIO

from config import DEBOUNCE_MS


class ButtonInput:
    """Handles a single momentary button with press/release events.

    Assumes NO button with pull-up: HIGH at rest, LOW when pressed.
    """

    def __init__(self, pin: int, name: str):
        self.pin = pin
        self.name = name
        self._press_time: float | None = None
        self.on_press = None
        self.on_release = None

        GPIO.setup(pin, GPIO.IN)

    def start(self):
        GPIO.add_event_detect(
            self.pin,
            GPIO.BOTH,
            callback=self._callback,
            bouncetime=DEBOUNCE_MS,
        )

    def stop(self):
        GPIO.remove_event_detect(self.pin)

    def _callback(self, channel):
        level = GPIO.input(channel)

        if level == GPIO.LOW:
            # Button pressed (active low)
            self._press_time = time.time()
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{ts}] {self.name:<8} PRESSED")
            if self.on_press:
                self.on_press()
        else:
            # Button released
            duration = 0.0
            if self._press_time is not None:
                duration = time.time() - self._press_time
                self._press_time = None
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{ts}] {self.name:<8} RELEASED (held {duration:.2f}s)")
            if self.on_release:
                self.on_release(duration)

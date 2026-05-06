"""Fan output controller via AQY210SZ opto-MOSFET relay (active-LOW)."""

from datetime import datetime

import os
os.environ.setdefault("JETSON_MODEL_NAME", "JETSON_ORIN_NANO")  # Orin Nano "Engineering Reference" model not auto-detected
import Jetson.GPIO as GPIO


class FanOutput:
    """Controls a 12V 2-wire fan through an AQY210SZ opto-MOSFET relay.

    GPIO LOW  = relay LED on  = fan running.
    GPIO HIGH = relay LED off = fan stopped.
    """

    def __init__(self, pin: int, name: str):
        self.pin = pin
        self.name = name
        self._is_on = False

        GPIO.setup(pin, GPIO.OUT, initial=GPIO.HIGH)

    @property
    def is_on(self) -> bool:
        return self._is_on

    def on(self):
        if not self._is_on:
            GPIO.output(self.pin, GPIO.LOW)
            self._is_on = True
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{ts}] {self.name:<8} ON")

    def off(self):
        if self._is_on:
            GPIO.output(self.pin, GPIO.HIGH)
            self._is_on = False
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{ts}] {self.name:<8} OFF")

    def toggle(self):
        if self._is_on:
            self.off()
        else:
            self.on()

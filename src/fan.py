"""Fan output controller via N-channel MOSFET switching."""

from datetime import datetime

import Jetson.GPIO as GPIO


class FanOutput:
    """Controls a 12V 2-wire fan through an N-ch MOSFET.

    GPIO HIGH = MOSFET on = fan running.
    GPIO LOW  = MOSFET off = fan stopped.
    """

    def __init__(self, pin: int, name: str):
        self.pin = pin
        self.name = name
        self._is_on = False

        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

    @property
    def is_on(self) -> bool:
        return self._is_on

    def on(self):
        if not self._is_on:
            GPIO.output(self.pin, GPIO.HIGH)
            self._is_on = True
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{ts}] {self.name:<8} ON")

    def off(self):
        if self._is_on:
            GPIO.output(self.pin, GPIO.LOW)
            self._is_on = False
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[{ts}] {self.name:<8} OFF")

    def toggle(self):
        if self._is_on:
            self.off()
        else:
            self.on()

"""Main entry point for the Jetson Orin Nano interface board input handler."""

import signal
import sys
import threading

import os
os.environ.setdefault("JETSON_MODEL_NAME", "JETSON_ORIN_NANO")  # Orin Nano "Engineering Reference" model not auto-detected
import Jetson.GPIO as GPIO

from config import (
    BUTTON1_PIN, BUTTON2_PIN, PIR_PIN,
    FAN1_PIN, FAN2_PIN,
    SERIAL_PORT, SERIAL_BAUDRATE, SERIAL_TIMEOUT,
)
from button import ButtonInput
from fan import FanOutput
from pir import PirInput
from serial_comm import SerialComm


def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    btn_zoom_in = ButtonInput(BUTTON1_PIN, "ZOOM_IN")
    btn_zoom_out = ButtonInput(BUTTON2_PIN, "ZOOM_OUT")
    pir = PirInput(PIR_PIN)

    # Fan outputs
    fan1 = FanOutput(FAN1_PIN, "FAN1")
    fan2 = FanOutput(FAN2_PIN, "FAN2")

    # PIR motion → fans on, buttons → fan toggle
    pir.on_motion = lambda: (fan1.on(), fan2.on())
    btn_zoom_in.on_press = fan1.toggle
    btn_zoom_out.on_press = fan2.toggle

    # Serial / BINGO dongle
    serial_comm = SerialComm(SERIAL_PORT, SERIAL_BAUDRATE, SERIAL_TIMEOUT)
    if serial_comm.open():
        result = serial_comm.query_status()
        if result:
            print(f"BINGO dongle status: {result['res_name']}")
        else:
            print("BINGO dongle: no response (check connection)")
    else:
        print("BINGO dongle: serial port unavailable")

    inputs = [btn_zoom_in, btn_zoom_out, pir]
    stop_event = threading.Event()

    def shutdown(signum, frame):
        print("\nShutting down...")
        stop_event.set()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for inp in inputs:
        inp.start()

    print("Interface board input handler started. Press Ctrl+C to quit.")
    stop_event.wait()

    for inp in inputs:
        inp.stop()

    fan1.off()
    fan2.off()
    serial_comm.close()
    GPIO.cleanup()
    print("GPIO cleaned up. Exiting.")


if __name__ == "__main__":
    main()

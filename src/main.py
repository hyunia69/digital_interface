"""Main entry point for the Jetson Orin Nano interface board input handler."""

import signal
import sys
import threading

import Jetson.GPIO as GPIO

from config import BUTTON1_PIN, BUTTON2_PIN, PIR_PIN
from button import ButtonInput
from pir import PirInput


def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    btn_zoom_in = ButtonInput(BUTTON1_PIN, "ZOOM_IN")
    btn_zoom_out = ButtonInput(BUTTON2_PIN, "ZOOM_OUT")
    pir = PirInput(PIR_PIN)

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

    GPIO.cleanup()
    print("GPIO cleaned up. Exiting.")


if __name__ == "__main__":
    main()

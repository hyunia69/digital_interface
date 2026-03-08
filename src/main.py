"""Main entry point for the Jetson Orin Nano interface board input handler."""

import signal
import sys
import threading

import Jetson.GPIO as GPIO

from config import (
    BUTTON1_PIN, BUTTON2_PIN, PIR_PIN,
    SERIAL_PORT, SERIAL_BAUDRATE, SERIAL_TIMEOUT,
)
from button import ButtonInput
from pir import PirInput
from serial_comm import SerialComm


def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    btn_zoom_in = ButtonInput(BUTTON1_PIN, "ZOOM_IN")
    btn_zoom_out = ButtonInput(BUTTON2_PIN, "ZOOM_OUT")
    pir = PirInput(PIR_PIN)

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

    serial_comm.close()
    GPIO.cleanup()
    print("GPIO cleaned up. Exiting.")


if __name__ == "__main__":
    main()

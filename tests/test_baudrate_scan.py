#!/usr/bin/env python3
"""Scan common baudrates to find the correct one for the BINGO dongle."""

import sys
import os
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import serial
from bingo import BingoProtocol, STX, ETX

DEVICE = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyTHS1"
BAUDRATES = [9600, 19200, 38400, 57600, 115200]
TIMEOUT = 3.0


def hexdump(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


def try_baudrate(device: str, baudrate: int) -> bool:
    print(f"\n{'='*60}")
    print(f"[SCAN] Trying {baudrate} bps ...")

    try:
        ser = serial.Serial(
            port=device,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=TIMEOUT,
        )
    except serial.SerialException as e:
        print(f"  [FAIL] Cannot open port: {e}")
        return False

    try:
        # Flush any stale data
        ser.reset_input_buffer()
        ser.reset_output_buffer()
        time.sleep(0.1)

        proto = BingoProtocol()
        pkt = proto.build_status(0x0000)
        print(f"  TX: {hexdump(pkt)}")

        ser.write(pkt)
        ser.flush()

        # Read response
        buf = bytearray()
        in_frame = False
        deadline = time.monotonic() + TIMEOUT

        while time.monotonic() < deadline:
            raw = ser.read(1)
            if not raw:
                continue
            b = raw[0]
            if not in_frame:
                if b == STX:
                    buf = bytearray([STX])
                    in_frame = True
                else:
                    # Print any garbage bytes received
                    print(f"  RX (noise): 0x{b:02X}", end=" ")
            else:
                buf.append(b)
                if b == ETX:
                    print(f"\n  RX: {hexdump(buf)}")
                    parsed = BingoProtocol.parse_response(bytes(buf))
                    if parsed:
                        print(f"  cmd=0x{parsed['cmd']:02X} res={parsed['res_name']}")
                        print(f"  [MATCH] Baudrate {baudrate} works!")
                        return True
                    else:
                        print(f"  [WARN] Frame received but CRC mismatch (wrong baudrate?)")
                        return False

        # Check if we got any partial data
        if buf:
            print(f"\n  RX (partial): {hexdump(buf)}")
            print(f"  [FAIL] Incomplete frame at {baudrate} bps")
        else:
            print(f"  [FAIL] No response at {baudrate} bps")
        return False

    finally:
        ser.close()


if __name__ == "__main__":
    print(f"Device: {DEVICE}")
    print(f"Testing baudrates: {BAUDRATES}")
    print(f"Timeout per rate: {TIMEOUT}s")

    found = None
    for rate in BAUDRATES:
        if try_baudrate(DEVICE, rate):
            found = rate
            break

    print(f"\n{'='*60}")
    if found:
        print(f"[RESULT] Dongle responded at {found} bps")
    else:
        print("[RESULT] No response at any baudrate.")
        print("  Check: wiring (TX/RX cross), GND, RS232 level converter, power")

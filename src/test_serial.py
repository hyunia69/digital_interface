"""Simple serial communication test between Jetson and Host PC.

Usage:
    python3 test_serial.py [port] [baudrate]

Defaults: /dev/ttyTHS1, 115200

Modes:
    1. Echo mode  - Echoes back anything received
    2. Send mode  - Type messages to send to host PC
    3. Loopback   - Send and expect echo back (host must echo)
"""

import sys
import time
import threading
import serial


DEFAULT_PORT = "/dev/ttyTHS1"
DEFAULT_BAUD = 115200


def open_port(port, baudrate):
    try:
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0,
        )
        print(f"[OK] Opened {port} @ {baudrate}bps")
        return ser
    except serial.SerialException as e:
        print(f"[ERROR] Cannot open {port}: {e}")
        sys.exit(1)


def rx_thread(ser, stop_event):
    """Background thread to print received data."""
    while not stop_event.is_set():
        try:
            data = ser.read(256)
            if data:
                try:
                    text = data.decode("utf-8", errors="replace")
                    hex_str = data.hex(" ")
                    print(f"\n  [RX] {text!r}  ({hex_str})")
                except Exception:
                    print(f"\n  [RX] {data.hex(' ')}")
                print(">> ", end="", flush=True)
        except serial.SerialException:
            if not stop_event.is_set():
                print("\n[ERROR] Serial read error")
            break


def mode_echo(ser):
    """Echo mode: return everything received back to sender."""
    print("\n=== ECHO MODE ===")
    print("Echoing all received data back. Press Ctrl+C to stop.\n")
    try:
        while True:
            data = ser.read(256)
            if data:
                ser.write(data)
                ser.flush()
                hex_str = data.hex(" ")
                text = data.decode("utf-8", errors="replace")
                print(f"  [ECHO] {text!r}  ({hex_str})")
    except KeyboardInterrupt:
        pass


def mode_send(ser):
    """Send mode: type messages to send, receive in background."""
    print("\n=== SEND/RECEIVE MODE ===")
    print("Type a message and press Enter to send.")
    print("Received data is shown with [RX]. Press Ctrl+C to stop.\n")

    stop_event = threading.Event()
    reader = threading.Thread(target=rx_thread, args=(ser, stop_event), daemon=True)
    reader.start()

    try:
        while True:
            msg = input(">> ")
            if not msg:
                continue
            data = (msg + "\r\n").encode("utf-8")
            ser.write(data)
            ser.flush()
            print(f"  [TX] {msg!r}  ({data.hex(' ')})")
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        stop_event.set()
        reader.join(timeout=2)


def mode_loopback(ser):
    """Loopback test: send test patterns and check if they come back."""
    print("\n=== LOOPBACK TEST ===")
    print("Sending test patterns. Host should echo data back.\n")

    patterns = [
        b"Hello from Jetson!\r\n",
        bytes(range(256)),
        b"ABCDEFGHIJKLMNOPQRSTUVWXYZ\r\n",
        b"\x00\x01\x02\x03\x04\x05",
    ]

    passed = 0
    failed = 0

    for i, pattern in enumerate(patterns):
        ser.reset_input_buffer()
        ser.write(pattern)
        ser.flush()

        time.sleep(0.5)
        received = ser.read(len(pattern) + 64)

        if received == pattern:
            print(f"  Test {i+1}: PASS ({len(pattern)} bytes)")
            passed += 1
        elif received:
            print(f"  Test {i+1}: MISMATCH")
            print(f"    Sent: {pattern[:32].hex(' ')}{'...' if len(pattern)>32 else ''}")
            print(f"    Got:  {received[:32].hex(' ')}{'...' if len(received)>32 else ''}")
            failed += 1
        else:
            print(f"  Test {i+1}: NO RESPONSE ({len(pattern)} bytes sent)")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")


def mode_continuous_tx(ser):
    """Continuously send counter data for signal testing."""
    print("\n=== CONTINUOUS TX MODE ===")
    print("Sending counter every 1 second. Press Ctrl+C to stop.\n")
    count = 0
    try:
        while True:
            msg = f"Jetson #{count:05d}\r\n"
            ser.write(msg.encode())
            ser.flush()
            print(f"  [TX] {msg.strip()}")
            count += 1
            time.sleep(1.0)
    except KeyboardInterrupt:
        pass


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_PORT
    baudrate = int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_BAUD

    ser = open_port(port, baudrate)

    try:
        print(f"\nSerial Test: {port} @ {baudrate}bps (8N1)")
        print("-" * 40)
        print("Select mode:")
        print("  1. Echo      - Echo received data back")
        print("  2. Send      - Interactive send/receive")
        print("  3. Loopback  - Automated loopback test")
        print("  4. TX Stream - Continuous counter output")
        print("  q. Quit")
        print("-" * 40)

        choice = input("Mode [2]: ").strip() or "2"

        if choice == "1":
            mode_echo(ser)
        elif choice == "2":
            mode_send(ser)
        elif choice == "3":
            mode_loopback(ser)
        elif choice == "4":
            mode_continuous_tx(ser)
        elif choice.lower() == "q":
            pass
        else:
            print(f"Unknown mode: {choice}")
    finally:
        ser.close()
        print("\nPort closed.")


if __name__ == "__main__":
    main()

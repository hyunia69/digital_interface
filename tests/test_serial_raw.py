#!/usr/bin/env python3
"""Raw serial test: open UART, send BINGO status query, verify CRC and response.

Usage:
    sudo python3 tests/test_serial_raw.py [/dev/ttyTHS1]
"""

import glob
import struct
import sys
import os

# Allow imports from src/
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from bingo import (
    BingoProtocol, crc16, STX, ETX,
    SENDER_POS, RECEIVER_TMS, CMD_STATUS, RESPONSE_NAMES,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_uart_device() -> str | None:
    """Auto-detect Jetson UART device."""
    candidates = sorted(glob.glob("/dev/ttyTHS*"))
    if not candidates:
        # Fallback for dev/test
        candidates = sorted(glob.glob("/dev/ttyUSB*")) + sorted(glob.glob("/dev/ttyAMA*"))
    return candidates[0] if candidates else None


def hexdump(data: bytes) -> str:
    return " ".join(f"{b:02X}" for b in data)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_crc16():
    """Verify CRC16 computation matches expected results."""
    print("=" * 60)
    print("[TEST] CRC16 calculation")

    # Build a known payload (status query, seq=0x01, error_flags=0x0000)
    # SeqNo + Sender + Receiver + Cmd + DataLen + Data
    payload = (
        bytes([0x01])          # SeqNo
        + SENDER_POS           # 0x0E 0x01
        + RECEIVER_TMS         # 0x0A 0x01
        + bytes([CMD_STATUS])  # 0xC3
        + struct.pack(">H", 2) # DataLen = 2
        + bytes([0x00, 0x00])  # error_flags = 0x0000
    )
    crc_val = crc16(payload)
    print(f"  Payload : {hexdump(payload)}")
    print(f"  CRC16   : 0x{crc_val:04X}")
    print(f"  CRC bytes: {hexdump(struct.pack('>H', crc_val))}")

    # Verify round-trip: build packet, parse it back
    proto = BingoProtocol()
    proto._seq = 0  # reset so next is 0x01
    packet = proto.build_status(0x0000)
    print(f"  Full pkt: {hexdump(packet)}")

    assert packet[0] == STX, "STX missing"
    assert packet[-1] == ETX, "ETX missing"

    # CRC in packet should match our manual calculation
    pkt_crc = struct.unpack(">H", packet[-3:-1])[0]
    assert pkt_crc == crc_val, f"CRC mismatch: packet={pkt_crc:#06x} vs calc={crc_val:#06x}"
    print("  [PASS] CRC16 verified")
    print()


def test_packet_build_parse():
    """Verify build -> parse round-trip."""
    print("=" * 60)
    print("[TEST] Packet build/parse round-trip")

    proto = BingoProtocol()
    proto._seq = 0

    pkt = proto.build_status(0x0000)
    print(f"  Request : {hexdump(pkt)}")

    # Simulate a response: dongle echoes back with response code
    # Build a fake response frame for parsing test
    resp_payload = (
        bytes([0x01])          # SeqNo
        + RECEIVER_TMS         # Sender is now the dongle
        + SENDER_POS           # Receiver is POS
        + bytes([CMD_STATUS])  # Cmd
        + struct.pack(">H", 1) # DataLen = 1 (just response code)
        + bytes([0x00])        # RC_SUCCESS
    )
    resp_crc = crc16(resp_payload)
    resp_frame = bytes([STX]) + resp_payload + struct.pack(">H", resp_crc) + bytes([ETX])
    print(f"  FakeResp: {hexdump(resp_frame)}")

    parsed = BingoProtocol.parse_response(resp_frame)
    assert parsed is not None, "Parse returned None"
    assert parsed["cmd"] == CMD_STATUS, f"Wrong cmd: {parsed['cmd']:#04x}"
    assert parsed["res_code"] == 0x00, f"Wrong res_code: {parsed['res_code']:#04x}"
    print(f"  Parsed  : cmd=0x{parsed['cmd']:02X} res={parsed['res_name']}")
    print("  [PASS] Round-trip verified")
    print()


def test_serial_port(device: str | None = None):
    """Open UART and send status query to BINGO dongle."""
    print("=" * 60)
    print("[TEST] Serial port + BINGO status query")

    if device is None:
        device = find_uart_device()
    if device is None:
        print("  [SKIP] No UART device found")
        return

    print(f"  Device  : {device}")

    try:
        import serial
    except ImportError:
        print("  [SKIP] pyserial not installed (pip install pyserial)")
        return

    from serial_comm import SerialComm

    comm = SerialComm(device, baudrate=38400, timeout=5.0)

    if not comm.open():
        print("  [FAIL] Could not open serial port")
        return

    try:
        print("  Sending status query (0xC3)...")
        pkt = comm.protocol.build_status(0x0000)
        print(f"  TX: {hexdump(pkt)}")

        result = comm.send_and_receive(pkt, timeout=5.0)

        if result is None:
            print("  [WARN] No response (dongle may not be connected)")
        else:
            print(f"  RX cmd   : 0x{result['cmd']:02X} ({result.get('res_name', '?')})")
            print(f"  RX code  : 0x{result['res_code']:02X}")
            print(f"  RX data  : {hexdump(result['data'])}")
            print("  [PASS] Response received")
    finally:
        comm.close()
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    device_arg = sys.argv[1] if len(sys.argv) > 1 else None

    test_crc16()
    test_packet_build_parse()
    test_serial_port(device_arg)

    print("All tests completed.")

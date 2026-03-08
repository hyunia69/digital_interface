"""Serial port manager for BINGO dongle communication over RS232C."""

import threading
import time
from datetime import datetime

import serial

from bingo import STX, ETX, BingoProtocol


class SerialComm:
    """Thread-safe serial port wrapper with STX/ETX frame reception."""

    def __init__(self, port: str, baudrate: int = 38400,
                 timeout: float = 3.0):
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser: serial.Serial | None = None
        self._lock = threading.Lock()
        self.protocol = BingoProtocol()

    # -- lifecycle -----------------------------------------------------------

    def open(self) -> bool:
        with self._lock:
            try:
                self._ser = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=self.timeout,
                )
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{ts}] SERIAL   Opened {self.port} @ {self.baudrate}bps")
                return True
            except serial.SerialException as e:
                print(f"[ERROR] Failed to open {self.port}: {e}")
                self._ser = None
                return False

    def close(self):
        with self._lock:
            if self._ser and self._ser.is_open:
                self._ser.close()
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{ts}] SERIAL   Closed {self.port}")
            self._ser = None

    @property
    def is_open(self) -> bool:
        return self._ser is not None and self._ser.is_open

    def reconnect(self, retries: int = 3, delay: float = 1.0) -> bool:
        for attempt in range(1, retries + 1):
            self.close()
            time.sleep(delay)
            if self.open():
                return True
            print(f"[WARN] Reconnect attempt {attempt}/{retries} failed")
        return False

    # -- I/O -----------------------------------------------------------------

    def send(self, packet: bytes) -> bool:
        with self._lock:
            if not self._ser or not self._ser.is_open:
                print("[ERROR] Serial port not open")
                return False
            try:
                self._ser.write(packet)
                self._ser.flush()
                return True
            except serial.SerialException as e:
                print(f"[ERROR] Send failed: {e}")
                return False

    def receive_frame(self, timeout: float | None = None) -> bytes | None:
        """Read bytes until a complete STX...ETX frame is captured.

        Returns the full frame including STX and ETX, or None on timeout.
        """
        t = timeout if timeout is not None else self.timeout
        with self._lock:
            if not self._ser or not self._ser.is_open:
                return None
            self._ser.timeout = t
            buf = bytearray()
            in_frame = False
            deadline = time.monotonic() + t

            while time.monotonic() < deadline:
                byte = self._ser.read(1)
                if not byte:
                    continue
                b = byte[0]
                if b == STX and not in_frame:
                    buf = bytearray([STX])
                    in_frame = True
                elif in_frame:
                    buf.append(b)
                    if b == ETX:
                        return bytes(buf)
            return None

    # -- high-level helpers --------------------------------------------------

    def send_and_receive(self, packet: bytes,
                         timeout: float | None = None) -> dict | None:
        if not self.send(packet):
            return None
        frame = self.receive_frame(timeout)
        if frame is None:
            return None
        return BingoProtocol.parse_response(frame)

    def query_status(self, error_flags: int = 0x0000,
                     timeout: float | None = None) -> dict | None:
        pkt = self.protocol.build_status(error_flags)
        return self.send_and_receive(pkt, timeout)

    def query_version(self, timeout: float | None = None) -> dict | None:
        pkt = self.protocol.build_version()
        return self.send_and_receive(pkt, timeout)

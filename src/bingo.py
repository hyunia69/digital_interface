"""UBCn BINGO dongle protocol: CRC16, packet build/parse, command helpers."""

import struct

# Frame delimiters
STX = 0x02
ETX = 0x03

# Default indices (POS -> DONGLE)
SENDER_POS = bytes([0x0E, 0x01])
RECEIVER_TMS = bytes([0x0A, 0x01])

# Command codes
CMD_CASH_COLLECT = 0xC1
CMD_SOLDOUT = 0xC2
CMD_STATUS = 0xC3
CMD_CANCEL_REQUEST = 0xC5
CMD_READ_PREPAID = 0xC6
CMD_CARD_INIT = 0xC7
CMD_CANCEL_LAST = 0xC8
CMD_DISPLAY = 0xC9
CMD_TRANSACTION = 0xCA
CMD_LTE_TIME = 0xD5
CMD_CLOSING = 0xD9
CMD_SALE_DETAIL = 0xDA
CMD_VERSION = 0x55
CMD_REBOOT = 0x5F
CMD_COLLECT_INFO = 0xFA
CMD_UNSENT_COUNT = 0xE4
CMD_TXN_COLLECT = 0x88
CMD_TMS_DOWNLOAD = 0x60

# Response codes
RC_SUCCESS = 0x00
RC_DATA = 0x01
RC_CONTINUE = 0x05
RC_NO_CARD = 0xF2
RC_MORE_CARDS = 0xF3
RC_FAILURE = 0xFF

RESPONSE_NAMES = {
    RC_SUCCESS: "RC_SUCCESS",
    RC_DATA: "RC_DATA",
    RC_CONTINUE: "RC_CONTINUE",
    RC_NO_CARD: "RC_NO_CARD",
    RC_MORE_CARDS: "RC_MORE_CARDS",
    RC_FAILURE: "RC_FAILURE",
}

COMMAND_NAMES = {
    CMD_CASH_COLLECT: "현금거래 수집",
    CMD_SOLDOUT: "상품 품절",
    CMD_STATUS: "상태 정보",
    CMD_CANCEL_REQUEST: "거래 요청 취소",
    CMD_READ_PREPAID: "선불/신용카드 읽기",
    CMD_CARD_INIT: "신용카드 초기화",
    CMD_CANCEL_LAST: "직전거래 취소",
    CMD_DISPLAY: "화면 문구",
    CMD_TRANSACTION: "거래",
    CMD_LTE_TIME: "LTE 모뎀시간 읽기",
    CMD_CLOSING: "마감 전송",
    CMD_SALE_DETAIL: "상세 판매 정보 전송",
    CMD_VERSION: "버전 정보",
    CMD_REBOOT: "재부팅",
    CMD_COLLECT_INFO: "거래 정보 수집",
    CMD_UNSENT_COUNT: "미전송 카운터 읽기",
    CMD_TXN_COLLECT: "거래 정보 수집",
    CMD_TMS_DOWNLOAD: "TMS 다운로드",
}


# ---------------------------------------------------------------------------
# CRC16 (polynomial 0x8005, matching the C code in the BINGO spec)
# ---------------------------------------------------------------------------

def _generate_crc_table(poly: int = 0x8005) -> list[int]:
    table = []
    for i in range(256):
        n_data = i << 8
        accum = 0
        for _ in range(8):
            if (n_data ^ accum) & 0x8000:
                accum = ((accum << 1) ^ poly) & 0xFFFF
            else:
                accum = (accum << 1) & 0xFFFF
            n_data = (n_data << 1) & 0xFFFF
        table.append(accum)
    return table


_CRC_TABLE = _generate_crc_table()


def crc16(data: bytes | bytearray) -> int:
    accum = 0
    for b in data:
        accum = ((accum << 8) & 0xFFFF) ^ _CRC_TABLE[((accum >> 8) ^ b) & 0xFF]
    return accum


# ---------------------------------------------------------------------------
# Packet builder / parser
# ---------------------------------------------------------------------------

class BingoProtocol:
    """Builds request packets and parses response packets for the BINGO dongle."""

    def __init__(self):
        self._seq = 0

    def _next_seq(self) -> int:
        self._seq += 1
        if self._seq > 0xFF:
            self._seq = 0x01
        return self._seq

    # -- build ---------------------------------------------------------------

    def build_request(self, cmd: int, data: bytes = b"") -> bytes:
        seq = self._next_seq()
        data_len = len(data)
        # Header: SeqNo(1) + Sender(2) + Receiver(2) + Cmd(1) + DataLen(2) + Data(var)
        payload = bytes([seq]) + SENDER_POS + RECEIVER_TMS + bytes([cmd])
        payload += struct.pack(">H", data_len)
        payload += data
        crc_val = crc16(payload)
        packet = bytes([STX]) + payload + struct.pack(">H", crc_val) + bytes([ETX])
        return packet

    # -- parse ---------------------------------------------------------------

    @staticmethod
    def parse_response(raw: bytes) -> dict | None:
        """Parse a response frame (STX ... ETX) into a dict.

        Returns None if the frame is too short or CRC mismatch.
        """
        if len(raw) < 12:  # minimum: STX + header(9) + CRC(2) + ETX
            return None
        if raw[0] != STX or raw[-1] != ETX:
            return None

        # Strip STX/ETX
        body = raw[1:-1]  # SeqNo...CRC
        crc_received = struct.unpack(">H", body[-2:])[0]
        payload = body[:-2]  # SeqNo ~ Data (includes response code)

        crc_calc = crc16(payload)
        if crc_calc != crc_received:
            return None

        seq = payload[0]
        sender = payload[1:3]
        receiver = payload[3:5]
        cmd = payload[5]
        data_len = struct.unpack(">H", payload[6:8])[0]
        res_code = payload[8] if len(payload) > 8 else None
        reply_data = payload[9:] if len(payload) > 9 else b""

        return {
            "seq": seq,
            "sender": sender,
            "receiver": receiver,
            "cmd": cmd,
            "data_len": data_len,
            "res_code": res_code,
            "res_name": RESPONSE_NAMES.get(res_code, f"0x{res_code:02X}") if res_code is not None else None,
            "data": reply_data,
        }

    # -- convenience methods -------------------------------------------------

    def build_status(self, error_flags: int = 0x0000) -> bytes:
        """상태 정보 (0xC3) - 2-byte error flag data."""
        return self.build_request(CMD_STATUS, struct.pack(">H", error_flags))

    def build_card_init(self) -> bytes:
        """신용카드 초기화 (0xC7) - no data."""
        return self.build_request(CMD_CARD_INIT)

    def build_read_prepaid(self, pass_auth: bool = False) -> bytes:
        """선불/신용카드 읽기 (0xC6)."""
        flag = ord("P") if pass_auth else ord("N")
        return self.build_request(CMD_READ_PREPAID, bytes([flag]))

    def build_transaction(self, timeout_100ms: int, amount: int, column: int,
                          lcd_lines: list[bytes] | None = None,
                          items: list[tuple[int, int, bytes]] | None = None) -> bytes:
        """거래 (0xCA).

        Args:
            timeout_100ms: Timeout in 100ms units (e.g. 0x32 = 5 seconds).
            amount: Total amount in won (big-endian 4 bytes).
            column: Column number (BCD).
            lcd_lines: Up to 4 lines of 16 chars for the dongle LCD.
            items: List of (column_bcd, amount, code_bytes) tuples for basket items.
        """
        data = bytearray()
        data.append(timeout_100ms & 0xFF)
        data += struct.pack(">I", amount)
        data.append(column & 0xFF)

        # LCD lines (pad to 16 bytes each)
        if lcd_lines is None:
            lcd_lines = []
        for i in range(4):
            line = lcd_lines[i] if i < len(lcd_lines) else b""
            data += line[:16].ljust(16, b" ")

        # File separator + item count + items
        if items:
            data.append(0x1C)  # file separator
            n = min(len(items), 5)
            data.append(n + 0x30)  # TOTAL NUMBER as ASCII digit
            for col_bcd, amt, code in items[:n]:
                data += struct.pack(">H", col_bcd)
                # amount as 3-byte BCD
                amt_bcd = int(str(amt))  # ensure int
                data += struct.pack(">I", amt_bcd)[1:]  # 3 bytes
                data += code[:7].ljust(7, b"\x00")
        else:
            data.append(0x1C)
            data.append(0x30)  # '0' items

        return self.build_request(CMD_TRANSACTION, bytes(data))

    def build_cancel_request(self) -> bytes:
        """거래 요청 취소 (0xC5) - no data."""
        return self.build_request(CMD_CANCEL_REQUEST)

    def build_cancel_last(self) -> bytes:
        """직전거래 취소 (0xC8) - no data."""
        return self.build_request(CMD_CANCEL_LAST)

    def build_cash_collect(self, amount: int, column: int) -> bytes:
        """현금거래 수집 (0xC1)."""
        data = struct.pack(">I", amount) + bytes([column & 0xFF])
        return self.build_request(CMD_CASH_COLLECT, data)

    def build_display(self, lines: list[bytes]) -> bytes:
        """화면 문구 (0xC9) - up to 4 lines of 16 chars."""
        data = bytearray()
        for i in range(4):
            line = lines[i] if i < len(lines) else b""
            data += line[:16].ljust(16, b" ")
        return self.build_request(CMD_DISPLAY, bytes(data))

    def build_version(self) -> bytes:
        """버전 정보 (0x55) - no data."""
        return self.build_request(CMD_VERSION)

    def build_reboot(self) -> bytes:
        """재부팅 (0x5F) - no data."""
        return self.build_request(CMD_REBOOT)

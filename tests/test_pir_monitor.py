#!/usr/bin/env python3
"""PIR 라이브 토글 모니터 — 토글이 있을 때마다 콘솔에 즉시 출력.

용도:
  HW-MS03 PIR 출력 라인의 raw idle/motion 토글을 관찰. bouncetime/cooldown
  없이 그대로. 직전 레벨이 얼마나 유지됐는지(`prev held ... ms`)도 같이
  찍어 모듈 hold time과 retrigger 거동을 추정할 수 있다.

핀:
  PIR (BCM24, Pin 18, PY.03) → gpiochip0 line 125

실행:
  python3 tests/test_pir_monitor.py     (sudo 불필요)
  Ctrl+C 로 종료.
"""

import signal
import sys
import time
from datetime import datetime

import gpiod

LINE_OFFSET = 125   # PY.03 (SPI3_CS0_PY3) — config.PIR_PIN(BCM24)에 해당
SAMPLE_HZ = 500     # 2ms 해상도


def fmt_level(v: int) -> str:
    return "HIGH" if v else "LOW "


def main():
    chip = gpiod.Chip("gpiochip0")
    line = chip.get_line(LINE_OFFSET)
    line.request(consumer="pir-monitor", type=gpiod.LINE_REQ_DIR_IN)

    initial = line.get_value()
    ts0 = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"[{ts0}] monitor start   line={LINE_OFFSET}  initial={fmt_level(initial)}")
    print("                Ctrl+C 로 종료. 토글이 있을 때마다 한 줄씩 찍힘.")
    sys.stdout.flush()

    stop = [False]

    def shutdown(signum, frame):
        stop[0] = True

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    prev = initial
    last_change_t = time.monotonic()
    interval = 1.0 / SAMPLE_HZ
    edge_count = 0

    while not stop[0]:
        v = line.get_value()
        if v != prev:
            now = time.monotonic()
            held_ms = (now - last_change_t) * 1000.0
            last_change_t = now
            edge_count += 1
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            edge = "RISING " if v == 1 else "FALLING"
            print(
                f"[{ts}] #{edge_count:>4}  {edge}  "
                f"{prev}->{v}  ({fmt_level(v)})  prev held {held_ms:>9.1f} ms"
            )
            sys.stdout.flush()
            prev = v
        time.sleep(interval)

    final = line.get_value()
    tsf = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    print(f"\n[{tsf}] monitor stop    final={fmt_level(final)}  total_edges={edge_count}")
    line.release()


if __name__ == "__main__":
    main()

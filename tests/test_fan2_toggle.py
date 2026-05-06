#!/usr/bin/env python3
"""FAN2 (보드 라벨) 토글 테스트.

대상 채널:
  - 보드 실크 라벨: FAN2
  - 헤더 위치: Pin 31 (BCM6)
  - 코드 매핑: config.FAN2_PIN (보드 라벨과 일치, §13 정합 후)

회로:
  - AQY210SZ 옵토MOSFET 릴레이 구동
  - active-LOW: GPIO LOW = 팬 ON, GPIO HIGH = 팬 OFF
  - 초기값은 HIGH(OFF)로 두고, 일정 주기로 ON/OFF 토글

테스트 목적:
  - FAN2 자리(Pin 31) 채널이 GPIO 레벨에 따라 정상 토글되는지 확인
  - 리부팅 후 FAN1과 함께 양 채널 모두 동작 확정

실행:
  sudo python3 tests/test_fan2_toggle.py
  sudo python3 tests/test_fan2_toggle.py --period 4   # ON/OFF 한 사이클 4초
"""

import argparse
import signal
import sys
import time
from datetime import datetime

import os
os.environ.setdefault("JETSON_MODEL_NAME", "JETSON_ORIN_NANO")
import Jetson.GPIO as GPIO

# 보드 라벨 FAN2 = Pin 31 = BCM6
FAN2_LABEL_PIN = 6
HEADER_PIN = 31

# active-LOW: LOW=ON, HIGH=OFF
LEVEL_ON = GPIO.LOW
LEVEL_OFF = GPIO.HIGH


def fmt(level: int) -> str:
    return "ON  (LOW)" if level == LEVEL_ON else "OFF (HIGH)"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--period", type=float, default=2.0,
        help="ON/OFF 한 단계 유지 시간(초). 기본 2.0초",
    )
    parser.add_argument(
        "--cycles", type=int, default=0,
        help="반복 사이클 수. 0이면 Ctrl+C 까지 무한",
    )
    args = parser.parse_args()

    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)
    GPIO.setup(FAN2_LABEL_PIN, GPIO.OUT, initial=LEVEL_OFF)

    print("=" * 60)
    print("  FAN2 (보드 라벨) 토글 테스트")
    print("=" * 60)
    print(f"  채널        : 보드 FAN2 / Pin {HEADER_PIN} / BCM{FAN2_LABEL_PIN}")
    print(f"  회로 극성   : active-LOW (LOW=ON)")
    print(f"  단계 시간   : {args.period:.2f}초")
    print(f"  반복 사이클 : {'무한' if args.cycles == 0 else args.cycles}")
    print("-" * 60)
    print("  Ctrl+C 로 종료. 종료 시 OFF 처리 후 정리합니다.")
    print("-" * 60)
    print()

    stop = [False]

    def shutdown(signum, frame):
        stop[0] = True

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    cycle = 0
    on_count = 0
    off_count = 0
    try:
        while not stop[0]:
            cycle += 1

            GPIO.output(FAN2_LABEL_PIN, LEVEL_ON)
            on_count += 1
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"  [{ts}] #{cycle:>3}  {fmt(LEVEL_ON)}  → 팬 회전 확인")

            t_end = time.time() + args.period
            while time.time() < t_end and not stop[0]:
                time.sleep(0.05)
            if stop[0]:
                break

            GPIO.output(FAN2_LABEL_PIN, LEVEL_OFF)
            off_count += 1
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            print(f"  [{ts}] #{cycle:>3}  {fmt(LEVEL_OFF)} → 팬 정지 확인")

            t_end = time.time() + args.period
            while time.time() < t_end and not stop[0]:
                time.sleep(0.05)

            if args.cycles and cycle >= args.cycles:
                break
    finally:
        GPIO.output(FAN2_LABEL_PIN, LEVEL_OFF)
        print()
        print("=" * 60)
        print("  테스트 결과 요약")
        print("=" * 60)
        print(f"  완료 사이클 : {cycle}")
        print(f"  ON  토글 수 : {on_count}")
        print(f"  OFF 토글 수 : {off_count}")
        print(f"  종료 상태   : {fmt(LEVEL_OFF)} (안전 정지)")
        print()
        GPIO.cleanup()
        print("GPIO 정리 완료.")


if __name__ == "__main__":
    main()

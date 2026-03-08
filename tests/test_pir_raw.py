#!/usr/bin/env python3
"""PIR 센서 감지 테스트 (HW-MS03 모션 센서).

현재 상태:
  - PIR 센서: HW-MS03 (BCM24, Pin 18)
  - 모션 감지 시 HIGH 출력, 미감지 시 LOW
  - 쿨다운 없이 원시 신호를 그대로 관찰

테스트 목적:
  - PIR 센서가 모션을 정상적으로 감지하는지 확인
  - RISING/FALLING 엣지를 모두 관찰하여 센서 반응 특성 파악
  - 오탐(false trigger) 빈도 확인

실행: sudo python3 tests/test_pir_raw.py
"""

import signal
import sys
import time
from datetime import datetime

import Jetson.GPIO as GPIO

# config.py 기준 핀 번호
PIR_PIN = 24  # Pin 18 (GP39 / SPI3_CS0)


def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    print("=" * 60)
    print("  PIR 센서 감지 테스트 (HW-MS03)")
    print("=" * 60)
    print()

    GPIO.setup(PIR_PIN, GPIO.IN)
    initial = GPIO.input(PIR_PIN)
    state = "HIGH (모션 감지 중)" if initial == GPIO.HIGH else "LOW (대기 상태)"
    print(f"  PIR 센서 (BCM24, Pin18)")
    print(f"    초기 상태: {state} (값: {initial})")
    print()

    print("[INFO] PIR 센서 안정화 대기 중 (최대 5초)...")
    # HW-MS03은 전원 인가 후 안정화 시간이 필요할 수 있음
    stable_start = time.time()
    while time.time() - stable_start < 5:
        if GPIO.input(PIR_PIN) == GPIO.LOW:
            print("[INFO] 센서 안정화 완료 (LOW 상태 확인)")
            break
        time.sleep(0.5)
    else:
        current = GPIO.input(PIR_PIN)
        if current == GPIO.HIGH:
            print("[WARN] 5초 후에도 HIGH 상태 — 센서 주변에 움직임이 있거나 배선 확인 필요")
        else:
            print("[INFO] 센서 안정화 완료")
    print()

    print("-" * 60)
    print("  센서 앞에서 움직여 보세요. Ctrl+C로 종료.")
    print("  RISING  = 모션 감지 시작")
    print("  FALLING = 모션 감지 종료 (센서 홀드 타임 후)")
    print("-" * 60)
    print()

    motion_count = 0
    last_rising = None

    def callback(channel):
        nonlocal motion_count, last_rising
        level = GPIO.input(channel)
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        if level == GPIO.HIGH:
            motion_count += 1
            last_rising = time.time()
            print(f"  [{ts}] #{motion_count:>4}  RISING   모션 감지 시작")
        else:
            duration = ""
            if last_rising is not None:
                hold = time.time() - last_rising
                duration = f" (홀드 시간: {hold:.1f}초)"
            print(f"  [{ts}]        FALLING  모션 감지 종료{duration}")

    GPIO.add_event_detect(PIR_PIN, GPIO.BOTH, callback=callback, bouncetime=200)

    stop = [False]

    def shutdown(signum, frame):
        stop[0] = True

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        while not stop[0]:
            time.sleep(0.1)
    except KeyboardInterrupt:
        pass

    print()
    print("=" * 60)
    print("  테스트 결과 요약")
    print("=" * 60)
    print(f"  PIR 센서 (BCM24, Pin18): 모션 감지 {motion_count}회")
    if motion_count == 0:
        print(f"    → 신호 감지 안 됨 (배선 확인 또는 센서 앞에서 움직여 주세요)")
    elif motion_count > 50:
        print(f"    → 오탐 과다 (센서 감도 조정 또는 배선 확인 필요)")
    else:
        print(f"    → 정상 범위")
    print()

    GPIO.cleanup()
    print("GPIO 정리 완료.")


if __name__ == "__main__":
    main()

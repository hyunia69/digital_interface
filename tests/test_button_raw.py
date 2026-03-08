#!/usr/bin/env python3
"""버튼 감지 테스트 (현재 보드 그대로, 풀업 저항 없는 상태).

현재 상태:
  - 보드/Jetson 양쪽 모두 풀업 저항 없음
  - GPIO 핀이 플로팅 상태일 수 있음 → 노이즈 발생 가능
  - 버튼 누르면 GND 연결 (Active LOW)

테스트 목적:
  - 버튼을 눌렀을 때 Jetson에서 실제로 신호 변화를 감지할 수 있는지 확인
  - 풀업 없이도 동작하는지, 노이즈가 얼마나 심한지 관찰

실행: sudo python3 tests/test_button_raw.py
"""

import signal
import sys
import time
from datetime import datetime

import Jetson.GPIO as GPIO

# 현재 config.py 기준 핀 번호
BUTTON1_PIN = 18  # Zoom In  - Pin 12
BUTTON2_PIN = 27  # Zoom Out - Pin 13

BUTTONS = {
    BUTTON1_PIN: "BUTTON1 (Zoom In,  BCM18, Pin12)",
    BUTTON2_PIN: "BUTTON2 (Zoom Out, BCM27, Pin13)",
}


def main():
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    print("=" * 60)
    print("  버튼 감지 테스트 (풀업 저항 없는 현재 보드 상태)")
    print("=" * 60)
    print()

    for pin, name in BUTTONS.items():
        GPIO.setup(pin, GPIO.IN)
        initial = GPIO.input(pin)
        state = "HIGH (정상 대기)" if initial == GPIO.HIGH else "LOW (눌림 또는 플로팅)"
        print(f"  {name}")
        print(f"    초기 상태: {state} (값: {initial})")
    print()

    # 소프트웨어 풀업 시도 (Orin Nano에서 미작동 가능)
    print("[INFO] 소프트웨어 풀업(PUD_UP) 설정 시도...")
    try:
        for pin in BUTTONS:
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        print("[INFO] PUD_UP 설정 완료 (실제 작동 여부는 하드웨어 의존)")
    except Exception as e:
        print(f"[WARN] PUD_UP 설정 실패: {e}")
        print("[WARN] Orin Nano에서는 내부 풀업이 미지원일 수 있음")

    for pin, name in BUTTONS.items():
        after = GPIO.input(pin)
        print(f"  {name} → PUD_UP 후: {'HIGH' if after else 'LOW'} ({after})")
    print()

    print("-" * 60)
    print("  버튼을 눌러보세요. Ctrl+C로 종료.")
    print("  (풀업 없으면 노이즈로 인한 오탐 발생 가능)")
    print("-" * 60)
    print()

    event_count = {pin: 0 for pin in BUTTONS}

    def callback(channel):
        level = GPIO.input(channel)
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        name = BUTTONS.get(channel, f"BCM{channel}")
        state = "LOW  (눌림)" if level == GPIO.LOW else "HIGH (해제)"
        event_count[channel] += 1
        print(f"  [{ts}] #{event_count[channel]:>4}  {name}  →  {state}")

    for pin in BUTTONS:
        GPIO.add_event_detect(pin, GPIO.BOTH, callback=callback, bouncetime=50)

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
    for pin, name in BUTTONS.items():
        cnt = event_count[pin]
        print(f"  {name}: 이벤트 {cnt}회")
        if cnt == 0:
            print(f"    → 신호 감지 안 됨 (배선 또는 풀업 문제 확인)")
        elif cnt > 100:
            print(f"    → 노이즈 과다 (풀업 저항 추가 필요)")
    print()

    GPIO.cleanup()
    print("GPIO 정리 완료.")


if __name__ == "__main__":
    main()

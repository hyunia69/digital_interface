#!/usr/bin/env python3
"""버튼 감지 테스트 (인터페이스보드 외부 풀업 사용).

회로도 (02_interface/20260429_회로도.pdf) 기준:
  - BUTTON1 (GPIO18, Pin12), BUTTON2 (GPIO27, Pin13)
  - 둘 다 +3.3V → 외부 풀업 저항 → GPIO 라인 → SMW250-02 커넥터 → 외부버튼 → GND
  - 평소 HIGH, 버튼 누르면 LOW (Active LOW)
  - GPIO 라인에 필터 커패시터도 실장되어 있음

테스트 목적:
  - idle 시 HIGH가 안정적으로 유지되는지 (외부 풀업 정상 동작 여부)
  - 버튼을 눌렀을 때 LOW 에지가 잡히는지
  - HIGH가 아닌 LOW/불안정이면 풀업 저항 미실장, 배선 단선,
    또는 핀 SFIO/pinmux 잔류 의심

실행: sudo python3 tests/test_button_raw.py
"""

import signal
import sys
import time
from datetime import datetime

import os
os.environ.setdefault("JETSON_MODEL_NAME", "JETSON_ORIN_NANO")  # Orin Nano "Engineering Reference" model not auto-detected
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
        state = "HIGH (정상 대기, 외부 풀업 OK)" if initial == GPIO.HIGH else "LOW (눌림 / 풀업 미작동 / 배선 끊김 의심)"
        print(f"  {name}")
        print(f"    초기 상태: {state} (값: {initial})")
    print()

    print("-" * 60)
    print("  버튼을 눌러보세요. Ctrl+C로 종료.")
    print("  정상: 누르면 LOW, 떼면 HIGH")
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
            print(f"    → 신호 감지 안 됨 (헤더 핀 연결 / 풀업 / 배선 / pinmux 점검)")
        elif cnt > 100:
            print(f"    → 노이즈 과다 (필터 캡 / 외부 풀업 점검)")
    print()

    GPIO.cleanup()
    print("GPIO 정리 완료.")


if __name__ == "__main__":
    main()

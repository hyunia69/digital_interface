#!/usr/bin/env python3
"""Jetson Orin Nano 40핀 헤더 전체 GPIO 모니터.

40핀 헤더에서 GPIO로 사용 가능한 모든 핀을 감시하여,
어떤 핀에 신호 변화가 발생하면 즉시 표시합니다.

용도:
  - 어떤 핀에 버튼/센서가 연결되어 있는지 모를 때
  - 보드 배선 확인용
  - 입력 신호 디버깅

실행: sudo python3 tests/test_gpio_monitor.py
옵션: sudo python3 tests/test_gpio_monitor.py --poll  (폴링 모드)
"""

import argparse
import signal
import sys
import time
from datetime import datetime

import Jetson.GPIO as GPIO

# Jetson Orin Nano 40핀 헤더 - GPIO 사용 가능 핀 목록
# (전원핀 Pin1,2,4,17 / GND핀 Pin6,9,14,20,25,30,34,39 제외)
# BCM 번호 기준
GPIO_PINS = {
    # BCM: (물리핀, 기본기능, 비고)
    4:   (7,   "GPIO09",       ""),
    17:  (11,  "GPIO10",       ""),
    18:  (12,  "I2S0_SCLK",   "← BUTTON1 예상"),
    27:  (13,  "SPI1_SCK",    "← BUTTON2 예상"),
    22:  (15,  "GPIO12",       ""),
    23:  (16,  "SPI1_CS1",    ""),
    24:  (18,  "SPI1_CS0",    "← PIR 예상"),
    10:  (19,  "SPI0_MOSI",   ""),
    9:   (21,  "SPI0_MISO",   ""),
    25:  (22,  "GPIO13",       ""),
    11:  (23,  "SPI0_SCK",    ""),
    8:   (24,  "SPI0_CS0",    ""),
    7:   (26,  "SPI0_CS1",    ""),
    5:   (29,  "GPIO01",       ""),
    6:   (31,  "GPIO11",      "← FAN1 예상"),
    12:  (32,  "GPIO07/PWM",  "← FAN2 예상"),
    13:  (33,  "GPIO15/PWM",  ""),
    19:  (35,  "I2S0_FS",     ""),
    26:  (37,  "GPIO19",       ""),
    20:  (38,  "I2S0_DIN",    ""),
    21:  (40,  "I2S0_DOUT",   ""),
}


def format_pin_info(bcm):
    phys, func, note = GPIO_PINS[bcm]
    return f"BCM{bcm:>2} (Pin{phys:>2}, {func:<12}) {note}"


def setup_all_gpio():
    """모든 GPIO 핀을 입력으로 설정하고 초기 상태를 반환."""
    GPIO.setmode(GPIO.BCM)
    GPIO.setwarnings(False)

    success = []
    failed = []

    for bcm in sorted(GPIO_PINS.keys()):
        try:
            GPIO.setup(bcm, GPIO.IN)
            success.append(bcm)
        except Exception as e:
            failed.append((bcm, str(e)))

    return success, failed


def show_initial_state(pins):
    """모든 핀의 현재 상태를 표시."""
    print()
    print("  핀 번호        물리핀   기본기능       상태    비고")
    print("  " + "-" * 62)

    for bcm in sorted(pins):
        level = GPIO.input(bcm)
        state = "HIGH" if level else "LOW "
        info = GPIO_PINS[bcm]
        note = info[2]
        print(f"  BCM{bcm:>2}  (Pin{info[0]:>2})  {info[1]:<12}   {state}    {note}")


def monitor_event_mode(pins):
    """이벤트 감지 모드 — 신호 변화 시 즉시 콜백."""
    event_log = []

    def make_callback(bcm_pin):
        def callback(channel):
            level = GPIO.input(channel)
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            state = "LOW  (활성)" if level == GPIO.LOW else "HIGH (해제)"
            info = format_pin_info(bcm_pin)
            msg = f"  [{ts}]  {info}  →  {state}"
            print(msg)
            event_log.append((ts, bcm_pin, level))
        return callback

    for bcm in pins:
        try:
            GPIO.add_event_detect(
                bcm, GPIO.BOTH,
                callback=make_callback(bcm),
                bouncetime=30,
            )
        except Exception as e:
            print(f"  [WARN] BCM{bcm} 이벤트 등록 실패: {e}")

    return event_log


def monitor_poll_mode(pins, interval=0.05):
    """폴링 모드 — 주기적으로 모든 핀 상태를 확인."""
    prev_state = {}
    for bcm in pins:
        prev_state[bcm] = GPIO.input(bcm)

    event_log = []
    stop = [False]

    def shutdown(signum, frame):
        stop[0] = True

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print()
    print(f"  폴링 모드 (간격: {interval*1000:.0f}ms)")
    print(f"  핀 변화가 감지되면 표시됩니다. Ctrl+C로 종료.")
    print()

    while not stop[0]:
        for bcm in pins:
            level = GPIO.input(bcm)
            if level != prev_state[bcm]:
                ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
                state = "LOW  (활성)" if level == GPIO.LOW else "HIGH (해제)"
                info = format_pin_info(bcm)
                print(f"  [{ts}]  {info}  →  {state}")
                event_log.append((ts, bcm, level))
                prev_state[bcm] = level
        time.sleep(interval)

    return event_log


def print_summary(event_log):
    """이벤트 요약 출력."""
    print()
    print("=" * 65)
    print("  감지 결과 요약")
    print("=" * 65)

    if not event_log:
        print("  이벤트 없음 — 아무 신호도 감지되지 않았습니다.")
        return

    # 핀별 이벤트 카운트
    pin_counts = {}
    for ts, bcm, level in event_log:
        pin_counts[bcm] = pin_counts.get(bcm, 0) + 1

    for bcm in sorted(pin_counts.keys()):
        cnt = pin_counts[bcm]
        info = format_pin_info(bcm)
        status = ""
        if cnt > 200:
            status = "  ⚠ 노이즈 과다 (풀업/풀다운 필요)"
        elif cnt > 0:
            status = "  ✓ 신호 감지됨"
        print(f"  {info}: {cnt:>5}회 {status}")

    # 활성 핀만 요약
    active = sorted(pin_counts.keys())
    if active:
        print()
        bcm_list = ", ".join(f"BCM{b}" for b in active)
        print(f"  → 활성 핀: {bcm_list}")


def main():
    parser = argparse.ArgumentParser(description="Jetson GPIO 전체 모니터")
    parser.add_argument(
        "--poll", action="store_true",
        help="폴링 모드 사용 (기본: 이벤트 감지 모드)",
    )
    parser.add_argument(
        "--interval", type=float, default=0.05,
        help="폴링 간격 초 (기본: 0.05)",
    )
    args = parser.parse_args()

    print("=" * 65)
    print("  Jetson Orin Nano — 40핀 GPIO 전체 모니터")
    print("=" * 65)

    success, failed = setup_all_gpio()

    print(f"\n  GPIO 설정: {len(success)}핀 성공, {len(failed)}핀 실패")
    if failed:
        for bcm, err in failed:
            print(f"    [FAIL] BCM{bcm}: {err}")

    show_initial_state(success)

    mode = "폴링" if args.poll else "이벤트 감지"
    print()
    print("-" * 65)
    print(f"  모니터링 시작 ({mode} 모드)")
    print(f"  아무 핀에 신호를 넣으면 여기에 표시됩니다.")
    print(f"  Ctrl+C로 종료.")
    print("-" * 65)
    print()

    if args.poll:
        event_log = monitor_poll_mode(success, args.interval)
    else:
        event_log = monitor_event_mode(success)

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

    print_summary(event_log)
    print()
    GPIO.cleanup()
    print("  GPIO 정리 완료.")


if __name__ == "__main__":
    main()

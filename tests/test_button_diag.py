#!/usr/bin/env python3
"""버튼 라인 하드웨어 진단 — 풀업/풀다운/floating 판별.

pinmux는 이미 GPIO이고 패드 컨트롤도 정상이라는 사실을 확인한 뒤,
이 스크립트는 사용자가 버튼을 직접 눌러보는 동안 idle 값과 에지 변화를
실시간으로 보여줍니다.

실행: python3 tests/test_button_diag.py   (sudo 불필요)
"""

import sys
import time
from datetime import datetime
from collections import Counter

import gpiod

LINES = [
    (50,  "BUTTON1 Pin12 BCM18 PH.07"),
    (122, "BUTTON2 Pin13 BCM27 PY.00"),
]

DURATION = 12  # seconds
SAMPLE_HZ = 200

chip = gpiod.Chip("gpiochip0")
lines = chip.get_lines([off for off, _ in LINES])
lines.request(consumer="btn-diag", type=gpiod.LINE_REQ_DIR_IN)

# Sample to characterize idle behavior
print("=" * 60)
print("  버튼 진단 시작")
print("=" * 60)
print(f"\n[1/2] 5초간 아무것도 누르지 마세요. idle 값 분포를 측정합니다.\n")
time.sleep(0.5)

end = time.time() + 5
samples = [[], []]
while time.time() < end:
    vals = lines.get_values()
    for i, v in enumerate(vals):
        samples[i].append(v)
    time.sleep(1.0 / SAMPLE_HZ)

for i, (off, name) in enumerate(LINES):
    c = Counter(samples[i])
    total = sum(c.values())
    high_pct = 100 * c.get(1, 0) / total
    low_pct = 100 * c.get(0, 0) / total
    print(f"  {name}: HIGH {high_pct:.1f}%   LOW {low_pct:.1f}%   (samples={total})")
    if high_pct > 95:
        verdict = "안정적 HIGH → 풀업 있음 ✓"
    elif low_pct > 95:
        verdict = "안정적 LOW → 풀다운 있음 또는 풀이 전혀 없고 GND 결합 / 또는 SFIO 잔류"
    else:
        verdict = "불안정 / floating (풀업도 풀다운도 없음) → 외부 풀업 필수"
    print(f"      → {verdict}")
print()

print(f"[2/2] {DURATION}초간 버튼을 자유롭게 눌렀다 떼주세요.")
print("      각 버튼을 2~3회씩 누르세요. 변화가 있을 때마다 로그가 찍힙니다.\n")

prev = lines.get_values()
events = [0, 0]
end = time.time() + DURATION
while time.time() < end:
    vals = lines.get_values()
    for i, (v, p) in enumerate(zip(vals, prev)):
        if v != p:
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
            state = "HIGH" if v else "LOW "
            print(f"  [{ts}] {LINES[i][1]}  {p}->{v}  ({state})")
            events[i] += 1
    prev = vals
    time.sleep(1.0 / SAMPLE_HZ)

print()
print("=" * 60)
print("  결과")
print("=" * 60)
for i, (off, name) in enumerate(LINES):
    print(f"  {name}: 에지 {events[i]}회")
    if events[i] == 0:
        print(f"      → 변화 없음. 버튼이 GND에 연결되는데 idle도 LOW면, ")
        print(f"        눌러도 변화가 없어서 안 보입니다. 풀업이 없거나 회로 문제.")
    elif events[i] > 50:
        print(f"      → 노이즈 과다. 풀업 부재 또는 디바운싱 필요.")
    else:
        print(f"      → 정상 동작. 버튼 신호가 잡힙니다.")

lines.release()

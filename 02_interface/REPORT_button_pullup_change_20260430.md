# 인터페이스 보드 BUTTON1/BUTTON2 풀업 저항(R17, R27) 변경 요청

작성일: 2026-04-30
대상 보드: 디지털 인터페이스 보드 (회로도: `20260429_회로도.pdf`)
대상 시스템: Jetson Orin Nano (Super) — `p3768-0000+p3767-0005-super`

---

## 요약

- 인터페이스 보드 + Jetson Orin Nano 결합 시 **BUTTON1/BUTTON2 idle 라인이 LOW(약 1V)로 처지고 뗌(릴리즈) 후에도 HIGH로 복귀하지 않는 현상**.
- 단계별 분리 시험으로 **인터페이스 보드 자체는 무결**, **Jetson 캐리어 보드 측에서 GPIO18/GPIO27 두 핀을 약 4.3kΩ 풀다운으로 끌어내리는 path가 존재**함을 확인.
- 해결책: **R17, R27 두 곳을 10kΩ → 1kΩ으로 교체** (회로 토폴로지 유지, 값만 조정).

---

## 1. 증상

- 결합 상태에서 버튼을 누르지 않은 idle: GPIO 라인 V ≈ 1.0V (기대 3.3V)
- 누름: 0V (정상)
- 뗌(릴리즈): 다시 1V로 처짐 (기대 3.3V로 복귀)
- SW(`gpioget`, `Jetson.GPIO add_event_detect`) 결과:
  - 누름 LOW 에지는 잡힘
  - 뗌 HIGH 에지가 신뢰할 수 없게 잡히거나 누락
  - 누름 테스트 후 idle이 LOW로 굳음 (BUTTON1, BUTTON2 동일 거동)

## 2. 진단 — 기각된 가설들

| # | 가설 | 검증 결과 |
|---|---|---|
| 1 | Jetson SoC pinmux/SFIO 잔류로 SoC가 라인을 GPIO로 인식 못 함 | DTBO로 핀 mux 명시 적용 + `pinconf-groups`에서 `pull=2` 확인 → SoC pad 측 정상 |
| 2 | 인터페이스 보드 자체 +3.3V Rail 부재 | LM1117MP-3.3 출력 측정 3.3V 정상 |
| 3 | R17/C15가 위치 바뀜으로 실장 (PCB 풋프린트 동일) | 육안 확인 정상 위치, 정상 부품 |
| 4 | C15(0.1µF) 캡 leakage 또는 PCB 표면 오염 | 항목 5의 보드 단독 시험으로 기각 |

## 3. 결정적 시험 ① — 인터페이스 보드 단독 동작

**Jetson을 분리하고 외부 전원만 인가**한 상태에서 J3 PIN12(GPIO18 라인) ↔ PIN6(GND) 사이 전압 측정:

| 외부 버튼 상태 | 측정 V | 기대 V | 판정 |
|---|---|---|---|
| 외부 버튼 미연결 | 3.3V | 3.3V | OK |
| 꽂고 누르지 않음 | 3.3V | 3.3V | OK |
| 누름 | 0V | 0V | OK |
| 뗌(릴리즈) | 3.3V (즉시) | 3.3V | OK |

→ **인터페이스 보드 자체는 회로도 의도대로 완벽히 동작.**
→ R17, C15, SMW250, LM1117MP-3.3, +3.3V Rail 트레이스 모두 정상.

## 4. 결정적 시험 ② — Jetson 측 단독 동작

인터페이스 보드를 분리하고 Jetson Orin Nano만 부팅된 상태에서 J41(40핀 헤더) PIN12, PIN13의 출력 동작도 정상.

## 5. 원인 추정 — Jetson 결합 시점의 ~4.3kΩ 풀다운 path

결합 상태에서 R17 아래쪽 노드(신호 노드)의 측정 V = 1V. 분압식으로 등가 풀다운 임피던스를 산출:

```
1V = 3.3V × R_pulldown / ( R17(10kΩ) + R_pulldown )
→ R_pulldown ≈ 4.3 kΩ
```

GPIO18(=Tegra234 PH.07, J41 PIN12)과 GPIO27(=PY.00, PIN13) 두 핀 모두 동일하게 4.3kΩ 풀다운 거동을 보이므로:

- Jetson Orin Nano 캐리어 보드(P3768) 측 또는 SoC 패드에서, **두 헤더 핀에 공통적으로 약 4.3kΩ 풀다운 path가 존재**한다고 판단.
- 일반적으로 이런 핀에는 부팅 시 strap 안정화 또는 ESD 보호 목적의 풀다운 저항이 실장될 수 있음.

Tegra234 SoC pad 측에서 device tree로 internal pull-up을 enable했으며 (`nvidia,pull = <2>`, `/sys/kernel/debug/pinctrl/2430000.pinmux/pinconf-groups`에서 적용 확인), 그럼에도 외부 4.3kΩ에 패배합니다. SoC internal pull-up 강도는 약 50~100kΩ로 추정. **SW(DT) 측에서는 더 강화할 수 있는 옵션이 없음.**

## 6. 권장 변경 — R17, R27: 10kΩ → 1kΩ

외부 풀업을 강화하여 Jetson 측 풀다운을 분압에서 압도. SoC HIGH 임계(V_IH ≈ 2.0V) 안정 충족.

| 항목 | 변경 전 (10kΩ) | 변경 후 (1kΩ) |
|---|---|---|
| idle V (Jetson 결합 시) | 3.3 × 4.3/14.3 = **0.99V** ❌ | 3.3 × 4.3/5.3 = **2.68V** ✓ |
| SoC HIGH 인식 (V_IH ≈ 2.0V) | 미달 → LOW로 오인식 | 충족 → HIGH 정상 인식 |
| 누름 시 라인 V | 0V (정상) | 0V (정상) |
| 누름 시 +3.3V → R → GND 전류 | 0.33 mA | **3.3 mA** |
| RC 시정수 (R × C15) | 1 ms | 0.1 ms |

## 7. 변경 영향 검토

- **+3.3V Rail 부하**: 두 BUTTON 채널 동시 누름 시 추가 전류 6.6 mA. LM1117MP-3.3 정격 출력(800mA) 대비 무시 가능.
- **신호 무결성**: RC 시정수가 1ms → 0.1ms로 단축. 기계식 스위치 chatter 흡수 효과는 감소하지만, SW 측 디바운스(현재 50ms)에서 충분히 처리됨. 필요시 C15/C17을 1µF로 키워 RC 시정수 1ms로 복원 가능.
- **회로 의도 보존**: 풀업/필터 캡 토폴로지는 그대로. 단지 R 값만 조정.
- **다른 회로 영향 없음**: R17/R27은 BUTTON1/BUTTON2 풀업 전용으로, 다른 회로와 공유되지 않음.

## 8. 대안 검토

| 대안 | idle V (결합 시) | 누름 전류 | 평가 |
|---|---|---|---|
| R = 470Ω | 2.97V | 7.0 mA | 안정 마진 ↑, 전류 다소 큼 |
| **R = 1kΩ (권장)** | **2.68V** | **3.3 mA** | **안전 마진 + 전류 균형 최적** |
| R = 2.2kΩ | 2.18V | 1.5 mA | HIGH 임계 간당간당, 권장 안 함 |
| Jetson 캐리어 풀다운 R 직접 제거 | — | — | NVIDIA 제조 보드 변경은 비현실적 |
| SW 디바운스만 강화 | — | — | idle LOW 처짐 자체는 해결 안 됨 |

→ **1kΩ이 안전 마진 + 전류 부담 사이 최적**

## 9. 결론

- 인터페이스 보드 회로 자체는 무결 (회로 분리 단독 시험으로 입증).
- 원인은 Jetson Orin Nano 캐리어 보드(P3768) 측 GPIO18/GPIO27 헤더 핀의 약 4.3kΩ 풀다운 path.
- 해결: **R17, R27 두 부품을 각 10kΩ → 1kΩ으로 교체** (회로 변경 없이 부품 값만 조정).

## 부록 A. 측정/진단 환경

- 보드: Jetson Orin Nano 개발 보드 super (`p3768-0000+p3767-0005-super`)
- 핀 매핑: BUTTON1=BCM18=PH.07=J41 PIN12=gpiochip0 line 50, BUTTON2=BCM27=PY.00=J41 PIN13=gpiochip0 line 122
- DTBO: `02_interface/dtbo/digital-interface-pinmux.dtbo` (적용 완료)
- 측정 도구: 디지털 멀티미터, `gpioget`, `gpioinfo`, `Jetson.GPIO`(`tests/test_button_raw.py`)

## 부록 B. 관련 파일

- `02_interface/20260429_회로도.pdf` — 회로도
- `02_interface/PINMUX_SETUP.md` — 핀mux/DTBO 적용 작업 기록 전체
- `02_interface/dtbo/digital-interface-pinmux.dts` — DTBO 소스
- `tests/test_button_raw.py` — 라이브 누름 테스트 스크립트

# HW-MS03 Microwave Radar Sensor — Technical Reference

**Ver. V.07** · v2 PDF의 치명적 오류 수정판 · Jetson Orin Nano 키오스크 프로젝트 레퍼런스

> **v3 주요 수정사항** (반드시 알아야 할 부분만)
> 1. `*time` / `*distance` 는 트리머가 아닌 **SMD 저항**. 솔더링 교체로만 변경 가능.
> 2. Jetson.GPIO `pull_up_down` 인자는 **무동작**. 외부 하드웨어 풀다운 필수.
> 3. 외부 풀다운 10 kΩ는 "권장"이 아니라 **필수**. 풀업은 **절대 금지**.
> 4. OUT은 푸시풀이 아니라 **오픈드레인성** (BISS0001 Vo 약한 NPN 베이스 드라이브).
> 5. VCC가 5 V/12 V/24 V 어디든 OUT은 **항상 ~3.3 V** (보드 내장 LDO 후단).
> 6. 동작 주파수 제조사 명시값은 **3.2 GHz** (2.4–5.8 GHz는 마케팅 표기).
> 7. 감지 거리 기본 **~10 m** (20 m는 과장). 모듈 두께 **1.6 mm** (PCB 두께).

---

## 1. Overview

HW-MS03는 Shenzhen HaiWang Sensor Co., Ltd.의 마이크로웨이브 레이더 센서 모듈이다.
시판 시 PIR 센서로 분류되는 경우가 많으나, 동작 원리는 열(적외선) 감지가 아닌
**3.2 GHz 마이크로웨이브의 도플러 반사**를 이용한다 (제조사 데이터 기준; 일부 판매
페이지는 2.4–5.8 GHz로 표기). 온도·습도·조도 변화에 독립적이며 플라스틱·유리 케이스
투과 감지가 가능하다.

> **PIR 센서가 아닙니다.** 마이크로파는 얇은 벽·유리·합판을 투과하므로 키오스크
> 외함 안에 둬도 옆방의 움직임까지 감지될 수 있다. 배치 시 R9 SMD 저항을 낮춰
> 감도를 줄이거나 후면을 금속으로 차폐할 것.

### 주요 구성 부품 (PCB 분석)

| 부품 | 역할 |
|---|---|
| 마이크로스트립 평면 안테나 (S-track) | 3.2 GHz 송수신 |
| 1-트랜지스터 마이크로파 발진기 | 도플러 신호 생성 |
| **BISS0001** (Silvan Chip Electronics) | 신호 처리·타이밍·출력 (PIR용 IC를 그대로 재사용) |
| **7533 LDO (3.3 V)** | OUT 핀이 항상 ~3.3 V로 클램프되는 이유 |
| 직렬 보호 다이오드 | 역전압 보호 |
| **R2** (기본 4.7 kΩ, SMD) | 출력 유지 시간(Hold time) 결정 |
| **R9** (기본 1 MΩ, SMD) | 감도(검출 거리) 결정 |

---

## 2. Electrical Specifications

| 파라미터 | 값 | 비고 |
|---|---|---|
| 동작 원리 | Doppler Microwave Radar | 도플러 위상 변화 감지 |
| 동작 주파수 | **3.2 GHz** (제조사 명시) | 일부 자료 2.4–5.8 GHz, 2.4–14 GHz 표기 (마케팅 표현) |
| VCC 입력 | DC 3.7 V – 24 V | 광범위 입력. 보드 내장 LDO로 안정화 |
| 정적 전류 | ≈ 2.7 mA | 무부하 대기 |
| 동작 전류 | ≈ 3 mA (피크 ≤ 6–7 mA) | 자료별 편차 있음 |
| **OUT HIGH** | **≈ 3.3 V** | LDO 후단 풀업. **VCC와 무관하게 항상 3.3 V** |
| **OUT LOW** | **≈ 0 V (단, 고임피던스에 가까움)** | 푸시풀 아님. 외부 풀다운 없으면 떠 있음 |
| **OUT 출력 단자** | **오픈드레인성 (약한 NPN base drive)** | sink 능력 μA 수준. **직접 부하 구동 불가** |
| **OUT 외부 풀다운** | **10 kΩ to GND 필수** | 없으면 LOW 상태에서도 핀이 떠서 항상 트리거된 것처럼 동작 |
| **OUT 외부 풀업** | **절대 금지** | MCU 내부 weak pull-up도 동작 불능 유발 |
| 감지 거리 | 기본 ~10 m, R9로 0.5–10 m 조정 | R9 = 1 MΩ 기준 (RadioKot 실측) |
| 감지 방향 | 360° 구형 전방향 | 블라인드스팟 없음, 투과 감지 주의 |
| 모듈 크기 | **41 × 20 × 1.6 mm (PCB 두께)** | 부품 포함 시 약 3 mm |
| 초기화 시간 | **약 30초** | 이 기간 모션 신호 무시 필수 |
| 트리거 모드 | 재트리거형 고정 (점퍼 없음) | 홀드 시간 중 추가 모션 시 타이머 재시작 |
| 안테나 | 평면 마이크로스트립 (Patch) | 무지향성 |
| 환경 내성 | 온도·습도·기류·먼지·조도 무관 | PIR 대비 환경 변화에 강함 |
| **RFI 민감도** | **높음** | Wi-Fi 안테나·SMPS·릴레이로부터 ≥ 10 cm 이격 권장 |

### OUT 핀 거동 핵심 정리

BISS0001의 Vo(2번 핀)는 본래 외부 NPN 트랜지스터의 베이스를 구동하기 위해
설계되었다. 따라서 source는 가능하지만 sink 능력은 μA 수준에 불과하다.
이 출력이 보드 내장 7533 LDO(3.3 V) 라인에 약하게 풀업되어 있는 형태이므로:

- **모션 검출(active)**: 출력이 강하게 HIGH(~3.3 V)로 끌어올려짐.
- **대기(inactive)**: 출력이 LOW로 강하게 떨어지지 않고, **고임피던스에 가까운 상태**가 됨.
- **외부 풀다운 10 kΩ가 없으면**: 노이즈/누설 전류로 핀이 HIGH 근처로 떠서
  계속 트리거되는 것처럼 보임.
- **외부 풀업이나 MCU 내부 풀업이 있으면**: BISS0001이 핀을 LOW로 끌어내릴 수
  없어서 검출이 동작하지 않음.

---

## 3. Pinout

| Pin # | PCB 실크 | 신호 | 전압 | 비고 |
|---|---|---|---|---|
| 1 (좌) | GND | Ground | 0 V | 시스템 공통 GND |
| 2 (중) | OUT | Digital Output | 3.3 V / 고임피던스 | HIGH = 모션 감지 |
| 3 (우) | +Vin | Power Input (VCC) | DC 3.7–24 V | Jetson 5 V 직결 가능 |

V.01 공식 다이어그램과 V.06 실물 PCB 핀 순서 일치 확인.

---

## 4. Wiring — Jetson Orin Nano GPIO Direct

### Circuit A : GPIO Direct (기본 구성)

| HW-MS03 핀 | 와이어 색 | Jetson 40-pin Header | 비고 |
|---|---|---|---|
| Pin 1 — GND | Black | Pin 6 (GND) | 공통 GND |
| Pin 2 — OUT | Green | Pin 7 (GPIO09) | **외부 10 kΩ Pull-down to GND 필수** |
| Pin 3 — +Vin | Red | Pin 2 또는 Pin 4 (5 V) | 5 V 직결 권장 (3.3 V 직결도 동작은 함) |

```
HW-MS03 V.06              Jetson Orin Nano 40-pin Header
+------------+            +---------------------------+
| Pin1 GND   |---[Black]------------>| Pin 6  GND       |
|            |                       |                  |
| Pin2 OUT   |---[Green]---+-------->| Pin 7  GPIO09 IN |
|            |             |         |                  |
| Pin3 +Vin  |---[Red]------------>  | Pin 2  5V        |
+------------+             |         +---------------------------+
                           |
                       [10 kΩ]  ← 필수 외부 풀다운
                           |
                          GND
                           |
                       [100 nF] ← 권장 RFI 억제 캡 (OUT-GND)
                           |
                          GND
```

> **OUT은 LDO 후단 ~3.3 V**이므로 Jetson 3.3 V 입력과 직접 호환된다.
> 레벨 시프터 불필요. VCC를 5 V로 줘도 OUT은 5 V로 나오지 않는다.

### 전원 권장사항

- VCC를 Jetson 5 V 핀에서 직접 끌어올 경우, **VCC–GND에 10 µF + 100 nF 디커플링** 권장.
- Jetson 5 V 라인이 깨끗하지 않다면 별도 외부 5 V LDO 후단에서 공급.
- HW-MS03 모듈을 Wi-Fi 안테나·SMPS·디스플레이 백라이트 인버터로부터 **≥ 10 cm 이격**.

### Circuit B : NPN Transistor Buffer (릴레이·버저 등 고부하 구동 시)

| Reference | 부품 | 값/사양 | 용도 |
|---|---|---|---|
| R_base | Resistor | 1 kΩ | OUT → NPN Base 전류 제한 |
| R_pull | Resistor | 10 kΩ | OUT Pull-down (필수) |
| Q1 | NPN Transistor | 2N2222 / S8050 / BC547 | Output 버퍼 |
| D1 | Diode | 1N4148 | 릴레이 플라이백 (릴레이 사용 시만) |
| C1 | Capacitor | 100 nF | VCC 바이패스 (VCC 핀 근처 배치) |

---

## 5. 조정 가능 파라미터 — **SMD 저항 교체 방식 (트리머 아님)**

> **중요**: 이전 v2 문서에는 *time / *distance가 가변저항(트리머)인 것처럼
> 기재되어 있었으나, **실제로는 SMD 저항**이며 시계방향 회전으로 조정할 수 없다.
> 값을 바꾸려면 **솔더링으로 SMD 저항을 교체**해야 한다.

| PCB 실크 | 위치 | 부품 | 기본값 | 기능 |
|---|---|---|---|---|
| `*R2` (`*time`) | Front | SMD 저항 | 4.7 kΩ | 출력 유지 시간 (Hold time) |
| `*R9` (`*distance`) | Back | SMD 저항 | 1 MΩ | 감도 / 검출 거리 |
| `Rin` | Back | SMD 저항 | (공장값) | 입력 임피던스. **건드리지 말 것** |
| `Ro` (`cut-out`) | Back | SMD 저항 | (공장값) | 출력 컷오프 임계값. **건드리지 말 것** |

### R2 교체별 홀드 타임 (Soloshin Wiki 실측)

| R2 값 | 출력 유지 시간 |
|---|---|
| 4.7 kΩ (기본) | ~2 초 |
| 150 kΩ | ~34 초 |
| 250 kΩ | ~57 초 |
| 470 kΩ | ~107 초 |

### R9 교체별 감지 거리 (Soloshin Wiki / RadioKot 실측)

| R9 값 | 감지 거리 |
|---|---|
| 1 MΩ (기본) | ~10 m |
| 100 kΩ | ~1 m |
| 56 kΩ | ~0.5 m |
| < 47 kΩ | 동작 불능 |

키오스크 현장 튜닝이 필요하다면, 설치 전에 R2/R9 값을 미리 결정하여 **공장 또는
재작업 공정에서 SMD 교체**해 두는 것이 유일한 방법이다.

---

## 6. Jetson GPIO Python 샘플 코드

```python
# pip install Jetson.GPIO
import Jetson.GPIO as GPIO
import time

# ============================================================
# 중요: Jetson.GPIO 라이브러리는 pull_up_down 인자를 무시한다
# ("Ignore pull_up_down" 경고 출력). SW로는 풀다운을 잡을 수 없으므로
# 반드시 OUT 핀과 GND 사이에 외부 10 kΩ 풀다운 저항을 달 것.
# 핀 mux 레벨에서 풀다운을 켜고 싶다면 DTBO에 다음 속성을 추가한다:
#   nvidia,pull = <TEGRA_PIN_PULL_DOWN>
# DTBO + 외부 저항을 함께 두는 것이 가장 안전하다.
# ============================================================

PIR_PIN = 7  # Physical Pin 7 = GPIO09 (인터페이스 보드 매핑에 맞게 조정)

GPIO.setmode(GPIO.BOARD)
GPIO.setup(PIR_PIN, GPIO.IN)   # pull_up_down 인자는 적지 않음 (어차피 무시됨)

# 워밍업 대기 (필수 — ~30초 동안 false-trigger 정상)
print("[MS03] Warming up... 30s")
time.sleep(30)
print("[MS03] Ready.")

def on_motion(channel):
    if GPIO.input(channel) == GPIO.HIGH:
        print("[MS03] MOTION DETECTED")
        # → MAIN VIEW → LIVE VIEW 화면 전환 트리거
    else:
        print("[MS03] No motion")

# Edge detection (RISING 추천 — 트리거 시작 시점만 잡으면 충분)
# bouncetime은 ms 단위. 홀드타임 2초보다 짧게 설정.
GPIO.add_event_detect(PIR_PIN, GPIO.RISING,
                      callback=on_motion,
                      bouncetime=300)

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    pass
finally:
    GPIO.cleanup()
```

### 동작 확인 절차

1. 외부 10 kΩ 풀다운이 OUT–GND에 연결되어 있는지 멀티미터로 저항 측정.
2. VCC 인가 후 30초 동안 출력 무시.
3. 손을 모듈 앞에서 천천히 움직였을 때 OUT 핀에서 ~3.3 V 펄스가 나오는지
   오실로스코프 또는 LED로 확인.
4. `gpioinfo` 또는 `cat /sys/kernel/debug/gpio` 로 핀 mux 풀 설정 확인.

---

## 7. 키오스크 적용 주의사항

| 항목 | 문제 | 대응 |
|---|---|---|
| **30초 초기화** | 전원 인가 후 ~30초 false trigger | 부팅 시퀀스에서 GPIO read를 30초 후 시작 |
| **풀다운 누락** | OUT이 떠서 항상 트리거된 것처럼 보임 | **외부 10 kΩ 풀다운 필수** |
| **풀업 결선** | BISS0001 Vo가 LOW로 끌어내리지 못함 | MCU 내부 weak pull-up 포함 **풀업 절대 금지** |
| **마이크로웨이브 투과** | 플라스틱·유리·얇은 벽 투과 감지 | 후면 금속 차폐 / R9 낮춰 감도 ↓ (예: 100 kΩ → 1 m) |
| **복수 설치 간섭** | 동일 공간 2개 이상 상호 간섭 | 유닛 간 최소 1 m 이상 이격 필수 |
| **출력 전류 미약** | OUT 핀 직접 부하 구동 불가 | 릴레이·버저 구동 시 NPN 버퍼 사용 (Circuit B) |
| **RF 노이즈** | Wi-Fi/SMPS/릴레이 노이즈로 false trigger | 모듈을 RF 소스로부터 ≥ 10 cm 이격, 외부 LDO + 디커플링 |
| **전원 품질** | DC 전원 리플 시 오감지 가능 | 정격 DC 전원, VCC–GND 10 µF + 100 nF 디커플링 |
| **Jetson.GPIO pull_up_down 무동작** | 코드의 `pull_up_down=GPIO.PUD_DOWN` 무시됨 | 외부 하드웨어 풀다운으로 해결 (위 표 참고) |
| **버전 차이** | V.01–V.06 외 다른 버전 가능 | 수령 시 PCB 실크 레이블 육안 확인 후 연결 |

---

## 8. HW-MS03 vs 일반 PIR 센서 비교

| 비교 항목 | HW-MS03 (Microwave Radar) | 일반 PIR |
|---|---|---|
| 감지 원리 | Doppler 마이크로파 반사 | 적외선(열) 변화 |
| 체온 의존성 | 없음 | 필요 |
| 케이스 투과 | **가능** (주의 필요) | 불가 |
| 조명 영향 | 없음 | 없음 |
| 온도 영향 | 없음 | 있음 (고온 환경 오감지) |
| 감지 각도 | 360° 구형 전방향 | ~120° 원추형 |
| 감지 거리 | 0.5 ~ 10 m (R9 SMD 교체) | 3 ~ 7 m (고정) |
| 초기화 시간 | ~30초 | ~5초 |
| 출력 단자 특성 | 오픈드레인성 (μA 수준 sink) | 푸시풀 (수 mA) |
| RF 노이즈 민감도 | 높음 | 낮음 |
| 오감지 요인 | 투과 감지, RF 노이즈, 전원 노이즈 | 바람·동물·온도 변화 |

---

## 9. 참고한 1차 소스

신뢰도 ★★★ (제조사 / 역공학):
- HaiWang Sensor 공식: <https://www.szhaiwang.com/HW-MS03-Microwave-Sensor-Module-Motion-Sensor-LED-Switch-with-10m-Distance-pd515733668.html>
- Hackaday.io 역공학: <https://hackaday.io/project/198178-radar-sensor-improvements-intelligent-sensing>
- Soloshin Wiki (러시아): <https://wiki.soloshin.su/iot/firmware/tasmota/sonoff/rfr2/haiwang/hw-ms03>
- BISS0001 데이터시트: <https://www.ladyada.net/media/sensors/BISS0001.pdf>

신뢰도 ★★ (튜토리얼 / 사용자):
- Electropeak Arduino: <https://electropeak.com/learn/interfacing-hw-ms03-motion-detection-module-with-arduino/>
- Arduino Forum: <https://forum.arduino.cc/t/hw-ms03-radar-sensor/623740>
- MySensors Forum: <https://forum.mysensors.org/topic/3568/microwave-radar-module-as-pir-replacement>
- RadioKot Forum (러시아): <https://m.radiokot.ru/forum/viewtopic.php?p=4148349>

Jetson 관련 ★★★:
- NVIDIA Forum — Jetson.GPIO pull_up_down 무시: <https://forums.developer.nvidia.com/t/gpio-pull-up-down-mode/174540>
- NVIDIA Forum — GPIO pull down resistor: <https://forums.developer.nvidia.com/t/gpio-pull-down-resistor/142529>
- GitHub jetson-gpio Issue #4: <https://github.com/NVIDIA/jetson-gpio/issues/4>
- JetsonHacks — Jetson Nano GPIO: <https://jetsonhacks.com/2019/06/07/jetson-nano-gpio/>

---

*HW-MS03 Technical Reference v3 · Jetson Orin Nano Telescope Kiosk Project · v2 문서의 트리머/풀다운/Jetson.GPIO 오류 수정판*

# Jetson Orin Nano 인터페이스 보드 - 입력단 구현 문서

> 작성일: 2026-03-06
> 대상: 커스텀 인터페이스 보드 (40핀 헤더 연결)
> 범위: 입력 페리페럴 (버튼 2개, PIR 센서 1개)

---

## 1. 시스템 개요

Jetson Orin Nano / Super Dev Kit의 40핀 GPIO 헤더에 연결되는 커스텀 인터페이스 보드의 입력단 소프트웨어.
현재 단계에서는 **입력 감지 → 콘솔 출력**만 수행하며, 출력 장치(팬, 리프트, 시리얼 통신 등)는 추후 구현 예정.

### 1.1 입력 장치 목록

| 장치 | 용도 | 타입 |
|------|------|------|
| BUTTON1 (Zoom In) | 카메라 줌 인 제어 | 방수 19mm 스테인리스, Momentary NO |
| BUTTON2 (Zoom Out) | 카메라 줌 아웃 제어 | 방수 19mm 스테인리스, Momentary NO |
| PIR (HW-MS03) | 모션 감지 | 마이크로웨이브 도플러 센서 |

### 1.2 동작 방식

- **버튼**: 누르고 있는 동안 동작하는 방식 (press/release 감지, 누른 시간 측정)
- **PIR**: HIGH 신호 = 모션 감지, LOW = 대기 상태. 쿨다운으로 재트리거 억제

---

## 2. 하드웨어 분석

### 2.1 핀 매핑

| 페리페럴 | BCM GPIO | 40핀 헤더 핀 | Linux GPIO | Jetson SoC 핀 | 기본 기능 | 비고 |
|---------|----------|------------|-----------|--------------|----------|------|
| BUTTON1 | GPIO18 | Pin 12 | GPIO 50 | GP122 | I2S0_SCLK | 풀업 저항, Active LOW |
| BUTTON2 | GPIO27 | Pin 13 | GPIO 122 | GP36 | SPI1_SCK | 풀업 저항, Active LOW |
| PIR | GPIO24 | Pin 18 | GPIO 125 | GP39 | SPI1_CS0 | 3.3V 직결 |

> `Jetson.GPIO` 라이브러리 소스(`gpio_pin_data.py`)에서 Jetson Orin Nano의 BCM 매핑 확인 완료.
> Orin Nano는 내부적으로 JETSON_ORIN_NX_PIN_DEFS와 동일한 핀 정의를 사용한다.

### 2.2 회로 특성

**버튼 회로**
- Momentary NO (Normally Open) 타입
- 버튼 누르면 GPIO → GND 연결 (Active LOW 의도)
- 인터페이스 보드에서 레벨 변환 처리 완료

**버튼 풀업 저항 문제 (미해결)**

회로도 확인 결과, 버튼 GPIO 라인에 **풀업 저항이 없다.**
Jetson Orin Nano 측도 해당 핀들의 Power-on Default가 **z (High-Z, 고임피던스)** 이며,
내부 풀업이 기본 비활성 상태이다.

| 확인 항목 | 상태 |
|----------|------|
| 인터페이스 보드 풀업 저항 | **없음** (회로도에 미표기) |
| Jetson 핀 Power-on Default | **z** (고임피던스, 플로팅) |
| Jetson 내부 풀업 기본값 | **비활성** |
| `Jetson.GPIO` PUD_UP 파라미터 | **Orin 계열에서 동작하지 않음** |
| Device Tree 수정으로 내부 풀업 | 가능하나 복잡 (pinmux + gpio dtsi 모두 수정 필요) |

**현재 상태의 문제:**
```
버튼 미누름 시: GPIO ── (연결 없음) ── 플로팅 ⚠️ → 노이즈에 의한 오동작
버튼 누름 시:   GPIO ── GND ── LOW ✅
```

**해결:** 인터페이스 보드에 **3.3V 풀업 저항 (10kΩ~100kΩ)** 추가 필요.
Jetson 데이터시트에서 풀업/풀다운 저항은 >50kΩ (weak pull) 권장.
→ 변경요청서(CR-2026-001)에 포함하여 보드 업체에 요청 진행.

**PIR 센서 (HW-MS03)**
- 마이크로웨이브 도플러 방식 (적외선 PIR과 다름)
- 3핀: VCC, GND, OUT
- 출력: HIGH(3.3V) = 모션 감지, LOW(0V) = 대기
- 출력 지연: ~2초, 초기화 시간: ~30초
- 소비 전류: ≤6mA
- 풀업/풀다운 불필요 (센서가 능동적으로 HIGH/LOW 구동)

**PIR 센서 전원 문제**

| 항목 | 내용 |
|------|------|
| 공식 VCC 범위 | **3.7V ~ 24V** (제조사 HaiWang 공식 사양) |
| 회로도 현재 설계 | 3.3V 직결 |
| 문제 | **3.3V는 최소 사양(3.7V) 미달** — 동작 불안정, 감지 거리 감소 가능 |
| 해결 | **5V 레일에서 공급** (인터페이스 보드 내부 5V 레일 활용) |
| OUT 핀 호환성 | VCC가 5V여도 OUT 출력은 **항상 3.3V** → Jetson GPIO 직결 가능, 레벨 변환 불필요 |

```
[권장 연결]
5V 레일  ──→ HW-MS03 VCC     (3.3V가 아닌 5V로 변경)
GND      ──→ HW-MS03 GND
              HW-MS03 OUT (3.3V) ──→ GPIO24 (Pin 18) 직결
```

→ 변경요청서(CR-2026-001)에 PIR 전원 변경 포함.

### 2.3 전원 구조 (회로도 기반)

인터페이스 보드는 **J3 커넥터 (NW-VH3.96-2A)** 를 통해 외부 전원을 공급받는다.

**외부 입력 전압: 12V (J3 VIN)**

| 전원 레일 | 전압 | 소스 | 용도 |
|----------|------|------|------|
| VIN | **12V** | J3 외부 입력 | 보드 메인 전원, 레귤레이터 입력 |
| +5V/7A | 5V | J3 또는 온보드 변환 | BTS7960B H-Bridge 모터, 팬 구동 |
| +3.3V | 3.3V | LMS116MHX/NOPB (12V→3.3V) | GPIO 로직, PIR, BME280, RS232C |

- LMS116MHX/NOPB: TI 벅 레귤레이터, 입력 4.5V~17V → 3.3V 출력
- Jetson 40핀 헤더 GPIO는 모두 3.3V 로직 레벨
- 외부 전원: 12V 25A (300W) SMPS 연결 예정

### 2.4 Jetson 전원 호환성 문제

인터페이스 보드는 **이전 Jetson Nano (5V/4A)** 기준으로 설계되었으나, 현재 대상은 **Jetson Orin Nano Super Dev Kit**이다.

**Jetson Orin Nano Super 전원 사양:**

| 항목 | 사양 |
|------|------|
| DC 잭 입력 | 9V ~ 20V |
| 기본 제공 어댑터 | 19V / 2.37A |
| 최대 소비 전력 | 25W |
| 내부 동작 전압 | 5V (VDD_5V_SYS) |
| 40핀 헤더 5V (Pin 2, 4) | 5V 입출력 가능, 최대 1A |

**호환성 문제:**

```
[기존 설계 - Jetson Nano]
12V → CONVERTER → 5V/7A → 40핀 Pin 2,4 → Jetson Nano (5V/4A) ✅

[현재 상황 - Jetson Orin Nano Super]
12V → CONVERTER → 5V/7A → 40핀 Pin 2,4 → Orin Nano (9V~20V 필요) ❌
```

- 기존 5V 출력으로는 Orin Nano에 전원 공급 불가 (9V 미만)
- 40핀 헤더 5V 핀은 1A 제한으로 전력 부족 (25W 필요)
- **인터페이스 보드 변경 필요**: 12V/3A 출력을 Jetson DC 잭으로 공급하는 경로 추가
- 변경요청 문서: `claudedocs/change-request-power-output.md` 참조

### 2.5 GPIO 모드 설정 (필수)

3개 입력 핀 모두 기본적으로 I2S/SPI 기능에 할당되어 있으므로, **GPIO 모드로 재설정이 필수**이다.

| 핀 | 기본 기능 | 변경 필요 |
|----|----------|----------|
| Pin 12 (BCM 18) | I2S0_SCLK | I2S0 비활성화 → GPIO |
| Pin 13 (BCM 27) | SPI1_SCK | SPI1 비활성화 → GPIO |
| Pin 18 (BCM 24) | SPI1_CS0 | SPI1 비활성화 → GPIO |

Jetson 데이터시트에 "All the interface signal pins (I2S, I2C, SPI, UART, and AU clock) can also be configured as GPIOs" 로 명시되어 있어 GPIO 전환에 문제없다.

**설정 방법:**

```bash
# 1. Jetson IO 도구로 핀 기능 확인/변경
sudo /opt/nvidia/jetson-io/jetson-io.py

# 2. I2S0, SPI1 기능을 비활성화하고 GPIO 모드로 설정
# 3. 재부팅 후 적용 확인
sudo gpioinfo | grep -E "50|122|125"
```

**주의:** Pin 13(SPI1_SCK)과 Pin 18(SPI1_CS0)은 같은 SPI1 버스에 속하므로, SPI1을 비활성화하면 두 핀 모두 GPIO로 사용 가능해진다.

---

## 3. 소프트웨어 구조

### 3.1 파일 구성

```
interface/
  src/
    config.py          # 핀 번호, 타이밍 상수 정의
    button.py          # ButtonInput 클래스 (press/release 감지)
    pir.py             # PirInput 클래스 (모션 감지)
    main.py            # 진입점 - 초기화, 이벤트 등록, 시그널 처리
  requirements.txt     # Jetson.GPIO>=2.1.0
  claudedocs/
    input-peripherals-implementation.md   # 본 문서
```

### 3.2 의존성

- `Jetson.GPIO>=2.1.0` (Jetson에 기본 설치됨)
- 추가 외부 라이브러리 없음

---

## 4. 구현 상세

### 4.1 config.py - 설정 상수

| 상수 | 값 | 설명 |
|------|----|------|
| `BUTTON1_PIN` | 18 | Zoom In 버튼 (BCM GPIO18) |
| `BUTTON2_PIN` | 27 | Zoom Out 버튼 (BCM GPIO27) |
| `PIR_PIN` | 24 | PIR 센서 (BCM GPIO24) |
| `DEBOUNCE_MS` | 200 | 버튼 디바운스 시간 (밀리초) |
| `PIR_COOLDOWN_SEC` | 3 | PIR 재감지 억제 시간 (초) |

### 4.2 button.py - ButtonInput 클래스

**역할**: 단일 Momentary 버튼의 press/release 이벤트 처리

**구현 방식**:
- `GPIO.BOTH` 에지 감지로 FALLING(누름)과 RISING(놓음) 모두 감지
- `bouncetime=DEBOUNCE_MS`로 하드웨어 바운싱 필터링
- 콜백 내부에서 `GPIO.input()`으로 현재 레벨을 읽어 press/release 구분
  - LOW → PRESSED (Active LOW 구성)
  - HIGH → RELEASED

**누른 시간 측정**:
- press 시 `time.time()` 기록
- release 시 현재 시간과의 차이를 계산하여 duration 출력
- 추후 줌 속도 제어 등에 활용 가능

**콜백 속성** (추후 확장용):
- `on_press`: 버튼 누를 때 호출될 콜백 (인자 없음)
- `on_release(duration)`: 버튼 놓을 때 호출될 콜백 (누른 시간 전달)

**주요 메서드**:

| 메서드 | 설명 |
|--------|------|
| `__init__(pin, name)` | GPIO 입력 핀 설정, 이름 지정 |
| `start()` | `GPIO.add_event_detect()` 등록 |
| `stop()` | `GPIO.remove_event_detect()` 해제 |

### 4.3 pir.py - PirInput 클래스

**역할**: HW-MS03 PIR 센서의 모션 감지 이벤트 처리

**구현 방식**:
- `GPIO.RISING` 에지 감지 (LOW→HIGH 전환 = 모션 감지)
- 쿨다운: `time.time()` 기반으로 마지막 감지 후 `PIR_COOLDOWN_SEC` 이내 재트리거 무시
- 쿨다운 내 이벤트는 콜백에서 조기 리턴하여 무시

**콜백 속성** (추후 확장용):
- `on_motion`: 모션 감지 시 호출될 콜백 (인자 없음)

**주요 메서드**:

| 메서드 | 설명 |
|--------|------|
| `__init__(pin)` | GPIO 입력 핀 설정 |
| `start()` | `GPIO.add_event_detect()` 등록 |
| `stop()` | `GPIO.remove_event_detect()` 해제 |

### 4.4 main.py - 진입점

**실행 흐름**:

```
1. GPIO.setmode(GPIO.BCM)        # BCM 넘버링 모드 설정
2. ButtonInput(18, "ZOOM_IN")    # 줌 인 버튼 생성
3. ButtonInput(27, "ZOOM_OUT")   # 줌 아웃 버튼 생성
4. PirInput(24)                  # PIR 센서 생성
5. signal 핸들러 등록             # SIGINT(Ctrl+C), SIGTERM 처리
6. 모든 입력 start()             # 이벤트 감지 시작
7. threading.Event.wait()        # 메인 스레드 대기 (CPU 사용 없음)
8. 시그널 수신 시:
   - stop_event.set()            # 대기 해제
   - 모든 입력 stop()            # 이벤트 감지 해제
   - GPIO.cleanup()              # GPIO 자원 정리
```

**메인 루프 방식**: `threading.Event.wait()`를 사용하여 busy-wait 없이 대기.
시그널 핸들러에서 `stop_event.set()`을 호출하면 즉시 깨어나 정리 루틴 실행.

---

## 5. 콘솔 출력 형식

```
Interface board input handler started. Press Ctrl+C to quit.
[2026-03-06 14:30:01] ZOOM_IN  PRESSED
[2026-03-06 14:30:02] ZOOM_IN  RELEASED (held 1.05s)
[2026-03-06 14:30:05] ZOOM_OUT PRESSED
[2026-03-06 14:30:05] ZOOM_OUT RELEASED (held 0.32s)
[2026-03-06 14:30:10] PIR      MOTION DETECTED
^C
Shutting down...
GPIO cleaned up. Exiting.
```

- 타임스탬프: `YYYY-MM-DD HH:MM:SS` 형식
- 장치 이름: 8자 좌측 정렬로 정리된 출력
- 버튼 release 시 누른 시간(초, 소수점 2자리) 표시

---

## 6. 실행 및 검증

### 6.1 실행 명령

```bash
cd /path/to/interface
sudo python3 src/main.py
```

`sudo` 필요: Jetson.GPIO는 root 권한 또는 gpio 그룹 소속 필요.

### 6.2 검증 체크리스트

| 항목 | 예상 결과 | 확인 |
|------|----------|------|
| BUTTON1 누름 | `ZOOM_IN PRESSED` 출력 | [ ] |
| BUTTON1 놓음 | `ZOOM_IN RELEASED (held Xs)` 출력 | [ ] |
| BUTTON2 누름 | `ZOOM_OUT PRESSED` 출력 | [ ] |
| BUTTON2 놓음 | `ZOOM_OUT RELEASED (held Xs)` 출력 | [ ] |
| PIR 모션 감지 | `PIR MOTION DETECTED` 출력 | [ ] |
| PIR 쿨다운 | 3초 내 재감지 시 출력 없음 | [ ] |
| Ctrl+C | `Shutting down...` → `GPIO cleaned up.` 출력 후 정상 종료 | [ ] |

### 6.3 트러블슈팅

**버튼 PRESSED/RELEASED가 반대로 동작하는 경우**:
- 실제 보드의 풀업/풀다운 구성이 예상과 다를 수 있음
- `GPIO.input(pin)` 값을 직접 확인하여 평상시 레벨 파악
- `button.py`의 `_callback`에서 `GPIO.LOW`/`GPIO.HIGH` 조건을 반전

**이벤트가 감지되지 않는 경우**:
- `sudo /opt/nvidia/jetson-io/jetson-io.py`로 핀이 GPIO 모드인지 확인
- 해당 핀이 I2S/SPI 기능에 점유되어 있으면 GPIO로 변경 필요
- 배선 확인: GND 연결 여부, 3.3V 공급 여부

**디바운스 문제 (중복 이벤트)**:
- `config.py`의 `DEBOUNCE_MS` 값을 300~500으로 증가시켜 테스트

---

## 7. 추후 확장 계획

### 7.1 카메라 줌 연동

현재 버튼은 콘솔 출력만 수행. 추후 카메라 줌 명령 연동 시:

```python
# 예시: on_press / on_release 콜백 연결
btn_zoom_in.on_press = lambda: camera.zoom_in_start()
btn_zoom_in.on_release = lambda duration: camera.zoom_in_stop()
```

`ButtonInput`의 콜백 속성(`on_press`, `on_release`)이 이미 준비되어 있으므로
카메라 제어 모듈만 구현하여 연결하면 된다.

### 7.2 팬 제어 (추후 구현)

#### 7.2.1 팬 사양

| 항목 | 사양 |
|------|------|
| 모델 | YeHAUS HFD0602512B2M |
| 크기 | 60x60x25mm |
| 전압 | **12V DC** |
| 배선 | **2선식** (VIN, GND / PWM 없음) |
| 베어링 | 볼 베어링 |
| 수량 | 2개 (FAN1, FAN2) |

#### 7.2.2 회로도 분석 (인터페이스 보드)

```
GPIO (3.3V) ──→ 트랜지스터 (N-ch MOSFET) ──→ FAN 커넥터 (2핀)
                 게이트: 3.3V 풀업                 VIN: 12V (VIN 레일)
                                                   GND: GND
```

- 트랜지스터로 3.3V GPIO 신호를 스위칭하여 12V 팬 전원을 on/off 제어
- 2선식이므로 **PWM 속도 제어 불가, on/off만 가능**
- 팬 전원은 VIN(12V) 레일에서 직접 공급

#### 7.2.3 핀 매핑 (Orin Nano 확인 완료)

| 팬 | BCM GPIO | 40핀 헤더 핀 | Linux GPIO | Jetson 기본 기능 | Power-on Default |
|----|---------|------------|-----------|----------------|-----------------|
| FAN1 | BCM 6 | **Pin 31** | GPIO 106 | GPIO011 (GP66) | pd (풀다운) |
| FAN2 | BCM 12 | **Pin 32** | GPIO 41 | GPIO007 (GP113_PWM7) | pd (풀다운) |

> `Jetson.GPIO` 라이브러리 소스에서 Orin Nano BCM 매핑 확인 완료.
> Pin 32(BCM 12)는 PWM 기능도 지원하나, 2선식 팬이므로 활용 불가.

#### 7.2.4 인터페이스 보드 변경 필요 여부

| 항목 | 변경 필요 | 사유 |
|------|----------|------|
| 팬 전원 (12V) | **불필요** | VIN 레일(12V)에서 공급, 팬 정격(12V)과 일치 |
| 트랜지스터 스위칭 회로 | **불필요** | 3.3V GPIO로 제어, Orin Nano도 3.3V 로직 |
| GPIO 핀 매핑 | **불필요** | BCM 6→Pin 31, BCM 12→Pin 32는 Orin Nano에서도 동일 매핑 |
| GPIO 모드 설정 | **확인 필요** | Pin 31(GPIO011), Pin 32(GPIO007)은 기본 GPIO 기능이므로 별도 설정 불필요할 가능성 높음. 단, `jetson-io.py`로 확인 권장 |

**결론: 팬 연결은 인터페이스 보드 변경 없이 현재 회로 그대로 사용 가능.**

#### 7.2.5 소프트웨어 구현 예정

```python
# fan.py (추후 구현)
class FanOutput:
    def __init__(self, pin, name):
        GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)  # 초기: 팬 OFF
    def on(self):
        GPIO.output(self.pin, GPIO.HIGH)
    def off(self):
        GPIO.output(self.pin, GPIO.LOW)
```

- `config.py`에 `FAN1_PIN = 6`, `FAN2_PIN = 12` 추가 예정
- PIR 모션 감지 → 팬 on 등의 연동은 콜백으로 연결

### 7.3 기타 출력 장치 (추후 구현)

추후 구현 예정인 출력 페리페럴:
- 리프트 모터 제어 (BTS7960B H-Bridge, GPIO13/GPIO19)
- 시리얼 통신 (RS232C)
- BME280 환경 센서 (I2C, GPIO02/GPIO03)

이들은 별도 모듈로 구현하되, PIR의 `on_motion` 콜백이나 버튼의 `on_press`/`on_release` 콜백을 통해 입력단과 연결할 수 있다.

### 7.4 EventBus 도입 시점

현재는 입력 3개뿐이므로 직접 콜백 연결로 충분.
출력 장치(팬, 리프트, 시리얼)가 추가되어 입력-출력 간 연결이 복잡해지면 EventBus 패턴 도입을 검토.

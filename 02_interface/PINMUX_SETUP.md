# 인터페이스보드 핀mux 설정 작업 기록

작성일: 2026-04-29
대상 보드: Jetson Orin Nano (Super) — `p3768-0000+p3767-0005-super`
대상 인터페이스: 자체 디지털 인터페이스 보드 (회로도: `20260429_회로도.pdf`)

## 요약

인터페이스 보드의 BUTTON1, BUTTON2를 비롯한 GPIO 핀들이 Linux GPIO API로 정상 동작하지 않는 문제를 진단하고, 디바이스트리 오버레이(DTBO)로 핀mux를 명시적으로 설정해 해결했다. 카메라 IMX219 오버레이는 그대로 보존된다.

## 1. 문제

`src/button.py` + `tests/test_button_raw.py`로 BUTTON1(BCM18, Pin12), BUTTON2(BCM27, Pin13)를 입력으로 잡고 사용하려 했으나:

- BUTTON1: 시점에 따라 idle HIGH로 잡혔다가 LOW로 굳음. 누름 동작이 일관되게 잡히지 않음.
- BUTTON2: idle 거의 항상 LOW. 멀티미터로 보드 측 신호선 측정 시 약 1V (정상이라면 0V 또는 3.3V).

## 2. 진단

### 2-1. 회로 점검 (멀티미터)
SMW250-02 커넥터 분리 후 BUTTON 신호선과 GND 사이 DC 전압 측정:

| 라인 | 측정값 | 해석 |
|---|---|---|
| BUTTON1 | 3.3V | 외부 풀업 정상 동작 (회로 OK) |
| BUTTON2 | 1V | 이상 — 풀업도 GND도 아님 |

→ BUTTON1 회로는 정상. BUTTON2 신호선이 어딘가에서 LOW 쪽으로 끌리고 있음.

### 2-2. 핀 식별 (gpiochip0)
`gpioinfo`로 SoC 핀 매핑 확인:

| 역할 | BCM | 헤더핀 | SoC | gpiochip0 line |
|---|---|---|---|---|
| BUTTON1 | 18 | 12 | PH.07 (`SOC_GPIO41_PH7`) | 50 |
| BUTTON2 | 27 | 13 | PY.00 (`SPI3_SCK_PY0`) | 122 |
| PIR | 24 | 18 | PY.03 (`SPI3_CS0_PY3`) | 125 |
| FAN1 | 6 | 31 | PQ.06 (`SOC_GPIO33_PQ6`) | 106 |
| FAN2 | 12 | 32 | PG.06 (`SOC_GPIO19_PG6`) | 41 |

핵심 단서: BUTTON2 핀의 default SFIO가 **SPI3_SCK** 였다.

### 2-3. SFIO 활성 확인 (라이브 모니터)
`gpiod`로 BUTTON2 라인을 200Hz 폴링한 결과: 5~30ms 간격으로 1↔0를 빠르게 토글링.

→ **SPI3_SCK 클럭 신호가 출력 중**. 멀티미터 1V는 이 토글의 평균값이었다. (SPI3 컨트롤러는 비활성으로 보였지만 패드 mux는 SPI3_SCK 그대로 살아있어 노이즈/누설로 토글)

### 2-4. 가설별 검증
| 가설 | 결론 | 근거 |
|---|---|---|
| input buffer 비활성 | 일부 적용 (PH.07) | FAN 핀들은 HIGH로 잘 읽힘 → input buffer는 핀별로 다름 |
| gpiod/Python 상태 오염 | 기각 | `gpioget` CLI도 동일 결과 |
| 회로 단락/풀업 부재 | 기각 | 멀티미터 측정으로 BUTTON1=3.3V 확인 |
| **default SFIO 잔류** | **확정** | BUTTON2가 SPI3_SCK로 토글링하는 라이브 증거 |

### 2-5. 런타임 우회 시도 (실패)
`/sys/kernel/debug/pinctrl/2430000.pinmux/pinmux-select`에 `spi3_sck_py0 rsvd1` 쓰기 → exit=0이지만 `pinmux-pins`는 여전히 `MUX UNCLAIMED`. **런타임 변경은 등록 안 됨**. → 영구 적용 위한 DTBO 필요.

## 3. 근본 원인

NVIDIA L4T 부트로더 (MB1)는 일부 핀의 패드 mux를 SFIO로 두고 boot 한다. JetPack의 `jetson-io`가 생성하는 `tegra234-...-hdr40.dtbo`가 헤더 핀들을 명시적으로 GPIO/SFIO로 재설정하지만, 현재 `extlinux.conf`의 `OVERLAYS`에는 카메라 오버레이만 들어있고 hdr40 오버레이가 빠져 있어, BUTTON2/PIR 핀이 SPI3 SFIO 상태 그대로 부팅됐다.

또한 jetson-io의 기존 hdr40 오버레이(`/boot/tegra234-p3767-0000+p3509-a02-hdr40.dtbo`)를 그대로 적용하면 Pin13가 `function="spi3"`로 설정되어 오히려 우리 BUTTON2를 망친다. 그래서 **인터페이스 보드 전용 DTBO를 신규 작성**한다.

## 4. 해결책 — Custom DTBO

`02_interface/dtbo/digital-interface-pinmux.dts` 작성. 핵심 구조 (jetson-io의 hdr40 dtbo와 동일 패턴):

```dts
/dts-v1/;
/plugin/;
/ {
    overlay-name = "Digital Interface Board Pinmux";
    compatible = "...,p3768-0000+p3767-0005-super", ... ;

    fragment@0 {
        target = <&pinmux>;       /* 활성 DTB의 __symbols__/pinmux 로 자동 해결 */
        __overlay__ {
            pinctrl-names = "default";
            pinctrl-0 = <&interface_board_pins>;

            interface_board_pins: interface_board_pins {
                button1_ph7  { nvidia,pins="soc_gpio41_ph7"; nvidia,function="rsvd0"; ...IN  };
                button2_py0  { nvidia,pins="spi3_sck_py0";  nvidia,function="rsvd1"; ...IN  };
                pir_py3      { nvidia,pins="spi3_cs0_py3";  nvidia,function="rsvd1"; ...IN  };
                fan2_pq6     { nvidia,pins="soc_gpio33_pq6"; nvidia,function="rsvd0"; ...OUT };  /* board "FAN2" */
                fan1_pg6     { nvidia,pins="soc_gpio19_pg6"; nvidia,function="rsvd1"; ...OUT };  /* board "FAN1" */
            };
        };
    };
};
```

### 핀별 설정 의미
| 항목 | 입력 핀 (BUTTON/PIR) | 출력 핀 (FAN) |
|---|---|---|
| `nvidia,function` | `rsvd0` 또는 `rsvd1` (GPIO mux. SFIO 해제) | `rsvd0` |
| `nvidia,tristate` | `1` (output disabled, 고임피던스) | `0` (drive enabled) |
| `nvidia,enable-input` | `1` (input buffer ON) | `1` |

### 함수 이름이 핀별로 다른 이유
Tegra234에서 `gpio` function은 가상이며 (group 비어있음), 실제 GPIO mux는 `rsvd0/1/2/3` 중 해당 핀이 속한 그룹을 선택해야 한다.

| 핀 | 사용한 function | 이유 |
|---|---|---|
| PH.07 | `rsvd0` | rsvd0가 `soc_gpio41_ph7`을 포함 |
| PY.00 | `rsvd1` | rsvd0에 없음, rsvd1에 `spi3_sck_py0` 포함 |
| PY.03 | `rsvd1` | rsvd0에 없음, rsvd1에 `spi3_cs0_py3` 포함 |
| PQ.06 | `rsvd0` | rsvd0에 `soc_gpio33_pq6` 포함 |
| PG.06 | `rsvd1` | ~~rsvd0~~ 잘못 (rsvd0에 미포함). 후보 `gp`/`rsvd1`/`rsvd2`/`rsvd3` 중 `gp`는 실제 GP_PWM SFIO를 패드에 라우팅해 GPIO 출력과 충돌 → 첫 "진짜 reserved"인 `rsvd1`로 확정. 2026-05-06 §12 참조 |

확인 명령:
```bash
sudo grep "^function .*: rsvd[0-9]," /sys/kernel/debug/pinctrl/2430000.pinmux/pinmux-functions
```

### 적용 메커니즘
DTBO를 적용하면 활성 DTB의 `pinmux@2430000` 노드에 다음이 추가된다:
- `pinctrl-names = "default";`
- `pinctrl-0 = <&interface_board_pins>;`
- 자식 노드 `interface_board_pins` (5개 핀의 conf)

→ pinctrl-tegra 드라이버가 probe 시 default state를 적용하면서 우리가 명시한 mux/conf를 HW 레지스터에 쓴다.

### 컴파일
```bash
cd 02_interface/dtbo
dtc -@ -I dts -O dtb -o digital-interface-pinmux.dtbo digital-interface-pinmux.dts
```

### 사전 검증 (fdtoverlay merge)
적용 전, 카메라 dtbo + 우리 dtbo를 활성 DTB에 합쳐 충돌 검증:
```bash
sudo fdtoverlay \
  -i /boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.dtb \
  -o /tmp/test-merged.dtb \
  /boot/tegra234-p3767-camera-p3768-imx219-C.dtbo \
  02_interface/dtbo/digital-interface-pinmux.dtbo
sudo fdtdump /tmp/test-merged.dtb | grep -A 8 "interface_board_pins"
```
exit=0이고, `pinmux@2430000` 안에 `pinctrl-0` + 5개 핀 노드가 들어있고, 카메라 노드(`rbpcv2_imx219_c@10`)도 살아있는 걸 확인했다.

## 5. 적용 절차 (이미 수행됨)

1. **DTBO 빌드 → /boot 배치**
   ```bash
   sudo cp 02_interface/dtbo/digital-interface-pinmux.dtbo /boot/
   ```

2. **`extlinux.conf` 백업**
   ```bash
   sudo cp /boot/extlinux/extlinux.conf /boot/extlinux/extlinux.conf.bak.before-interface-pinmux
   ```

3. **새 부팅 LABEL `InterfaceBoard` 추가, DEFAULT 변경**

   `extlinux.conf` 변경 사항:
   - `DEFAULT JetsonIO` → `DEFAULT InterfaceBoard`
   - 기존 `LABEL JetsonIO` 그대로 보존 (fallback용)
   - 새 `LABEL InterfaceBoard` 추가:
     ```
     LABEL InterfaceBoard
         MENU LABEL Custom Header Config: <CSI Camera IMX219-C + Digital Interface Board>
         LINUX /boot/Image
         FDT /boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.dtb
         INITRD /boot/initrd
         APPEND ${cbootargs} root=PARTUUID=... ...
         OVERLAYS /boot/tegra234-p3767-camera-p3768-imx219-C.dtbo /boot/digital-interface-pinmux.dtbo
     ```

4. **재부팅**
   ```bash
   sudo reboot
   ```

## 6. 검증 (재부팅 후 수행)

```bash
# (1) extlinux 적용 확인
grep "^DEFAULT" /boot/extlinux/extlinux.conf
# DEFAULT InterfaceBoard 가 출력되어야 함

# (2) pinmux 등록 확인
sudo grep -E "pin (50|122|125|41|106) " /sys/kernel/debug/pinctrl/2430000.pinmux/pinmux-pins
# 각 핀에 대해 (MUX:rsvd0/rsvd1) 또는 owner가 표시되면 성공

# (3) idle 값 — BUTTON1, BUTTON2 둘 다 1 (HIGH)
gpioget gpiochip0 50 122
# 1
# 1

# (4) 라이브 press 테스트
sudo python3 tests/test_button_raw.py
# BUTTON1, BUTTON2 누를 때마다 LOW 에지, 떼면 HIGH 에지

# (5) 카메라 정상 동작 (회귀 확인)
ls /dev/video*
sudo nvgstcapture-1.0   # 또는 v4l2-ctl로 캡처 시도
```

## 7. 복구 절차 (만약 InterfaceBoard 부팅이 실패하면)

### 7-1. HDMI 모니터 + USB 키보드 사용
부팅 시 30초 boot menu가 나옴. 화살표로 `JetsonIO` 선택 → Enter → 카메라만 들어간 기존 환경으로 부팅.

### 7-2. 시리얼 콘솔 접근
J17 디버그 헤더 (115200 baud). boot menu에서 `JetsonIO` 선택.

### 7-3. SD 카드 떼서 다른 PC에서 복원
```
mount /dev/sdX1 /mnt
cp /mnt/boot/extlinux/extlinux.conf.bak.before-interface-pinmux \
   /mnt/boot/extlinux/extlinux.conf
umount /mnt
```

### 7-4. 부팅이 됐는데 핀mux만 적용 안 된 경우
DTBO 자체에 문제 있을 가능성. JetsonIO label로 fallback 후 dts를 수정/재컴파일.

## 8. 후속 — UEFI extlinux `OVERLAYS` 미적용 이슈와 사전 머지 우회

작성일: 2026-04-29 (5장 작업 후 같은 날)

### 8-1. 증상
5장 적용 후 InterfaceBoard label로 재부팅했지만 버튼 동작이 잡히지 않음. 검증 결과:

```
$ sudo grep -E "pin (50|122|125|41|106) " /sys/kernel/debug/pinctrl/2430000.pinmux/pinmux-pins
pin 41  (SOC_GPIO19_PG6): (MUX UNCLAIMED) (GPIO UNCLAIMED)
pin 50  (SOC_GPIO41_PH7): (MUX UNCLAIMED) (GPIO UNCLAIMED)
pin 106 (SOC_GPIO33_PQ6): (MUX UNCLAIMED) (GPIO UNCLAIMED)
pin 122 (SPI3_SCK_PY0):   (MUX UNCLAIMED) (GPIO UNCLAIMED)
pin 125 (SPI3_CS0_PY3):   (MUX UNCLAIMED) (GPIO UNCLAIMED)
```

5개 핀 모두 `MUX UNCLAIMED`. 활성 device tree (`/proc/device-tree/bus@0/pinmux@2430000/`)에 `interface_board_pins` 노드 없음. 추가로 `/dev/video*`도 없고 `rbpcv2_imx219_*` 노드도 부재 → **카메라 DTBO마저 활성 DTB에 머지되지 않은 상태**.

`gpiod`로 BUTTON1/BUTTON2 200Hz 폴링 결과 둘 다 100% LOW 고정, 12초 라이브 누름 테스트 에지 0회. SMW250 분리 후 보드측 신호선 ↔ GND 전압 측정 시 1V (5장 전 BUTTON1=3.3V 확인했던 회로가 그대로인데 SoC 핀이 라인을 끌어내림).

### 8-2. 원인
이 시스템은 NVIDIA UEFI L4T (EDK2)로 부팅하는데, **UEFI BootApp가 `extlinux.conf`의 `OVERLAYS` 라인을 처리하지 않고 `FDT` 라인의 DTB만 그대로 로드**한다. 즉 5장에서 만든 `LABEL InterfaceBoard`의 OVERLAYS 두 개(`tegra234-p3767-camera-p3768-imx219-C.dtbo`, `digital-interface-pinmux.dtbo`)는 **부팅 시 무시**된다.

검증:
- `efibootmgr -v`: BootCurrent=0002 (NVMe Seagate FireCuda) → UEFI 부팅 경로
- `fdtoverlay`로 DTBO를 활성 DTB와 수동 머지하면 정상 (DTBO 자체는 멀쩡)
- 활성 DT에 두 DTBO 어느 쪽 노드도 없음 → OVERLAYS 라인 통째로 미처리

`OVERLAYS` 키워드를 처리하던 것은 구버전 U-Boot 기반 부팅 경로다. JetPack의 jetson-io 도구가 만든 라벨(예: 기존 `JetsonIO`)도 같은 이유로 카메라 DTBO 미적용일 가능성이 큼 (별도 검증 필요).

### 8-3. 해결책 — 활성 DTB 사전 머지 (pre-merged DTB)

`OVERLAYS` 라인 의존을 제거하고, 부팅에 사용되는 DTB 파일에 DTBO를 미리 합쳐 둔다. 부팅 시점에는 `FDT` 라인이 가리키는 단일 머지 DTB만 로드된다.

#### 명령

```bash
# (1) 활성 DTB 백업
sudo cp /boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.dtb \
        /boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.dtb.bak

# (2) 카메라 + 인터페이스보드 DTBO를 활성 DTB에 머지
sudo fdtoverlay \
  -i /boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.dtb \
  -o /boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.merged.dtb \
  /boot/tegra234-p3767-camera-p3768-imx219-C.dtbo \
  /boot/digital-interface-pinmux.dtbo

# (3) extlinux.conf 백업
sudo cp /boot/extlinux/extlinux.conf \
        /boot/extlinux/extlinux.conf.bak.before-merged-dtb

# (4) InterfaceBoard 라벨에서 FDT를 머지 DTB로 변경, OVERLAYS 라인 제거
#     (cat /boot/extlinux/extlinux.conf 로 결과 확인)
```

수정 후 `LABEL InterfaceBoard`:
```
LABEL InterfaceBoard
    MENU LABEL Custom Header Config: <CSI Camera IMX219-C + Digital Interface Board (pre-merged DTB)>
    LINUX /boot/Image
    FDT /boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.merged.dtb
    INITRD /boot/initrd
    APPEND ${cbootargs} root=PARTUUID=... ...
    # OVERLAYS 라인 없음 — 머지된 DTB가 이미 다 포함
```

기존 `LABEL JetsonIO`는 보존 (장애 시 fallback).

#### 적용 일자 (이미 수행됨)
- DTB 백업: `kernel_*-nv-super.dtb.bak` (md5 `2ac738d2...`)
- 머지 DTB: `kernel_*-nv-super.merged.dtb` 254,449 B (md5 `89fe485f...`)
- DTBO: `digital-interface-pinmux.dtbo` (md5 `fc1ab99c...`)
- extlinux.conf 백업: `extlinux.conf.bak.before-merged-dtb`

### 8-4. 재부팅 후 검증 절차 — 다음 세션 진입 시 첫 작업

머지된 DTB로 부팅 후, 아래 순서로 검증한다. 시스템 비번: `123456`.

```bash
# (a) 부팅 라벨/DTB 확인
grep "^DEFAULT" /boot/extlinux/extlinux.conf
# DEFAULT InterfaceBoard

cat /proc/device-tree/model
# NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super

# (b) pinmux 등록 — 가장 중요
sudo grep -E "pin (50|122|125|41|106) " \
  /sys/kernel/debug/pinctrl/2430000.pinmux/pinmux-pins
# 기대: 각 라인에 owner 표시
#   pin 50  (SOC_GPIO41_PH7): interface_button1 (...)
#   pin 122 (SPI3_SCK_PY0):   interface_button2 (...)
#   pin 125 (SPI3_CS0_PY3):   interface_pir (...)
#   pin 106 (SOC_GPIO33_PQ6): interface_fan2 (...)   ← board silk "FAN2"
#   pin 41  (SOC_GPIO19_PG6): interface_fan1 (...)   ← board silk "FAN1"

# (c) idle 값 — 둘 다 HIGH 기대
gpioget gpiochip0 50 122 125
# 기대: 1 1 ?(PIR은 모듈 상태에 따라 0 또는 1)

# (d) 보드측 멀티미터 (선택) — SMW250 분리 후 신호선↔GND
# 기대: BUTTON1, BUTTON2 둘 다 3.3V (외부 풀업 정상 + SoC INPUT 고임피던스)
# 5장 이전 측정값 BUTTON1=3.3V로 회로 정상 확인된 바 있음.
# 이번 세션에서 1V로 떨어졌던 건 DTBO 미적용 SFIO 잔류 영향으로 추정.

# (e) 라이브 누름 테스트
sudo python3 tests/test_button_raw.py
# 기대: 누르면 LOW 에지, 떼면 HIGH 에지 (둘 다)

# (f) 카메라 회귀 (카메라 연결 시)
ls /dev/video*
# 기대: /dev/video0 (이번 세션엔 카메라 미연결이라 옵션)
```

#### 결과 분기

| 결과 | 의미 / 다음 단계 |
|---|---|
| (b)에서 owner 정상 표시 + (c) 1 1 ? | DTBO 적용 성공. 8.5의 후속 항목으로 진행. |
| (b) MUX UNCLAIMED 그대로 | 머지 DTB 자체가 안 로드된 것. `cat /proc/cmdline` 그대로면 부팅이 다른 라벨로 갔을 수 있음. extlinux.conf의 FDT 라인 / 부팅 메뉴 선택 재확인. |
| (b) 정상인데 (c)에서 50/122 LOW | SoC 핀mux는 GPIO지만 외부 풀업이 약하거나 `nvidia,pull` 명시가 필요한 상황. dts에 `nvidia,pull = <2>;` (pull-up) 추가 후 재컴파일/재머지. |
| (e) 누름 시 에지 0회 | 회로 점검 — 멀티미터로 신호선↔GND, 풀업 저항 위치, SMW250 결선 확인. |

### 8-5. 1차 머지 DTB 부팅 검증 결과 (2026-04-29 22:44 부팅)

8-3의 머지 DTB로 부팅 후 §8-4 절차 실행 결과:

| 단계 | 결과 |
|---|---|
| (a) DEFAULT/model | `DEFAULT InterfaceBoard`, model="Jetson Orin Nano Engineering Reference Developer Kit Super" |
| (b) pinmux owner | **5개 핀 중 4개** OK (pin 50/106/122/125 모두 `2430000.pinmux` HOG, function rsvd0/rsvd1 정상). pin 41 (FAN2/PG6)만 `MUX UNCLAIMED` |
| (c) idle 부팅 직후 | `gpioget gpiochip0 50 122 125` → `1 1 1` (BUTTON1/BUTTON2/PIR 모두 HIGH 정상) |
| (e) 라이브 누름 테스트 | 이벤트는 잡히나 **뗐을 때 HIGH 에지가 거의 안 잡힘**. 누름 테스트 종료 후 idle 재측정 시 `0 0 1` (BUTTON1/BUTTON2 LOW로 굳음) |

→ pinmux DTBO 적용은 성공. SFIO 잔류 문제(BUTTON2 SPI3_SCK 토글)는 해소. 그러나 외부 풀업이 약하거나 GPIO 라인의 필터 cap 시정수 영향으로 누름 후 SoC 핀이 HIGH로 복귀를 못 하는 새 증상.

§8-4 결과 분기 표의 *"(b) 정상인데 (c)에서 50/122 LOW"* 케이스에 정확히 해당 → SoC internal pull-up 보강 필요.

FAN2 (pin 41) UNCLAIMED는 BUTTON 검증과는 별개 잔여 항목으로 분리 (§9).

### 8-6. Pull-up 보강 (BUTTON1/BUTTON2만 우선 적용)

#### 변경
`02_interface/dtbo/digital-interface-pinmux.dts`의 `button1_ph7`, `button2_py0` 두 노드에만 `nvidia,pull = <2>` (pull-up enable) 추가.

PIR/FAN 핀은 이번 라운드에선 건드리지 않음 — BUTTON 동작 먼저 확정한 뒤 후속에서 동일 패턴 검토.

```
nvidia,pins = "soc_gpio41_ph7";   /* PH.07, BUTTON1 */
nvidia,function = "rsvd0";
nvidia,pull = <2>;                /* added: pull-up */
nvidia,tristate = <1>;
nvidia,enable-input = <1>;
```

`nvidia,pull` 값 의미: `0`=none, `1`=pull-down, `2`=pull-up.
(stock DTB 모든 pinconf가 `pull=0`이라 NVIDIA 관행은 미사용이지만, 외부 풀업이 약한 본 보드에선 SoC 측 보강이 필요.)

#### 빌드/머지/배치 (이미 수행됨, 재부팅만 남음)
```bash
cd 02_interface/dtbo
dtc -@ -I dts -O dtb -o digital-interface-pinmux.dtbo digital-interface-pinmux.dts
sudo cp digital-interface-pinmux.dtbo /boot/

# 이전 머지 DTB 백업 (8-3에서 만든 것 보존)
sudo cp /boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.merged.dtb \
        /boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.merged.dtb.bak.before-pullup

# 새 dtbo로 머지 DTB 재생성
sudo fdtoverlay \
  -i /boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.dtb \
  -o /boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.merged.dtb \
  /boot/tegra234-p3767-camera-p3768-imx219-C.dtbo \
  /boot/digital-interface-pinmux.dtbo
```

#### 적용 파일 (2026-04-29)
| 파일 | md5 | 비고 |
|---|---|---|
| `02_interface/dtbo/digital-interface-pinmux.dtbo` | `1e4436fe07bd640e8898f1e1430402e2` | pull-up 반영 |
| `/boot/digital-interface-pinmux.dtbo` | 동일 | 부팅 입력 |
| `/boot/dtb/kernel_*-nv-super.merged.dtb` | `5daa6490adca9c3ae172344d31be8c8c` | 254,481 B, 부팅 FDT 타깃 |
| `/boot/dtb/kernel_*-nv-super.merged.dtb.bak.before-pullup` | `89fe485f...` (8-3 산출물) | 직전 머지 DTB |
| `/boot/dtb/kernel_*-nv-super.dtb.bak` | `2ac738d2...` (8-3 산출물) | 원본 DTB |

`extlinux.conf`는 8-3에서 이미 머지 DTB를 가리키도록 수정됐으므로 추가 변경 없음.

### 8-7. 재부팅 후 검증 — 다음 세션 진입 시 첫 작업

머지 DTB가 pull-up 포함으로 갱신됐으니 재부팅만 남았다. **재부팅 후 새 세션에서 아래 순서로 검증한다. 시스템 비번: `123456`.**

```bash
# (a) 부팅 라벨 / 모델 / 머지 DTB md5 확인
grep "^DEFAULT" /boot/extlinux/extlinux.conf
# DEFAULT InterfaceBoard

cat /proc/device-tree/model
# NVIDIA Jetson Orin Nano Engineering Reference Developer Kit Super

md5sum /boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.merged.dtb
# 5daa6490adca9c3ae172344d31be8c8c

# (b) pinmux 등록 — pin 50, 122 둘 다 owner 표시
sudo grep -E "pin (50|122) " /sys/kernel/debug/pinctrl/2430000.pinmux/pinmux-pins
# 기대:
#   pin 50  (SOC_GPIO41_PH7): 2430000.pinmux (GPIO UNCLAIMED) (HOG) function rsvd0 group soc_gpio41_ph7
#   pin 122 (SPI3_SCK_PY0):   2430000.pinmux (GPIO UNCLAIMED) (HOG) function rsvd1 group spi3_sck_py0

# (c) idle 안정성 — HIGH 안정 + 시간 경과해도 유지
gpioget gpiochip0 50 122
# 기대: 1 1
sleep 5; gpioget gpiochip0 50 122
# 여전히 1 1 (이전 라운드에선 시간 지나며 0 0으로 떨어졌었음)

# (d) 라이브 누름 테스트 (unbuffered 필수)
echo 123456 | sudo -S -p '' python3 -u tests/test_button_raw.py
# 기대:
#   - 누를 때 LOW 에지
#   - 뗄 때 HIGH 에지 (이전엔 거의 안 잡혔던 부분 — 이게 핵심 회귀 확인 포인트)
#   - 종료 후 gpioget도 1 1 유지

# (e) 카메라 회귀 (카메라 연결 시)
ls /dev/video*
```

#### 결과 분기

| 결과 | 의미 / 다음 단계 |
|---|---|
| (b)(c)(d) 모두 OK, idle 1 1 안정, 뗌 HIGH 에지도 잡힘 | **버튼 검증 완료**. §9의 PIR (필요시 동일 패턴으로 pull-up 추가), FAN, BME280로 진행 |
| (c)는 1 1인데 (d) 종료 후 다시 0 0으로 굳음 | pull-up이 약함 / 핀이 floating에 가까움. dtbo의 nvidia,pull은 적용됐는지 fdtdump로 확인. 적용됐다면 외부 풀업 R 값 자체를 낮추거나 SoC pull-up이 driver-pull-up이 아닌 케이스인지 추가 조사 |
| (b)에서 owner 표시인데 (d) 누름 에지 0회 | bouncetime 50ms 안에 노이즈 흡수됐거나 회로 단선. test_button_raw.py의 bouncetime을 10~20ms로 낮춰 재시도. 그래도 안 잡히면 SMW250 결선/스위치 점검 |
| (a) `DEFAULT InterfaceBoard` 인데 (b) MUX UNCLAIMED | 머지 DTB가 안 로드된 것. md5 확인, 부팅 메뉴에서 다른 라벨로 갔는지 / `cat /proc/cmdline` |

#### 작업 큐 (다음 세션 시작점)
- [in_progress] BUTTON pull-up 적용 후 §8-7 (a)~(d) 검증
- [pending] PIR 모션 검증 (8-7 결과에 따라 PIR 핀에도 pull-up 적용 여부 결정)
- [pending] FAN1/FAN2 출력 토글 검증
- [pending] FAN2 pin 41 UNCLAIMED 원인 분석 (DTBO에 노드는 들어갔으나 pinctrl-tegra가 적용 안 함 — 다른 노드와 핀 충돌? 별도 조사)
- [pending] BME280 (I2C1 0x76) 미응답 — 모듈 전원/결선

### 8-8. 유지보수 주의 — 머지 DTB 재생성 조건

다음 중 하나라도 변경되면 `kernel_*-nv-super.merged.dtb`를 다시 만들어야 한다:

1. JetPack/L4T 업데이트로 `kernel_tegra234-...-nv-super.dtb`가 갱신될 때
2. `digital-interface-pinmux.dts`를 수정해 `.dtbo`를 다시 빌드할 때
3. 카메라 DTBO를 다른 모델로 바꿀 때 (현재 IMX219-C 기준)

재생성 명령은 8-3의 (1)~(2)와 동일.

dtbo만 갱신할 경우 빌드:
```bash
cd 02_interface/dtbo
dtc -@ -I dts -O dtb -o digital-interface-pinmux.dtbo digital-interface-pinmux.dts
sudo cp digital-interface-pinmux.dtbo /boot/
# 그리고 머지 DTB 재생성 (8-3의 step 2)
```

## 9. 미해결/후속 항목

진행 상태 (2026-04-30 기준):

- **[HW 작업 대기] BUTTON1/BUTTON2 풀업 강화** — 진단 결과 인터페이스 보드 자체는 무결, Jetson 캐리어 측 GPIO18/27에 약 4.3kΩ 풀다운 path 존재. **R17, R27을 10kΩ → 1kΩ으로 교체** 후 재검증 예정. 상세는 §11 및 `REPORT_button_pullup_change_20260430.md`.
- **[적용 완료, 2026-05-07 재부팅 후 검증됨] FAN2 (pin 41 PG6) UNCLAIMED** — 2026-05-06 원인 확정: dts의 `nvidia,function = "rsvd0"`이 잘못된 매핑(PG6는 rsvd0 그룹에 미포함). 1차 시도 `gp`는 SFIO 충돌로 실패 → 최종 `rsvd1`로 확정. 2026-05-07 재부팅 후 `pin 41` owner 등록(function rsvd1) 및 라이브 토글 정상 확인. 다만 FAN1 자리 팬 유닛 결함 가능성은 별도 트랙(§12-5).
- **[보류] PIR (HW-MS03) 동작 검증** — idle/motion 시 출력 레벨 실측. 현재 idle HIGH 관측됨. BUTTON과 같은 풀다운 영향 가능성 → 같은 진단 절차로 확인 후 R 값 조정 검토.
- **[보류] FAN 출력 검증** — GPIO 토글 시 옵토 LED → MOSFET → 팬 회전 체인 확인 (FAN1만이라도 우선).
- **[보류] BME280 (I2C1 0x76) 미응답** — `i2cdetect -y 1`에서 0x76 무응답. I2C1은 default DTB에 활성. 모듈 전원/SDA-SCL 결선 점검부터.

## 10. 참고 — 관련 파일

| 파일 | 역할 |
|---|---|
| `02_interface/dtbo/digital-interface-pinmux.dts` | DTBO 소스 (이 작업의 본체) |
| `02_interface/dtbo/digital-interface-pinmux.dtbo` | 컴파일된 dtbo (`/boot/`에도 동일 파일 배치) |
| `02_interface/20260429_회로도.pdf` | 회로도 (BUTTON 풀업 등 회로 설계) |
| `02_interface/20260429_보드배치도.png` | 보드 배치도 (커넥터 위치) |
| `tests/test_button_raw.py` | 외부 풀업 가정으로 주석 정정 |
| `tests/test_button_diag.py` | gpiod 기반 진단 스크립트 (SoC 라인 오프셋 직접 사용) |
| `/boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.dtb` | 활성 DTB (원본, 8-3에서 머지 입력으로 사용) |
| `/boot/dtb/kernel_*-nv-super.dtb.bak` | 8-3에서 만든 원본 DTB 백업 |
| `/boot/dtb/kernel_*-nv-super.merged.dtb` | 카메라+인터페이스 DTBO 사전 머지된 부팅용 DTB (현재 InterfaceBoard 라벨이 사용) |
| `/boot/extlinux/extlinux.conf` | 부팅 LABEL (InterfaceBoard 라벨이 머지 DTB 가리킴) |
| `/boot/extlinux/extlinux.conf.bak.before-interface-pinmux` | 5장 이전 백업 |
| `/boot/extlinux/extlinux.conf.bak.before-merged-dtb` | 8장 이전 백업 |
| `/boot/dtb/kernel_*-nv-super.merged.dtb.bak.before-pullup` | 8-6 pull-up 적용 직전 머지 DTB 백업 (2026-04-29) |
| `/boot/dtb/kernel_*-nv-super.merged.dtb.bak.before-fan2-fix` | 12-2 fan2 `gp` 적용 직전 머지 DTB (2026-05-06 21:46) |
| `/boot/dtb/kernel_*-nv-super.merged.dtb.bak.before-fan2-rsvd1.20260506-222917` | 12-4 fan2 `rsvd1` 확정 직전 머지 DTB (gp 적용본, 2026-05-06 22:29) |
| `/boot/dtb/kernel_*-nv-super.merged.dtb.bak.before-label-realign.20260507-004226` | 13장 라벨 정합(보드 ↔ 코드 swap) 직전 머지 DTB (rsvd1 적용본) |
| `/boot/digital-interface-pinmux.dtbo.bak.before-label-realign.20260507-004226` | 13장 직전 dtbo (fan1_pq6 / fan2_pg6 노드명 시점) |
| `/boot/digital-interface-pinmux.dtbo` | dtbo 사본 (재머지 시 입력) |
| `/boot/tegra234-p3767-camera-p3768-imx219-C.dtbo` | 카메라 dtbo (재머지 시 입력) |
| `02_interface/REPORT_button_pullup_change_20260430.md` | HW 설계자 공유용 R17/R27 변경 요청 보고서 |

## 11. BUTTON 풀업 진단 — Jetson 측 풀다운 발견 (2026-04-30)

§8-7 (d) 단계에서 누름 테스트 후 idle이 `0 0`으로 굳는 잔여 증상을 추적한 결과, **인터페이스 보드 자체는 무결하고 Jetson 캐리어 측 GPIO 헤더 핀에 약 4.3kΩ의 풀다운 path가 있음**을 확인했다. SoC 측 `nvidia,pull=2`가 적용됐어도 외부 풀다운에 패배해 라인이 LOW로 처진다.

### 11-1. 진단 요약

| 시험 | 조건 | 결과 |
|---|---|---|
| 인터페이스 보드 단독 (Jetson 분리 + VIN 인가) | J3 PIN12 ↔ PIN6 V 측정 | 미연결/미누름 3.3V, 누름 0V, 릴리즈 즉시 3.3V → **보드 무결** |
| Jetson 단독 (인터페이스 보드 분리) | J41 PIN12, PIN13 동작 | 정상 |
| 결합 상태 | R17 아래쪽 노드 ↔ GND V | **1.0V** (3.3V 분압) |

분압식: `1V = 3.3V × R_pd / (10kΩ + R_pd)` → **R_pd ≈ 4.3 kΩ** (Jetson 측 등가 풀다운).

BUTTON1(PH.07), BUTTON2(PY.00) 두 핀 모두 동일 거동 → 캐리어 보드(P3768) 측 헤더 핀 strap/ESD 보호 풀다운 가능성.

### 11-2. 결정된 해결책 — R17, R27: 10kΩ → 1kΩ

| 항목 | 변경 전 | 변경 후 |
|---|---|---|
| idle V (결합 시) | 0.99V (LOW 오인식) | 2.68V (HIGH 정상) |
| 누름 시 +3.3V → R → GND 전류 | 0.33 mA | 3.3 mA |
| RC 시정수 (× C15 0.1µF) | 1 ms | 0.1 ms |

LM1117MP-3.3 출력 정격(800mA) 대비 두 채널 동시 누름 6.6mA는 무시 가능. SW 디바운스(50ms)가 RC 시정수 단축을 충분히 커버.

상세 분석/대안 비교/HW 설계자 공유용 본문은 별도 보고서 참고:
- `02_interface/REPORT_button_pullup_change_20260430.md`

### 11-3. 부품 교체 후 재검증 절차 (다음 라운드 작업 큐)

1. R17, R27을 1kΩ(0805 동일 패키지)으로 교체.
2. Jetson 결합 + 부팅 후 §8-7 (b)~(d) 동일 절차로 재검증:
   - pinmux owner 등록 유지 (pin 50/122 HOG)
   - idle `gpioget gpiochip0 50 122` → 1 1 안정 (시간 지나도 유지)
   - 라이브 누름 테스트에서 누름 LOW + 뗌 HIGH 에지 모두 정상, 종료 후 idle 1 1 유지
3. PIR(GPIO24, PY.03)도 같은 풀다운 영향 가능성 있으므로 동일 진단 절차 반복 후 필요 시 풀업 R 값 조정.

## 12. FAN2 (PG.06) function 매핑 정정 — `rsvd0` → `gp` 시도 → `rsvd1` 확정 (2026-05-06 ~ 05-07)

§9의 "FAN2 pin 41 UNCLAIMED" 미해결 항목을 추적한 결과, 5장에서 작성한 `dts`의 함수 매핑이 잘못되어 있었음을 확인했다. 1차 시도 `gp`는 SFIO 충돌로 실패해 다시 `rsvd1`로 확정했다. 본 절은 그 전 과정을 모두 보존한다.

### 12-1. 진단

먼저 보드의 FAN2 커넥터(BCM6 / PQ6, gpiochip0 line 106)로 active-LOW 검증을 수행 — `gpioset gpiochip0 106=0/1` 토글에 따라 회전/정지가 일관됨. 이로써 FAN 회로(AQY210SZ 옵토MOSFET 릴레이) 자체와 FAN1 핀(PQ6, rsvd0 매핑) 적용은 정상임을 확정.

이어 보드의 FAN1 커넥터(BCM12 / PG6, line 41) 검증:
- `pin 41`은 여전히 `(MUX UNCLAIMED) (GPIO UNCLAIMED)` — 8-6 pull-up 작업 후에도 변하지 않음.
- 활성 DT의 `pinmux@2430000/interface_board_pins/fan2_pg6/` 노드는 **존재**. 즉 DTBO 적용 자체는 됨.
- `/proc/device-tree/pwm-fan/`이 존재하지만 PG6를 직접 잡고 있지는 않음 (gpioinfo line 41 = "unused").
- 결정적으로 `/sys/kernel/debug/pinctrl/2430000.pinmux/pinmux-functions` 검색 결과:
  - **`rsvd0` 함수 그룹에는 `soc_gpio19_pg6` 미포함**
  - 포함되는 함수: `gp` (function 0), `rsvd1` (56), `rsvd2` (72), `rsvd3` (84)
- 결론: `nvidia,function = "rsvd0"`이 매칭되지 않아 pinctrl-tegra가 `fan2_pg6` 노드만 silently skip → MUX UNCLAIMED 잔류. (다른 4개 핀은 자기 함수에 포함되어 정상 적용됨.)

5장 §4의 표는 PG.06을 `rsvd0`으로 적었지만 검증 누락이었음. PQ.06은 `rsvd0` 매칭이 우연히 맞아 동작했고, 이게 PG.06도 같은 패턴으로 가정하게 만든 원인.

### 12-2. 수정 — 1차 시도 `gp` (실패)

`02_interface/dtbo/digital-interface-pinmux.dts`의 `fan2_pg6` 노드 함수만 변경 (다른 핀은 동작 중이므로 그대로 둠):

```
fan2_pg6 {
    nvidia,pins = "soc_gpio19_pg6";
    nvidia,function = "gp";   /* was "rsvd0" — wrong group */
    ...
};
```

이 시점에는 §4 표의 PG.06 줄도 `gp`로 정정한 바 있음 (이후 §12-5에서 `rsvd1`로 재정정).

#### 1차 빌드/머지 산출물 (2026-05-06, gp 시도)

| 파일 | md5 | 비고 |
|---|---|---|
| `02_interface/dtbo/digital-interface-pinmux.dtbo` (gp 버전) | `aa59e484dd1e4c94db7f4f35d08be4d5` | 이 시점 산출물 — 현재는 폐기, /boot/에는 없음 |
| `/boot/dtb/kernel_*-nv-super.merged.dtb.bak.before-fan2-fix` | `5daa6490adca9c3ae172344d31be8c8c` | gp 적용 직전 머지 DTB (8-6 pull-up 반영본) |

`extlinux.conf`는 변경 없음 — 8-3에서 이미 머지 DTB 가리킴.

### 12-3. 1차 부팅 검증 결과 (2026-05-06, gp 적용본)

`gp` DTBO로 재부팅하니 owner는 잡혔으나 GPIO 출력이 정상 동작하지 않았다:

- `pin 41 (SOC_GPIO19_PG6): 2430000.pinmux (HOG) function gp group soc_gpio19_pg6` — owner 등록은 정상.
- 그러나 GPIO 출력 토글 시 패드 전압이 약 1.7V 부근에서 ~50% duty 평균으로 측정됨. GPIO HIGH는 3.3V까지 도달했지만 GPIO LOW가 idle 아래로 못 끌어내림.
- 원인 분석: PG.06의 `gp` 함수는 **이름과 달리 "general GPIO"가 아니라 GP-PWM 페리페럴**의 SFIO 매핑. SFIO가 패드를 점유한 상태에서 GPIO 컨트롤러가 sink 시도 시 충돌 → 전형적 "SFIO winning over GPIO sink" 패턴.
- 즉 `gp`는 PG.06 후보 함수 목록에는 들어 있지만, 이 패드에서는 실제 SFIO를 끌어와 routing하므로 GPIO 용도로 부적합.

### 12-4. 2차 수정 — `rsvd1`로 확정 (2026-05-06 22:29)

PG.06의 후보(`gp`/`rsvd1`/`rsvd2`/`rsvd3`) 중 첫 번째 "진짜 reserved"인 `rsvd1`로 변경. rsvd2/rsvd3은 더 큰 인덱스의 reserved이므로 가장 보수적인 rsvd1을 선택.

```
fan2_pg6 {
    nvidia,pins = "soc_gpio19_pg6";
    nvidia,function = "rsvd1";   /* gp routes real SFIO; rsvd1 is first true-reserved */
    ...
};
```

#### 2차 빌드/머지 산출물 (2026-05-06 22:29, rsvd1 확정 — **현재 deployed**)

| 파일 | md5 | 비고 |
|---|---|---|
| `02_interface/dtbo/digital-interface-pinmux.dtbo` | `319e423d49f847fd6f50ed8e2a468a5a` | fan2 function="rsvd1" 반영, **현재 작업트리 = /boot/ 동일** |
| `/boot/digital-interface-pinmux.dtbo` | `319e423d49f847fd6f50ed8e2a468a5a` | 부팅 입력 |
| `/boot/dtb/kernel_*-nv-super.merged.dtb` | `c5c9bb8ddba91b71d1299431d967db63` | 254,481 B, 부팅 FDT 타깃 |
| `/boot/dtb/kernel_*-nv-super.merged.dtb.bak.before-fan2-rsvd1.20260506-222917` | (gp 적용본) 254,477 B | rsvd1 적용 직전 머지 DTB |

### 12-5. 2차 부팅 검증 결과 (2026-05-07, rsvd1 적용본)

```bash
$ sudo grep -E "pin (41|50|106|122|125) " /sys/kernel/debug/pinctrl/2430000.pinmux/pinmux-pins
pin 41  (SOC_GPIO19_PG6): 2430000.pinmux (HOG) function rsvd1 group soc_gpio19_pg6
pin 50  (SOC_GPIO41_PH7): 2430000.pinmux (HOG) function rsvd0 group soc_gpio41_ph7
pin 106 (SOC_GPIO33_PQ6): 2430000.pinmux (HOG) function rsvd0 group soc_gpio33_pq6
pin 122 (SPI3_SCK_PY0):   2430000.pinmux (HOG) function rsvd1 group spi3_sck_py0
pin 125 (SPI3_CS0_PY3):   2430000.pinmux (HOG) function rsvd1 group spi3_cs0_py3
```

5개 핀 모두 owner 정상 표시. PG.06이 `function rsvd1`로 잡힘 → 1차 `gp` 시도의 SFIO 충돌 해소.

라이브 토글 시험 (`tests/test_fan1_toggle.py`, 2026-05-07): 보드 FAN1 자리(BCM12, Pin 32) 채널이 active-LOW 회로 극성에 따라 ON/OFF 정상 동작 확인. 3 사이클 모두 회전/정지 일관됨.

#### 원인 진단 정리 — 채널 vs 팬 유닛

`rsvd0` 매핑 오류는 **객관적 사실**(`pinmux-functions`에 PG.06이 rsvd0 그룹 미포함)이므로 DTBO 수정 자체는 정당. 다만 다음 두 가지가 동시에 성립할 수 있음에 유의:

1. **DTBO 측 결함**: 원본 `rsvd0`은 매칭 실패 → pin 41 UNCLAIMED → 패드가 부팅 SFIO 잔류 상태로 방치됨. (해결됨)
2. **팬 유닛 측 결함**: 2026-05-06 23시대 팬 유닛 교차시험에서 Pin 32 자리에 다른 팬을 꽂았더니 정상 회전. 즉 FAN1 자리 원래 팬 유닛에 자체 결함 가능성. 이번 토글 시험으로 채널은 분명히 정상이므로, 이 가설은 **별도 트랙으로 팬 유닛 자체 통전/저항 점검 필요**.

따라서 "원래 안 돌던 이유 = rsvd0 단독"이라고 단정할 수 없음. 두 결함이 겹쳐 증상을 만들었을 가능성이 충분히 있고, DTBO 수정만으로 해결됐는지/팬 유닛도 같이 새 것이 들어가서 해결됐는지는 분리 검증 안 됨. 다만 운영 배치 시 양쪽 모두 OK여야 하므로 결과적 무해.

### 12-6. 재부팅 후 재검증 절차 (참고)

향후 보드/SoC 변경 후 회귀 시:

```bash
# (a) 부팅 라벨 / 머지 DTB md5
grep "^DEFAULT" /boot/extlinux/extlinux.conf
md5sum /boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.merged.dtb
# 기대: DEFAULT InterfaceBoard, md5 c5c9bb8ddba91b71d1299431d967db63

# (b) pin 41 owner — 핵심 확인 포인트
sudo grep "pin 41 " /sys/kernel/debug/pinctrl/2430000.pinmux/pinmux-pins
# 기대: pin 41 (SOC_GPIO19_PG6): 2430000.pinmux (...) (HOG) function rsvd1 group soc_gpio19_pg6

# (c) 보드 FAN1 회전 — active-LOW: LOW에서 회전
sudo python3 tests/test_fan1_toggle.py --period 2 --cycles 3
# 또는:
sudo gpioset --mode=time --sec=5 gpiochip0 41=0   # 팬 돌아야 함
sudo gpioset --mode=time --sec=3 gpiochip0 41=1   # 정지

# (d) 회귀 — 보드 FAN2 (BCM6) 그대로 동작
sudo gpioset --mode=time --sec=5 gpiochip0 106=0  # 돌아야 함
sudo gpioset --mode=time --sec=3 gpiochip0 106=1  # 정지
```

#### 결과 분기

| 결과 | 의미 |
|---|---|
| (b) pin 41 `function rsvd1` + (c) LOW 시 회전 | 정상. §9 FAN2 항목 종료 상태 유지. |
| (b) `function gp` 또는 UNCLAIMED | DTBO/머지 DTB가 옛 버전. md5 재확인. |
| (b) 정상인데 (c) 회전 안 함 | 채널 OK, 팬 유닛 측 결함 — 다른 팬으로 교차시험. §12-5 (2)번 가설. |
| (d) FAN2 회귀 깨짐 | rsvd1 변경이 다른 핀 적용에 영향. 백업으로 롤백: `sudo cp /boot/dtb/kernel_*-nv-super.merged.dtb.bak.before-fan2-rsvd1.20260506-222917 /boot/dtb/kernel_*-nv-super.merged.dtb` 후 재부팅 |

> **참고**: 본 §12 안에 등장하는 `fan2_pg6` 노드명은 §13 라벨 정합 작업 이전의 이름이다. 같은 핀(PG.06 / Pin 32)의 현재 노드명은 `fan1_pg6` (보드 라벨에 맞춤). md5 등 산출물 hash도 §13 적용 후 갱신됨.

## 13. FAN1/FAN2 라벨 정합 — 보드 실크 기준으로 코드/DTS 통일 (2026-05-07)

§12 작업 종료 시점까지 **보드 실크와 코드/DTS의 FAN1/FAN2 라벨이 서로 반대**였다. 보드는 `Pin 32 = FAN1, Pin 31 = FAN2` 인데 코드는 `FAN1_PIN = BCM6 (Pin 31)`, DTS 노드는 `fan1_pq6 = Pin 31` / `fan2_pg6 = Pin 32` — 매번 머리로 환산해야 하는 인지 부담이 있었다. 본 절에서 **보드 실크 라벨을 단일 기준**으로 삼아 정렬한다.

### 13-1. 변경 요약

| 위치 | 이전 | 이후 |
|---|---|---|
| `src/config.py` | `FAN1_PIN = 6` (Pin 31), `FAN2_PIN = 12` (Pin 32) | `FAN1_PIN = 12` (Pin 32), `FAN2_PIN = 6` (Pin 31) |
| `02_interface/dtbo/...dts` 노드명 | `fan1_pq6` (Pin 31), `fan2_pg6` (Pin 32) | `fan2_pq6` (Pin 31), `fan1_pg6` (Pin 32) |
| `02_interface/dtbo/...dts` `pin-label` | `interface_fan1` ↔ Pin 31 (PQ.06), `interface_fan2` ↔ Pin 32 (PG.06) | `interface_fan2` ↔ Pin 31 (PQ.06), `interface_fan1` ↔ Pin 32 (PG.06) |
| 헤더 주석 Pin map | Pin31 = FAN1, Pin32 = FAN2 | Pin31 = FAN2, Pin32 = FAN1 |

`src/main.py`의 호출 사이트는 변경 없음. `fan1 = FanOutput(FAN1_PIN, "FAN1")` 그대로 두면 `FAN1_PIN`이 이제 Pin 32를 가리키므로, 사용자 의도("FAN1 켜기")와 보드 동작("Pin 32 자리 팬 회전")이 자동 일치.

### 13-2. 빌드/머지 산출물 (2026-05-07 00:42, **현재 deployed**)

| 파일 | md5 | 비고 |
|---|---|---|
| `02_interface/dtbo/digital-interface-pinmux.dtbo` | `18666d584be6d9c2eb322b1dce60d57b` | 라벨 정합 반영, 작업트리 = /boot/ 동일 |
| `/boot/digital-interface-pinmux.dtbo` | `18666d584be6d9c2eb322b1dce60d57b` | 부팅 입력 |
| `/boot/dtb/kernel_*-nv-super.merged.dtb` | `6e3cad35f68c56760fbac20c58550d5d` | 254,481 B, 부팅 FDT 타깃 |
| `/boot/digital-interface-pinmux.dtbo.bak.before-label-realign.20260507-004226` | `319e423d49f847fd6f50ed8e2a468a5a` | 13-1 직전 dtbo (12장 종료 시점) |
| `/boot/dtb/kernel_*-nv-super.merged.dtb.bak.before-label-realign.20260507-004226` | (12장 종료 시점) | 13-1 직전 머지 DTB |

`extlinux.conf`는 변경 없음.

### 13-3. 재부팅 후 검증 절차

```bash
# (a) 머지 DTB md5 확인
md5sum /boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.merged.dtb
# 기대: 6e3cad35f68c56760fbac20c58550d5d

# (b) pinmux owner — fan1/fan2 라벨이 보드와 일치하는지
sudo grep -E "pin (41|106) " /sys/kernel/debug/pinctrl/2430000.pinmux/pinmux-pins
# 기대:
#   pin 41  (SOC_GPIO19_PG6): 2430000.pinmux (...) (HOG) function rsvd1 group soc_gpio19_pg6   ← interface_fan1 (보드 FAN1)
#   pin 106 (SOC_GPIO33_PQ6): 2430000.pinmux (...) (HOG) function rsvd0 group soc_gpio33_pq6   ← interface_fan2 (보드 FAN2)

# (c) 라이브 토글 — config.FAN1_PIN(=12, Pin 32, 보드 FAN1) 회전 확인
sudo python3 tests/test_fan1_toggle.py --period 2 --cycles 3
# 기대: 보드 FAN1 자리 팬이 LOW=ON 토글에 따라 회전/정지

# (d) 회귀 — config.FAN2_PIN(=6, Pin 31, 보드 FAN2) 채널 동작
sudo gpioset --mode=time --sec=3 gpiochip0 106=0  # 보드 FAN2 회전
sudo gpioset --mode=time --sec=2 gpiochip0 106=1  # 정지

# (e) main.py 운영 동작 — 버튼 누르면 보드 FAN1/FAN2가 라벨 그대로 토글
sudo python3 src/main.py
# zoom-in 버튼 → 보드 FAN1(Pin 32) 토글
# zoom-out 버튼 → 보드 FAN2(Pin 31) 토글
```

#### 결과 분기

| 결과 | 의미 |
|---|---|
| (b) 두 핀 owner 정상 + (c)(d) 모두 회전 | **정합 완료**. 이후 코드/문서/보드 라벨이 한 의미로 정렬됨. |
| (b) UNCLAIMED 출현 | DTBO/머지 DTB가 적용 안 됨. md5 재확인. 필요 시 13-1 직전 백업으로 롤백: `sudo cp /boot/dtb/kernel_*-nv-super.merged.dtb.bak.before-label-realign.20260507-004226 /boot/dtb/kernel_*-nv-super.merged.dtb` |
| (e)에서 zoom-in과 보드 FAN1 라벨이 안 맞음 | 라벨 정합이 빠진 곳이 남아 있다는 의미. `grep -rnE "FAN1_PIN|FAN2_PIN|fan1_p|fan2_p|interface_fan1|interface_fan2"` 로 잔존 미정합 위치 확인 |

## 14. LIFT H-BRIDGE 핀 추가 — BCM13/BCM19 (2026-05-07 21:51)

§13 라벨 정합 완료 후, 리프트컬럼 모터 구동을 위해 BCM13(Pin 33, PH.00)과 BCM19(Pin 35, PI.02)를 DTBO에 추가했다. 회로상 두 핀은 74HC244(U2) 버퍼를 거쳐 BTS7960B 두 개로 구성된 H-Bridge의 IN 입력으로 들어간다. INH(enable)는 +3.3V 상시 풀로 고정되어 있어 방향/구동은 IN1/IN2 두 GPIO가 단독 결정한다.

### 14-1. 핀 매핑

| 노드 | BCM | Pin | SoC pad | function | pull | 역할 |
|---|---|---|---|---|---|---|
| `lift_in1_ph0` | 13 | 33 | `soc_gpio21_ph0` (PH.00, line 43) | `rsvd0` | 1 (down) | 74HC244 1A0 → BTS7960B (U3) IN |
| `lift_in2_pi2` | 19 | 35 | `soc_gpio44_pi2` (PI.02, line 53) | `rsvd0` | 1 (down) | 74HC244 1A2 → BTS7960B (U1) IN |

### 14-2. 함수 선택 근거

`/sys/kernel/debug/pinctrl/2430000.pinmux/pinmux-functions` 검색 결과:

| 핀 | 후보 그룹 | 채택 | 이유 |
|---|---|---|---|
| PH.00 | `gp` / `rsvd0` / `i2s7` / `rsvd3` | `rsvd0` | `gp`는 GP-PWM(`32c0000.pwm`) SFIO를 패드에 라우팅 — §12 PG.06 사례와 동일 함정. `rsvd0`이 첫 true-reserved이며 PH.00 포함. |
| PI.02 | `rsvd0` / `i2s2` / `rsvd2` / `rsvd3` | `rsvd0` | i2s2 SFIO 회피. `rsvd0`이 첫 true-reserved이며 PI.02 포함. |

### 14-3. Pull-down 채택 근거

두 핀 모두 출력 GPIO지만 `nvidia,pull = <1>` (pull-down)을 명시했다. 부팅 시 GPIO 컨트롤러가 핀을 잡고 userspace가 값을 쓰기 전 짧은 윈도에서 패드는 hi-Z이고 74HC244 입력은 floating한다. 두 BTS7960B의 INH가 +3.3V 상시 ON이므로 IN이 floating 상태에서 어느 한쪽이라도 우연히 HIGH로 latch되면 모터 OUT이 +12V로 끌려 의도치 않은 회전이 발생할 수 있다. 양쪽 IN을 LOW로 fix해 두면 두 BTS7960 OUT 모두 GND → 모터 양 단자 동전위 → 정지 상태로 안전하게 머문다.

### 14-4. 빌드/머지 산출물 (2026-05-07 21:51, **현재 deployed**)

| 파일 | md5 | 비고 |
|---|---|---|
| `02_interface/dtbo/digital-interface-pinmux.dtbo` | `927e784d67288715f4d45d9ed11388dc` | LIFT IN1/IN2 추가 |
| `/boot/digital-interface-pinmux.dtbo` | 동일 | 부팅 입력 |
| `/boot/dtb/kernel_*-nv-super.merged.dtb` | `01bb168a780e8943e39dad04503c4753` | 254,785 B, 부팅 FDT 타깃 |
| `/boot/digital-interface-pinmux.dtbo.bak.before-lift.20260507-215102` | `319e423d49f847fd6f50ed8e2a468a5a` (실제로는 §13 deploy본 = `18666d584be6d9c2eb322b1dce60d57b`) | 14 직전 dtbo |
| `/boot/dtb/kernel_*-nv-super.merged.dtb.bak.before-lift.20260507-215102` | `6e3cad35f68c56760fbac20c58550d5d` | 14 직전 머지 DTB (§13 결과물) |
| `02_interface/dtbo/digital-interface-pinmux.dts.bak.before-lift.20260507-215102` | — | 14 직전 dts 백업 |

`extlinux.conf`는 변경 없음.

### 14-5. 재부팅 후 검증 절차 — 다음 세션 진입 시 첫 작업

머지 DTB가 갱신됐으니 재부팅 후 새 세션에서 아래 순서로 검증한다. 시스템 비번: `123456`.

```bash
# (a) 머지 DTB md5 — 부팅된 게 새 버전인지 확인
md5sum /boot/dtb/kernel_tegra234-p3768-0000+p3767-0005-nv-super.merged.dtb
# 기대: 01bb168a780e8943e39dad04503c4753

# (b) pinmux owner — 7개 핀 모두 HOG 등록되는지
sudo grep -E "pin (41|43|50|53|106|122|125) " \
  /sys/kernel/debug/pinctrl/2430000.pinmux/pinmux-pins
# 기대 (신규 두 줄):
#   pin 43 (SOC_GPIO21_PH0): 2430000.pinmux (...) (HOG) function rsvd0 group soc_gpio21_ph0
#   pin 53 (SOC_GPIO44_PI2): 2430000.pinmux (...) (HOG) function rsvd0 group soc_gpio44_pi2
# 기존 5개도 그대로 owner 표시 유지되는지 회귀 확인.

# (c) idle — pull-down으로 둘 다 LOW
gpioget gpiochip0 43 53
# 기대: 0 0
sleep 5; gpioget gpiochip0 43 53
# 여전히 0 0 (시간 경과해도 floating으로 흔들리지 않는지)

# (d) 라이브 토글 — 한 방향씩 짧게 (2초)
#     ⚠️ 첫 시도 전 리프트가 충분한 가동 범위에 있는지 육안 확인
sudo gpioset --mode=time --sec=2 gpiochip0 43=1 53=0
# 기대: 한 방향 회전, 2초 뒤 line 모두 0/0 복귀로 정지
sudo gpioset --mode=time --sec=2 gpiochip0 43=0 53=1
# 기대: 반대 방향 회전 후 정지

# (e) 회귀 — BUTTON/PIR/FAN 기존 동작 유지
gpioget gpiochip0 50 122 125
# 기대: 1 1 ?(PIR 상태 의존)
sudo python3 tests/test_fan1_toggle.py --period 2 --cycles 2
# 기대: 보드 FAN1(Pin32) 회전 정상
sudo gpioset --mode=time --sec=2 gpiochip0 106=0
# 기대: 보드 FAN2(Pin31) 회전 정상

# (f) 카메라 회귀 (연결 시)
ls /dev/video*
```

#### 결과 분기

| 결과 | 의미 / 다음 단계 |
|---|---|
| (b) pin 43, 53 모두 `function rsvd0` HOG + (c) idle 0 0 안정 + (d) 양방향 회전 + (e) 회귀 OK | **LIFT 핀 추가 완료**. `src/lift.py` 모듈화 등 다음 단계로 진행. |
| (b) pin 43 또는 53 `MUX UNCLAIMED` | dtc 매칭 실패 가능성. `fdtdump` 로 머지 DTB 안에 두 노드가 있는지 확인 (이미 21:51 시점엔 있었음). md5 일치 확인. |
| (c) idle 0 0인데 (d) 한쪽 방향만 동작 | 74HC244 1A0/1A2 결선, BTS7960B 한쪽 칩 점검. 두 GPIO가 line 43↔53 BCM13↔BCM19 순서 맞는지 헷갈리면 보드 J5 핀 매핑 (Pin 33=BCM13=line 43, Pin 35=BCM19=line 53) 재확인. |
| (e) 어느 회귀라도 깨짐 | LIFT 노드 추가가 다른 핀 적용에 영향 — 14 직전 백업으로 롤백:<br>`sudo cp /boot/digital-interface-pinmux.dtbo.bak.before-lift.20260507-215102 /boot/digital-interface-pinmux.dtbo`<br>`sudo cp /boot/dtb/kernel_*-nv-super.merged.dtb.bak.before-lift.20260507-215102 /boot/dtb/kernel_*-nv-super.merged.dtb`<br>재부팅 후 회귀 재확인. |
| (a) md5 불일치 | 부팅 메뉴가 다른 라벨로 갔거나 머지 DTB가 안 갱신된 상태. `grep "^DEFAULT" /boot/extlinux/extlinux.conf` 로 확인. |

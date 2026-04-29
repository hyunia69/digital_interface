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
                fan1_pq6     { nvidia,pins="soc_gpio33_pq6"; nvidia,function="rsvd0"; ...OUT };
                fan2_pg6     { nvidia,pins="soc_gpio19_pg6"; nvidia,function="rsvd0"; ...OUT };
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
| PG.06 | `rsvd0` | rsvd0에 `soc_gpio19_pg6` 포함 |

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

## 8. 미해결/후속 항목

- **BME280 (I2C1 0x76) 미응답**: i2cdetect 결과 buses 1번에서 0x76 응답 없음. I2C1은 default DTB에 활성이지만 BME280 모듈 자체의 전원/결선 문제일 가능성. 인터페이스 보드 DTBO 적용 후 재확인 예정.
- **PIR (HW-MS03) 동작 검증**: idle/motion 시 출력 레벨 실제 측정 필요.
- **FAN 출력 검증**: GPIO를 토글했을 때 옵토 LED → MOSFET → 팬 회전 체인 동작 확인.

## 9. 참고 — 관련 파일

| 파일 | 역할 |
|---|---|
| `02_interface/dtbo/digital-interface-pinmux.dts` | DTBO 소스 (이 작업의 본체) |
| `02_interface/dtbo/digital-interface-pinmux.dtbo` | 컴파일된 dtbo (`/boot/`에도 동일 파일 배치) |
| `02_interface/20260429_회로도.pdf` | 회로도 (BUTTON 풀업 등 회로 설계) |
| `02_interface/20260429_보드배치도.png` | 보드 배치도 (커넥터 위치) |
| `tests/test_button_raw.py` | 외부 풀업 가정으로 주석 정정 |
| `tests/test_button_diag.py` | gpiod 기반 진단 스크립트 (SoC 라인 오프셋 직접 사용) |
| `/boot/extlinux/extlinux.conf` | 부팅 LABEL 수정 |
| `/boot/extlinux/extlinux.conf.bak.before-interface-pinmux` | 변경 전 백업 |
| `/boot/digital-interface-pinmux.dtbo` | 부팅에 사용되는 dtbo |

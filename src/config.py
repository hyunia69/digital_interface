"""GPIO pin mapping and timing constants for the interface board."""

# GPIO mode: BCM numbering
# Matches 40-pin header via BCM GPIO numbers

# Button pins (Momentary NO, pulled HIGH, active LOW)
BUTTON1_PIN = 18   # Zoom In  - Pin 12 (GP122 / I2S0_SCLK)
BUTTON2_PIN = 27   # Zoom Out - Pin 13 (GP36 / SPI3_CLK)

# PIR sensor pin (HW-MS03, HIGH = motion detected)
PIR_PIN = 24       # Pin 18 (GP39 / SPI3_CS0)

# Timing
DEBOUNCE_MS = 200       # Button debounce in milliseconds
PIR_COOLDOWN_SEC = 3    # PIR re-trigger suppression in seconds

# Serial / RS232C (BINGO card dongle)
SERIAL_PORT = "/dev/ttyTHS1"   # UART1: Pin8 TXD, Pin10 RXD
SERIAL_BAUDRATE = 115200
SERIAL_TIMEOUT = 5.0           # Read timeout in seconds

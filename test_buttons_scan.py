#!/usr/bin/env python3
"""Scan ALL GPIO pins to find which ones respond to button presses.

Run: sudo python3 test_buttons_scan.py
Press each button one at a time. The script will show which pin changed.
Ctrl+C to exit.
"""

import time
import RPi.GPIO as GPIO

# All usable BOARD pins on Pi Zero 2 W 40-pin header
# Excluding: power (1,2,4,17), ground (6,9,14,20,25,30,34,39), and reserved
SCAN_PINS = [
    3, 5, 7, 8, 10, 11, 12, 13, 15, 16, 18, 19, 21, 22, 23, 24, 26,
    27, 28, 29, 31, 32, 33, 35, 36, 37, 38, 40,
]

# Known pins to skip (already used by LCD/SPI/LED)
KNOWN_USED = {
    7: "LCD_RST",
    8: "SPI_CE0",
    10: "SPI_MISO",
    11: "MAIN_BTN",
    12: "SPI_MOSI",
    13: "LCD_DC",
    15: "BACKLIGHT",
    16: "LED_BLUE",
    18: "LED_GREEN",
    19: "SPI_MOSI",
    21: "SPI_MISO",
    22: "LED_RED",
    23: "SPI_CLK",
    24: "SPI_CE0",
}

GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)

# Try to set up each pin as input with pull-up
active_pins = []
for pin in SCAN_PINS:
    try:
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        active_pins.append(pin)
    except Exception as e:
        pass

prev = {}
for pin in active_pins:
    prev[pin] = GPIO.input(pin)

print(f"Scanning {len(active_pins)} GPIO pins for button presses...")
print(f"Known buttons: MAIN=11, B=31, C=32")
print(f"Looking for: A and D")
print("-" * 50)
print("Press buttons one at a time. Ctrl+C to exit.\n")

try:
    while True:
        for pin in active_pins:
            val = GPIO.input(pin)
            if val != prev[pin]:
                action = "RELEASED" if val else "PRESSED"
                label = KNOWN_USED.get(pin, "??? UNKNOWN")
                print(f"[{time.strftime('%H:%M:%S')}] Pin {pin:>2} ({label:>12}): {action}")
                prev[pin] = val
        time.sleep(0.015)
except KeyboardInterrupt:
    print("\nDone.")
finally:
    GPIO.cleanup()

#!/usr/bin/env python3
"""Focused button test — only known button pins.

Run: sudo python3 test_buttons_focused.py
Press each physical button one at a time, left to right.
"""

import time
import RPi.GPIO as GPIO

# Only test known/suspected button pins
PINS = {
    11: "MAIN (known)",
    29: "A (config)",
    31: "B (config)",
    32: "C (config)",
    33: "D (config)",
    35: "maybe btn?",
    36: "maybe btn?",
    37: "maybe btn?",
    38: "maybe btn?",
    40: "mystery btn",
}

GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)

for pin in PINS:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

prev = {}
for pin in PINS:
    val = GPIO.input(pin)
    prev[pin] = val
    state = "LOW (pressed?)" if not val else "HIGH (idle)"
    print(f"  Pin {pin:>2} [{PINS[pin]:>14}]: {state}")

print("\nPress each of the 5 buttons one at a time. Ctrl+C to exit.\n")

try:
    while True:
        for pin in PINS:
            val = GPIO.input(pin)
            if val != prev[pin]:
                action = "PRESSED " if not val else "RELEASED"
                print(f"[{time.strftime('%H:%M:%S')}] Pin {pin:>2} ({PINS[pin]:>14}): {action}")
                prev[pin] = val
        time.sleep(0.01)
except KeyboardInterrupt:
    print("\nDone.")
finally:
    GPIO.cleanup()

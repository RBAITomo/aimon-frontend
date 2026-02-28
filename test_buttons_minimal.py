#!/usr/bin/env python3
"""Minimal test — ONLY the 4 pins that confirmed working.

Run: sudo python3 test_buttons_minimal.py
Press ALL 5 physical buttons one at a time. Report which pin fires for each.
"""

import time
import RPi.GPIO as GPIO

PINS = {11: "MAIN", 31: "pin31", 32: "pin32", 40: "pin40"}

GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)

for pin in PINS:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

prev = {p: GPIO.input(p) for p in PINS}

print("Monitoring pins: 11, 31, 32, 40")
print("Press ALL 5 physical buttons one at a time.\n")

try:
    while True:
        for pin in PINS:
            val = GPIO.input(pin)
            if val != prev[pin]:
                action = "PRESSED " if not val else "RELEASED"
                print(f"[{time.strftime('%H:%M:%S')}] {PINS[pin]:>6} (pin {pin}): {action}")
                prev[pin] = val
        time.sleep(0.01)
except KeyboardInterrupt:
    print("\nDone.")
finally:
    GPIO.cleanup()

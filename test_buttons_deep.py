#!/usr/bin/env python3
"""Deep GPIO scan — try every pin including ones that fail with PUD_UP.

Run: sudo python3 test_buttons_deep.py
"""

import time
import RPi.GPIO as GPIO

ALL_PINS = list(range(3, 41))
# Power/ground pins that can't be used as GPIO
SKIP = {1, 2, 4, 6, 9, 14, 17, 20, 25, 30, 34, 39}

GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)

active = []
failed = []

for pin in ALL_PINS:
    if pin in SKIP:
        continue
    for pud in [GPIO.PUD_UP, GPIO.PUD_DOWN, GPIO.PUD_OFF]:
        try:
            GPIO.setup(pin, GPIO.IN, pull_up_down=pud)
            active.append(pin)
            break
        except Exception as e:
            pass
    else:
        failed.append(pin)

print(f"Active: {len(active)} pins: {active}")
if failed:
    print(f"Failed: {len(failed)} pins: {failed}")
print()

prev = {}
for pin in active:
    prev[pin] = GPIO.input(pin)

# Show initial state of all pins
print("Initial pin states:")
for pin in active:
    print(f"  Pin {pin:>2}: {'HIGH' if prev[pin] else 'LOW'}")
print()
print("Press A and D separately. Ctrl+C to exit.\n")

try:
    while True:
        for pin in active:
            val = GPIO.input(pin)
            if val != prev[pin]:
                action = "RELEASED" if val else "PRESSED"
                print(f"[{time.strftime('%H:%M:%S')}] Pin {pin:>2}: {action}")
                prev[pin] = val
        time.sleep(0.01)
except KeyboardInterrupt:
    print("\nDone.")
finally:
    GPIO.cleanup()

#!/usr/bin/env python3
"""Test script: poll all 5 buttons and print state changes.

Run: sudo python3 test_buttons.py
Press Ctrl+C to exit.
"""

import time
import RPi.GPIO as GPIO

# BOARD pin numbering (matches Whisplay HAT schematic)
BUTTONS = {
    11: "MAIN",
    29: "A",
    31: "B",
    32: "C",
    33: "D",
}

GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)

for pin in BUTTONS:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

prev = {}
for pin in BUTTONS:
    prev[pin] = GPIO.input(pin)

print("Button test started. Press buttons...")
print(f"{'Pin':>4}  {'Name':>5}  Initial state")
print("-" * 30)
for pin, name in BUTTONS.items():
    state = "HIGH (released)" if prev[pin] else "LOW (pressed)"
    print(f"{pin:>4}  {name:>5}  {state}")
print("-" * 30)
print("Waiting for changes... (Ctrl+C to exit)\n")

try:
    while True:
        for pin, name in BUTTONS.items():
            val = GPIO.input(pin)
            if val != prev[pin]:
                action = "RELEASED" if val else "PRESSED"
                print(f"[{time.strftime('%H:%M:%S')}] Button {name} (pin {pin}): {action}")
                prev[pin] = val
        time.sleep(0.02)  # 20ms poll
except KeyboardInterrupt:
    print("\nDone.")
finally:
    GPIO.cleanup()

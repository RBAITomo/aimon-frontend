#!/usr/bin/env python3
"""Guided button test — press one button at a time when prompted.

Run: sudo python3 test_buttons_guided.py
"""

import time
import RPi.GPIO as GPIO

PINS = [11, 31, 32, 40]

GPIO.setmode(GPIO.BOARD)
GPIO.setwarnings(False)
for pin in PINS:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def wait_for_press():
    """Wait for any pin to go LOW, return set of pins that fired."""
    # Wait for all pins to be released first
    while True:
        if all(GPIO.input(p) for p in PINS):
            break
        time.sleep(0.01)

    # Wait for a press
    fired = set()
    while not fired:
        for p in PINS:
            if not GPIO.input(p):
                fired.add(p)
        time.sleep(0.005)

    # Brief settle time to catch simultaneous pins
    time.sleep(0.05)
    for p in PINS:
        if not GPIO.input(p):
            fired.add(p)

    # Wait for release
    while True:
        if all(GPIO.input(p) for p in PINS):
            break
        time.sleep(0.01)

    return fired


try:
    buttons = ["MAIN (big button)", "top-left side button", "top-right side button",
               "bottom-left side button", "bottom-right side button"]

    print("=== GUIDED BUTTON TEST ===")
    print("Press ONLY the button asked for. Press gently, one at a time.\n")

    for i, name in enumerate(buttons):
        input(f"  >> Press ENTER, then press [{name}] once...")
        fired = wait_for_press()
        pins_str = ", ".join(str(p) for p in sorted(fired))
        print(f"     Result: pins [{pins_str}]\n")

    print("=== DONE ===")
    print("Copy the output above and send it.")

except KeyboardInterrupt:
    print("\nCancelled.")
finally:
    GPIO.cleanup()

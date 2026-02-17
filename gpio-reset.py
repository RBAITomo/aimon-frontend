#!/usr/bin/env python3
"""Reset GPIO state for AI-MON frontend."""

import sys

try:
    import RPi.GPIO as GPIO
    
    print("Resetting GPIO...")
    GPIO.setmode(GPIO.BOARD)
    GPIO.setwarnings(False)
    
    # Clean up all GPIO
    GPIO.cleanup()
    
    print("✅ GPIO reset complete!")
    print("You can now run: ./run.sh")
    
except Exception as e:
    print(f"❌ Error: {e}")
    sys.exit(1)

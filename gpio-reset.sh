#!/usr/bin/env bash
# Reset GPIO state before running AI-MON frontend

echo "Resetting GPIO pins..."

# Unexport all GPIO pins
for pin in /sys/class/gpio/gpio*/; do
    if [ -d "$pin" ]; then
        pin_num=$(basename "$pin" | sed 's/gpio//')
        echo "$pin_num" > /sys/class/gpio/unexport 2>/dev/null || true
    fi
done

# Kill any existing Python processes using GPIO
pkill -f "python.*main.py" 2>/dev/null || true

echo "GPIO reset complete. You can now run ./run.sh"

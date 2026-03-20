"""Whisplay HAT hardware abstraction: ST7789 LCD, button, RGB LED.

Ported from whisplay-ai-chatbot/python/whisplay.py for AI-MON.
Pin layout uses BOARD numbering matching the Whisplay HAT schematic.
"""

import time
import logging
import threading

import RPi.GPIO as GPIO
import spidev
import numpy as np

import config

log = logging.getLogger(__name__)

# BOARD pin 15 = BCM 22; pigpio uses BCM numbering for DMA PWM
_BACKLIGHT_BCM = 22


class WhisplayHAT:
    """Singleton wrapper for Whisplay HAT peripherals."""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        GPIO.setmode(GPIO.BOARD)
        GPIO.setwarnings(False)

        self._init_lcd()
        self._init_led()
        self._init_button()

        log.info("WhisplayHAT initialized")

    # ===== LCD (ST7789 240x280 via SPI) =====

    def _init_lcd(self):
        GPIO.setup(
            [config.PIN_DC, config.PIN_RST, config.PIN_BACKLIGHT], GPIO.OUT
        )
        # Enable backlight immediately (active-low: LOW = on)
        GPIO.output(config.PIN_BACKLIGHT, GPIO.LOW)

        # Prefer stable PWM over RPi.GPIO software PWM.
        # RPi.GPIO uses a Python thread + time.sleep() → OS scheduler jitter → visible flicker.
        # Priority: lgpio (Bookworm/kernel 6.6+ compatible, apt) → pigpio DMA (older OS, manual
        # install) → RPi.GPIO (last resort).
        self._lgpio_h = None
        self._pi = None
        self._bl_pwm = None
        try:
            import lgpio
            h = lgpio.gpiochip_open(0)
            # duty 0 = GPIO always LOW = full brightness (active-low backlight)
            lgpio.tx_pwm(h, _BACKLIGHT_BCM, 800, 0)
            self._lgpio_h = h
            log.info("Backlight: lgpio software PWM at 800 Hz (Bookworm-compatible)")
        except Exception as e_lg:
            log.warning("lgpio unavailable (%s); trying pigpio DMA PWM", e_lg)
            try:
                import pigpio
                pi = pigpio.pi()
                if not pi.connected:
                    raise RuntimeError("pigpiod not running — run: sudo systemctl start pigpiod")
                # range 0-100 maps 1:1 to brightness; 800 Hz is well above flicker threshold
                pi.set_PWM_range(_BACKLIGHT_BCM, 100)
                pi.set_PWM_frequency(_BACKLIGHT_BCM, 800)
                pi.set_PWM_dutycycle(_BACKLIGHT_BCM, 0)  # 0 = GPIO always LOW = full brightness
                self._pi = pi
                log.info("Backlight: pigpio DMA PWM at 800 Hz (flicker-free)")
            except Exception as e_pi:
                log.warning("pigpio unavailable (%s); falling back to RPi.GPIO software PWM", e_pi)
                self._bl_pwm = GPIO.PWM(config.PIN_BACKLIGHT, 800)
                self._bl_pwm.start(0)  # 0% duty = LOW = backlight ON

        # SPI bus
        self.spi = spidev.SpiDev()
        self.spi.open(config.SPI_BUS, config.SPI_DEVICE)
        self.spi.max_speed_hz = config.SPI_SPEED_HZ
        self.spi.mode = 0b00
        log.info("SPI opened bus=%d dev=%d speed=%dHz",
                 config.SPI_BUS, config.SPI_DEVICE, config.SPI_SPEED_HZ)

        self._reset_lcd()
        self._init_display_registers()
        # Startup test: flash green to verify LCD hardware works
        log.info("LCD init complete, flashing green test pattern...")
        self.fill_screen(0x07E0)  # green
        time.sleep(0.5)
        self.fill_screen(0x0000)  # then clear to black
        log.info("LCD startup test done")

    def _reset_lcd(self):
        GPIO.output(config.PIN_RST, GPIO.HIGH)
        time.sleep(0.1)
        GPIO.output(config.PIN_RST, GPIO.LOW)
        time.sleep(0.1)
        GPIO.output(config.PIN_RST, GPIO.HIGH)
        time.sleep(0.12)

    def _init_display_registers(self):
        """ST7789 initialization sequence."""
        self._cmd(0x11)  # Sleep out
        time.sleep(0.12)
        self._cmd(0x36, 0x60)  # Memory access: landscape mode (MX=1, MV=1)
        self._cmd(0x3A, 0x05)  # 16-bit color (RGB565)
        self._cmd(0xB2, 0x0C, 0x0C, 0x00, 0x33, 0x33)  # Porch
        self._cmd(0xB7, 0x35)  # Gate
        self._cmd(0xBB, 0x32)  # VCOM
        self._cmd(0xC2, 0x01)  # VDV/VRH enable
        self._cmd(0xC3, 0x15)  # VRH
        self._cmd(0xC4, 0x20)  # VDV
        self._cmd(0xC6, 0x0F)  # Frame rate
        self._cmd(0xD0, 0xA4, 0xA1)  # Power
        # Gamma positive
        self._cmd(
            0xE0, 0xD0, 0x08, 0x0E, 0x09, 0x09, 0x05,
            0x31, 0x33, 0x48, 0x17, 0x14, 0x15, 0x31, 0x34,
        )
        # Gamma negative
        self._cmd(
            0xE1, 0xD0, 0x08, 0x0E, 0x09, 0x09, 0x15,
            0x31, 0x33, 0x48, 0x17, 0x14, 0x15, 0x31, 0x34,
        )
        self._cmd(0x21)  # Inversion on
        self._cmd(0x29)  # Display on

    def _cmd(self, cmd, *args):
        """Send command byte, optionally followed by data bytes."""
        GPIO.output(config.PIN_DC, GPIO.LOW)
        self.spi.xfer2([cmd])
        if args:
            GPIO.output(config.PIN_DC, GPIO.HIGH)
            self._spi_write(list(args))

    def _spi_write(self, data):
        """Send data bytes to LCD with DC=HIGH. Accepts list or bytes."""
        GPIO.output(config.PIN_DC, GPIO.HIGH)
        try:
            self.spi.writebytes2(data)
        except AttributeError:
            # Fallback for older spidev without writebytes2
            if isinstance(data, (bytes, bytearray)):
                data = list(data)
            for i in range(0, len(data), 4096):
                self.spi.writebytes(data[i : i + 4096])

    def _set_window(self, x0, y0, x1, y1):
        """Set draw region with 20px corner offset on X-axis for landscape mode."""
        off = config.LCD_CORNER_HEIGHT
        self._cmd(
            0x2A,
            (x0 + off) >> 8, (x0 + off) & 0xFF,
            (x1 + off) >> 8, (x1 + off) & 0xFF,
        )
        self._cmd(0x2B, y0 >> 8, y0 & 0xFF, y1 >> 8, y1 & 0xFF)
        self._cmd(0x2C)

    def fill_screen(self, color_rgb565):
        """Fill entire LCD with a single RGB565 color."""
        self._set_window(0, 0, config.LCD_WIDTH - 1, config.LCD_HEIGHT - 1)
        high = (color_rgb565 >> 8) & 0xFF
        low = color_rgb565 & 0xFF
        row = [high, low] * config.LCD_WIDTH
        for _ in range(config.LCD_HEIGHT):
            self._spi_write(row)

    def draw_frame(self, rgb565_bytes):
        """Write full-frame RGB565 data (240*280*2 bytes) to LCD.

        Sends in 4096-byte chunks to stay within SPI bufsiz limit.
        """
        self._set_window(0, 0, config.LCD_WIDTH - 1, config.LCD_HEIGHT - 1)
        GPIO.output(config.PIN_DC, GPIO.HIGH)
        # Chunk data to avoid SPI bufsiz overflow (default 4096 bytes)
        _CHUNK = 4096
        try:
            for i in range(0, len(rgb565_bytes), _CHUNK):
                self.spi.writebytes2(rgb565_bytes[i:i + _CHUNK])
        except AttributeError:
            if isinstance(rgb565_bytes, (bytes, bytearray)):
                rgb565_bytes = list(rgb565_bytes)
            for i in range(0, len(rgb565_bytes), _CHUNK):
                self.spi.writebytes(rgb565_bytes[i:i + _CHUNK])

    def set_backlight(self, brightness):
        """Set LCD backlight 0-100. Uses lgpio/pigpio PWM if available."""
        if not 0 <= brightness <= 100:
            return
        duty = 100 - brightness  # active-low: duty 0 = full on, 100 = off
        if self._lgpio_h is not None:
            import lgpio
            lgpio.tx_pwm(self._lgpio_h, _BACKLIGHT_BCM, 800, duty)
        elif self._pi is not None:
            self._pi.set_PWM_dutycycle(_BACKLIGHT_BCM, duty)
        elif self._bl_pwm is not None:
            self._bl_pwm.ChangeDutyCycle(duty)

    # ===== RGB LED (common-anode, PWM) =====

    def _init_led(self):
        GPIO.setup(
            [config.PIN_LED_RED, config.PIN_LED_GREEN, config.PIN_LED_BLUE],
            GPIO.OUT,
        )
        self._r_pwm = GPIO.PWM(config.PIN_LED_RED, 100)
        self._g_pwm = GPIO.PWM(config.PIN_LED_GREEN, 100)
        self._b_pwm = GPIO.PWM(config.PIN_LED_BLUE, 100)
        self._r_pwm.start(0)
        self._g_pwm.start(0)
        self._b_pwm.start(0)
        self._cur_rgb = (0, 0, 0)

    def set_rgb(self, r, g, b):
        """Set RGB LED color (0-255 per channel, common-anode inverted)."""
        self._r_pwm.ChangeDutyCycle(100 - (r / 255 * 100))
        self._g_pwm.ChangeDutyCycle(100 - (g / 255 * 100))
        self._b_pwm.ChangeDutyCycle(100 - (b / 255 * 100))
        self._cur_rgb = (r, g, b)

    def set_rgb_tuple(self, rgb):
        """Set RGB LED from (r, g, b) tuple."""
        self.set_rgb(*rgb)

    # ===== Buttons (GPIO interrupt with polling fallback) =====

    # All button configs: (pin, suffix) — suffix used for attribute/method names
    _BUTTON_CONFIGS = [
        (config.PIN_BUTTON, ""),      # main button (no suffix)
        (config.PIN_BUTTON_A, "_a"),
        (config.PIN_BUTTON_B, "_b"),
        (config.PIN_BUTTON_C, "_c"),
        (config.PIN_BUTTON_D, "_d"),
    ]

    def _init_button(self):
        self._poll_thread = None
        self._poll_stop = threading.Event()
        self._use_polling = False

        # Init callback storage for each button
        for _pin, suffix in self._BUTTON_CONFIGS:
            setattr(self, f"_on_press{suffix}", None)
            setattr(self, f"_on_release{suffix}", None)

        # Clean up and setup each pin
        all_pins = [pin for pin, _ in self._BUTTON_CONFIGS]
        for pin in all_pins:
            try:
                GPIO.remove_event_detect(pin)
            except Exception:
                pass
            try:
                GPIO.cleanup(pin)
            except Exception:
                pass
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Try edge detection; fall back to polling on Bookworm 6.6+ kernels
        try:
            for pin, _suffix in self._BUTTON_CONFIGS:
                GPIO.add_event_detect(
                    pin, GPIO.BOTH,
                    callback=self._button_event, bouncetime=50,
                )
            log.info("Buttons: using GPIO edge detection (pins %s)", all_pins)
        except RuntimeError:
            log.warning(
                "GPIO edge detection unavailable (Bookworm kernel 6.6+?). "
                "Falling back to polling."
            )
            self._use_polling = True
            self._start_button_poll()

    def _start_button_poll(self):
        """Start a daemon thread that polls all button pins at ~20ms."""
        self._poll_stop.clear()
        self._poll_thread = threading.Thread(
            target=self._button_poll_loop, daemon=True,
        )
        self._poll_thread.start()

    def _button_poll_loop(self):
        """Poll all button states and fire callbacks on transitions.

        Dispatches callbacks in separate threads so slow handlers
        don't block release detection.
        """
        prev = {pin: GPIO.input(pin) for pin, _ in self._BUTTON_CONFIGS}
        while not self._poll_stop.is_set():
            for pin, suffix in self._BUTTON_CONFIGS:
                cur = GPIO.input(pin)
                if cur != prev[pin]:
                    if cur == 0:
                        cb = getattr(self, f"_on_press{suffix}", None)
                        if cb:
                            threading.Thread(target=cb, daemon=True).start()
                    else:
                        cb = getattr(self, f"_on_release{suffix}", None)
                        if cb:
                            threading.Thread(target=cb, daemon=True).start()
                    prev[pin] = cur
            self._poll_stop.wait(0.02)

    def _button_event(self, channel):
        """Dispatch press/release based on GPIO level for any button.

        A small delay before reading lets contact bounce settle so the
        level matches the actual physical state, not a transient spike.
        """
        time.sleep(0.005)  # 5 ms settle time
        suffix = ""
        for pin, s in self._BUTTON_CONFIGS:
            if pin == channel:
                suffix = s
                break
        if GPIO.input(channel):
            cb = getattr(self, f"_on_release{suffix}", None)
            if cb:
                cb()
        else:
            cb = getattr(self, f"_on_press{suffix}", None)
            if cb:
                cb()

    # --- Main button API ---
    def on_button_press(self, callback):
        self._on_press = callback

    def on_button_release(self, callback):
        self._on_release = callback

    def button_pressed(self):
        return GPIO.input(config.PIN_BUTTON) == 0

    # --- Extra button A-D API ---
    def on_button_a_press(self, callback):
        self._on_press_a = callback

    def on_button_a_release(self, callback):
        self._on_release_a = callback

    def button_a_pressed(self):
        return GPIO.input(config.PIN_BUTTON_A) == 0

    def on_button_b_press(self, callback):
        self._on_press_b = callback

    def on_button_b_release(self, callback):
        self._on_release_b = callback

    def button_b_pressed(self):
        return GPIO.input(config.PIN_BUTTON_B) == 0

    def on_button_c_press(self, callback):
        self._on_press_c = callback

    def on_button_c_release(self, callback):
        self._on_release_c = callback

    def button_c_pressed(self):
        return GPIO.input(config.PIN_BUTTON_C) == 0

    def on_button_d_press(self, callback):
        self._on_press_d = callback

    def on_button_d_release(self, callback):
        self._on_release_d = callback

    def button_d_pressed(self):
        return GPIO.input(config.PIN_BUTTON_D) == 0

    # ===== Cleanup =====

    def cleanup(self):
        """Release all hardware resources."""
        # Stop button polling thread if active
        if self._use_polling:
            self._poll_stop.set()
            if self._poll_thread and self._poll_thread.is_alive():
                self._poll_thread.join(timeout=1)
        else:
            for pin, _ in self._BUTTON_CONFIGS:
                try:
                    GPIO.remove_event_detect(pin)
                except Exception:
                    pass

        try:
            self.set_rgb(0, 0, 0)
            self.fill_screen(0x0000)
        except Exception:
            pass

        try:
            self.spi.close()
        except Exception:
            pass

        # Stop backlight PWM (lgpio → pigpio → RPi.GPIO)
        if self._lgpio_h is not None:
            try:
                import lgpio
                lgpio.tx_pwm(self._lgpio_h, _BACKLIGHT_BCM, 0, 0)  # cancel PWM
                lgpio.gpiochip_close(self._lgpio_h)
            except Exception:
                pass
        elif self._pi is not None:
            try:
                self._pi.set_PWM_dutycycle(_BACKLIGHT_BCM, 100)  # backlight off
                self._pi.stop()
            except Exception:
                pass
        elif self._bl_pwm is not None:
            try:
                self._bl_pwm.stop()
            except Exception:
                pass

        for pwm in ('_r_pwm', '_g_pwm', '_b_pwm'):
            try:
                getattr(self, pwm).stop()
            except Exception:
                pass

        GPIO.cleanup()
        log.info("WhisplayHAT cleaned up")


def surface_to_rgb565(pygame_surface):
    """Convert a Pygame RGB surface (240x280) to RGB565 bytes for SPI.

    Args:
        pygame_surface: Pygame Surface in RGB format (must be 24-bit).

    Returns:
        bytes: Big-endian RGB565 pixel data ready for SPI transfer.
    """
    import pygame
    arr = pygame.surfarray.array3d(pygame_surface)  # (W, H, 3)
    arr = arr.transpose(1, 0, 2)  # (H, W, 3)
    r = (arr[:, :, 0] >> 3).astype(np.uint16)
    g = (arr[:, :, 1] >> 2).astype(np.uint16)
    b = (arr[:, :, 2] >> 3).astype(np.uint16)
    rgb565 = (r << 11) | (g << 5) | b
    # Convert to big-endian bytes for SPI (byteswap from native little-endian)
    return rgb565.astype(">u2").tobytes()

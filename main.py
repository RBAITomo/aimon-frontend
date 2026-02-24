"""AI-MON Frontend — Main entry point.

Initializes all modules and runs the Pygame event loop at 30 FPS.
The loop renders the current state to the LCD via SPI each frame.

Usage:
    python3 main.py
"""

import logging
import os
import signal
import sys

# Load .env file before anything reads env vars
from dotenv import load_dotenv
load_dotenv()

# LCD is driven via SPI, not a framebuffer. Use SDL dummy driver so
# pygame works headless (no monitor / no fbcon needed).
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("aimon")


def main():
    log.info("AI-MON Frontend starting...")

    # --- Initialize hardware ---
    from hardware.whisplay_hat import WhisplayHAT
    hat = WhisplayHAT()

    # --- Initialize Pygame subsystems (rendering + audio mixer) ---
    pygame.display.init()
    pygame.display.set_mode((1, 1))  # minimal surface for dummy driver
    pygame.font.init()
    pygame.mixer.init()
    clock = pygame.time.Clock()

    # --- Initialize display engine ---
    from display.display_engine import DisplayEngine
    display = DisplayEngine(hat)

    # --- Initialize audio ---
    from audio.audio_capture import AudioCapture
    from audio.audio_playback import AudioPlayback
    capture = AudioCapture()
    playback = AudioPlayback()

    # --- Initialize storage ---
    from storage.turn_logger import TurnLogger
    turn_logger = TurnLogger()

    # --- Initialize network ---
    from network.ws_client import WSClient
    ws = WSClient()

    # --- Initialize state machine (wires everything together) ---
    from state.state_machine import StateMachine
    sm = StateMachine(hat, display, capture, playback, ws, turn_logger)

    # --- Graceful shutdown ---
    running = True

    def shutdown(signum=None, frame=None):
        nonlocal running
        log.info("Shutting down (signal=%s)...", signum)
        running = False

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    # --- Connect to backend ---
    sm.initial_connect()

    # --- Main event loop (adaptive FPS: 30 active / 10 idle / 1 standby) ---
    log.info("Entering main loop (active=%d FPS, idle=%d FPS, standby=%d FPS)",
             config.LCD_FPS, config.LCD_FPS_IDLE, config.LCD_FPS_STANDBY)
    try:
        while running:
            # Poll Pygame events (needed even without a window)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            # State machine tick: updates display + handles timeouts
            sm.tick()

            # Adaptive FPS: 10fps in IDLE to reduce CPU load, 30fps when active
            clock.tick(sm.target_fps)

    except KeyboardInterrupt:
        log.info("KeyboardInterrupt received")
    finally:
        log.info("Cleaning up...")
        ws.disconnect()
        playback.cleanup()
        capture.cleanup()
        turn_logger.close()
        hat.cleanup()
        pygame.quit()
        log.info("AI-MON Frontend stopped.")


if __name__ == "__main__":
    main()

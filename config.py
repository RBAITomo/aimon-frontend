"""AI-MON frontend configuration loaded from environment variables."""

import os

# --- Backend Connection ---
BACKEND_WS_URL = os.getenv("BACKEND_WS_URL", "ws://localhost:8080")
ROBOT_ID = os.getenv("ROBOT_ID", "robot001")
WS_RECONNECT_INTERVAL_S = 2
WS_RECONNECT_MAX_ATTEMPTS = 5
WS_PING_INTERVAL_S = 15

# --- Audio ---
AUDIO_SAMPLE_RATE = 16000  # mic capture and PCM16 rate (Hz)
AUDIO_CHANNELS = 1
AUDIO_FORMAT_WIDTH = 2  # 16-bit PCM = 2 bytes
AUDIO_FRAME_DURATION_MS = 20  # 20ms capture frames
AUDIO_PLAYBACK_RATE = 24000  # VieNeu TTS native rate is 24kHz, avoids per-chunk resampling artifacts
AUDIO_DEVICE_NAME = "hw:1,0"  # wm8960 on Whisplay HAT

# --- Display ---
LCD_WIDTH = 240
LCD_HEIGHT = 280
LCD_FPS = 30
LCD_CORNER_HEIGHT = 20  # ST7789 corner offset
SPRITE_DIR = os.path.join(os.path.dirname(__file__), "sprites")

# --- Pet UI Layout (240x280 portrait) ---
# Top stat bar region
STAT_BAR_HEIGHT = 24
STAT_BAR_WIDTH = 60
STAT_BAR_THICKNESS = 6
STAT_BAR_Y = 9
STAT_BAR_GAP = 8

# Bottom XP bar region
XP_BAR_HEIGHT = 24
XP_BAR_Y = LCD_HEIGHT - XP_BAR_HEIGHT + 8
XP_BAR_HEIGHT_PX = 8
XP_BAR_X = 40
XP_BAR_WIDTH = LCD_WIDTH - XP_BAR_X - 10

# Content area (between stat bar and XP bar)
CONTENT_Y_START = STAT_BAR_HEIGHT
CONTENT_Y_END = LCD_HEIGHT - XP_BAR_HEIGHT
CONTENT_HEIGHT = CONTENT_Y_END - CONTENT_Y_START

# Character sprite position (centered in content area)
CHAR_SPRITE_SIZE = (156, 156)
CHAR_SPRITE_X = (LCD_WIDTH - 156) // 2
CHAR_SPRITE_Y = CONTENT_Y_START + 10

# Speech bubble (below character)
BUBBLE_Y = CHAR_SPRITE_Y + 160
BUBBLE_HEIGHT = 80
BUBBLE_WIDTH = LCD_WIDTH - 20
BUBBLE_X = 10

# Asset directories
ASSET_DIR = os.path.join(os.path.dirname(__file__), "assets")
BACKGROUND_DIR = os.path.join(os.path.dirname(__file__), "sprites", "backgrounds")

# Animation name mapping: asset folder name -> internal animation name
ANIMATION_MAP = {
    "idle-long": "idle",
    "custom-Listening, with his right ear stretching ": "listening",
    "custom-Happy, heart emoji floating on top": "happy",
    "custom-speaking, happy mood": "speaking",
    "eating": "eating",
    "jump": "jump",
}

# Evolution stage -> asset folder mapping
STAGE_ASSET_MAP = {
    "egg": "Coneko-egg-form",
    "baby": "Coneko-baby-Form",
}

# --- Hardware Pins (BOARD numbering) ---
PIN_BUTTON = 11
PIN_DC = 13
PIN_RST = 7
PIN_BACKLIGHT = 15
PIN_LED_RED = 22
PIN_LED_GREEN = 18
PIN_LED_BLUE = 16

# --- SPI ---
SPI_BUS = 0
SPI_DEVICE = 0
SPI_SPEED_HZ = 100_000_000  # 100MHz

# --- SQLite ---
TURN_DB_PATH = os.getenv(
    "TURN_DB_PATH",
    os.path.join(os.path.dirname(__file__), "data", "turns.db"),
)
TURN_MAX_COUNT = 200

# --- LED Colors (R, G, B) per state ---
LED_IDLE = (30, 60, 120)  # soft blue
LED_LISTENING = (0, 200, 50)  # green
LED_ASR = (200, 180, 0)  # yellow
LED_ANSWER = (0, 180, 200)  # cyan
LED_EMOTION_HAPPY = (255, 200, 0)  # warm yellow
LED_EMOTION_SAD = (80, 80, 200)  # blue
LED_OFFLINE = (200, 30, 30)  # red

"""AI-MON frontend configuration loaded from environment variables."""

import os
from dotenv import load_dotenv

load_dotenv()

# --- Backend Connection ---
BACKEND_WS_URL = os.getenv("BACKEND_WS_URL", "ws://localhost:8080")
ROBOT_ID = os.getenv("ROBOT_ID", "1")  # numeric userId or pet name from pet_profiles
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
CHAR_SPRITE_Y = CONTENT_Y_START + 30

# Speech bubble (below character)
BUBBLE_Y = CHAR_SPRITE_Y + 150
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

# --- Camera ---
CAMERA_ENABLED = os.getenv("CAMERA_ENABLED", "true").lower() == "true"
CAMERA_RATE_LIMIT_S = 30  # min seconds between captures
CAMERA_DOUBLE_PRESS_MS = 500  # max ms between presses for double-press detection
LED_CAMERA = (200, 100, 255)  # purple — camera capture in progress

# --- Gemini Vision (direct from Pi) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
VISION_ENABLED = bool(GEMINI_API_KEY) and CAMERA_ENABLED

# --- SFX & Audio ---
SFX_DIR = os.path.join(os.path.dirname(__file__), "audio", "sfx")
OFFLINE_AUDIO_DIR = os.path.join(os.path.dirname(__file__), "audio", "offline")

# Pygame mixer channel assignments
SFX_CHANNEL_TTS = 0       # reserved for TTS (existing)
SFX_CHANNEL_PRIMARY = 1   # eat, level up, evolution
SFX_CHANNEL_NOTIFY = 2    # badge, quest
SFX_CHANNEL_AMBIENT = 3   # warning, ambient

# Food sprite overlay
FOOD_SPRITE_SIZE = 40
FOOD_SPRITE_MAX = 3
FOOD_TWEEN_FRAMES = 20
# 3 fixed slot positions near pet (below character, spaced horizontally)
FOOD_SLOT_POSITIONS = [
    (CHAR_SPRITE_X + 10, CHAR_SPRITE_Y + CHAR_SPRITE_SIZE[1] - 10),
    (CHAR_SPRITE_X + CHAR_SPRITE_SIZE[0] // 2 - FOOD_SPRITE_SIZE // 2, CHAR_SPRITE_Y + CHAR_SPRITE_SIZE[1]),
    (CHAR_SPRITE_X + CHAR_SPRITE_SIZE[0] - FOOD_SPRITE_SIZE - 10, CHAR_SPRITE_Y + CHAR_SPRITE_SIZE[1] - 10),
]
# Pet center target for tween animation
FOOD_PET_CENTER = (CHAR_SPRITE_X + CHAR_SPRITE_SIZE[0] // 2, CHAR_SPRITE_Y + CHAR_SPRITE_SIZE[1] // 2)

# Animation durations (frames at 30 FPS)
EVOLUTION_ANIM_FRAMES = 90    # 3 seconds
BADGE_POPUP_FRAMES = 90       # 3 seconds
WARNING_ANIM_FRAMES = 60      # 2 seconds
REGRESSION_ANIM_FRAMES = 120  # 4 seconds

# SFX ducking (volume scale 0.0-1.0)
SFX_DUCK_VOLUME = 0.3
SFX_NORMAL_VOLUME = 1.0

"""Generate placeholder sprite PNGs for testing the display engine.

Creates simple geometric animations for each emotion:
- idle: breathing circle (scale pulse)
- listening: expanding rings
- thinking: rotating dots
- happy: bouncing circle with smile
- sad: drooping circle

Run once: python3 generate_placeholder_sprites.py
"""

import math
import os

try:
    from PIL import Image, ImageDraw
except ImportError:
    print("Install Pillow: pip install Pillow")
    raise

W, H = 240, 280
BG = (10, 10, 20)
SPRITE_DIR = os.path.join(os.path.dirname(__file__), "sprites")


def _save(img, emotion, idx):
    d = os.path.join(SPRITE_DIR, emotion)
    os.makedirs(d, exist_ok=True)
    img.save(os.path.join(d, f"frame-{idx:03d}.png"))


def gen_idle(frames=30):
    """Breathing circle that pulses in size."""
    cx, cy = W // 2, H // 2 - 20
    for i in range(frames):
        img = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(img)
        t = i / frames * 2 * math.pi
        r = 40 + int(8 * math.sin(t))
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(80, 200, 180))
        # Eyes
        draw.ellipse([cx - 12, cy - 10, cx - 6, cy - 4], fill=BG)
        draw.ellipse([cx + 6, cy - 10, cx + 12, cy - 4], fill=BG)
        # Mouth
        draw.arc([cx - 10, cy + 2, cx + 10, cy + 16], 0, 180, fill=BG, width=2)
        _save(img, "idle", i)
    print(f"  idle: {frames} frames")


def gen_listening(frames=10):
    """Expanding concentric rings."""
    cx, cy = W // 2, H // 2 - 20
    for i in range(frames):
        img = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(img)
        # Pet circle
        draw.ellipse([cx - 35, cy - 35, cx + 35, cy + 35], fill=(0, 200, 50))
        draw.ellipse([cx - 12, cy - 10, cx - 6, cy - 4], fill=BG)
        draw.ellipse([cx + 6, cy - 10, cx + 12, cy - 4], fill=BG)
        # Rings
        for ring in range(3):
            r = 50 + (i + ring * 4) * 5
            alpha = max(0, 255 - r * 2)
            col = (0, min(255, alpha), 50)
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=2)
        _save(img, "listening", i)
    print(f"  listening: {frames} frames")


def gen_thinking(frames=15):
    """Three rotating dots."""
    cx, cy = W // 2, H // 2 - 20
    for i in range(frames):
        img = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(img)
        # Pet circle (dimmed)
        draw.ellipse([cx - 35, cy - 35, cx + 35, cy + 35], fill=(100, 100, 50))
        # Rotating dots
        for d in range(3):
            angle = (i / frames * 2 * math.pi) + (d * 2 * math.pi / 3)
            dx = cx + int(55 * math.cos(angle))
            dy = cy + int(55 * math.sin(angle))
            draw.ellipse([dx - 6, dy - 6, dx + 6, dy + 6], fill=(200, 180, 0))
        _save(img, "thinking", i)
    print(f"  thinking: {frames} frames")


def gen_happy(frames=20):
    """Bouncing circle with wide smile."""
    cx = W // 2
    for i in range(frames):
        img = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(img)
        t = i / frames * math.pi
        cy = H // 2 - 20 - int(30 * abs(math.sin(t)))
        r = 40
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 200, 0))
        # Happy eyes (^_^)
        draw.arc([cx - 16, cy - 14, cx - 4, cy - 2], 180, 360, fill=BG, width=2)
        draw.arc([cx + 4, cy - 14, cx + 16, cy - 2], 180, 360, fill=BG, width=2)
        # Wide smile
        draw.arc([cx - 18, cy + 2, cx + 18, cy + 22], 0, 180, fill=BG, width=3)
        _save(img, "happy", i)
    print(f"  happy: {frames} frames")


def gen_sad(frames=20):
    """Slowly drooping circle with frown."""
    cx = W // 2
    for i in range(frames):
        img = Image.new("RGB", (W, H), BG)
        draw = ImageDraw.Draw(img)
        cy = H // 2 - 20 + int(10 * (i / frames))
        r = 38
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(80, 80, 200))
        # Sad eyes
        draw.ellipse([cx - 12, cy - 10, cx - 6, cy - 4], fill=BG)
        draw.ellipse([cx + 6, cy - 10, cx + 12, cy - 4], fill=BG)
        # Frown
        draw.arc([cx - 14, cy + 8, cx + 14, cy + 24], 180, 360, fill=BG, width=2)
        _save(img, "sad", i)
    print(f"  sad: {frames} frames")


if __name__ == "__main__":
    print("Generating placeholder sprites (240x280 PNGs)...")
    gen_idle()
    gen_listening()
    gen_thinking()
    gen_happy()
    gen_sad()
    print("Done! Sprites saved to sprites/")

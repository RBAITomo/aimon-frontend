"""Sprite sheet loader and frame-by-frame animation manager.

Loads PNG frames from sprites/{emotion}/ directories and provides
the correct frame for the current animation tick.
"""

import os
import json
import logging

import pygame

import config

log = logging.getLogger(__name__)

# Default animation metadata if metadata.json is missing
_DEFAULT_META = {
    "idle": {"fps": 5, "loop": True},
    "listening": {"fps": 15, "loop": True},
    "thinking": {"fps": 8, "loop": True},
    "happy": {"fps": 10, "loop": False},
    "sad": {"fps": 8, "loop": False},
}


class SpriteManager:
    """Loads and caches sprite animations, returns frames by tick."""

    def __init__(self):
        self._cache = {}  # {emotion: [Surface, ...]}
        self._meta = self._load_metadata()
        self._preload_sprites()

    def _load_metadata(self):
        path = os.path.join(config.SPRITE_DIR, "metadata.json")
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                log.warning("Failed to load sprite metadata: %s", e)
        return _DEFAULT_META

    def _preload_sprites(self):
        """Load all sprite frames into memory on startup."""
        for emotion in self._meta:
            frames = self._load_emotion(emotion)
            if frames:
                self._cache[emotion] = frames
                log.info("Loaded %d frames for '%s'", len(frames), emotion)
            else:
                log.warning("No sprite frames found for '%s'", emotion)

    def _load_emotion(self, emotion):
        """Load sorted PNG frames from sprites/{emotion}/ directory."""
        sprite_dir = os.path.join(config.SPRITE_DIR, emotion)
        if not os.path.isdir(sprite_dir):
            return []

        files = sorted(
            f for f in os.listdir(sprite_dir)
            if f.lower().endswith(".png")
        )
        frames = []
        for fname in files:
            try:
                path = os.path.join(sprite_dir, fname)
                # Skip .convert() — SDL dummy driver on headless Pi may
                # produce incompatible display format (8-bit/broken palette)
                surf = pygame.image.load(path)
                # Scale to LCD size if needed
                if surf.get_size() != (config.LCD_WIDTH, config.LCD_HEIGHT):
                    surf = pygame.transform.scale(
                        surf, (config.LCD_WIDTH, config.LCD_HEIGHT)
                    )
                frames.append(surf)
            except pygame.error as e:
                log.warning("Failed to load sprite %s: %s", fname, e)
        return frames

    def get_frame(self, emotion, tick):
        """Return the Pygame Surface for the given emotion at this tick.

        Args:
            emotion: Animation name (idle, listening, happy, etc.)
            tick: Current animation tick counter.

        Returns:
            (Surface, bool): The frame surface and whether animation is done.
        """
        frames = self._cache.get(emotion)
        if not frames:
            return None, True

        meta = self._meta.get(emotion, {"fps": 10, "loop": True})
        anim_fps = meta.get("fps", 10)
        loops = meta.get("loop", True)

        # Convert tick (at LCD_FPS) to frame index (at anim_fps)
        frame_idx = int(tick * anim_fps / config.LCD_FPS)

        if loops:
            frame_idx = frame_idx % len(frames)
            return frames[frame_idx], False
        else:
            if frame_idx >= len(frames):
                return frames[-1], True  # animation done
            return frames[frame_idx], False

    def has_emotion(self, emotion):
        return emotion in self._cache and len(self._cache[emotion]) > 0

    def available_emotions(self):
        return list(self._cache.keys())

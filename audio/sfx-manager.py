"""SFX manager: loads OGG files, manages mixer channels, TTS ducking.

Pre-loads all SFX at startup for <50ms playback latency.
Channels 1-3 reserved for SFX (channel 0 = TTS).
Ducking reduces SFX volume during TTS playback.
Lazy-initializes on first play() to avoid "mixer not initialized" errors.
"""

import os
import logging

import pygame

import config

log = logging.getLogger(__name__)

# SFX name -> (filename, channel_key)
_SFX_REGISTRY = {
    "eat": ("eat.ogg", "primary"),
    "level_up": ("level-up.ogg", "primary"),
    "evolution": ("evolution.ogg", "primary"),
    "badge": ("badge-earned.ogg", "notify"),
    "quest": ("quest-start.ogg", "notify"),
    "transform": ("transform.ogg", "primary"),
    "warning": ("warning.ogg", "ambient"),
    "regression": ("regression.ogg", "ambient"),
    "shutter": ("shutter.wav", "notify"),
}


class SfxManager:
    """Loads and plays SFX with TTS ducking support."""

    def __init__(self):
        self._sounds = {}
        self._channels = {}
        self._ducked = False
        self._initialized = False

    def _ensure_init(self):
        """Lazy init: load sounds and channels when mixer is ready."""
        if self._initialized:
            return True
        try:
            if not pygame.mixer.get_init():
                return False
        except pygame.error:
            return False
        self._load_sounds()
        self._init_channels()
        self._initialized = True
        return True

    def _load_sounds(self):
        """Pre-load all SFX OGG files."""
        for name, (filename, _) in _SFX_REGISTRY.items():
            path = os.path.join(config.SFX_DIR, filename)
            if os.path.exists(path):
                try:
                    self._sounds[name] = pygame.mixer.Sound(path)
                    log.debug("Loaded SFX: %s", name)
                except pygame.error as e:
                    log.warning("Failed to load SFX %s: %s", name, e)
        log.info("SFX loaded: %d/%d", len(self._sounds), len(_SFX_REGISTRY))

    def _init_channels(self):
        """Reserve mixer channels for SFX (channels 1-3)."""
        pygame.mixer.set_num_channels(8)
        self._channels = {
            "primary": pygame.mixer.Channel(config.SFX_CHANNEL_PRIMARY),
            "notify": pygame.mixer.Channel(config.SFX_CHANNEL_NOTIFY),
            "ambient": pygame.mixer.Channel(config.SFX_CHANNEL_AMBIENT),
        }

    def play(self, name, channel=None):
        """Play named SFX on its default channel (or override)."""
        if not self._ensure_init():
            return
        sound = self._sounds.get(name)
        if not sound:
            return
        ch_key = channel or _SFX_REGISTRY.get(name, ("", "primary"))[1]
        ch = self._channels.get(ch_key)
        if ch:
            ch.play(sound)

    def duck_for_tts(self):
        """Reduce SFX volume during TTS playback."""
        if not self._initialized or self._ducked:
            return
        for ch in self._channels.values():
            ch.set_volume(config.SFX_DUCK_VOLUME)
        self._ducked = True

    def unduck(self):
        """Restore SFX volume after TTS ends."""
        if not self._initialized or not self._ducked:
            return
        for ch in self._channels.values():
            ch.set_volume(config.SFX_NORMAL_VOLUME)
        self._ducked = False

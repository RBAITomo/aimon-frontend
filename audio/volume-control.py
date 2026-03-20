"""System volume control via amixer (wm8960 soundcard)."""

import logging
import subprocess

import config

log = logging.getLogger(__name__)


class VolumeControl:
    """Manages system volume via ALSA amixer."""

    def __init__(self):
        self._volume = config.VOLUME_DEFAULT
        self._apply()

    @property
    def volume(self) -> int:
        return self._volume

    def increase(self):
        """Increase volume by one step, clamped to 100."""
        self._volume = min(100, self._volume + config.VOLUME_STEP)
        self._apply()

    def decrease(self):
        """Decrease volume by one step, clamped to 0."""
        self._volume = max(0, self._volume - config.VOLUME_STEP)
        self._apply()

    def _apply(self):
        """Apply current volume to all amixer controls."""
        for ctl in config.VOLUME_AMIXER_CONTROLS:
            try:
                subprocess.run(
                    ["amixer", "-c", str(config.VOLUME_AMIXER_CARD),
                     "sset", ctl, f"{self._volume}%"],
                    capture_output=True, timeout=2,
                )
            except Exception:
                pass
        log.info("Volume set to %d%%", self._volume)

"""PCM16 audio playback via PyAudio (ALSA) with queue-based streaming.

Receives PCM16 16kHz mono chunks from the backend via WebSocket and
plays them through the WM8960 speaker on the Whisplay HAT.
Supports immediate stop for interrupt handling.
"""

import logging
import queue
import threading

import pyaudio

import config

log = logging.getLogger(__name__)

# Playback chunk: 20ms at 16kHz = 320 samples * 2 bytes = 640 bytes
_PLAYBACK_CHUNK = int(config.AUDIO_PLAYBACK_RATE * 0.02) * config.AUDIO_FORMAT_WIDTH


class AudioPlayback:
    """Queue-based PCM16 audio playback with interrupt support."""

    def __init__(self):
        self._pa = pyaudio.PyAudio()
        self._queue = queue.Queue(maxsize=200)
        self._playing = False
        self._thread = None
        self._stream = None
        log.info("AudioPlayback initialized")

    def start(self):
        """Start the playback background thread."""
        if self._playing:
            return
        self._playing = True
        self._thread = threading.Thread(
            target=self._playback_loop, daemon=True
        )
        self._thread.start()
        log.info("Audio playback started")

    def enqueue(self, pcm_bytes):
        """Add a PCM16 chunk to the playback queue.

        Args:
            pcm_bytes: Raw PCM16 16kHz mono audio bytes.
        """
        if not self._playing:
            return
        try:
            self._queue.put_nowait(pcm_bytes)
        except queue.Full:
            log.warning("Playback queue full, dropping chunk")

    def stop(self):
        """Stop playback immediately and clear the queue (interrupt)."""
        self._playing = False
        # Drain the queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception as e:
                log.warning("Error closing playback stream: %s", e)
            self._stream = None

        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

        log.info("Audio playback stopped")

    def is_playing(self):
        """True if playback thread is active and queue has data."""
        return self._playing and not self._queue.empty()

    def _playback_loop(self):
        """Background thread: drain queue to ALSA output stream."""
        try:
            self._stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=config.AUDIO_CHANNELS,
                rate=config.AUDIO_PLAYBACK_RATE,
                output=True,
                frames_per_buffer=_PLAYBACK_CHUNK,
            )

            while self._playing:
                try:
                    chunk = self._queue.get(timeout=0.1)
                    self._stream.write(chunk)
                except queue.Empty:
                    continue
                except Exception as e:
                    log.warning("Playback write error: %s", e)
                    break

        except Exception as e:
            log.error("Failed to open playback stream: %s", e)
        finally:
            if self._stream:
                try:
                    self._stream.stop_stream()
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None
            log.debug("Playback loop exited")

    def cleanup(self):
        """Release PyAudio resources."""
        self.stop()
        self._pa.terminate()
        log.info("AudioPlayback cleaned up")

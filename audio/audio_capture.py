"""Microphone capture via PyAudio (ALSA) with raw PCM16 buffering.

Records PCM16 at 16kHz mono from the WM8960 codec on Whisplay HAT.
Buffers raw PCM16 frames for direct transmission to the backend.
"""

import logging
import threading

import pyaudio

import config

log = logging.getLogger(__name__)

# Capture chunk: 20ms at 16kHz = 320 samples
_CAPTURE_CHUNK = int(config.AUDIO_SAMPLE_RATE * config.AUDIO_FRAME_DURATION_MS / 1000)


class AudioCapture:
    """Records mic audio and produces raw PCM16 frames."""

    def __init__(self):
        self._pa = pyaudio.PyAudio()
        self._stream = None
        self._recording = False
        self._lock = threading.Lock()
        self._pcm_frames = []
        log.info("AudioCapture initialized")

    def start(self):
        """Open mic stream and begin recording."""
        with self._lock:
            if self._recording:
                return
            self._pcm_frames = []
            self._recording = True

        try:
            self._stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=config.AUDIO_CHANNELS,
                rate=config.AUDIO_SAMPLE_RATE,
                input=True,
                frames_per_buffer=_CAPTURE_CHUNK,
                stream_callback=self._audio_callback,
            )
            self._stream.start_stream()
            log.info("Mic recording started")
        except Exception as e:
            log.error("Failed to open mic stream: %s", e)
            self._recording = False

    def stop(self):
        """Stop recording and return list of raw PCM16 frames.

        Returns:
            list[bytes]: PCM16 frames ready to send over WebSocket.
        """
        with self._lock:
            self._recording = False

        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception as e:
                log.warning("Error closing mic stream: %s", e)
            self._stream = None

        frames = self._pcm_frames
        self._pcm_frames = []
        log.info("Mic recording stopped, %d PCM16 frames", len(frames))
        return frames

    def is_recording(self):
        return self._recording

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio callback: buffer raw PCM16 data."""
        if not self._recording:
            return (None, pyaudio.paComplete)

        try:
            with self._lock:
                if self._recording:
                    self._pcm_frames.append(in_data)
        except Exception as e:
            log.warning("Audio capture error: %s", e)

        return (None, pyaudio.paContinue)

    def cleanup(self):
        """Release PyAudio resources."""
        if self._recording:
            self.stop()
        self._pa.terminate()
        log.info("AudioCapture cleaned up")

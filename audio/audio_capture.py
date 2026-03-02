"""Microphone capture via PyAudio (ALSA) with raw PCM16 buffering.

Records PCM16 at 16kHz mono from the WM8960 codec on Whisplay HAT.
Buffers raw PCM16 frames for direct transmission to the backend.
Optionally runs WebRTC VAD on each frame for hands-free conversation mode.
"""

import importlib
import logging
import threading

import pyaudio

import config

log = logging.getLogger(__name__)

# Capture chunk: 20ms at 16kHz = 320 samples
_CAPTURE_CHUNK = int(config.AUDIO_SAMPLE_RATE * config.AUDIO_FRAME_DURATION_MS / 1000)

# Lazy-load VAD module (kebab-case filename)
_vad_mod = importlib.import_module("audio.voice-activity-detector")
VoiceActivityDetector = _vad_mod.VoiceActivityDetector
VadResult = _vad_mod.VadResult


class AudioCapture:
    """Records mic audio and produces raw PCM16 frames."""

    def __init__(self):
        self._pa = pyaudio.PyAudio()
        self._stream = None
        self._recording = False
        self._lock = threading.Lock()
        self._pcm_frames = []
        self._vad = None
        self._vad_enabled = False
        self._on_vad_stop = None
        self._vad_fired = False
        log.info("AudioCapture initialized")

    def start(self, vad=False, on_vad_stop=None):
        """Open mic stream and begin recording.

        Args:
            vad: Enable VAD processing on each frame.
            on_vad_stop: Callback(VadResult) fired once when VAD triggers stop.
        """
        with self._lock:
            if self._recording:
                return
            self._pcm_frames = []
            self._recording = True
            self._vad_enabled = vad
            self._on_vad_stop = on_vad_stop
            self._vad_fired = False
            self._insufficient_count = 0
            if vad:
                self._vad = VoiceActivityDetector(
                    sample_rate=config.AUDIO_SAMPLE_RATE,
                    frame_duration_ms=config.AUDIO_FRAME_DURATION_MS,
                    aggressiveness=config.VAD_AGGRESSIVENESS,
                    silence_threshold_ms=config.VAD_SILENCE_THRESHOLD_MS,
                    min_speech_ms=config.VAD_MIN_SPEECH_MS,
                    max_duration_ms=config.VAD_MAX_LISTEN_MS,
                )

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
            log.info("Mic recording started (vad=%s)", vad)
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
            self._vad_enabled = False
            self._vad = None

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
        """PyAudio callback: buffer raw PCM16 data and optionally run VAD."""
        if not self._recording:
            return (None, pyaudio.paComplete)

        try:
            with self._lock:
                if self._recording:
                    self._pcm_frames.append(in_data)
                    # VAD processing
                    if self._vad_enabled and not self._vad_fired:
                        result = self._vad.process_frame(in_data)
                        if result in (VadResult.SILENCE_DETECTED, VadResult.MAX_DURATION):
                            self._vad_fired = True
                            if self._on_vad_stop:
                                has_speech = self._vad.has_speech
                                # Fire callback outside lock to avoid deadlock
                                threading.Thread(
                                    target=self._on_vad_stop,
                                    args=(result, has_speech),
                                    daemon=True,
                                ).start()
                        elif result == VadResult.INSUFFICIENT_SPEECH:
                            self._insufficient_count += 1
                            if self._insufficient_count >= 2:
                                # No real speech after silence cycles — treat as idle
                                self._vad_fired = True
                                if self._on_vad_stop:
                                    threading.Thread(
                                        target=self._on_vad_stop,
                                        args=(result, False),
                                        daemon=True,
                                    ).start()
                            else:
                                self._vad.reset()  # noise burst, keep listening
        except Exception as e:
            log.warning("Audio capture error: %s", e)

        return (None, pyaudio.paContinue)

    def cleanup(self):
        """Release PyAudio resources."""
        if self._recording:
            self.stop()
        self._pa.terminate()
        log.info("AudioCapture cleaned up")

"""WebRTC VAD wrapper with silence-duration tracking.

Processes raw PCM16 frames and detects speech end via consecutive
silence frames exceeding a configurable threshold.
"""

import enum

import webrtcvad


class VadResult(enum.Enum):
    LISTENING = "listening"              # speech or silence < threshold
    SILENCE_DETECTED = "silence"         # silence threshold exceeded + min speech met
    MAX_DURATION = "max_duration"        # recording too long
    INSUFFICIENT_SPEECH = "insufficient" # silence detected but < min speech


class VoiceActivityDetector:
    """Stateful VAD that tracks consecutive silence and speech duration."""

    def __init__(self, sample_rate, frame_duration_ms, aggressiveness,
                 silence_threshold_ms, min_speech_ms, max_duration_ms):
        self._vad = webrtcvad.Vad(aggressiveness)
        self._sample_rate = sample_rate
        self._frame_ms = frame_duration_ms
        self._silence_frames = silence_threshold_ms // frame_duration_ms
        self._min_speech_frames = min_speech_ms // frame_duration_ms
        self._max_frames = max_duration_ms // frame_duration_ms
        self.reset()

    def reset(self):
        """Reset all counters. Call on recording start or after INSUFFICIENT_SPEECH."""
        self._consecutive_silent = 0
        self._speech_frames = 0
        self._total_frames = 0

    def process_frame(self, pcm_bytes) -> VadResult:
        """Process one PCM16 frame. Returns VadResult indicating current state."""
        self._total_frames += 1
        is_speech = self._vad.is_speech(pcm_bytes, self._sample_rate)

        if is_speech:
            self._speech_frames += 1
            self._consecutive_silent = 0
        else:
            self._consecutive_silent += 1

        if self._total_frames >= self._max_frames:
            return VadResult.MAX_DURATION

        if self._consecutive_silent >= self._silence_frames:
            if self._speech_frames >= self._min_speech_frames:
                return VadResult.SILENCE_DETECTED
            return VadResult.INSUFFICIENT_SPEECH

        return VadResult.LISTENING

    @property
    def has_speech(self):
        """True if enough speech frames accumulated to consider this a valid utterance."""
        return self._speech_frames >= self._min_speech_frames

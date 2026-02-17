"""Unit tests for audio capture and playback.

Tests audio recording, OPUS encoding, playback queue, and cleanup.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch, call
import queue


class TestAudioCapture:
    """Test AudioCapture module."""

    @pytest.fixture
    def mock_pyaudio(self):
        """Mock PyAudio instance."""
        with patch('audio.audio_capture.pyaudio.PyAudio') as mock:
            yield mock

    @pytest.fixture
    def mock_encoder(self):
        """Mock OPUS encoder."""
        with patch('audio.audio_capture.opuslib.Encoder') as mock:
            encoder_instance = Mock()
            encoder_instance.encode = Mock(return_value=b'\x00\x01\x02')
            mock.return_value = encoder_instance
            yield encoder_instance

    @pytest.fixture
    def audio_capture(self, mock_pyaudio, mock_encoder):
        """Create AudioCapture with mocked dependencies."""
        from audio.audio_capture import AudioCapture
        return AudioCapture()

    def test_initialization(self, audio_capture):
        """AudioCapture should initialize without errors."""
        assert audio_capture is not None
        assert audio_capture._recording is False
        assert audio_capture._opus_frames == []

    def test_start_recording(self, audio_capture, mock_pyaudio):
        """start() should open mic stream and begin recording."""
        mock_stream = Mock()
        mock_pyaudio.return_value.open.return_value = mock_stream
        
        audio_capture.start()
        
        assert audio_capture._recording is True
        mock_pyaudio.return_value.open.assert_called_once()
        mock_stream.start_stream.assert_called_once()

    def test_stop_recording_returns_opus_frames(self, audio_capture, mock_encoder):
        """stop() should return accumulated OPUS frames."""
        audio_capture._opus_frames = [b'frame1', b'frame2', b'frame3']
        audio_capture._recording = True
        audio_capture._stream = Mock()
        
        frames = audio_capture.stop()
        
        assert frames == [b'frame1', b'frame2', b'frame3']
        assert audio_capture._recording is False
        assert audio_capture._opus_frames == []

    def test_stop_closes_stream(self, audio_capture):
        """stop() should close audio stream."""
        mock_stream = Mock()
        audio_capture._stream = mock_stream
        audio_capture._recording = True
        
        audio_capture.stop()
        
        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()

    def test_is_recording(self, audio_capture):
        """is_recording() should return recording state."""
        assert audio_capture.is_recording() is False
        
        audio_capture._recording = True
        assert audio_capture.is_recording() is True

    @patch('audio.audio_capture.np.frombuffer')
    @patch('audio.audio_capture.np.repeat')
    def test_audio_callback_encodes_opus(self, mock_repeat, mock_frombuffer, audio_capture, mock_encoder):
        """Audio callback should resample and encode to OPUS."""
        audio_capture._recording = True
        
        # Mock numpy operations
        mock_pcm16 = Mock()
        mock_pcm48 = Mock()
        mock_pcm48.tobytes.return_value = b'pcm48_data'
        mock_frombuffer.return_value = mock_pcm16
        mock_repeat.return_value = mock_pcm48
        
        in_data = b'\x00\x01\x02\x03'
        result, flag = audio_capture._audio_callback(in_data, 320, None, None)
        
        # Should encode and store frame
        assert len(audio_capture._opus_frames) == 1
        mock_encoder.encode.assert_called_once()

    def test_cleanup(self, audio_capture, mock_pyaudio):
        """cleanup() should terminate PyAudio."""
        audio_capture.cleanup()
        
        mock_pyaudio.return_value.terminate.assert_called_once()


class TestAudioPlayback:
    """Test AudioPlayback module."""

    @pytest.fixture
    def mock_pyaudio(self):
        """Mock PyAudio instance."""
        with patch('audio.audio_playback.pyaudio.PyAudio') as mock:
            yield mock

    @pytest.fixture
    def audio_playback(self, mock_pyaudio):
        """Create AudioPlayback with mocked dependencies."""
        from audio.audio_playback import AudioPlayback
        return AudioPlayback()

    def test_initialization(self, audio_playback):
        """AudioPlayback should initialize without errors."""
        assert audio_playback is not None
        assert audio_playback._playing is False
        assert audio_playback._queue.empty()

    def test_start_playback(self, audio_playback):
        """start() should spawn playback thread."""
        audio_playback.start()
        
        assert audio_playback._playing is True
        assert audio_playback._thread is not None

    def test_enqueue_audio_chunk(self, audio_playback):
        """enqueue() should add PCM chunk to queue."""
        audio_playback._playing = True
        chunk = b'\x00\x01\x02\x03'
        
        audio_playback.enqueue(chunk)
        
        assert not audio_playback._queue.empty()
        assert audio_playback._queue.get_nowait() == chunk

    def test_enqueue_when_not_playing_does_nothing(self, audio_playback):
        """enqueue() should ignore chunks when not playing."""
        audio_playback._playing = False
        chunk = b'\x00\x01\x02\x03'
        
        audio_playback.enqueue(chunk)
        
        assert audio_playback._queue.empty()

    def test_enqueue_full_queue_drops_chunk(self, audio_playback):
        """enqueue() should drop chunk if queue is full."""
        audio_playback._playing = True
        
        # Fill queue to capacity
        for _ in range(200):  # maxsize=200
            audio_playback._queue.put_nowait(b'x')
        
        # This should be dropped (not raise exception)
        audio_playback.enqueue(b'dropped')
        
        assert audio_playback._queue.qsize() == 200

    def test_stop_clears_queue(self, audio_playback):
        """stop() should clear playback queue."""
        audio_playback._playing = True
        audio_playback._queue.put(b'chunk1')
        audio_playback._queue.put(b'chunk2')
        
        audio_playback.stop()
        
        assert audio_playback._queue.empty()
        assert audio_playback._playing is False

    def test_stop_closes_stream(self, audio_playback):
        """stop() should close audio stream."""
        mock_stream = Mock()
        audio_playback._stream = mock_stream
        audio_playback._playing = True
        audio_playback._thread = Mock()
        audio_playback._thread.join = Mock()
        
        audio_playback.stop()
        
        mock_stream.stop_stream.assert_called_once()
        mock_stream.close.assert_called_once()

    def test_is_playing(self, audio_playback):
        """is_playing() should return True if playing and queue has data."""
        assert audio_playback.is_playing() is False
        
        audio_playback._playing = True
        assert audio_playback.is_playing() is False  # Queue empty
        
        audio_playback._queue.put(b'data')
        assert audio_playback.is_playing() is True

    @patch('audio.audio_playback.queue.Queue')
    def test_playback_loop_drains_queue(self, mock_queue_class, audio_playback, mock_pyaudio):
        """Playback loop should drain queue to audio stream."""
        mock_stream = Mock()
        mock_pyaudio.return_value.open.return_value = mock_stream
        
        # Mock queue with 3 chunks then empty
        mock_queue = Mock()
        mock_queue.get.side_effect = [
            b'chunk1',
            b'chunk2',
            b'chunk3',
            queue.Empty,
        ]
        audio_playback._queue = mock_queue
        audio_playback._playing = True
        
        # Run loop briefly
        import threading
        thread = threading.Thread(target=audio_playback._playback_loop)
        thread.daemon = True
        thread.start()
        
        import time
        time.sleep(0.1)
        audio_playback._playing = False
        thread.join(timeout=1.0)
        
        # Stream should have received chunks
        assert mock_stream.write.call_count >= 3

    def test_cleanup(self, audio_playback, mock_pyaudio):
        """cleanup() should stop playback and terminate PyAudio."""
        audio_playback.cleanup()
        
        mock_pyaudio.return_value.terminate.assert_called_once()


class TestAudioIntegration:
    """Integration tests for capture and playback."""

    @patch('audio.audio_capture.pyaudio.PyAudio')
    @patch('audio.audio_capture.opuslib.Encoder')
    @patch('audio.audio_playback.pyaudio.PyAudio')
    def test_capture_to_playback_flow(self, mock_pb_pa, mock_encoder, mock_cap_pa):
        """Test full flow: capture → encode → (backend) → playback."""
        from audio.audio_capture import AudioCapture
        from audio.audio_playback import AudioPlayback
        
        # Setup
        capture = AudioCapture()
        playback = AudioPlayback()
        
        # Capture audio
        capture._recording = True
        capture._opus_frames = [b'opus1', b'opus2']
        opus_frames = capture.stop()
        
        # Simulate backend processing
        # (In real flow, backend would decode OPUS, process, re-encode, send back PCM16)
        pcm_audio = b'\x00\x01\x02\x03\x04\x05'
        
        # Playback audio
        playback.start()
        playback.enqueue(pcm_audio)
        
        # Verify
        assert len(opus_frames) == 2
        assert not playback._queue.empty()
        
        # Cleanup
        capture.cleanup()
        playback.cleanup()

"""Unit tests for AI-MON state machine.

Tests state transitions, button handling, WebSocket callbacks, and
half-duplex enforcement.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from state.state_machine import StateMachine, State


@pytest.fixture
def mock_components():
    """Create mock hardware/network/display components."""
    return {
        'hat': Mock(),
        'display': Mock(),
        'capture': Mock(),
        'playback': Mock(),
        'ws': Mock(),
        'logger': Mock(),
    }


@pytest.fixture
def state_machine(mock_components):
    """Create StateMachine with mocked dependencies."""
    sm = StateMachine(**mock_components)
    return sm


class TestStateInitialization:
    """Test state machine initialization."""

    def test_initial_state_is_offline(self, state_machine):
        """State machine should start in OFFLINE state."""
        assert state_machine.state == State.OFFLINE

    def test_callbacks_registered(self, state_machine, mock_components):
        """All callbacks should be registered on init."""
        hat = mock_components['hat']
        ws = mock_components['ws']
        
        hat.on_button_press.assert_called_once()
        hat.on_button_release.assert_called_once()
        
        # WebSocket callbacks
        assert ws.on_hello_ack is not None
        assert ws.on_asr_result is not None
        assert ws.on_llm_stream is not None
        assert ws.on_tts_audio is not None
        assert ws.on_turn_end is not None


class TestStateTransitions:
    """Test state machine transitions."""

    def test_idle_to_listening_on_button_press(self, state_machine, mock_components):
        """Button press in IDLE should transition to LISTENING."""
        state_machine._state = State.IDLE
        state_machine._on_button_press()
        
        assert state_machine.state == State.LISTENING
        mock_components['capture'].start.assert_called_once()
        mock_components['ws'].send_audio_start.assert_called_once()

    def test_listening_to_asr_on_button_release(self, state_machine, mock_components):
        """Button release in LISTENING should transition to ASR."""
        mock_components['capture'].stop.return_value = [b'opus1', b'opus2']
        state_machine._state = State.LISTENING
        
        state_machine._on_button_release()
        
        assert state_machine.state == State.ASR
        mock_components['capture'].stop.assert_called_once()

    def test_asr_to_answer_on_valid_transcript(self, state_machine, mock_components):
        """Valid ASR result should transition to ANSWER."""
        state_machine._state = State.ASR
        
        state_machine._on_asr_result("Hello AI-MON", 0.95)
        
        assert state_machine.state == State.ANSWER
        assert state_machine._turn_user_text == "Hello AI-MON"
        mock_components['playback'].start.assert_called_once()

    def test_asr_to_idle_on_empty_transcript(self, state_machine, mock_components):
        """Empty ASR result should return to IDLE."""
        state_machine._state = State.ASR
        
        state_machine._on_asr_result("", 0.0)
        
        assert state_machine.state == State.IDLE

    def test_answer_to_emotion_on_turn_end(self, state_machine, mock_components):
        """Turn end should transition to EMOTION state."""
        state_machine._state = State.ANSWER
        state_machine._turn_user_text = "test"
        state_machine._turn_start_time = 0
        
        with patch('time.time', return_value=1.5):
            state_machine._on_turn_end("turn_123")
        
        assert state_machine.state == State.EMOTION
        mock_components['logger'].log_turn.assert_called_once()

    def test_emotion_to_idle_after_animation(self, state_machine, mock_components):
        """EMOTION state should return to IDLE after animation completes."""
        state_machine._state = State.EMOTION
        mock_components['display'].render_emotion.return_value = True  # Animation done
        
        state_machine.tick()
        
        assert state_machine.state == State.IDLE


class TestHalfDuplexEnforcement:
    """Test strict half-duplex: mic ON only in LISTENING."""

    def test_mic_off_when_entering_idle(self, state_machine, mock_components):
        """Mic should be disabled when entering IDLE."""
        mock_components['capture'].is_recording.return_value = True
        state_machine._state = State.LISTENING
        
        state_machine._set_state(State.IDLE)
        
        mock_components['capture'].stop.assert_called()

    def test_mic_off_when_entering_asr(self, state_machine, mock_components):
        """Mic should be disabled when entering ASR."""
        mock_components['capture'].is_recording.return_value = True
        
        state_machine._set_state(State.ASR)
        
        mock_components['capture'].stop.assert_called()

    def test_mic_off_when_entering_answer(self, state_machine, mock_components):
        """Mic should be disabled when entering ANSWER."""
        mock_components['capture'].is_recording.return_value = True
        
        state_machine._set_state(State.ANSWER)
        
        mock_components['capture'].stop.assert_called()

    def test_mic_allowed_only_in_listening(self, state_machine, mock_components):
        """Mic should only record in LISTENING state."""
        mock_components['capture'].is_recording.return_value = False
        
        # Transition to LISTENING
        state_machine._set_state(State.LISTENING)
        # No stop() call expected since we're entering LISTENING
        
        # Verify mic starts when we explicitly start listening
        state_machine._state = State.IDLE
        state_machine._start_listening()
        mock_components['capture'].start.assert_called()


class TestInterruptHandling:
    """Test user interrupt during ANSWER."""

    def test_interrupt_stops_playback(self, state_machine, mock_components):
        """Interrupt should stop audio playback."""
        state_machine._state = State.ANSWER
        
        state_machine._on_button_press()
        
        mock_components['playback'].stop.assert_called_once()

    def test_interrupt_sends_cancel_to_backend(self, state_machine, mock_components):
        """Interrupt should send interrupt message to backend."""
        state_machine._state = State.ANSWER
        
        state_machine._on_button_press()
        
        mock_components['ws'].send_interrupt.assert_called_once()

    def test_interrupt_returns_to_idle(self, state_machine, mock_components):
        """Interrupt should transition back to IDLE."""
        state_machine._state = State.ANSWER
        
        state_machine._on_button_press()
        
        assert state_machine.state == State.IDLE


class TestTokenStreaming:
    """Test LLM token accumulation."""

    def test_tokens_accumulate_during_answer(self, state_machine):
        """Tokens should accumulate during ANSWER state."""
        state_machine._state = State.ANSWER
        
        state_machine._on_llm_stream("Hello ", False)
        state_machine._on_llm_stream("world", False)
        state_machine._on_llm_stream("!", True)
        
        assert state_machine._tokens == ["Hello ", "world", "!"]

    def test_tokens_cleared_on_new_listening(self, state_machine):
        """Tokens should be cleared when starting new listening session."""
        state_machine._tokens = ["old", "tokens"]
        state_machine._state = State.IDLE
        
        state_machine._start_listening()
        
        assert state_machine._tokens == []


class TestConnectionManagement:
    """Test WebSocket connection lifecycle."""

    def test_hello_ack_transitions_to_idle(self, state_machine):
        """hello_ack should transition from OFFLINE to IDLE."""
        state_machine._state = State.OFFLINE
        
        state_machine._on_hello_ack("session_abc123")
        
        assert state_machine.state == State.IDLE

    def test_disconnect_transitions_to_offline(self, state_machine, mock_components):
        """Disconnect should transition to OFFLINE and stop audio."""
        mock_components['capture'].is_recording.return_value = True
        state_machine._state = State.ANSWER
        
        state_machine._on_disconnect()
        
        assert state_machine.state == State.OFFLINE
        mock_components['capture'].stop.assert_called()
        mock_components['playback'].stop.assert_called()

    def test_initial_connect_success(self, state_machine, mock_components):
        """Successful initial connect should send hello."""
        mock_components['ws'].connect.return_value = True
        
        state_machine.initial_connect()
        
        mock_components['ws'].connect.assert_called_once()
        mock_components['ws'].send_hello.assert_called_once()

    def test_initial_connect_failure_goes_offline(self, state_machine, mock_components):
        """Failed initial connect should transition to OFFLINE."""
        mock_components['ws'].connect.return_value = False
        
        state_machine.initial_connect()
        
        assert state_machine.state == State.OFFLINE


class TestErrorHandling:
    """Test error handling."""

    def test_backend_error_returns_to_idle(self, state_machine, mock_components):
        """Backend error should return to IDLE and stop playback."""
        state_machine._state = State.ANSWER
        
        state_machine._on_error("ASR_FAILED", "Speech recognition timeout")
        
        assert state_machine.state == State.IDLE
        mock_components['playback'].stop.assert_called_once()
        mock_components['display'].render_error.assert_called_once()


class TestDisplayUpdates:
    """Test display rendering for each state."""

    def test_tick_updates_display_for_idle(self, state_machine, mock_components):
        """Tick in IDLE should render idle animation."""
        state_machine._state = State.IDLE
        
        state_machine.tick()
        
        mock_components['display'].render_idle.assert_called_once()

    def test_tick_updates_display_for_listening(self, state_machine, mock_components):
        """Tick in LISTENING should render listening indicator."""
        state_machine._state = State.LISTENING
        
        state_machine.tick()
        
        mock_components['display'].render_listening.assert_called_once()

    def test_tick_updates_display_for_asr(self, state_machine, mock_components):
        """Tick in ASR should render thinking animation."""
        state_machine._state = State.ASR
        
        state_machine.tick()
        
        mock_components['display'].render_thinking.assert_called_once()

    def test_tick_updates_display_for_answer(self, state_machine, mock_components):
        """Tick in ANSWER should render streaming tokens."""
        state_machine._state = State.ANSWER
        state_machine._tokens = ["Hello", " world"]
        
        state_machine.tick()
        
        mock_components['display'].render_answer.assert_called_once()
        args = mock_components['display'].render_answer.call_args[0]
        assert args[1] == ["Hello", " world"]

    def test_tick_updates_display_for_offline(self, state_machine, mock_components):
        """Tick in OFFLINE should render offline indicator."""
        state_machine._state = State.OFFLINE
        
        state_machine.tick()
        
        mock_components['display'].render_offline.assert_called_once()


class TestLEDColorUpdates:
    """Test RGB LED updates per state."""

    def test_led_color_updates_on_state_change(self, state_machine, mock_components):
        """LED color should update when state changes."""
        import config
        
        state_machine._set_state(State.LISTENING)
        mock_components['hat'].set_rgb_tuple.assert_called_with(config.LED_LISTENING)
        
        state_machine._set_state(State.ANSWER)
        mock_components['hat'].set_rgb_tuple.assert_called_with(config.LED_ANSWER)

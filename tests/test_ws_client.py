"""Unit tests for WebSocket client.

Tests connection lifecycle, message handling, reconnection logic,
and protocol compliance.
"""

import pytest
import json
from unittest.mock import Mock, MagicMock, patch, call
from network.ws_client import WSClient


@pytest.fixture
def ws_client():
    """Create WSClient instance."""
    client = WSClient()
    return client


@pytest.fixture
def mock_websocket():
    """Create mock WebSocket connection."""
    ws = Mock()
    ws.recv = Mock(side_effect=TimeoutError)
    ws.send = Mock()
    ws.close = Mock()
    return ws


class TestConnectionLifecycle:
    """Test WebSocket connection management."""

    @patch('network.ws_client.ws_sync.connect')
    def test_connect_success(self, mock_connect, ws_client, mock_websocket):
        """Successful connection should set connected flag."""
        mock_connect.return_value = mock_websocket
        
        result = ws_client.connect()
        
        assert result is True
        assert ws_client.connected is True
        assert ws_client._ws is not None
        mock_connect.assert_called_once()

    @patch('network.ws_client.ws_sync.connect')
    def test_connect_failure(self, mock_connect, ws_client):
        """Failed connection should return False."""
        mock_connect.side_effect = Exception("Connection refused")
        
        result = ws_client.connect()
        
        assert result is False
        assert ws_client.connected is False

    def test_disconnect_closes_connection(self, ws_client, mock_websocket):
        """Disconnect should close WebSocket and stop receive thread."""
        ws_client._ws = mock_websocket
        ws_client._connected = True
        ws_client._running = True
        
        ws_client.disconnect()
        
        assert ws_client.connected is False
        assert ws_client._running is False
        mock_websocket.close.assert_called_once()

    @patch('network.ws_client.ws_sync.connect')
    @patch('time.sleep')
    def test_reconnect_with_retry(self, mock_sleep, mock_connect, ws_client, mock_websocket):
        """Reconnect should retry up to max attempts."""
        mock_connect.side_effect = [
            Exception("Failed"),
            Exception("Failed"),
            mock_websocket,  # Success on 3rd attempt
        ]
        
        result = ws_client.reconnect()
        
        assert result is True
        assert mock_connect.call_count == 3
        assert mock_sleep.call_count == 2  # Sleep between attempts

    @patch('network.ws_client.ws_sync.connect')
    @patch('time.sleep')
    def test_reconnect_max_attempts_exceeded(self, mock_sleep, mock_connect, ws_client):
        """Reconnect should fail after max attempts."""
        mock_connect.side_effect = Exception("Connection refused")
        
        result = ws_client.reconnect()
        
        assert result is False
        assert mock_connect.call_count == 5  # WS_RECONNECT_MAX_ATTEMPTS


class TestSendMessages:
    """Test outgoing message formatting."""

    def test_send_hello(self, ws_client, mock_websocket):
        """send_hello should send correct protocol version and params."""
        ws_client._ws = mock_websocket
        ws_client._connected = True
        
        ws_client.send_hello()
        
        mock_websocket.send.assert_called_once()
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        assert sent_data['type'] == 'hello'
        assert sent_data['version'] == 4
        assert 'device_id' in sent_data
        assert 'audio_params' in sent_data
        assert sent_data['audio_params']['format'] == 'opus'

    def test_send_audio_start(self, ws_client, mock_websocket):
        """send_audio_start should send audio_start message."""
        ws_client._ws = mock_websocket
        ws_client._connected = True
        
        ws_client.send_audio_start()
        
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        assert sent_data['type'] == 'audio_start'

    def test_send_audio_frame(self, ws_client, mock_websocket):
        """send_audio_frame should send binary PCM16 data."""
        ws_client._ws = mock_websocket
        ws_client._connected = True
        pcm_data = b'\x00\x01\x02\x03'

        ws_client.send_audio_frame(pcm_data)

        mock_websocket.send.assert_called_once_with(pcm_data)

    def test_send_audio_stop(self, ws_client, mock_websocket):
        """send_audio_stop should send audio_stop message."""
        ws_client._ws = mock_websocket
        ws_client._connected = True
        
        ws_client.send_audio_stop()
        
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        assert sent_data['type'] == 'audio_stop'

    def test_send_interrupt(self, ws_client, mock_websocket):
        """send_interrupt should send interrupt message."""
        ws_client._ws = mock_websocket
        ws_client._connected = True
        
        ws_client.send_interrupt()
        
        sent_data = json.loads(mock_websocket.send.call_args[0][0])
        assert sent_data['type'] == 'interrupt'

    def test_send_when_disconnected_does_not_raise(self, ws_client):
        """Sending when disconnected should not raise exception."""
        ws_client._ws = None
        ws_client._connected = False
        
        # Should not raise
        ws_client.send_hello()
        ws_client.send_interrupt()


class TestReceiveMessages:
    """Test incoming message parsing."""

    def test_handle_hello_ack(self, ws_client):
        """hello_ack should extract session_id and call callback."""
        callback = Mock()
        ws_client.on_hello_ack = callback
        
        msg = json.dumps({
            'type': 'hello_ack',
            'session_id': 'session_abc123',
        })
        
        ws_client._handle_text(msg)
        
        assert ws_client.session_id == 'session_abc123'
        callback.assert_called_once_with('session_abc123')

    def test_handle_asr_result(self, ws_client):
        """asr_result should extract text and confidence."""
        callback = Mock()
        ws_client.on_asr_result = callback
        
        msg = json.dumps({
            'type': 'asr_result',
            'text': 'Hello AI-MON',
            'confidence': 0.95,
        })
        
        ws_client._handle_text(msg)
        
        callback.assert_called_once_with('Hello AI-MON', 0.95)

    def test_handle_llm_stream(self, ws_client):
        """llm_stream should extract token and done flag."""
        callback = Mock()
        ws_client.on_llm_stream = callback
        
        messages = [
            json.dumps({'type': 'llm_stream', 'token': 'Hello', 'done': False}),
            json.dumps({'type': 'llm_stream', 'token': ' world', 'done': False}),
            json.dumps({'type': 'llm_stream', 'token': '!', 'done': True}),
        ]
        
        for msg in messages:
            ws_client._handle_text(msg)
        
        assert callback.call_count == 3
        assert callback.call_args_list[0] == call('Hello', False)
        assert callback.call_args_list[1] == call(' world', False)
        assert callback.call_args_list[2] == call('!', True)

    def test_handle_tts_start(self, ws_client):
        """tts_start should extract text."""
        callback = Mock()
        ws_client.on_tts_start = callback
        
        msg = json.dumps({
            'type': 'tts_start',
            'text': 'Hello from AI-MON',
        })
        
        ws_client._handle_text(msg)
        
        callback.assert_called_once_with('Hello from AI-MON')

    def test_handle_tts_stop(self, ws_client):
        """tts_stop should extract has_more flag."""
        callback = Mock()
        ws_client.on_tts_stop = callback
        
        msg = json.dumps({
            'type': 'tts_stop',
            'has_more': True,
        })
        
        ws_client._handle_text(msg)
        
        callback.assert_called_once_with(True)

    def test_handle_turn_end(self, ws_client):
        """turn_end should extract turn_id."""
        callback = Mock()
        ws_client.on_turn_end = callback
        
        msg = json.dumps({
            'type': 'turn_end',
            'turn_id': 'turn_12345',
        })
        
        ws_client._handle_text(msg)
        
        callback.assert_called_once_with('turn_12345')

    def test_handle_error(self, ws_client):
        """error message should extract code and message."""
        callback = Mock()
        ws_client.on_error = callback
        
        msg = json.dumps({
            'type': 'error',
            'code': 'ASR_FAILED',
            'message': 'Speech recognition timeout',
        })
        
        ws_client._handle_text(msg)
        
        callback.assert_called_once_with('ASR_FAILED', 'Speech recognition timeout')

    def test_handle_interrupt_ack(self, ws_client):
        """interrupt_ack should call callback."""
        callback = Mock()
        ws_client.on_interrupt_ack = callback
        
        msg = json.dumps({'type': 'interrupt_ack'})
        
        ws_client._handle_text(msg)
        
        callback.assert_called_once()

    def test_handle_binary_audio(self, ws_client):
        """Binary data should be routed to tts_audio callback."""
        callback = Mock()
        ws_client.on_tts_audio = callback
        
        audio_data = b'\x00\x01\x02\x03\x04\x05'
        
        ws_client._handle_binary(audio_data)
        
        callback.assert_called_once_with(audio_data)

    def test_handle_invalid_json(self, ws_client):
        """Invalid JSON should not crash (log warning)."""
        callback = Mock()
        ws_client.on_error = callback
        
        # Should not raise
        ws_client._handle_text("not valid json{")
        
        # Callback should not be called for invalid JSON
        callback.assert_not_called()

    def test_handle_unknown_message_type(self, ws_client):
        """Unknown message types should be ignored gracefully."""
        msg = json.dumps({'type': 'unknown_future_type', 'data': 'test'})
        
        # Should not raise
        ws_client._handle_text(msg)


class TestDisconnectionHandling:
    """Test disconnect detection and recovery."""

    def test_recv_loop_detects_disconnect(self, ws_client, mock_websocket):
        """Receive loop should detect disconnection and call callback."""
        disconnect_callback = Mock()
        ws_client.on_disconnect = disconnect_callback
        ws_client._ws = mock_websocket
        ws_client._connected = True
        ws_client._running = True
        
        # Simulate disconnect by raising exception
        mock_websocket.recv.side_effect = Exception("Connection closed")
        
        ws_client._recv_loop()
        
        assert ws_client.connected is False
        disconnect_callback.assert_called_once()

    def test_send_failure_triggers_disconnect(self, ws_client, mock_websocket):
        """Send failure should trigger disconnect handling."""
        disconnect_callback = Mock()
        ws_client.on_disconnect = disconnect_callback
        ws_client._ws = mock_websocket
        ws_client._connected = True
        
        mock_websocket.send.side_effect = Exception("Broken pipe")
        
        ws_client.send_hello()
        
        assert ws_client.connected is False
        disconnect_callback.assert_called_once()


class TestCallbackSafety:
    """Test that missing callbacks don't crash."""

    def test_missing_callbacks_dont_crash(self, ws_client):
        """Messages should be handled gracefully even if callbacks not set."""
        ws_client.on_hello_ack = None
        ws_client.on_asr_result = None
        ws_client.on_llm_stream = None
        
        # Should not raise
        ws_client._handle_text(json.dumps({'type': 'hello_ack', 'session_id': 'test'}))
        ws_client._handle_text(json.dumps({'type': 'asr_result', 'text': 'test'}))
        ws_client._handle_text(json.dumps({'type': 'llm_stream', 'token': 'test'}))

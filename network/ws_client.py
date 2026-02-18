"""WebSocket v4 protocol client for AI-MON backend.

Bidirectional JSON + binary audio over ws://{host}:8080/ws/audio/{robotId}.
"""

import json
import logging
import threading
import time

import websockets.sync.client as ws_sync

import config

log = logging.getLogger(__name__)


class WSClient:
    """Synchronous WebSocket client with background receive thread."""

    def __init__(self):
        self._ws = None
        self._connected = False
        self._session_id = None
        self._recv_thread = None
        self._running = False

        # Callbacks (set by StateMachine)
        self.on_hello_ack = None
        self.on_asr_result = None
        self.on_llm_stream = None
        self.on_tts_start = None
        self.on_tts_audio = None
        self.on_tts_stop = None
        self.on_turn_end = None
        self.on_error = None
        self.on_interrupt_ack = None
        self.on_disconnect = None
        self.on_reconnect = None
        self.on_pet_feed_result = None
        self.on_pet_status = None
        self.on_camera_result = None
        self.on_badge_earned = None
        self.on_pet_evolution = None
        self.on_pet_transform = None
        self.on_pet_transform_end = None
        self.on_pet_warning = None
        self.on_pet_regression = None
        self.on_quest_start = None

    def connect(self):
        url = f"{config.BACKEND_WS_URL}/ws/audio/{config.ROBOT_ID}"
        log.info("Connecting to %s", url)

        try:
            self._ws = ws_sync.connect(
                url,
                close_timeout=5,
                additional_headers={"User-Agent": "aimon-frontend/1.0"},
            )
            self._connected = True
            self._running = True
            self._recv_thread = threading.Thread(
                target=self._recv_loop, daemon=True
            )
            self._recv_thread.start()
            log.info("WebSocket connected")
            return True
        except Exception as e:
            log.error("WebSocket connection failed: %s", e)
            self._connected = False
            return False

    def reconnect(self):
        """Attempt reconnect with retry logic."""
        self.disconnect()
        for attempt in range(1, config.WS_RECONNECT_MAX_ATTEMPTS + 1):
            log.info("Reconnect attempt %d/%d", attempt, config.WS_RECONNECT_MAX_ATTEMPTS)
            if self.connect():
                if self.on_reconnect:
                    self.on_reconnect()
                return True
            time.sleep(config.WS_RECONNECT_INTERVAL_S)
        log.error("Reconnect failed after %d attempts", config.WS_RECONNECT_MAX_ATTEMPTS)
        return False

    def disconnect(self):
        """Close WebSocket connection and stop receive thread."""
        self._running = False
        self._connected = False
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
            self._ws = None
        if self._recv_thread:
            self._recv_thread.join(timeout=2.0)
            self._recv_thread = None

    @property
    def connected(self):
        return self._connected

    @property
    def session_id(self):
        return self._session_id

    # ===== Send Methods =====

    def send_hello(self):
        """Send hello handshake with protocol version and audio params."""
        self._send_json({
            "type": "hello",
            "version": 4,
            "device_id": config.ROBOT_ID,
            "audio_params": {
                "format": "pcm16",
                "sample_rate": config.AUDIO_SAMPLE_RATE,
            },
        })

    def send_audio_start(self):
        self._send_json({"type": "audio_start"})

    def send_audio_frame(self, pcm_bytes):
        """Send a binary PCM16 audio frame."""
        if self._ws and self._connected:
            try:
                self._ws.send(pcm_bytes)
            except Exception as e:
                log.warning("Failed to send audio frame: %s", e)
                self._handle_disconnect()

    def send_audio_stop(self):
        self._send_json({"type": "audio_stop"})

    def send_interrupt(self):
        self._send_json({"type": "interrupt"})

    def send_feed_confirm(self, food_name="unknown"):
        """Confirm feeding after food detection (food analyzed on Pi)."""
        self._send_json({"type": "pet_feed_confirm", "food_name": food_name})

    def send_ping(self):
        self._send_json({"type": "ping"})

    def _send_json(self, data):
        if self._ws and self._connected:
            try:
                self._ws.send(json.dumps(data))
            except Exception as e:
                log.warning("Failed to send %s: %s", data.get("type"), e)
                self._handle_disconnect()

    # ===== Receive Loop =====

    def _recv_loop(self):
        """Background thread: receive and dispatch messages."""
        while self._running and self._ws:
            try:
                msg = self._ws.recv(timeout=1.0)
                if isinstance(msg, bytes):
                    self._handle_binary(msg)
                elif isinstance(msg, str):
                    self._handle_text(msg)
            except TimeoutError:
                continue
            except Exception as e:
                if self._running:
                    log.warning("WebSocket recv error: %s", e)
                    self._handle_disconnect()
                break
        log.debug("Recv loop exited")

    def _handle_text(self, raw):
        """Parse JSON text message and dispatch to callback."""
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Invalid JSON from server: %s", raw[:100])
            return

        msg_type = msg.get("type", "")

        if msg_type == "hello_ack":
            self._session_id = msg.get("session_id")
            log.info("Hello ACK, session=%s", self._session_id)
            if self.on_hello_ack:
                self.on_hello_ack(self._session_id)

        elif msg_type == "asr_result":
            if self.on_asr_result:
                self.on_asr_result(msg.get("text", ""), msg.get("confidence", 0))

        elif msg_type == "llm_stream":
            if self.on_llm_stream:
                self.on_llm_stream(msg.get("token", ""), msg.get("done", False))

        elif msg_type == "tts_start":
            if self.on_tts_start:
                self.on_tts_start(msg.get("text", ""))

        elif msg_type == "tts_stop":
            if self.on_tts_stop:
                self.on_tts_stop(msg.get("has_more", False))

        elif msg_type == "turn_end":
            if self.on_turn_end:
                self.on_turn_end(msg.get("turn_id", ""))

        elif msg_type == "error":
            log.error("Server error: [%s] %s", msg.get("code"), msg.get("message"))
            if self.on_error:
                self.on_error(msg.get("code", ""), msg.get("message", ""))

        elif msg_type == "interrupt_ack":
            if self.on_interrupt_ack:
                self.on_interrupt_ack()

        elif msg_type == "pet_feed_result":
            if self.on_pet_feed_result:
                self.on_pet_feed_result(
                    msg.get("success", False),
                    msg.get("food_name"),
                    msg.get("hunger_reduction", 0),
                )

        elif msg_type == "pet_status":
            if self.on_pet_status:
                self.on_pet_status(msg)

        elif msg_type == "camera_result":
            if self.on_camera_result:
                self.on_camera_result(msg)

        elif msg_type == "badge_earned":
            if self.on_badge_earned:
                self.on_badge_earned(msg)

        elif msg_type == "pet_evolution":
            if self.on_pet_evolution:
                self.on_pet_evolution(msg)

        elif msg_type == "pet_transform":
            if self.on_pet_transform:
                self.on_pet_transform(msg)

        elif msg_type == "pet_transform_end":
            if self.on_pet_transform_end:
                self.on_pet_transform_end(msg)

        elif msg_type == "pet_warning":
            if self.on_pet_warning:
                self.on_pet_warning(msg)

        elif msg_type == "pet_regression":
            if self.on_pet_regression:
                self.on_pet_regression(msg)

        elif msg_type == "quest_start":
            if self.on_quest_start:
                self.on_quest_start(msg)

        elif msg_type == "pong":
            log.debug("Pong received")

        elif msg_type == "ack":
            log.debug("ACK for %s", msg.get("message_type"))

        else:
            log.debug("Unknown message type: %s", msg_type)

    def _handle_binary(self, data):
        """Route binary PCM16 audio chunk to playback callback."""
        if self.on_tts_audio:
            self.on_tts_audio(data)

    def _handle_disconnect(self):
        """Handle unexpected disconnection."""
        self._connected = False
        if self.on_disconnect:
            self.on_disconnect()

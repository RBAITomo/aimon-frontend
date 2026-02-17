"""AI-MON state machine: IDLE->LISTENING->ASR->ANSWER->EMOTION->IDLE.

Strict half-duplex: mic ON only in LISTENING. Wires hardware, display,
audio, network, and storage via callbacks. Maintains PetState for
compositor-based rendering.
"""

import dataclasses
import enum
import importlib
import logging
import time
import threading

import config

log = logging.getLogger(__name__)

# Import PetState from kebab-case module
_pet_mod = importlib.import_module("display.pet-state-model")
PetState = _pet_mod.PetState


class State(enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"
    ASR = "asr"
    ANSWER = "answer"
    EMOTION = "emotion"
    OFFLINE = "offline"


# Map conversation state -> pet animation name
_STATE_ANIMATION_MAP = {
    State.IDLE: "idle",
    State.LISTENING: "listening",
    State.ASR: "idle",          # keep idle during thinking
    State.ANSWER: "speaking",
    State.EMOTION: "happy",     # overridden by _current_emotion
    State.OFFLINE: "idle",
}


class StateMachine:
    """Orchestrates conversation flow across all frontend modules."""

    def __init__(self, hat, display, capture, playback, ws, logger):
        self._hat = hat
        self._display = display
        self._capture = capture
        self._playback = playback
        self._ws = ws
        self._logger = logger

        self._state = State.OFFLINE
        self._tick = 0
        self._emotion_tick = 0
        self._current_emotion = "happy"
        self._tokens = []
        self._turn_user_text = ""
        self._turn_start_time = 0

        # Pet state for compositor rendering (guarded by _pet_lock)
        self._pet_state = PetState()
        self._pet_lock = threading.Lock()

        self._register_callbacks()

    def _register_callbacks(self):
        self._hat.on_button_press(self._on_button_press)
        self._hat.on_button_release(self._on_button_release)
        self._ws.on_hello_ack = self._on_hello_ack
        self._ws.on_asr_result = self._on_asr_result
        self._ws.on_llm_stream = self._on_llm_stream
        self._ws.on_tts_start = self._on_tts_start
        self._ws.on_tts_audio = self._on_tts_audio
        self._ws.on_tts_stop = self._on_tts_stop
        self._ws.on_turn_end = self._on_turn_end
        self._ws.on_error = self._on_error
        self._ws.on_interrupt_ack = self._on_interrupt_ack
        self._ws.on_disconnect = self._on_disconnect
        self._ws.on_reconnect = self._on_reconnect

    _LED_MAP = {
        State.IDLE: config.LED_IDLE, State.LISTENING: config.LED_LISTENING,
        State.ASR: config.LED_ASR, State.ANSWER: config.LED_ANSWER,
        State.EMOTION: config.LED_EMOTION_HAPPY, State.OFFLINE: config.LED_OFFLINE,
    }

    def _set_state(self, new_state):
        old = self._state
        if old == new_state:
            return
        if new_state != State.LISTENING:
            self._ensure_mic_off()
        self._state = new_state
        self._tick = 0
        self._hat.set_rgb_tuple(self._LED_MAP.get(new_state, config.LED_IDLE))
        self._display.reset_scroll()

        # Update pet animation based on new state
        if new_state == State.EMOTION:
            self._pet_state.animation = self._current_emotion
        else:
            self._pet_state.animation = _STATE_ANIMATION_MAP.get(new_state, "idle")

        log.info("State: %s -> %s", old.value, new_state.value)

    def _ensure_mic_off(self):
        if self._capture.is_recording():
            self._capture.stop()

    def _on_button_press(self):
        if self._state == State.IDLE:
            self._start_listening()
        elif self._state == State.ANSWER:
            self._interrupt()

    def _on_button_release(self):
        if self._state == State.LISTENING:
            self._stop_listening()

    def _start_listening(self):
        self._set_state(State.LISTENING)
        self._tokens = []
        self._turn_start_time = time.time()
        self._ws.send_audio_start()
        self._capture.start()

    def _stop_listening(self):
        pcm_frames = self._capture.stop()
        self._set_state(State.ASR)
        def _send():
            for f in pcm_frames:
                self._ws.send_audio_frame(f)
            self._ws.send_audio_stop()
        threading.Thread(target=_send, daemon=True).start()

    def _interrupt(self):
        self._playback.stop()
        self._ws.send_interrupt()
        self._set_state(State.IDLE)

    def _on_hello_ack(self, session_id):
        log.info("Session established: %s", session_id)
        self._set_state(State.IDLE)

    def _on_asr_result(self, text, confidence):
        log.info("ASR: '%s' (conf=%.2f)", text, confidence)
        self._turn_user_text = text
        if text.strip():
            self._set_state(State.ANSWER)
            self._playback.start()
        else:
            log.info("Empty ASR result, returning to IDLE")
            self._set_state(State.IDLE)

    def _on_llm_stream(self, token, done):
        if self._state in (State.ASR, State.ANSWER):
            self._tokens.append(token)

    def _on_tts_start(self, text):
        pass

    def _on_tts_audio(self, pcm_bytes):
        if self._state == State.ASR:
            self._set_state(State.ANSWER)
            self._playback.start()
            self._playback.enqueue(pcm_bytes)
        elif self._state == State.ANSWER:
            self._playback.enqueue(pcm_bytes)

    def _on_tts_stop(self, has_more):
        pass

    def _on_turn_end(self, turn_id):
        if self._state not in (State.ASR, State.ANSWER):
            return
        duration_ms = int((time.time() - self._turn_start_time) * 1000)
        assistant_text = "".join(self._tokens)
        self._logger.log_turn(
            turn_id=turn_id,
            user_text=self._turn_user_text,
            assistant_text=assistant_text,
            emotion=self._current_emotion,
            duration_ms=duration_ms,
        )
        self._emotion_tick = 0
        self._set_state(State.EMOTION)

    def _on_error(self, code, message):
        log.error("Backend error [%s]: %s", code, message)
        self._display.render_error(f"{code}: {message}")
        self._playback.stop()
        self._set_state(State.IDLE)

    def _on_interrupt_ack(self):
        pass

    def _on_disconnect(self):
        self._ensure_mic_off()
        self._playback.stop()
        self._set_state(State.OFFLINE)
        threading.Thread(target=self._reconnect_loop, daemon=True).start()

    def _on_reconnect(self):
        self._ws.send_hello()

    def _reconnect_loop(self):
        if self._ws.reconnect():
            self._ws.send_hello()

    def tick(self):
        """Called once per frame (30 FPS). Updates display for current state."""
        self._tick += 1
        state = self._state

        if state == State.OFFLINE:
            self._display.render_offline(self._tick)
            return

        if state == State.EMOTION:
            self._emotion_tick += 1

        # Build text for speech bubble (only during ANSWER)
        text = "".join(self._tokens) if state == State.ANSWER else None

        # Snapshot pet state under lock to avoid torn reads from WS thread
        with self._pet_lock:
            pet_snapshot = dataclasses.replace(self._pet_state)

        # Use tick or emotion_tick depending on state
        render_tick = self._emotion_tick if state == State.EMOTION else self._tick

        done = self._display.render(render_tick, pet_snapshot, text)

        if state == State.EMOTION and done:
            self._set_state(State.IDLE)

    def update_pet_state(self, **kwargs):
        """Update pet state from backend pet_status messages (thread-safe).

        Call with keyword args matching PetState fields:
            update_pet_state(hunger=30, energy=80, level=5)
        """
        with self._pet_lock:
            for key, value in kwargs.items():
                if hasattr(self._pet_state, key):
                    setattr(self._pet_state, key, value)
        self._display.on_stats_changed()

    @property
    def state(self):
        return self._state

    @property
    def pet_state(self):
        return self._pet_state

    def initial_connect(self):
        """Perform initial connection to backend. Called once at startup."""
        if self._ws.connect():
            self._ws.send_hello()
        else:
            self._set_state(State.OFFLINE)
            threading.Thread(target=self._reconnect_loop, daemon=True).start()

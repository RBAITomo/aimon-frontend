"""AI-MON state machine: IDLE->LISTENING->ASR->ANSWER->EMOTION->IDLE.

Strict half-duplex: mic ON only in LISTENING. Wires hardware, display,
audio, network, and storage via callbacks. Maintains PetState for
compositor-based rendering.
"""

import dataclasses
import enum
import glob as glob_mod
import importlib
import logging
import os
import random
import time
import threading

import pygame

import config

log = logging.getLogger(__name__)

# Import PetState from kebab-case module
_pet_mod = importlib.import_module("display.pet-state-model")
PetState = _pet_mod.PetState

# Import camera capture service
_cam_mod = importlib.import_module("hardware.camera-capture-service")
CameraCaptureService = _cam_mod.CameraCaptureService

# Import vision analysis service (direct Gemini from Pi)
_vision_mod = importlib.import_module("hardware.vision-analysis-service")
VisionAnalysisService = _vision_mod.VisionAnalysisService

# Import SFX, badge popup, and pet event handler
_sfx_mod = importlib.import_module("audio.sfx-manager")
SfxManager = _sfx_mod.SfxManager
_badge_mod = importlib.import_module("display.badge-popup-renderer")
BadgePopupRenderer = _badge_mod.BadgePopupRenderer
_pet_handler_mod = importlib.import_module("state.pet-event-handler")
PetEventHandler = _pet_handler_mod.PetEventHandler

_food_mgr_mod = importlib.import_module("state.food-sprite-manager")
FoodSpriteManager = _food_mgr_mod.FoodSpriteManager

_move_mod = importlib.import_module("display.character-movement-engine")
CharacterMovementEngine = _move_mod.CharacterMovementEngine


class State(enum.Enum):
    IDLE = "idle"
    LISTENING = "listening"
    ASR = "asr"
    ANSWER = "answer"
    EMOTION = "emotion"
    OFFLINE = "offline"
    EVOLUTION = "evolution"  # black screen flash → hold new form until button


# Map conversation state -> pet animation name
_STATE_ANIMATION_MAP = {
    State.IDLE: "idle",
    State.LISTENING: "listening",
    State.ASR: "warning",       # thinking animation while waiting for TTS
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

        self._state = State.IDLE
        self._offline = False  # True when WS disconnected; pet renders normally
        self._tick = 0
        self._emotion_tick = 0
        self._current_emotion = "happy"
        self._tokens = []
        self._turn_user_text = ""
        self._turn_start_time = 0
        self._last_bubble_text = None

        # Pet state for compositor rendering (guarded by _pet_lock)
        self._pet_state = PetState()
        self._pet_lock = threading.Lock()

        # Camera: double-press detection (guarded by _press_lock)
        self._camera = None
        self._last_press_time = 0.0
        self._press_pending = False  # True = waiting to see if double-press
        self._press_timer = None
        self._press_lock = threading.Lock()
        self._vision = None
        if config.CAMERA_ENABLED:
            self._camera = CameraCaptureService(min_interval_s=config.CAMERA_RATE_LIMIT_S)
            self._camera.initialize()
        if config.VISION_ENABLED:
            self._vision = VisionAnalysisService()

        # Evolution sequence state
        self._evolution_old_stage = "egg"
        self._evolution_new_stage = "baby"
        self._evolution_tick = 0
        self._evolution_holding = False   # True = flash done, holding new form

        # Character movement engine (autonomous wandering for child/adult)
        self._movement = CharacterMovementEngine()

        # SFX, badge popup, food sprite manager, and pet event handler
        self._sfx = SfxManager()
        self._badge_popup = BadgePopupRenderer()
        self._food_mgr = FoodSpriteManager()
        self._pet_handler = PetEventHandler(
            self._pet_state, self._pet_lock, self._display,
            self._sfx, self._badge_popup, self._food_mgr, self._ws,
        )

        # Set default background
        self._display.set_background("marshmallow-meadow.png")

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
        self._ws.on_pet_feed_result = self._on_pet_feed_result
        # Pet event handler callbacks
        self._ws.on_pet_status = self._pet_handler.on_pet_status
        self._ws.on_camera_result = self._pet_handler.on_camera_result
        self._ws.on_badge_earned = self._pet_handler.on_badge_earned
        self._ws.on_pet_evolution = self._pet_handler.on_pet_evolution
        self._ws.on_pet_transform = self._pet_handler.on_pet_transform
        self._ws.on_pet_transform_end = self._pet_handler.on_pet_transform_end
        self._ws.on_pet_warning = self._pet_handler.on_pet_warning
        self._ws.on_pet_regression = self._pet_handler.on_pet_regression
        self._ws.on_quest_start = self._pet_handler.on_quest_start

    _LED_MAP = {
        State.IDLE: config.LED_IDLE, State.LISTENING: config.LED_LISTENING,
        State.ASR: config.LED_ASR, State.ANSWER: config.LED_ANSWER,
        State.EMOTION: config.LED_EMOTION_HAPPY, State.OFFLINE: config.LED_OFFLINE,
        State.EVOLUTION: (160, 0, 220),  # purple during evolution
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
        if self._state == State.EVOLUTION:
            if self._evolution_holding:
                # Exit evolution: restore background and go idle
                self._pet_handler.end_evolution()
                self._display.clear_black_background()
                self._display.set_background("marshmallow-meadow.png")
                self._set_state(State.IDLE)
            # During flash phase, ignore button (don't cut the animation short)
            return

        if self._state == State.ANSWER:
            self._interrupt()
            return

        if self._state != State.IDLE:
            return

        with self._press_lock:
            now = time.time()
            elapsed_ms = (now - self._last_press_time) * 1000
            self._last_press_time = now

            # Double-press detected -> camera capture
            if self._press_pending and elapsed_ms < config.CAMERA_DOUBLE_PRESS_MS:
                self._press_pending = False
                if self._press_timer:
                    self._press_timer.cancel()
                    self._press_timer = None
                self._trigger_camera()
                return

            # First press -> wait to see if double-press follows
            self._press_pending = True
            delay_s = config.CAMERA_DOUBLE_PRESS_MS / 1000.0
            self._press_timer = threading.Timer(delay_s, self._on_single_press_confirmed)
            self._press_timer.daemon = True
            self._press_timer.start()

    def _on_single_press_confirmed(self):
        """Called after double-press window expires -> treat as single press (talk)."""
        with self._press_lock:
            self._press_pending = False
            self._press_timer = None
        if self._state == State.IDLE:
            if self._offline:
                self._play_offline_clip()
            else:
                self._start_listening()

    def _trigger_camera(self):
        """Capture photo and analyze directly via Gemini on Pi."""
        if not self._camera or not self._camera.available:
            log.warning("Camera not available")
            return

        if not self._vision or not self._vision.available:
            log.warning("Vision service not available")
            return

        self._hat.set_rgb_tuple(config.LED_CAMERA)
        log.info("Camera capture triggered (double-press)")

        def _capture_and_analyze():
            try:
                jpeg_bytes = self._camera.capture_bytes()
                if not jpeg_bytes:
                    log.warning("Camera capture returned None")
                    return

                result = self._vision.analyze(jpeg_bytes)

                if result is None:
                    self._last_bubble_text = "Mình không thấy rõ, thử lại nhé!"
                    return

                if result.get("is_food") and result.get("food_name"):
                    food = result["food_name"]
                    sprite_key = result.get("sprite_key", "default")
                    log.info("Food detected: %s (sprite=%s)", food, sprite_key)

                    with self._pet_lock:
                        hunger = self._pet_state.hunger

                    if hunger > 0:
                        # Pet is hungry — eat immediately
                        self._food_mgr.add(sprite_key, food, eat_immediately=True)
                        self._last_bubble_text = food + " ngon quá! Cho mình ăn nhé?"
                        self._ws.send_feed_confirm(food, sprite_key)
                        self._sfx.play("eat")
                    else:
                        # Pet is full — store food on screen
                        self._food_mgr.add(sprite_key, food, eat_immediately=False)
                        self._last_bubble_text = "Mình no rồi! Để dành ăn sau nhé~"
                else:
                    desc = result.get("description", "")
                    log.info("Non-food: %s", desc)
                    self._last_bubble_text = desc
            finally:
                self._hat.set_rgb_tuple(config.LED_IDLE)

        threading.Thread(target=_capture_and_analyze, daemon=True).start()

    def _on_button_release(self):
        if self._state == State.LISTENING:
            self._stop_listening()

    def _start_listening(self):
        self._set_state(State.LISTENING)
        self._tokens = []
        self._last_bubble_text = None
        self._pet_handler.clear_quest()  # clear quest bubble when child starts speaking
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
        self._offline = False
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
        # Defer EMOTION transition until playback queue drains
        # (turn_end can arrive before all binary PCM chunks are played)
        threading.Thread(
            target=self._finish_turn_after_playback, daemon=True
        ).start()

    def _finish_turn_after_playback(self):
        """Wait for playback queue to drain, then transition to EMOTION."""
        timeout = time.time() + 30  # safety: 30s max wait
        while self._playing_active() and time.time() < timeout:
            time.sleep(0.05)
        self._emotion_tick = 0
        self._set_state(State.EMOTION)

    def _playing_active(self):
        """Check if playback is still active (thread running and queue non-empty)."""
        return self._playback._playing and not self._playback._queue.empty()

    def _on_error(self, code, message):
        log.error("Backend error [%s]: %s", code, message)
        self._display.render_error(f"{code}: {message}")
        self._playback.stop()
        self._set_state(State.IDLE)

    def _on_interrupt_ack(self):
        pass

    def _on_pet_feed_result(self, success, food_name, hunger_reduction):
        """Handle feed result after camera food confirmation."""
        if success:
            log.info("Fed with %s (hunger -%d)", food_name, hunger_reduction)
            # Use "eating" as the emotion so _set_state(EMOTION) picks it up
            self._current_emotion = "eating"
            self._emotion_tick = 0
            self._set_state(State.EMOTION)
        else:
            log.warning("Feed failed for %s", food_name)

    def _on_disconnect(self):
        self._ensure_mic_off()
        self._playback.stop()
        self._offline = True
        self._set_state(State.IDLE)
        self._play_offline_clip()
        threading.Thread(target=self._reconnect_loop, daemon=True).start()

    def _play_offline_clip(self):
        """Play random pre-recorded offline audio clip if available."""
        if not pygame.mixer.get_init():
            log.debug("Mixer not initialized, skipping offline clip")
            return
        clips = glob_mod.glob(os.path.join(config.OFFLINE_AUDIO_DIR, "*.ogg"))
        if clips:
            clip = random.choice(clips)
            try:
                sound = pygame.mixer.Sound(clip)
                pygame.mixer.Channel(config.SFX_CHANNEL_PRIMARY).play(sound)
            except pygame.error as e:
                log.warning("Failed to play offline clip: %s", e)

    def _on_reconnect(self):
        self._ws.send_hello()

    def _reconnect_loop(self):
        self._ws.reconnect()
        # hello is sent by _on_reconnect callback, no need to send again

    def tick(self):
        """Called once per frame (30 FPS). Updates display for current state."""
        self._tick += 1
        state = self._state

        # Check for pending evolution event (can arrive in any state)
        if self._pet_handler.has_evolution_pending:
            self._enter_evolution()
            state = self._state

        if state == State.EVOLUTION:
            self._tick_evolution()
            return

        if state == State.EMOTION:
            self._emotion_tick += 1

        # Character movement: wander during IDLE for movable stages
        with self._pet_lock:
            current_stage = self._pet_state.stage
        is_movable = current_stage in config.MOVABLE_STAGES
        self._movement.set_enabled(is_movable and state == State.IDLE)
        if is_movable:
            move_anim = self._movement.tick()
            with self._pet_lock:
                self._pet_state.char_x = self._movement.x
                self._pet_state.char_y = self._movement.y
                self._pet_state.direction = self._movement.direction
                if state == State.IDLE:
                    self._pet_state.animation = move_anim
        else:
            with self._pet_lock:
                self._pet_state.char_x = -1
                self._pet_state.char_y = -1
                self._pet_state.direction = "south"

        # Tick warning countdown
        if self._pet_handler.tick_warning():
            with self._pet_lock:
                self._pet_state.animation = _STATE_ANIMATION_MAP.get(state, "idle")

        # Build text for speech bubble — persist through ANSWER, EMOTION, and IDLE
        # until next LISTENING clears it
        if state == State.ANSWER:
            if self._pet_state.stage in ("egg", "EGG"):
                self._last_bubble_text = "❤️❤️❤️❤️❤️❤️❤️❤️❤️❤️❤️..."
            else:
                self._last_bubble_text = "".join(self._tokens)

        # Quest text overrides bubble when active
        quest = self._pet_handler.quest_text
        if quest and state == State.IDLE:
            text = quest
        else:
            text = self._last_bubble_text if state in (State.ANSWER, State.EMOTION, State.IDLE) else None

        # Snapshot pet state under lock to avoid torn reads from WS thread
        with self._pet_lock:
            pet_snapshot = dataclasses.replace(self._pet_state)

        # Use tick or emotion_tick depending on state
        render_tick = self._emotion_tick if state == State.EMOTION else self._tick

        # Advance food sprite tweens
        self._food_mgr.tick()

        done = self._display.render(render_tick, pet_snapshot, text, self._badge_popup, self._food_mgr)

        # SFX ducking: reduce SFX volume during TTS playback
        if self._playback.is_playing():
            self._sfx.duck_for_tts()
        else:
            self._sfx.unduck()

        # Return to IDLE when emotion animation completes or after 3s timeout
        if state == State.EMOTION:
            # Eating: play eating anim for ~3s, then switch to happy for remainder
            if self._current_emotion == "eating" and self._emotion_tick >= 90:
                self._current_emotion = "happy"
                self._pet_state.animation = "happy"
            elif (done and self._emotion_tick >= 60) or self._emotion_tick > 150:
                self._current_emotion = "happy"  # restore default emotion
                self._set_state(State.IDLE)

        # Quest clears server-side via pet_status (not on LISTENING)
        # Child may need multiple attempts, quest persists until answered correctly

    def _enter_evolution(self):
        """Consume pending evolution event and enter EVOLUTION state."""
        old_stage, new_stage = self._pet_handler.evolution_data
        self._pet_handler.clear_evolution()
        self._evolution_old_stage = old_stage.lower()
        self._evolution_new_stage = new_stage.lower()
        self._evolution_tick = 0
        self._evolution_holding = False
        # Preload new stage sprites so evolution animation is ready
        self._display.preload_stage(self._evolution_new_stage)
        # Force old stage so backend's pet_status update doesn't reveal new form early
        with self._pet_lock:
            self._pet_state.stage = self._evolution_old_stage
            self._pet_state.animation = "idle"
        self._food_mgr.clear()  # clear food sprites during evolution
        self._display.set_black_background()
        self._set_state(State.EVOLUTION)
        log.info("Evolution started: %s -> %s", self._evolution_old_stage, self._evolution_new_stage)

    def _tick_evolution(self):
        """Drive the evolution animation + hold sequence each frame.

        Phase 1 (flash): White flash pulses over old form on black background.
        Phase 2 (evolution anim): Play new stage's "evolution" animation on black.
        Phase 3 (hold): Show new form idle on black until button press.
        """
        self._evolution_tick += 1

        if not self._evolution_holding:
            # Phase 1: Flash over old form (first 90 frames / 3s)
            if self._evolution_tick <= 90:
                with self._pet_lock:
                    self._pet_state.stage = self._evolution_old_stage
                    self._pet_state.animation = "idle"
                    pet_snapshot = dataclasses.replace(self._pet_state)
                self._display.render_evolution(self._evolution_tick, pet_snapshot)
            else:
                # Phase 2: Play new stage's "evolution" animation on black
                anim_tick = self._evolution_tick - 90
                with self._pet_lock:
                    self._pet_state.stage = self._evolution_new_stage
                    self._pet_state.animation = "evolution"
                    pet_snapshot = dataclasses.replace(self._pet_state)
                done = self._display.render(anim_tick, pet_snapshot, None, None)
                if done:
                    # Evolution animation finished, enter hold phase
                    with self._pet_lock:
                        self._pet_state.animation = "idle"
                    self._display.on_stats_changed()
                    self._evolution_holding = True
                    log.info("Evolution anim done, holding on %s — press button to continue",
                             self._evolution_new_stage)
        else:
            # Phase 3: Hold new form with rotation animation on black until button press
            with self._pet_lock:
                self._pet_state.stage = self._evolution_new_stage
                self._pet_state.animation = "idle"  # idle uses rotation rocking sequence
                pet_snapshot = dataclasses.replace(self._pet_state)

            self._display.render(self._evolution_tick, pet_snapshot, None, None)

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
            self._offline = True
            threading.Thread(target=self._reconnect_loop, daemon=True).start()

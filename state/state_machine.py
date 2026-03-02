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

_journal_mod = importlib.import_module("state.offline-event-journal")
OfflineEventJournal = _journal_mod.OfflineEventJournal
_rbank_mod = importlib.import_module("state.offline-response-bank")
OfflineResponseBank = _rbank_mod.OfflineResponseBank
_engine_mod = importlib.import_module("state.offline-game-engine")
OfflineGameEngine = _engine_mod.OfflineGameEngine

_wifi_mod = importlib.import_module("hardware.wifi-manager")
WifiManager = _wifi_mod.WifiManager

_vol_mod = importlib.import_module("audio.volume-control")
VolumeControl = _vol_mod.VolumeControl

_battery_mod = importlib.import_module("hardware.battery-monitor")
BatteryMonitor = _battery_mod.BatteryMonitor

_food_inv_mod = importlib.import_module("state.food-inventory-manager")
FoodInventoryManager = _food_inv_mod.FoodInventoryManager

_menu_ctrl_mod = importlib.import_module("state.menu-overlay-controller")
MenuOverlayController = _menu_ctrl_mod.MenuOverlayController
MenuItem = _menu_ctrl_mod.MenuItem


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

        # Conversation mode: single press toggles, VAD auto-detects speech end
        self._conversation_mode = False
        self._finishing_turn = False  # guard against double _finish_turn_after_playback

        # Pet state for compositor rendering (guarded by _pet_lock)
        self._pet_state = PetState()
        self._pet_lock = threading.Lock()

        # Main button tap tracking (limit switch: each physical press = one edge)
        self._camera = None
        self._tap_count = 0
        self._tap_lock = threading.Lock()
        self._tap_timer = None  # pending Timer for tap resolution
        self._last_tap_time = 0.0  # debounce: ignore edges within this window

        # Shutdown flow: warning → 5s countdown → confirm/cancel
        self._shutdown_pending = False
        self._shutdown_deadline = 0.0
        self._shutdown_warning_time = 0.0  # debounce against GPIO bounce

        # Quest trigger cooldown
        self._last_quest_trigger = 0.0
        self._vision = None
        self._wifi_manager = WifiManager(config.WIFI_PROFILES_PATH)
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

        # Food inventory (persistent JSON storage)
        self._food_inventory = FoodInventoryManager()

        # Menu overlay controller
        self._menu = MenuOverlayController()
        self._volume = VolumeControl()

        # Offline gameplay components
        self._offline_journal = OfflineEventJournal()
        self._offline_response_bank = OfflineResponseBank()
        self._offline_engine = None
        self._pending_sync_ids = []  # event IDs awaiting sync_result

        # Backlight auto-dim / standby state
        self._last_activity = time.time()
        self._backlight_dimmed = False
        self._in_standby = False
        self._last_battery_refresh = 0.0  # epoch 0 triggers first refresh immediately

        # Battery monitor (Waveshare UPS HAT C / INA219 at 0x43)
        self._battery = None
        if config.BATTERY_MONITOR_ENABLED:
            self._battery = BatteryMonitor(
                poll_interval_s=config.BATTERY_MONITOR_INTERVAL_S
            )
            # Apply initial reading to pet state immediately
            with self._pet_lock:
                self._pet_state.battery_pct = self._battery.battery_pct

        # Background set dynamically from pet_status on connect

        self._register_callbacks()

    def _register_callbacks(self):
        self._hat.on_button_press(self._on_button_press)
        self._hat.on_button_release(self._on_button_release)
        # Extra buttons A-D: placeholder callbacks (log only)
        self._hat.on_button_a_press(self._on_button_a_press)
        self._hat.on_button_a_release(self._on_button_a_release)
        self._hat.on_button_b_press(self._on_button_b_press)
        self._hat.on_button_b_release(self._on_button_b_release)
        self._hat.on_button_c_press(self._on_button_c_press)
        self._hat.on_button_c_release(self._on_button_c_release)
        self._hat.on_button_d_press(self._on_button_d_press)
        self._hat.on_button_d_release(self._on_button_d_release)
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
        self._ws.on_location_changed = self._pet_handler.on_location_changed
        self._ws.on_sync_result = self._on_sync_result

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
        # Any active state (non-IDLE) resets backlight dim timer
        if new_state != State.IDLE:
            self._notify_activity()

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
        """Main button edge (press direction) — route to unified tap handler."""
        self._on_main_tap()

    def _on_main_tap(self):
        """Unified handler for main button limit switch.

        Each physical press produces one GPIO edge (alternating press/release).
        We treat every edge as a 'tap' and use tap counting for shutdown.
        - Single tap: menu toggle / action
        - 3 taps within 2s: shutdown warning
        """
        now = time.time()
        self._notify_activity()

        # Debounce: ignore edges within 200ms of last tap (limit switch bounce)
        if now - self._last_tap_time < 0.2:
            return
        self._last_tap_time = now

        # During shutdown countdown: tap = confirm shutdown
        if self._shutdown_pending:
            if now - self._shutdown_warning_time >= 0.5:
                self._confirm_shutdown()
            return

        # Evolution: tap dismisses hold phase
        if self._state == State.EVOLUTION and self._evolution_holding:
            self._pet_handler.end_evolution()
            self._display.clear_black_background()
            self._set_state(State.IDLE)
            return
        if self._state == State.EVOLUTION:
            return

        # Track taps: cancel previous timer, increment count, start new timer
        with self._tap_lock:
            self._tap_count += 1
            if self._tap_timer is not None:
                self._tap_timer.cancel()
            count_snapshot = self._tap_count
            # After 500ms of no new taps, resolve the tap sequence
            self._tap_timer = threading.Timer(0.5, self._resolve_taps, args=[count_snapshot])
            self._tap_timer.daemon = True
            self._tap_timer.start()

        # Immediate triple-tap: don't wait for timer
        if count_snapshot >= 3:
            with self._tap_lock:
                self._tap_timer.cancel()
                self._tap_count = 0
                self._tap_timer = None
            self._enter_shutdown_warning()

    def _resolve_taps(self, count):
        """Called 500ms after the last tap — execute action based on tap count."""
        with self._tap_lock:
            # Stale timer: more taps arrived since this timer was scheduled
            if self._tap_count != count:
                return
            self._tap_count = 0
            self._tap_timer = None
        log.debug("Tap sequence resolved: %d tap(s)", count)
        if count >= 3:
            self._enter_shutdown_warning()
        elif count == 2 and self._offline:
            self._trigger_wifi_qr_scan()
        else:
            self._toggle_menu()

    # --- Shutdown flow ---

    def _enter_shutdown_warning(self):
        """Triple-tap detected: show warning, start 5s countdown."""
        log.warning("Shutdown warning triggered (triple-tap)")
        self._shutdown_pending = True
        now = time.time()
        self._shutdown_deadline = now + 5.0
        self._shutdown_warning_time = now
        self._hat.set_rgb(255, 0, 0)
        self._last_bubble_text = "Tắt máy? Nhấn thêm lần nữa để tắt, bấm A để hủy. (5s)"

    def _confirm_shutdown(self):
        """Main button pressed again during countdown = immediate shutdown."""
        log.warning("Shutdown confirmed by user")
        self._display.render_shutdown_screen()
        import subprocess
        subprocess.Popen(["sudo", "shutdown", "-h", "now"])

    def _cancel_shutdown(self):
        """Button A pressed during countdown = cancel."""
        log.info("Shutdown cancelled")
        self._shutdown_pending = False
        self._hat.set_rgb_tuple(self._LED_MAP.get(self._state, config.LED_IDLE))
        self._last_bubble_text = "Đã hủy tắt máy."

    def _check_shutdown_countdown(self):
        """Called in main loop tick: auto-shutdown if deadline passed."""
        if self._shutdown_pending and time.time() >= self._shutdown_deadline:
            self._confirm_shutdown()

    def _trigger_camera(self):
        """Capture photo and analyze directly via Gemini on Pi."""
        if not self._camera or not self._camera.available:
            log.warning("Camera not available")
            return

        if not self._vision or not self._vision.available:
            log.warning("Vision service not available")
            return

        self._hat.set_rgb_tuple(config.LED_CAMERA)
        log.info("Camera capture triggered (Button B)")

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

                    # Store in inventory instead of immediate feed
                    self._food_inventory.add(food, sprite_key)
                    self._food_mgr.add(sprite_key, food, eat_immediately=False)
                    self._last_bubble_text = f"{food} - đã lưu vào kho!"
                    self._sfx.play("collect")
                else:
                    desc = result.get("description", "")
                    log.info("Non-food: %s", desc)
                    if desc and not self._offline:
                        self._last_bubble_text = f"Thấy: {desc}"
                        self._ws.send_vision_describe(desc)
                        self._set_state(State.ANSWER)
                    else:
                        self._last_bubble_text = desc or "Mình không nhận ra đây là gì!"
            finally:
                self._hat.set_rgb_tuple(config.LED_IDLE)

        threading.Thread(target=_capture_and_analyze, daemon=True).start()

    def _trigger_wifi_qr_scan(self):
        """Continuous QR scan loop (offline long-press). Runs in daemon thread."""
        if not self._camera or not self._camera.available:
            self._show_offline_text("Camera không khả dụng")
            return

        self._hat.set_rgb_tuple(config.LED_WIFI_SCAN)
        self._show_offline_text("Đang quét mã QR...")
        log.info("WiFi QR scan started (offline long-press)")

        def _scan_loop():
            deadline = time.time() + config.WIFI_QR_SCAN_TIMEOUT_S
            found = False
            try:
                while time.time() < deadline:
                    try:
                        jpeg_bytes = self._camera.capture_bytes(bypass_rate_limit=True)
                    except Exception as e:
                        log.warning("Camera capture failed: %s", e)
                        time.sleep(0.5)
                        continue

                    if not jpeg_bytes:
                        time.sleep(0.5)
                        continue

                    result = self._wifi_manager.scan_qr_for_wifi(jpeg_bytes)
                    if result:
                        found = True
                        ssid = result["ssid"]
                        password = result["password"]

                        self._show_offline_text(f"Tìm thấy: {ssid}")
                        log.info("WiFi QR decoded: ssid=%s", ssid)
                        time.sleep(1.5)

                        self._wifi_manager.add_profile(ssid, password)
                        self._show_offline_text("Đang kết nối...")

                        success = self._wifi_manager.connect_to_profile(ssid, password)
                        if success:
                            self._show_offline_text("Kết nối thành công!")
                            log.info("Connected to %s, triggering reconnect", ssid)
                            time.sleep(2)
                            threading.Thread(target=self._reconnect_loop, daemon=True).start()
                        else:
                            self._show_offline_text("Lỗi kết nối")
                        break

                    time.sleep(0.5)

                if not found:
                    self._show_offline_text("Không tìm thấy mã QR")
                    log.info("WiFi QR scan timed out after %ds", config.WIFI_QR_SCAN_TIMEOUT_S)

            except Exception as e:
                log.error("WiFi QR scan error: %s", e)
                self._show_offline_text("Lỗi kết nối")
            finally:
                self._hat.set_rgb_tuple(config.LED_OFFLINE)

        threading.Thread(target=_scan_loop, daemon=True).start()

    # --- Button release (main) ---

    def _on_button_release(self):
        """Main button edge (release direction) — route to unified tap handler."""
        self._on_main_tap()

    def _toggle_menu(self):
        """Toggle menu overlay on/off."""
        self._menu.toggle()
        log.info("Menu toggled: is_open=%s", self._menu.is_open)

    # --- Button A: Talk (conversation toggle) ---

    def _on_button_a_press(self):
        self._notify_activity()
        log.info("Button A pressed (state=%s, menu_open=%s)", self._state.value, self._menu.is_open)
        if self._menu.is_open:
            if self._menu.in_screen and self._menu.current_item == MenuItem.VOLUME:
                self._volume.increase()
            else:
                self._menu.next_item()
            return
        # Shutdown pending: A = cancel
        if self._shutdown_pending:
            self._cancel_shutdown()
            return
        if self._state == State.ANSWER:
            self._interrupt()
            self._conversation_mode = False
            return
        if self._state == State.LISTENING:
            # Manual stop: keep conversation mode so pet answers then auto-resumes
            self._stop_listening()
            return
        if self._state == State.IDLE and not self._offline:
            self._conversation_mode = True
            self._start_listening()
        elif self._offline and self._offline_engine:
            self._offline_engine.on_interaction()

    def _on_button_a_release(self):
        pass

    # --- Button B: Camera capture ---

    def _on_button_b_press(self):
        self._notify_activity()
        log.info("Button B pressed (state=%s, menu_open=%s)", self._state.value, self._menu.is_open)
        if self._menu.is_open:
            self._menu.enter()
            return
        if self._state != State.IDLE:
            return
        if self._offline and self._offline_engine:
            self._offline_engine.on_feed()
            self._sfx.play("eat")
        else:
            self._trigger_camera()

    def _on_button_b_release(self):
        pass

    # --- Button C: Quick-feed from inventory ---

    def _on_button_c_press(self):
        self._notify_activity()
        log.info("Button C pressed (state=%s, menu_open=%s)", self._state.value, self._menu.is_open)
        if self._menu.is_open:
            self._menu.back()
            return
        if self._state != State.IDLE:
            return
        self._quick_feed_from_inventory()

    def _on_button_c_release(self):
        pass

    # --- Button D: Quest trigger / menu prev ---

    def _on_button_d_press(self):
        self._notify_activity()
        log.info("Button D pressed (state=%s, menu_open=%s)", self._state.value, self._menu.is_open)
        if self._menu.is_open:
            if self._menu.in_screen and self._menu.current_item == MenuItem.VOLUME:
                self._volume.decrease()
            else:
                self._menu.prev_item()
            return
        if self._state != State.IDLE or self._offline:
            return
        # Check cooldown
        now = time.time()
        if now - self._last_quest_trigger < config.QUEST_TRIGGER_COOLDOWN_S:
            return
        # Clear active quest so new one replaces it
        if self._pet_handler.quest_text:
            self._pet_handler.clear_quest()
        self._last_quest_trigger = now
        self._hat.set_rgb_tuple(config.LED_QUEST)
        self._last_bubble_text = "Dang tim quest..."
        self._ws.send_quest_trigger()
        # Reset LED after brief flash
        def _reset_led():
            time.sleep(0.5)
            self._hat.set_rgb_tuple(self._LED_MAP.get(self._state, config.LED_IDLE))
        threading.Thread(target=_reset_led, daemon=True).start()

    def _on_button_d_release(self):
        pass

    # --- Quick-feed from inventory (Phase 03) ---

    def _quick_feed_from_inventory(self):
        """Pop oldest food from inventory and feed to pet."""
        item = self._food_inventory.pop()
        if not item:
            self._last_bubble_text = "Kho trong, chup anh de them do an!"
            return
        self._food_mgr.add(item["sprite_key"], item["food_name"], eat_immediately=True)
        self._ws.send_feed_confirm(item["food_name"], item["sprite_key"])
        self._sfx.play("eat")
        self._last_bubble_text = f"Cho an {item['food_name']}!"

    def _start_listening(self):
        self._set_state(State.LISTENING)
        self._tokens = []
        self._last_bubble_text = None
        self._pet_handler.clear_quest()  # clear quest bubble when child starts speaking
        self._turn_start_time = time.time()
        self._ws.send_audio_start()
        self._capture.start(vad=True, on_vad_stop=self._on_vad_stop)

    def _stop_listening(self):
        pcm_frames = self._capture.stop()
        self._set_state(State.ASR)
        def _send():
            for f in pcm_frames:
                self._ws.send_audio_frame(f)
            self._ws.send_audio_stop()
        threading.Thread(target=_send, daemon=True).start()

    def _on_vad_stop(self, vad_result, has_speech):
        """Called from AudioCapture thread when VAD detects speech end."""
        if self._state != State.LISTENING:
            return
        log.info("VAD triggered: %s (has_speech=%s)", vad_result.value, has_speech)
        _vad_mod = importlib.import_module("audio.voice-activity-detector")
        # No meaningful speech — return to idle quietly
        if not has_speech:
            if vad_result in (_vad_mod.VadResult.MAX_DURATION,
                              _vad_mod.VadResult.INSUFFICIENT_SPEECH):
                log.info("No speech detected, returning to idle")
                self._conversation_mode = False
                self._capture.stop()
                self._set_state(State.IDLE)
                return
        self._stop_listening()

    def _auto_resume_listening(self):
        """Auto-resume mic after playback in conversation mode."""
        if not self._conversation_mode:
            return
        if self._offline:
            self._conversation_mode = False
            return
        self._sfx.play("listen-resume")
        # Small delay for SFX to play before opening mic
        time.sleep(0.15)
        if self._conversation_mode and self._state == State.IDLE:
            self._start_listening()

    def _interrupt(self):
        self._playback.stop()
        self._ws.send_interrupt()
        self._set_state(State.IDLE)

    def _on_hello_ack(self, session_id):
        log.info("Session established: %s", session_id)
        # Flush offline events before going online
        if self._offline_engine:
            snapshot = self._offline_engine.stop()
            events = self._offline_journal.get_all_pending_for_sync()
            if events:
                self._pending_sync_ids = [e["id"] for e in events]
                self._ws.send_offline_sync(events=events, state_snapshot=snapshot)
                log.info("Sent %d offline events for sync", len(events))
            self._offline_engine = None
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
            # In conversation mode, auto-resume even on empty ASR
            if self._conversation_mode:
                threading.Thread(target=self._auto_resume_listening, daemon=True).start()

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
        # When no more TTS sentences and turn_end hasn't arrived yet, start watchdog
        if not has_more and not self._finishing_turn:
            threading.Thread(target=self._turn_end_watchdog, daemon=True).start()

    def _turn_end_watchdog(self):
        """Safety net: if turn_end never arrives, force transition after playback drains."""
        time.sleep(2.0)  # give backend time to send turn_end
        if self._state in (State.ASR, State.ANSWER) and not self._finishing_turn:
            log.warning("turn_end not received, forcing finish after playback drain")
            self._on_turn_end("watchdog")

    def _on_turn_end(self, turn_id):
        log.info("turn_end received (state=%s, turn_id=%s)", self._state.value, turn_id)
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
        if not self._finishing_turn:
            self._finishing_turn = True
            threading.Thread(
                target=self._finish_turn_after_playback, daemon=True
            ).start()

    def _finish_turn_after_playback(self):
        """Wait for playback queue to drain, then transition to EMOTION.

        In conversation mode: show brief EMOTION (~1s / 30 frames) then auto-resume.
        """
        timeout = time.time() + 30  # safety: 30s max wait
        while self._playing_active() and time.time() < timeout:
            time.sleep(0.05)
        self._emotion_tick = 0
        self._set_state(State.EMOTION)
        self._finishing_turn = False

        if self._conversation_mode:
            # Brief EMOTION display (~1s) then auto-resume
            time.sleep(1.0)
            self._set_state(State.IDLE)
            threading.Thread(target=self._auto_resume_listening, daemon=True).start()

    def _playing_active(self):
        """Check if playback is still active (thread running and queue non-empty)."""
        return self._playback._playing and not self._playback._queue.empty()

    def _on_error(self, code, message):
        log.error("Backend error [%s]: %s", code, message)
        self._display.render_error(f"{code}: {message}")
        self._playback.stop()
        self._conversation_mode = False
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
        if self._offline and self._offline_engine and self._offline_engine.running:
            return  # already in offline mode
        self._ensure_mic_off()
        self._playback.stop()
        self._conversation_mode = False
        self._offline = True
        self._set_state(State.OFFLINE)
        # Start offline game engine
        self._offline_engine = OfflineGameEngine(
            pet_state_updater=self._apply_offline_stat_update,
            display_callback=self._show_offline_text,
            journal=self._offline_journal,
            response_bank=self._offline_response_bank,
        )
        self._offline_engine.start(time.time())
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

    def _apply_offline_stat_update(self, hunger_delta=0, energy_delta=0, happiness_delta=0):
        """Apply stat deltas during offline mode (thread-safe). Returns stats dict."""
        with self._pet_lock:
            self._pet_state.hunger += hunger_delta
            self._pet_state.energy += energy_delta
            self._pet_state.happiness += happiness_delta
            self._pet_state.clamp_stats()
            stats = {
                "hunger": self._pet_state.hunger,
                "energy": self._pet_state.energy,
                "happiness": self._pet_state.happiness,
            }
        self._display.on_stats_changed()
        return stats

    def _show_offline_text(self, text: str):
        """Display Vietnamese text bubble during offline mode."""
        self._last_bubble_text = text

    def _on_sync_result(self, msg):
        """Handle sync_result from backend — overwrite local state with authoritative values."""
        status = msg.get("status")
        if status == "error":
            log.error("Sync failed: %s", msg.get("reason"))
            return

        pet_status = msg.get("pet_status", {})
        if pet_status:
            with self._pet_lock:
                for key in ("hunger", "energy", "happiness", "level", "xp",
                            "xp_for_next", "stage", "variant", "mood"):
                    if key in pet_status:
                        setattr(self._pet_state, key, pet_status[key])
                self._pet_state.clamp_stats()
            self._display.on_stats_changed()

        # Mark only the flushed events as synced and clear
        if self._pending_sync_ids:
            self._offline_journal.mark_synced(self._pending_sync_ids)
            self._offline_journal.clear_synced()
            self._pending_sync_ids = []
        log.info("Sync complete: %d events processed", msg.get("events_processed", 0))

    def tick(self):
        """Called once per frame (adaptive FPS). Updates display for current state."""
        self._tick += 1
        # Shutdown countdown check
        self._check_shutdown_countdown()
        # Backlight dim / standby check every ~1s
        if self._tick % 10 == 0:
            self._check_backlight_dim()

        # Standby: backlight off, no rendering — just keep loop alive at 1fps
        if self._in_standby:
            return

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
            text = self._last_bubble_text if state in (State.ANSWER, State.EMOTION, State.IDLE, State.OFFLINE) else None

        # Refresh battery % every 60s (time-based, FPS-independent)
        if self._battery and time.time() - self._last_battery_refresh >= config.BATTERY_MONITOR_INTERVAL_S:
            self._last_battery_refresh = time.time()
            with self._pet_lock:
                self._pet_state.battery_pct = self._battery.battery_pct

        # Snapshot pet state under lock to avoid torn reads from WS thread
        with self._pet_lock:
            pet_snapshot = dataclasses.replace(self._pet_state)

        # Use tick or emotion_tick depending on state
        render_tick = self._emotion_tick if state == State.EMOTION else self._tick

        # Advance food sprite tweens
        self._food_mgr.tick()

        done = self._display.render(
            render_tick, pet_snapshot, text, self._badge_popup, self._food_mgr,
            menu=self._menu, food_inventory=self._food_inventory,
            volume_pct=self._volume.volume,
        )

        # SFX ducking: reduce SFX volume during TTS playback
        if self._playback.is_playing():
            self._sfx.duck_for_tts()
        else:
            self._sfx.unduck()

        # Return to IDLE when emotion animation completes or after 3s timeout
        # (In conversation mode, _finish_turn_after_playback handles EMOTION→IDLE transition)
        if state == State.EMOTION and not self._conversation_mode:
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

    def _notify_activity(self):
        """Reset backlight dim timer and restore brightness on any user action."""
        self._last_activity = time.time()
        if self._in_standby:
            self._in_standby = False
            self._backlight_dimmed = False
            self._hat.set_backlight(100)
            self._display.invalidate()  # force full redraw after black standby screen
        elif self._backlight_dimmed:
            self._hat.set_backlight(100)
            self._backlight_dimmed = False

    def _check_backlight_dim(self):
        """Dim backlight at BACKLIGHT_DIM_TIMEOUT_S; enter standby at STANDBY_TIMEOUT_S."""
        idle_s = time.time() - self._last_activity
        if not self._in_standby and idle_s > config.STANDBY_TIMEOUT_S:
            self._hat.set_backlight(0)
            self._hat.fill_screen(0x0000)
            self._in_standby = True
            self._backlight_dimmed = True
        elif not self._backlight_dimmed and idle_s > config.BACKLIGHT_DIM_TIMEOUT_S:
            self._hat.set_backlight(config.BACKLIGHT_DIM_PCT)
            self._backlight_dimmed = True

    @property
    def target_fps(self) -> int:
        """Return LCD_FPS_STANDBY in standby, LCD_FPS_IDLE during IDLE/OFFLINE, LCD_FPS otherwise."""
        if self._in_standby:
            return config.LCD_FPS_STANDBY
        return config.LCD_FPS_IDLE if self._state in (State.IDLE, State.OFFLINE) else config.LCD_FPS

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
            self._on_disconnect()

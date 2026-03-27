"""Pet event handler: processes pet-related WebSocket messages.

Extracted from StateMachine to keep it under 250 LOC.
Updates PetState, triggers SFX, badge popups, and animation flags.
All methods are WebSocket callbacks invoked from the recv thread.
"""

import json
import logging
import threading
import urllib.request

import config

log = logging.getLogger(__name__)


class PetEventHandler:
    """Handles pet WebSocket messages, updates PetState, triggers UI/SFX."""

    def __init__(self, pet_state, pet_lock, display, sfx, badge_popup, food_mgr=None, ws=None):
        self._pet_state = pet_state
        self._pet_lock = pet_lock
        self._display = display
        self._sfx = sfx
        self._badge_popup = badge_popup
        self._food_mgr = food_mgr
        self._ws = ws

        # Badge cache (fetched from REST API on connect), guarded by _pet_lock
        self._badges_cache = None  # list of badge dicts or None

        # Animation state flags (read by StateMachine.tick)
        self._evolution_pending = None   # (old_stage, new_stage) or None
        self._evolution_active = False   # True while evolution animation plays
        self._regression_pending = False
        self._warning_frames = 0
        self._quest_text = None          # current quest question text
        self._quest_dismissed = False    # True after user starts talking; suppresses restore

    # --- WebSocket Callbacks ---

    def on_pet_status(self, data):
        """Update PetState from server pet_status message.

        Skips stage/variant updates while evolution is pending or in progress
        to prevent the pet_status race from overriding the animation sequence.
        """
        log.info("on_pet_status: stage=%s level=%s", data.get("stage"), data.get("level"))
        with self._pet_lock:
            self._pet_state.hunger = data.get("hunger", self._pet_state.hunger)
            self._pet_state.energy = data.get("energy", self._pet_state.energy)
            self._pet_state.happiness = data.get("happiness", self._pet_state.happiness)
            self._pet_state.level = data.get("level", self._pet_state.level)
            self._pet_state.xp = data.get("xp", self._pet_state.xp)
            self._pet_state.xp_for_next = data.get("xp_for_next", self._pet_state.xp_for_next)
            # Skip stage/variant update during evolution to avoid race condition
            if not self._evolution_pending and not self._evolution_active:
                raw_stage = data.get("stage", self._pet_state.stage)
                self._pet_state.stage = raw_stage.lower() if isinstance(raw_stage, str) else raw_stage
                self._pet_state.variant = data.get("variant", self._pet_state.variant)
            self._pet_state.mood = data.get("mood", self._pet_state.mood)
            hunger = self._pet_state.hunger

        # Parse quest from pet_status (reconnect/refresh scenario)
        quest = data.get("quest")
        if quest and quest.get("text"):
            if not self._quest_dismissed:
                self._quest_text = quest["text"]
                log.debug("Quest restored from pet_status: %s", self._quest_text[:50])
        elif quest is None:
            # Server confirms quest answered — clear display and reset flag
            self._quest_text = None
            self._quest_dismissed = False
            log.debug("Quest cleared (answered)")

        self._display.on_stats_changed()

        # Restore background from pet_status (on connect/reconnect)
        background = data.get("background")
        if background and self._display:
            try:
                self._display.set_background(background)
            except Exception as e:
                log.warning("Failed to set background from pet_status: %s", e)

        log.debug("Pet status updated: lvl=%d stage=%s", self._pet_state.level, self._pet_state.stage)

        # Auto-eat stored food when hunger increases
        if self._food_mgr and hunger > 0:
            self._food_mgr.check_auto_eat(hunger, self._auto_eat_callback)

    def on_pet_feed_result(self, data):
        """Handle successful feeding — play eat SFX."""
        success = data.get("success", False)
        if success:
            self._sfx.play("eat")
            log.info("Fed: %s (hunger -%s)", data.get("food_name"), data.get("hunger_reduction"))
        else:
            log.warning("Feed failed: %s", data.get("food_name"))

    def on_badge_earned(self, data):
        """Show badge popup + play SFX. Update badge cache."""
        self._sfx.play("badge")
        name = data.get("name", "Badge")
        desc = data.get("description", "")
        self._badge_popup.show(name, desc)
        log.info("Badge earned: %s", name)
        # Update cache: mark badge as earned (guarded by pet_lock)
        code = data.get("badge_code", "")
        with self._pet_lock:
            if self._badges_cache and code:
                for b in self._badges_cache:
                    if b.get("code") == code:
                        b["earned"] = True
                        break

    def on_pet_evolution(self, data):
        """Trigger evolution animation sequence."""
        self._sfx.play("evolution")
        old_stage = data.get("old_stage", "egg")
        new_stage = data.get("new_stage", "baby")
        self._evolution_pending = (old_stage, new_stage)
        log.info("Evolution: %s -> %s", old_stage, new_stage)

    def on_pet_transform(self, data):
        """Handle variant transformation start."""
        self._sfx.play("transform")
        with self._pet_lock:
            self._pet_state.variant = data.get("variant")
            self._pet_state.stage = "variant"
        self._display.on_stats_changed()
        log.info("Transform to variant: %s", data.get("variant"))

    def on_pet_transform_end(self, data):
        """Revert from variant to adult stage."""
        with self._pet_lock:
            self._pet_state.variant = None
            self._pet_state.stage = "adult"
        self._display.on_stats_changed()
        log.info("Transform ended, reverted to adult")

    def on_pet_warning(self, data):
        """Show warning animation + SFX."""
        self._sfx.play("warning")
        self._warning_frames = config.WARNING_ANIM_FRAMES
        with self._pet_lock:
            self._pet_state.animation = "warning"
        log.warning("Pet warning: severity=%s", data.get("severity", "warning"))

    def on_pet_regression(self, data):
        """Trigger regression animation sequence."""
        self._sfx.play("regression")
        self._regression_pending = True
        log.warning("Pet regression triggered")

    def on_quest_start(self, data):
        """Display quest question — child answers via normal voice flow."""
        self._sfx.play("quest")
        self._quest_dismissed = False
        self._quest_text = data.get("quest_text", data.get("question", ""))
        log.info("Quest started: %s", self._quest_text[:50] if self._quest_text else "empty")

    def on_location_changed(self, data):
        """Handle sub-location travel — swap background image."""
        background = data.get("background")
        location_code = data.get("location_code")
        log.info("Location changed to %s, background: %s", location_code, background)
        if background and self._display:
            try:
                self._display.set_background(background)
            except Exception as e:
                log.warning("Failed to set background %s: %s", background, e)

    def on_camera_result(self, data):
        """Handle camera analysis result from backend (legacy path)."""
        if data.get("is_food"):
            log.info("Camera food detected: %s", data.get("food_name"))
        else:
            log.info("Camera non-food: %s", data.get("description", "")[:50])

    # --- State Query Properties (read by StateMachine.tick) ---

    @property
    def has_evolution_pending(self):
        return self._evolution_pending is not None

    @property
    def evolution_data(self):
        return self._evolution_pending

    @property
    def has_regression_pending(self):
        return self._regression_pending

    @property
    def warning_frames(self):
        return self._warning_frames

    @property
    def quest_text(self):
        return self._quest_text

    def clear_evolution(self):
        self._evolution_pending = None
        self._evolution_active = True

    def end_evolution(self):
        """Called when evolution sequence fully ends (button press exits hold)."""
        self._evolution_active = False

    def clear_regression(self):
        self._regression_pending = False

    def tick_warning(self):
        """Decrement warning frame counter. Returns True if warning ended."""
        if self._warning_frames > 0:
            self._warning_frames -= 1
            if self._warning_frames <= 0:
                return True
        return False

    def _auto_eat_callback(self, food_name, sprite_key):
        """Called when auto-eat triggers on stored food."""
        self._sfx.play("eat")
        with self._pet_lock:
            self._pet_state.animation = "eating"
        if self._ws:
            self._ws.send_feed_confirm(food_name, sprite_key)
        log.info("Auto-eat: %s (sprite=%s)", food_name, sprite_key)

    @property
    def badges_cache(self):
        """Thread-safe read of badge cache for rendering."""
        with self._pet_lock:
            # Use `is not None` — empty list [] is a valid "loaded but no badges" state
            return list(self._badges_cache) if self._badges_cache is not None else None

    def clear_quest(self):
        self._quest_text = None
        self._quest_dismissed = True

    def fetch_badges(self, user_id: str):
        """Fetch all badges from REST API in background thread. Cache result."""
        def _fetch():
            url = f"{config.BACKEND_HTTP_URL}/api/badges/{user_id}"
            try:
                req = urllib.request.Request(url, headers={"Accept": "application/json"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                with self._pet_lock:
                    self._badges_cache = data
                log.info("Fetched %d badges from API", len(data))
            except Exception as e:
                log.warning("Failed to fetch badges: %s", e)
        threading.Thread(target=_fetch, daemon=True).start()

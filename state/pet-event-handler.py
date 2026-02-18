"""Pet event handler: processes pet-related WebSocket messages.

Extracted from StateMachine to keep it under 250 LOC.
Updates PetState, triggers SFX, badge popups, and animation flags.
All methods are WebSocket callbacks invoked from the recv thread.
"""

import logging
import threading

import config

log = logging.getLogger(__name__)


class PetEventHandler:
    """Handles pet WebSocket messages, updates PetState, triggers UI/SFX."""

    def __init__(self, pet_state, pet_lock, display, sfx, badge_popup):
        self._pet_state = pet_state
        self._pet_lock = pet_lock
        self._display = display
        self._sfx = sfx
        self._badge_popup = badge_popup

        # Animation state flags (read by StateMachine.tick)
        self._evolution_pending = None   # (old_stage, new_stage) or None
        self._evolution_active = False   # True while evolution animation plays
        self._regression_pending = False
        self._warning_frames = 0
        self._quest_text = None          # current quest question text

    # --- WebSocket Callbacks ---

    def on_pet_status(self, data):
        """Update PetState from server pet_status message.

        Skips stage/variant updates while evolution is pending or in progress
        to prevent the pet_status race from overriding the animation sequence.
        """
        with self._pet_lock:
            stats = data.get("stats", {})
            self._pet_state.hunger = stats.get("hunger", self._pet_state.hunger)
            self._pet_state.energy = stats.get("energy", self._pet_state.energy)
            self._pet_state.happiness = stats.get("happiness", self._pet_state.happiness)
            self._pet_state.level = data.get("level", self._pet_state.level)
            self._pet_state.xp = data.get("xp", self._pet_state.xp)
            self._pet_state.xp_for_next = data.get("xp_for_next", self._pet_state.xp_for_next)
            # Skip stage/variant update during evolution to avoid race condition
            if not self._evolution_pending and not self._evolution_active:
                raw_stage = data.get("stage", self._pet_state.stage)
                self._pet_state.stage = raw_stage.lower() if isinstance(raw_stage, str) else raw_stage
                self._pet_state.variant = data.get("variant", self._pet_state.variant)
            self._pet_state.mood = data.get("mood", self._pet_state.mood)
        self._display.on_stats_changed()
        log.debug("Pet status updated: lvl=%d stage=%s", self._pet_state.level, self._pet_state.stage)

    def on_pet_feed_result(self, data):
        """Handle successful feeding — play eat SFX."""
        success = data.get("success", False)
        if success:
            self._sfx.play("eat")
            log.info("Fed: %s (hunger -%s)", data.get("food_name"), data.get("hunger_reduction"))
        else:
            log.warning("Feed failed: %s", data.get("food_name"))

    def on_badge_earned(self, data):
        """Show badge popup + play SFX."""
        self._sfx.play("badge")
        name = data.get("name", "Badge")
        desc = data.get("description", "")
        self._badge_popup.show(name, desc)
        log.info("Badge earned: %s", name)

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
        self._quest_text = data.get("question", "")
        log.info("Quest started: %s", self._quest_text[:50])

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

    def clear_quest(self):
        self._quest_text = None

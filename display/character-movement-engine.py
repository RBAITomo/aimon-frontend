"""Autonomous character wandering engine.

Manages position, target picking, direction calculation, and idle pauses.
Only active for movable stages (child/adult). Egg/baby stay fixed.
"""

import math
import random
import logging

import config

log = logging.getLogger(__name__)

# Angle-to-direction mapping (8 sectors of 45 degrees each)
# Angle 0 = east, 90 = south (pygame Y-down), measured counter-clockwise
_DIRECTION_SECTORS = [
    ("east", -22.5, 22.5),
    ("north-east", -67.5, -22.5),
    ("north", -112.5, -67.5),
    ("north-west", -157.5, -112.5),
    ("south-east", 22.5, 67.5),
    ("south", 67.5, 112.5),
    ("south-west", 112.5, 157.5),
    ("west", 157.5, 180.0),
    ("west", -180.0, -157.5),
]


def _angle_to_direction(dx, dy):
    """Convert movement delta to 8-direction string."""
    if dx == 0 and dy == 0:
        return "south"
    angle = math.degrees(math.atan2(dy, dx))
    for name, lo, hi in _DIRECTION_SECTORS:
        if lo <= angle < hi:
            return name
    # Catch exactly ±180 degrees (pure west)
    if abs(angle) >= 157.5:
        return "west"
    return "south"


class CharacterMovementEngine:
    """Drives autonomous wandering within a bounded movement zone."""

    def __init__(self):
        # Start at center of movement zone
        self._x = float((config.MOVE_ZONE_X_MIN + config.MOVE_ZONE_X_MAX) // 2)
        self._y = float((config.MOVE_ZONE_Y_MIN + config.MOVE_ZONE_Y_MAX) // 2)
        self._target_x = self._x
        self._target_y = self._y
        self._direction = "south"
        self._walking = False
        self._enabled = False

        # Idle pause countdown (frames remaining)
        self._idle_frames_left = 0
        self._pick_new_idle_pause()

    @property
    def x(self):
        return int(self._x)

    @property
    def y(self):
        return int(self._y)

    @property
    def direction(self):
        return self._direction

    @property
    def is_walking(self):
        return self._walking

    def set_enabled(self, enabled):
        """Enable/disable wandering. When disabled, character stays put."""
        if self._enabled == enabled:
            return
        self._enabled = enabled
        if not enabled:
            self._walking = False

    def tick(self):
        """Advance one frame. Call every frame during IDLE state.

        Returns:
            str: "walking" if moving, "idle" if paused — use as animation name.
        """
        if not self._enabled:
            return "idle"

        if self._walking:
            self._move_toward_target()
        else:
            self._idle_frames_left -= 1
            if self._idle_frames_left <= 0:
                self._pick_new_target()

        return "walking" if self._walking else "idle"

    def _move_toward_target(self):
        """Move one step toward the target position."""
        dx = self._target_x - self._x
        dy = self._target_y - self._y
        dist = math.sqrt(dx * dx + dy * dy)

        if dist <= config.MOVE_SPEED:
            # Arrived at target
            self._x = self._target_x
            self._y = self._target_y
            self._walking = False
            self._pick_new_idle_pause()
            return

        # Normalize and move
        self._x += (dx / dist) * config.MOVE_SPEED
        self._y += (dy / dist) * config.MOVE_SPEED
        self._direction = _angle_to_direction(dx, dy)

    def _pick_new_target(self):
        """Pick a random target within the movement zone, avoiding current pos."""
        for _ in range(10):
            tx = float(random.randint(config.MOVE_ZONE_X_MIN, config.MOVE_ZONE_X_MAX))
            ty = float(random.randint(config.MOVE_ZONE_Y_MIN, config.MOVE_ZONE_Y_MAX))
            if abs(tx - self._x) > 2.0 or abs(ty - self._y) > 2.0:
                break
        self._target_x = tx
        self._target_y = ty
        dx = self._target_x - self._x
        dy = self._target_y - self._y
        self._direction = _angle_to_direction(dx, dy)
        self._walking = True

    def _pick_new_idle_pause(self):
        """Set a random idle pause duration."""
        self._idle_frames_left = random.randint(
            config.MOVE_IDLE_MIN_FRAMES, config.MOVE_IDLE_MAX_FRAMES
        )

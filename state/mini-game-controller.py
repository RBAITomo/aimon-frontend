"""MiniGameController: game state machine, tick loop, button handlers, WS integration.

90-second food catcher arcade game. Controller owns all game state;
StateMachine only delegates to it during MINI_GAME state.
"""

import enum
import importlib
import logging

_obj_mod = importlib.import_module("state.mini-game-objects")
FallingItem = _obj_mod.FallingItem
Player = _obj_mod.Player
ItemSpawner = _obj_mod.ItemSpawner
check_collision = _obj_mod.check_collision

log = logging.getLogger(__name__)


class GameState(enum.Enum):
    WAITING   = "waiting"     # sent WS start, awaiting backend response
    COUNTDOWN = "countdown"
    PLAYING   = "playing"
    PAUSED    = "paused"
    GAME_OVER = "game_over"


class MiniGameController:
    """Controls Food Catcher mini-game lifecycle."""

    GAME_DURATION_FRAMES = 2700   # 90s * 30fps
    COUNTDOWN_FRAMES = 90         # 3s countdown
    TIER_THRESHOLDS = [900, 1800] # frames where tier increases (30s, 60s)

    def __init__(self, ws_send_fn, load_sprite_fn):
        """
        ws_send_fn: callable(msg_dict) to send WebSocket JSON message
        load_sprite_fn: callable(sprite_key) -> pygame.Surface
        """
        self._ws_send = ws_send_fn
        self._load_sprite = load_sprite_fn
        self._player = Player()
        self._spawner = ItemSpawner(load_sprite_fn)
        self._state = GameState.WAITING
        self._score = 0
        self._timer_frames = 0
        self._countdown_frames = 0
        self._waiting_frames = 0
        self._high_score = 0
        self._cotton_candy_earned = 0
        self._error_reason = None

    # --- Lifecycle ---

    def start(self):
        """Called when entering MINI_GAME state. Sends start request to backend."""
        self._state = GameState.WAITING
        self._waiting_frames = 0
        self._error_reason = None
        self._ws_send({"type": "mini_game_start"})
        log.info("Mini-game start requested")

    def on_game_ready(self, success: bool, reason: str = None):
        """Called when backend responds to mini_game_start."""
        if success:
            self._reset_game()
            self._state = GameState.COUNTDOWN
            self._countdown_frames = self.COUNTDOWN_FRAMES
            log.info("Mini-game ready, starting countdown")
        else:
            self._error_reason = reason
            self._state = GameState.GAME_OVER
            log.warning("Mini-game rejected: %s", reason)

    def _reset_game(self):
        self._score = 0
        self._timer_frames = self.GAME_DURATION_FRAMES
        self._cotton_candy_earned = 0
        self._player.reset()
        self._spawner.reset()
        self._spawner.set_tier(0)

    # --- Tick ---

    WAITING_TIMEOUT_FRAMES = 150  # 5s at 30fps

    def tick(self):
        """Called once per frame by StateMachine."""
        if self._state == GameState.WAITING:
            self._waiting_frames += 1
            if self._waiting_frames >= self.WAITING_TIMEOUT_FRAMES:
                self._error_reason = "server_timeout"
                self._state = GameState.GAME_OVER
                log.warning("Mini-game start timed out")
        elif self._state == GameState.COUNTDOWN:
            self._tick_countdown()
        elif self._state == GameState.PLAYING:
            self._tick_playing()

    def _tick_countdown(self):
        self._countdown_frames -= 1
        if self._countdown_frames <= 0:
            self._state = GameState.PLAYING
            log.info("Mini-game playing")

    def _tick_playing(self):
        # Timer
        self._timer_frames -= 1
        if self._timer_frames <= 0:
            self._end_game()
            return

        # Difficulty tier progression
        elapsed = self.GAME_DURATION_FRAMES - self._timer_frames
        tier = sum(1 for t in self.TIER_THRESHOLDS if elapsed >= t)
        self._spawner.set_tier(tier)

        # Update objects
        self._player.update()
        self._spawner.tick()

        # Collision detection
        items_to_remove = []
        for i, item in enumerate(self._spawner.items):
            if check_collision(self._player, item):
                if item.item_type == "food":
                    self._score += 10
                else:
                    self._player.stun()
                items_to_remove.append(i)

        for i in reversed(items_to_remove):
            self._spawner.items.pop(i)

    # --- Game end ---

    def _end_game(self):
        self._state = GameState.GAME_OVER
        self._cotton_candy_earned = self._score // 50
        if self._score > self._high_score:
            self._high_score = self._score
        self._ws_send({
            "type": "mini_game_result",
            "score": self._score,
        })
        log.info("Mini-game ended: score=%d, candy=%d", self._score, self._cotton_candy_earned)

    def on_reward(self, cotton_candy: int):
        """Called when backend responds with mini_game_reward."""
        self._cotton_candy_earned = cotton_candy
        log.info("Mini-game reward received: %d cotton candy", cotton_candy)

    # --- Button handlers ---

    def poll_buttons(self, button_a_held: bool, button_d_held: bool):
        """Hold-to-move: call each tick with GPIO pin states.

        A = move right, D = move left (swapped for physical button layout).
        Resets moving direction each frame before checking buttons.
        """
        self._player.moving = None
        if self._state == GameState.PLAYING:
            if button_a_held:
                self._player.move_right()
            if button_d_held:
                self._player.move_left()

    def on_button_a(self):
        """Move right (edge callback fallback)."""
        if self._state == GameState.PLAYING:
            self._player.move_right()

    def on_button_d(self):
        """Move left (edge callback fallback)."""
        if self._state == GameState.PLAYING:
            self._player.move_left()

    def on_button_b(self):
        """Pause/resume or exit game-over screen."""
        if self._state == GameState.PLAYING:
            self._state = GameState.PAUSED
            log.info("Mini-game paused")
        elif self._state == GameState.PAUSED:
            self._state = GameState.PLAYING
            log.info("Mini-game resumed")
        elif self._state == GameState.GAME_OVER:
            return "exit"
        return None

    def on_button_c(self):
        """Exit game early."""
        if self._state in (GameState.PLAYING, GameState.PAUSED, GameState.COUNTDOWN):
            self._end_game()
        elif self._state in (GameState.GAME_OVER, GameState.WAITING):
            return "exit"
        return None

    # --- Properties for renderer ---

    @property
    def state(self) -> GameState:
        return self._state

    @property
    def score(self) -> int:
        return self._score

    @property
    def high_score(self) -> int:
        return self._high_score

    @property
    def timer_seconds(self) -> float:
        return max(0, self._timer_frames / 30.0)

    @property
    def timer_ratio(self) -> float:
        """0.0 to 1.0, for timer bar rendering."""
        return max(0, self._timer_frames / self.GAME_DURATION_FRAMES)

    @property
    def countdown_number(self) -> int:
        """3, 2, 1, or 0."""
        return min(3, max(0, (self._countdown_frames - 1) // 30 + 1))

    @property
    def player(self):
        return self._player

    @property
    def items(self):
        return self._spawner.items

    @property
    def cotton_candy_earned(self) -> int:
        return self._cotton_candy_earned

    @property
    def error_reason(self):
        return self._error_reason

    @property
    def is_running(self) -> bool:
        return self._state in (GameState.COUNTDOWN, GameState.PLAYING, GameState.PAUSED)

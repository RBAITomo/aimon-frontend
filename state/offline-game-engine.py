"""Offline game engine orchestrator.

Composes stat decay, feed handler, response bank, and event journal
into a unified offline gameplay loop. Started on disconnect, stopped
on reconnect with state snapshot for sync.
"""

import importlib
import logging
import time

import config

log = logging.getLogger(__name__)

_stat_mod = importlib.import_module("state.offline-stat-engine")
OfflineStatEngine = _stat_mod.OfflineStatEngine

_feed_mod = importlib.import_module("state.offline-feed-handler")
OfflineFeedHandler = _feed_mod.OfflineFeedHandler


class OfflineGameEngine:
    """Orchestrates offline tamagotchi gameplay."""

    def __init__(self, pet_state_updater, display_callback, journal, response_bank):
        """
        Args:
            pet_state_updater: fn(hunger_delta, energy_delta, happiness_delta) -> stats dict
            display_callback: fn(text: str) — show text bubble on screen
            journal: OfflineEventJournal instance
            response_bank: OfflineResponseBank instance
        """
        self._updater = pet_state_updater
        self._display = display_callback
        self._journal = journal
        self._response_bank = response_bank

        self._stat_engine = OfflineStatEngine(
            update_callback=self._updater,
            journal=self._journal,
        )
        self._feed_handler = OfflineFeedHandler(
            update_callback=self._updater,
            journal=self._journal,
        )
        self._offline_since = 0.0
        self._running = False

    def start(self, offline_since_ts: float = None):
        """Start offline gameplay loop."""
        self._offline_since = offline_since_ts or time.time()
        self._running = True
        self._stat_engine.start()
        log.info("Offline game engine started")

    def stop(self) -> dict:
        """Stop engine and return state snapshot for sync."""
        self._running = False
        self._stat_engine.stop()
        snapshot = {
            "offline_since": self._offline_since,
            "offline_duration_s": time.time() - self._offline_since,
        }
        log.info("Offline game engine stopped (duration=%.0fs)",
                 snapshot["offline_duration_s"])
        return snapshot

    def on_interaction(self):
        """Handle single-press interaction: show text + gain XP."""
        if not self._running:
            return

        # Get current stats for condition check (via updater with 0 deltas)
        stats = self._updater(hunger_delta=0, energy_delta=0, happiness_delta=0)
        if stats:
            condition = self._response_bank.determine_condition(
                stats.get("hunger", 50),
                stats.get("energy", 50),
                stats.get("happiness", 50),
            )
            text = self._response_bank.get_response(condition)
            self._display(text)

        # XP gain
        self._apply_xp(config.OFFLINE_XP_INTERACTION)
        self._journal.log_event("interaction", {"xp": config.OFFLINE_XP_INTERACTION})

    def on_feed(self):
        """Handle double-press feed attempt."""
        if not self._running:
            return False

        success = self._feed_handler.try_feed()
        if success:
            self._apply_xp(config.OFFLINE_XP_FEED)
        return success

    def _apply_xp(self, amount: int):
        """Add XP and check for level-up."""
        self._journal.log_event("xp_gain", {"amount": amount})
        # XP application is handled via the pet_state_updater callback
        # The state machine will apply XP to pet_state and check level-up

    @property
    def running(self) -> bool:
        return self._running

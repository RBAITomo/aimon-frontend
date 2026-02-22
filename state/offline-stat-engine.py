"""Offline stat decay engine running on a daemon background thread.

Applies periodic stat decay (hunger +1, energy -0.5, happiness -0.3)
every OFFLINE_DECAY_INTERVAL_S seconds while offline.
"""

import logging
import threading
import time

import config

log = logging.getLogger(__name__)


class OfflineStatEngine:
    """Background thread that decays pet stats at regular intervals."""

    def __init__(self, update_callback, journal, interval_s=None):
        """
        Args:
            update_callback: fn(hunger_delta, energy_delta, happiness_delta)
            journal: OfflineEventJournal instance
            interval_s: decay interval (default from config)
        """
        self._update_callback = update_callback
        self._journal = journal
        self._interval = interval_s or config.OFFLINE_DECAY_INTERVAL_S
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        """Start the decay daemon thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._decay_loop, daemon=True)
        self._thread.start()
        log.info("Offline stat decay started (interval=%ds)", self._interval)

    def stop(self):
        """Stop the decay thread and wait for it to finish."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        log.info("Offline stat decay stopped")

    def _decay_loop(self):
        next_tick = time.time() + self._interval
        while not self._stop_event.is_set():
            now = time.time()
            if now >= next_tick:
                self._apply_decay()
                next_tick = now + self._interval
            # Sleep in small increments for responsive stop
            self._stop_event.wait(timeout=1.0)

    def _apply_decay(self):
        """Apply one decay tick and log to journal."""
        try:
            stats = self._update_callback(
                hunger_delta=1, energy_delta=-0.5, happiness_delta=-0.3
            )
            if stats:
                self._journal.log_event("decay_tick", {
                    "hunger": stats.get("hunger"),
                    "energy": stats.get("energy"),
                    "happiness": stats.get("happiness"),
                })
                # Check critical thresholds
                if stats.get("hunger", 0) >= 80 or stats.get("energy", 100) <= 20:
                    self._journal.log_event("warning", {
                        "reason": "critical_stats",
                        "hunger": stats.get("hunger"),
                        "energy": stats.get("energy"),
                    })
                if stats.get("hunger", 0) >= 100:
                    self._journal.log_event("regression", {
                        "reason": "hunger_maxed",
                    })
        except Exception as e:
            log.error("Decay tick failed: %s", e)

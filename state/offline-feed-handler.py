"""Offline feed handler with cooldown enforcement.

Handles manual feeding during offline mode with configurable
cooldown period and hunger reduction.
"""

import logging
import time

import config

log = logging.getLogger(__name__)


class OfflineFeedHandler:
    """Feed logic with cooldown for offline gameplay."""

    def __init__(self, update_callback, journal, cooldown_s=None):
        """
        Args:
            update_callback: fn(hunger_delta, energy_delta, happiness_delta) -> stats dict
            journal: OfflineEventJournal instance
            cooldown_s: seconds between feeds (default from config)
        """
        self._update_callback = update_callback
        self._journal = journal
        self._cooldown = cooldown_s or config.OFFLINE_FEED_COOLDOWN_S
        self._last_feed_ts = 0.0

    def can_feed(self) -> bool:
        """Check if cooldown has elapsed since last feed."""
        return (time.time() - self._last_feed_ts) >= self._cooldown

    def try_feed(self) -> bool:
        """Attempt to feed. Returns True if successful (cooldown passed)."""
        if not self.can_feed():
            log.debug("Feed on cooldown (%.0fs remaining)",
                      self._cooldown - (time.time() - self._last_feed_ts))
            return False

        self._last_feed_ts = time.time()
        reduction = config.OFFLINE_FEED_HUNGER_REDUCTION
        energy_restore = config.OFFLINE_FEED_ENERGY_RESTORE
        stats = self._update_callback(
            hunger_delta=-reduction, energy_delta=energy_restore, happiness_delta=5
        )
        self._journal.log_event("feed", {
            "hunger_reduction": reduction,
            "energy_restore": energy_restore,
            "hunger": stats.get("hunger") if stats else None,
            "energy": stats.get("energy") if stats else None,
        })
        log.info("Offline feed applied (hunger -%d, energy +%d)", reduction, energy_restore)
        return True

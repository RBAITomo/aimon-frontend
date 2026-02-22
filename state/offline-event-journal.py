"""SQLite event journal for offline gameplay events.

Stores offline events (decay ticks, feeds, interactions, XP gains) locally
and provides sync methods for reconnect flush to backend.
"""

import json
import logging
import sqlite3
import threading
import time

import config

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS offline_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    timestamp INTEGER NOT NULL,
    payload TEXT,
    synced INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_offline_synced ON offline_events(synced, timestamp);
"""


class OfflineEventJournal:
    """Thread-safe SQLite journal for offline gameplay events."""

    def __init__(self, db_path=None):
        self._db_path = db_path or config.OFFLINE_DB_PATH
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        log.info("OfflineEventJournal ready at %s", self._db_path)

    def log_event(self, event_type: str, payload: dict = None) -> int:
        """Insert an event and auto-prune if over max. Returns row id."""
        with self._lock:
            try:
                payload_json = json.dumps(payload) if payload else None
                cur = self._conn.execute(
                    "INSERT INTO offline_events (event_type, timestamp, payload) VALUES (?, ?, ?)",
                    (event_type, int(time.time()), payload_json),
                )
                self._conn.commit()
                row_id = cur.lastrowid
                self._prune()
                return row_id
            except sqlite3.Error as e:
                log.error("Failed to log offline event: %s", e)
                return -1

    def get_pending(self, limit=200) -> list:
        """Return unsynced events ordered by timestamp."""
        with self._lock:
            try:
                rows = self._conn.execute(
                    "SELECT id, event_type, timestamp, payload, synced "
                    "FROM offline_events WHERE synced=0 ORDER BY timestamp ASC LIMIT ?",
                    (limit,),
                ).fetchall()
                return [self._row_to_dict(r) for r in rows]
            except sqlite3.Error as e:
                log.error("Failed to get pending events: %s", e)
                return []

    def get_all_pending_for_sync(self) -> list:
        """Get ALL unsynced events for reconnect flush."""
        with self._lock:
            try:
                rows = self._conn.execute(
                    "SELECT id, event_type, timestamp, payload, synced "
                    "FROM offline_events WHERE synced=0 ORDER BY timestamp ASC",
                ).fetchall()
                return [self._row_to_dict(r) for r in rows]
            except sqlite3.Error as e:
                log.error("Failed to get all pending events: %s", e)
                return []

    def mark_synced(self, ids: list):
        """Mark events as synced by id list."""
        if not ids:
            return
        with self._lock:
            try:
                placeholders = ",".join("?" * len(ids))
                self._conn.execute(
                    f"UPDATE offline_events SET synced=1 WHERE id IN ({placeholders})",
                    ids,
                )
                self._conn.commit()
            except sqlite3.Error as e:
                log.error("Failed to mark events synced: %s", e)

    def clear_synced(self):
        """Delete all synced events."""
        with self._lock:
            try:
                self._conn.execute("DELETE FROM offline_events WHERE synced=1")
                self._conn.commit()
            except sqlite3.Error as e:
                log.error("Failed to clear synced events: %s", e)

    def _prune(self):
        """Delete oldest events if count exceeds max."""
        try:
            count = self._conn.execute(
                "SELECT COUNT(*) FROM offline_events"
            ).fetchone()[0]
            if count > config.OFFLINE_EVENT_MAX:
                excess = count - config.OFFLINE_EVENT_MAX
                self._conn.execute(
                    "DELETE FROM offline_events WHERE id IN "
                    "(SELECT id FROM offline_events ORDER BY timestamp ASC LIMIT ?)",
                    (excess,),
                )
                self._conn.commit()
                log.debug("Pruned %d old offline events", excess)
        except sqlite3.Error as e:
            log.error("Failed to prune offline events: %s", e)

    @staticmethod
    def _row_to_dict(row) -> dict:
        d = dict(row)
        if d.get("payload"):
            try:
                d["payload"] = json.loads(d["payload"])
            except (json.JSONDecodeError, TypeError):
                pass
        return d

    def close(self):
        self._conn.close()
        log.info("OfflineEventJournal closed")

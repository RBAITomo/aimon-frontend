"""SQLite-based local turn logger for AI-MON conversations.

Stores recent conversation turns locally on the Pi for diagnostics
and short-term context. Enforces a maximum of 200 turns.
"""

import logging
import os
import sqlite3
import time

import config

log = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    turn_id TEXT,
    timestamp INTEGER NOT NULL,
    user_text TEXT NOT NULL,
    assistant_text TEXT NOT NULL,
    emotion TEXT,
    duration_ms INTEGER
);
CREATE INDEX IF NOT EXISTS idx_turns_timestamp ON turns(timestamp DESC);
"""


class TurnLogger:
    """Local SQLite turn log with automatic pruning."""

    def __init__(self):
        db_dir = os.path.dirname(config.TURN_DB_PATH)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)

        self._conn = sqlite3.connect(
            config.TURN_DB_PATH, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        log.info("TurnLogger ready at %s", config.TURN_DB_PATH)

    def log_turn(self, turn_id, user_text, assistant_text, emotion=None, duration_ms=0):
        """Insert a turn and prune old entries if over limit.

        Args:
            turn_id: Backend-assigned turn identifier.
            user_text: User's spoken text (ASR result).
            assistant_text: AI response text (joined LLM tokens).
            emotion: Detected emotion tag (optional).
            duration_ms: Turn duration in milliseconds.
        """
        try:
            self._conn.execute(
                "INSERT INTO turns (turn_id, timestamp, user_text, assistant_text, emotion, duration_ms) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (turn_id, int(time.time()), user_text, assistant_text, emotion, duration_ms),
            )
            self._conn.commit()
            self._prune()
        except sqlite3.Error as e:
            log.error("Failed to log turn: %s", e)

    def get_recent(self, limit=20):
        """Return the most recent turns as list of dicts.

        Args:
            limit: Max number of turns to return.

        Returns:
            list[dict]: Recent turns ordered newest-first.
        """
        try:
            rows = self._conn.execute(
                "SELECT * FROM turns ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [dict(r) for r in rows]
        except sqlite3.Error as e:
            log.error("Failed to query turns: %s", e)
            return []

    def _prune(self):
        """Delete oldest turns if count exceeds TURN_MAX_COUNT."""
        try:
            count = self._conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
            if count > config.TURN_MAX_COUNT:
                excess = count - config.TURN_MAX_COUNT
                self._conn.execute(
                    "DELETE FROM turns WHERE id IN "
                    "(SELECT id FROM turns ORDER BY timestamp ASC LIMIT ?)",
                    (excess,),
                )
                self._conn.commit()
                log.debug("Pruned %d old turns", excess)
        except sqlite3.Error as e:
            log.error("Failed to prune turns: %s", e)

    def close(self):
        self._conn.close()
        log.info("TurnLogger closed")

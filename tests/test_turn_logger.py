"""Unit tests for SQLite turn logger.

Tests turn logging, retrieval, pruning, and database operations.
"""

import pytest
import sqlite3
import tempfile
import os
from unittest.mock import patch
from storage.turn_logger import TurnLogger


@pytest.fixture
def temp_db_path():
    """Create temporary database file path."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    # Cleanup
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def turn_logger(temp_db_path):
    """Create TurnLogger with temporary database."""
    with patch('config.TURN_DB_PATH', temp_db_path):
        logger = TurnLogger()
        yield logger
        logger.close()


class TestInitialization:
    """Test logger initialization and schema creation."""

    def test_creates_database_file(self, temp_db_path):
        """Logger should create database file on init."""
        with patch('config.TURN_DB_PATH', temp_db_path):
            logger = TurnLogger()
            assert os.path.exists(temp_db_path)
            logger.close()

    def test_creates_turns_table(self, turn_logger):
        """Logger should create turns table with correct schema."""
        cursor = turn_logger._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='turns'"
        )
        assert cursor.fetchone() is not None

    def test_creates_index_on_timestamp(self, turn_logger):
        """Logger should create index on timestamp for fast queries."""
        cursor = turn_logger._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_turns_timestamp'"
        )
        assert cursor.fetchone() is not None


class TestLogTurn:
    """Test turn logging functionality."""

    def test_log_turn_inserts_record(self, turn_logger):
        """log_turn should insert record into database."""
        turn_logger.log_turn(
            turn_id="turn_001",
            user_text="Hello AI-MON",
            assistant_text="Hello! How can I help?",
            emotion="happy",
            duration_ms=2500,
        )
        
        cursor = turn_logger._conn.execute("SELECT COUNT(*) FROM turns")
        count = cursor.fetchone()[0]
        assert count == 1

    def test_log_turn_stores_correct_data(self, turn_logger):
        """log_turn should store all fields correctly."""
        turn_logger.log_turn(
            turn_id="turn_002",
            user_text="Tell me a joke",
            assistant_text="Why did the robot go to school? To improve its AI-Q!",
            emotion="playful",
            duration_ms=3200,
        )
        
        cursor = turn_logger._conn.execute("SELECT * FROM turns WHERE turn_id='turn_002'")
        row = cursor.fetchone()
        
        assert row['turn_id'] == 'turn_002'
        assert row['user_text'] == 'Tell me a joke'
        assert row['assistant_text'] == "Why did the robot go to school? To improve its AI-Q!"
        assert row['emotion'] == 'playful'
        assert row['duration_ms'] == 3200
        assert row['timestamp'] > 0

    def test_log_turn_with_none_emotion(self, turn_logger):
        """log_turn should handle None emotion gracefully."""
        turn_logger.log_turn(
            turn_id="turn_003",
            user_text="Test",
            assistant_text="Response",
            emotion=None,
            duration_ms=1000,
        )
        
        cursor = turn_logger._conn.execute("SELECT emotion FROM turns WHERE turn_id='turn_003'")
        row = cursor.fetchone()
        assert row['emotion'] is None

    def test_log_turn_handles_database_error(self, turn_logger):
        """log_turn should handle database errors gracefully."""
        # Close connection to simulate error
        turn_logger._conn.close()
        
        # Should not raise exception
        turn_logger.log_turn(
            turn_id="turn_999",
            user_text="Test",
            assistant_text="Test",
        )


class TestGetRecent:
    """Test retrieving recent turns."""

    def test_get_recent_returns_list(self, turn_logger):
        """get_recent should return list of dicts."""
        turn_logger.log_turn("t1", "User 1", "Assistant 1")
        turn_logger.log_turn("t2", "User 2", "Assistant 2")
        
        recent = turn_logger.get_recent(10)
        
        assert isinstance(recent, list)
        assert len(recent) == 2
        assert isinstance(recent[0], dict)

    def test_get_recent_returns_newest_first(self, turn_logger):
        """get_recent should return newest turns first."""
        import time
        
        turn_logger.log_turn("t1", "First", "Response 1")
        time.sleep(0.01)  # Ensure different timestamps
        turn_logger.log_turn("t2", "Second", "Response 2")
        time.sleep(0.01)
        turn_logger.log_turn("t3", "Third", "Response 3")
        
        recent = turn_logger.get_recent(10)
        
        assert recent[0]['turn_id'] == 't3'
        assert recent[1]['turn_id'] == 't2'
        assert recent[2]['turn_id'] == 't1'

    def test_get_recent_respects_limit(self, turn_logger):
        """get_recent should respect limit parameter."""
        for i in range(10):
            turn_logger.log_turn(f"turn_{i}", f"User {i}", f"Assistant {i}")
        
        recent = turn_logger.get_recent(5)
        
        assert len(recent) == 5

    def test_get_recent_empty_database(self, turn_logger):
        """get_recent should return empty list for empty database."""
        recent = turn_logger.get_recent(10)
        
        assert recent == []

    def test_get_recent_handles_database_error(self, turn_logger):
        """get_recent should handle database errors gracefully."""
        turn_logger._conn.close()
        
        recent = turn_logger.get_recent(10)
        
        assert recent == []


class TestPruning:
    """Test automatic pruning of old turns."""

    @patch('config.TURN_MAX_COUNT', 5)
    def test_prune_removes_oldest_turns(self, turn_logger):
        """Pruning should remove oldest turns beyond max count."""
        import time
        
        # Insert 7 turns (exceeds TURN_MAX_COUNT=5)
        for i in range(7):
            turn_logger.log_turn(f"turn_{i}", f"User {i}", f"Assistant {i}")
            time.sleep(0.01)  # Ensure different timestamps
        
        cursor = turn_logger._conn.execute("SELECT COUNT(*) FROM turns")
        count = cursor.fetchone()[0]
        
        assert count == 5  # Should have pruned 2 oldest

    @patch('config.TURN_MAX_COUNT', 5)
    def test_prune_keeps_newest_turns(self, turn_logger):
        """Pruning should keep newest turns."""
        import time
        
        for i in range(7):
            turn_logger.log_turn(f"turn_{i}", f"User {i}", f"Assistant {i}")
            time.sleep(0.01)
        
        cursor = turn_logger._conn.execute(
            "SELECT turn_id FROM turns ORDER BY timestamp DESC"
        )
        remaining = [row['turn_id'] for row in cursor.fetchall()]
        
        # Should keep turns 2-6 (newest 5)
        assert 'turn_6' in remaining
        assert 'turn_5' in remaining
        assert 'turn_0' not in remaining
        assert 'turn_1' not in remaining

    @patch('config.TURN_MAX_COUNT', 100)
    def test_no_prune_below_limit(self, turn_logger):
        """Should not prune if below max count."""
        for i in range(10):
            turn_logger.log_turn(f"turn_{i}", f"User {i}", f"Assistant {i}")
        
        cursor = turn_logger._conn.execute("SELECT COUNT(*) FROM turns")
        count = cursor.fetchone()[0]
        
        assert count == 10  # No pruning

    def test_prune_handles_database_error(self, turn_logger):
        """Pruning should handle database errors gracefully."""
        # Insert one turn to trigger prune
        turn_logger.log_turn("t1", "User", "Assistant")
        
        # Close connection
        turn_logger._conn.close()
        
        # Reconnect to test
        turn_logger._conn = sqlite3.connect(':memory:')
        
        # Should not raise exception
        turn_logger._prune()


class TestConcurrency:
    """Test thread safety (via check_same_thread=False)."""

    def test_connection_allows_multithreading(self, turn_logger):
        """Database connection should allow access from multiple threads."""
        import threading
        
        results = []
        
        def log_turn_thread(turn_id):
            try:
                turn_logger.log_turn(turn_id, "User", "Assistant")
                results.append(True)
            except sqlite3.ProgrammingError:
                results.append(False)
        
        threads = [
            threading.Thread(target=log_turn_thread, args=(f"t{i}",))
            for i in range(5)
        ]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All threads should succeed
        assert all(results)
        
        cursor = turn_logger._conn.execute("SELECT COUNT(*) FROM turns")
        assert cursor.fetchone()[0] == 5


class TestClose:
    """Test cleanup."""

    def test_close_closes_connection(self, turn_logger):
        """close() should close database connection."""
        turn_logger.close()
        
        # Attempting to execute should raise
        with pytest.raises(sqlite3.ProgrammingError):
            turn_logger._conn.execute("SELECT 1")

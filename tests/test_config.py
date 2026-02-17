"""Unit tests for configuration module.

Tests environment variable loading and default values.
"""

import pytest
import os
from unittest.mock import patch


class TestConfigDefaults:
    """Test default configuration values."""

    def test_backend_ws_url_default(self):
        """Backend URL should default to localhost."""
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.BACKEND_WS_URL == "ws://localhost:8080"

    def test_robot_id_default(self):
        """Robot ID should have default value."""
        with patch.dict(os.environ, {}, clear=True):
            import importlib
            import config
            importlib.reload(config)
            assert config.ROBOT_ID == "robot001"

    def test_audio_sample_rates(self):
        """Audio sample rates should be correctly configured."""
        import config
        assert config.AUDIO_SAMPLE_RATE == 16000
        assert config.AUDIO_PLAYBACK_RATE == 16000

    def test_audio_format(self):
        """Audio format should be mono 16-bit."""
        import config
        assert config.AUDIO_CHANNELS == 1
        assert config.AUDIO_FORMAT_WIDTH == 2

    def test_audio_frame_parameters(self):
        """Audio frame parameters should be configured."""
        import config
        assert config.AUDIO_FRAME_DURATION_MS == 20

    def test_lcd_dimensions(self):
        """LCD dimensions should match ST7789."""
        import config
        assert config.LCD_WIDTH == 240
        assert config.LCD_HEIGHT == 280
        assert config.LCD_FPS == 30
        assert config.LCD_CORNER_HEIGHT == 20

    def test_websocket_reconnect_params(self):
        """WebSocket reconnect parameters should be reasonable."""
        import config
        assert config.WS_RECONNECT_INTERVAL_S == 2
        assert config.WS_RECONNECT_MAX_ATTEMPTS == 5
        assert config.WS_PING_INTERVAL_S == 15

    def test_turn_max_count(self):
        """Turn logger should limit to 200 turns."""
        import config
        assert config.TURN_MAX_COUNT == 200

    def test_led_colors_defined(self):
        """LED colors should be defined for all states."""
        import config
        assert isinstance(config.LED_IDLE, tuple)
        assert isinstance(config.LED_LISTENING, tuple)
        assert isinstance(config.LED_ASR, tuple)
        assert isinstance(config.LED_ANSWER, tuple)
        assert isinstance(config.LED_EMOTION_HAPPY, tuple)
        assert isinstance(config.LED_EMOTION_SAD, tuple)
        assert isinstance(config.LED_OFFLINE, tuple)
        
        # All should be RGB tuples (3 values, 0-255)
        for color in [config.LED_IDLE, config.LED_LISTENING, config.LED_ASR]:
            assert len(color) == 3
            assert all(0 <= c <= 255 for c in color)

    def test_gpio_pins_defined(self):
        """GPIO pins should be defined."""
        import config
        assert hasattr(config, 'PIN_BUTTON')
        assert hasattr(config, 'PIN_DC')
        assert hasattr(config, 'PIN_RST')
        assert hasattr(config, 'PIN_BACKLIGHT')
        assert hasattr(config, 'PIN_LED_RED')
        assert hasattr(config, 'PIN_LED_GREEN')
        assert hasattr(config, 'PIN_LED_BLUE')

    def test_spi_configuration(self):
        """SPI should be configured for ST7789."""
        import config
        assert config.SPI_BUS == 0
        assert config.SPI_DEVICE == 0
        assert config.SPI_SPEED_HZ == 100_000_000  # 100MHz


class TestEnvironmentVariables:
    """Test environment variable overrides."""

    def test_backend_url_from_env(self):
        """BACKEND_WS_URL should be overridable."""
        with patch.dict(os.environ, {'BACKEND_WS_URL': 'ws://custom:9000'}):
            import importlib
            import config
            importlib.reload(config)
            assert config.BACKEND_WS_URL == 'ws://custom:9000'

    def test_robot_id_from_env(self):
        """ROBOT_ID should be overridable."""
        with patch.dict(os.environ, {'ROBOT_ID': 'robot_custom_123'}):
            import importlib
            import config
            importlib.reload(config)
            assert config.ROBOT_ID == 'robot_custom_123'

    def test_turn_db_path_from_env(self):
        """TURN_DB_PATH should be overridable."""
        with patch.dict(os.environ, {'TURN_DB_PATH': '/custom/path/turns.db'}):
            import importlib
            import config
            importlib.reload(config)
            assert config.TURN_DB_PATH == '/custom/path/turns.db'


class TestConfigConsistency:
    """Test configuration value consistency."""

    def test_capture_chunk_size_calculation(self):
        """Capture chunk size should be valid for 16kHz."""
        import config
        chunk_samples = int(
            config.AUDIO_SAMPLE_RATE * config.AUDIO_FRAME_DURATION_MS / 1000
        )
        # 16000 Hz * 0.020s = 320 samples
        assert chunk_samples == 320

    def test_sprite_dir_exists_or_creatable(self):
        """SPRITE_DIR should be valid path."""
        import config
        assert isinstance(config.SPRITE_DIR, str)
        assert len(config.SPRITE_DIR) > 0

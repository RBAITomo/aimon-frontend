"""Pytest configuration and shared fixtures for AI-MON frontend tests.

Provides common mocks, fixtures, and test utilities.
"""

import pytest
import sys
import os
from unittest.mock import Mock, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


@pytest.fixture(autouse=True)
def mock_gpio():
    """Auto-mock RPi.GPIO for all tests (since tests run on non-Pi systems)."""
    gpio_mock = MagicMock()
    gpio_mock.BOARD = 'BOARD'
    gpio_mock.OUT = 'OUT'
    gpio_mock.IN = 'IN'
    gpio_mock.HIGH = 1
    gpio_mock.LOW = 0
    gpio_mock.PUD_UP = 'PUD_UP'
    gpio_mock.BOTH = 'BOTH'
    
    sys.modules['RPi'] = MagicMock()
    sys.modules['RPi.GPIO'] = gpio_mock
    
    yield gpio_mock
    
    # Cleanup
    if 'RPi.GPIO' in sys.modules:
        del sys.modules['RPi.GPIO']
    if 'RPi' in sys.modules:
        del sys.modules['RPi']


@pytest.fixture(autouse=True)
def mock_spidev():
    """Auto-mock spidev for all tests."""
    spidev_mock = MagicMock()
    sys.modules['spidev'] = spidev_mock
    
    yield spidev_mock
    
    if 'spidev' in sys.modules:
        del sys.modules['spidev']


@pytest.fixture(autouse=True)
def mock_pygame():
    """Auto-mock pygame for all tests."""
    pygame_mock = MagicMock()
    pygame_mock.QUIT = 0
    sys.modules['pygame'] = pygame_mock
    sys.modules['pygame.font'] = MagicMock()
    sys.modules['pygame.display'] = MagicMock()
    sys.modules['pygame.surfarray'] = MagicMock()
    
    yield pygame_mock
    
    # Cleanup
    for module in list(sys.modules.keys()):
        if module.startswith('pygame'):
            del sys.modules[module]


@pytest.fixture(autouse=True)
def mock_pyaudio():
    """Auto-mock pyaudio for all tests."""
    pyaudio_mock = MagicMock()
    pyaudio_mock.paInt16 = 8
    pyaudio_mock.paContinue = 0
    pyaudio_mock.paComplete = 1
    sys.modules['pyaudio'] = pyaudio_mock
    
    yield pyaudio_mock
    
    if 'pyaudio' in sys.modules:
        del sys.modules['pyaudio']


@pytest.fixture(autouse=True)
def mock_opuslib():
    """Auto-mock opuslib for all tests."""
    opuslib_mock = MagicMock()
    opuslib_mock.APPLICATION_VOIP = 2048
    sys.modules['opuslib'] = opuslib_mock
    
    yield opuslib_mock
    
    if 'opuslib' in sys.modules:
        del sys.modules['opuslib']


@pytest.fixture(autouse=True)
def mock_numpy():
    """Auto-mock numpy for all tests."""
    numpy_mock = MagicMock()
    numpy_mock.uint8 = 'uint8'
    numpy_mock.uint16 = 'uint16'
    numpy_mock.int16 = 'int16'
    
    # Mock array operations
    def frombuffer_mock(data, dtype):
        mock_array = MagicMock()
        mock_array.astype = Mock(return_value=mock_array)
        mock_array.tobytes = Mock(return_value=data)
        return mock_array
    
    def repeat_mock(arr, times):
        mock_array = MagicMock()
        mock_array.astype = Mock(return_value=mock_array)
        mock_array.tobytes = Mock(return_value=b'repeated_data')
        return mock_array
    
    numpy_mock.frombuffer = frombuffer_mock
    numpy_mock.repeat = repeat_mock
    numpy_mock.dstack = Mock(return_value=MagicMock(flatten=Mock(return_value=MagicMock(tolist=Mock(return_value=[])))))
    
    sys.modules['numpy'] = numpy_mock
    sys.modules['np'] = numpy_mock
    
    yield numpy_mock
    
    if 'numpy' in sys.modules:
        del sys.modules['numpy']
    if 'np' in sys.modules:
        del sys.modules['np']


@pytest.fixture
def mock_websocket():
    """Create mock WebSocket connection."""
    ws = Mock()
    ws.recv = Mock(side_effect=TimeoutError)
    ws.send = Mock()
    ws.close = Mock()
    return ws


@pytest.fixture
def sample_turn_data():
    """Provide sample turn data for testing."""
    return {
        'turn_id': 'turn_test_001',
        'user_text': 'Hello AI-MON',
        'assistant_text': 'Hello! How can I help you today?',
        'emotion': 'happy',
        'duration_ms': 2500,
    }


@pytest.fixture
def sample_audio_data():
    """Provide sample audio data for testing."""
    return {
        'pcm16': b'\x00\x01\x02\x03\x04\x05',
        'opus': b'\x00\x01\x02',
        'sample_rate': 16000,
        'channels': 1,
    }


@pytest.fixture
def sample_websocket_messages():
    """Provide sample WebSocket messages for testing."""
    return {
        'hello_ack': {
            'type': 'hello_ack',
            'session_id': 'session_abc123',
        },
        'asr_result': {
            'type': 'asr_result',
            'text': 'Test transcript',
            'confidence': 0.95,
        },
        'llm_stream': {
            'type': 'llm_stream',
            'token': 'Hello',
            'done': False,
        },
        'tts_start': {
            'type': 'tts_start',
            'text': 'Response text',
        },
        'turn_end': {
            'type': 'turn_end',
            'turn_id': 'turn_123',
        },
        'error': {
            'type': 'error',
            'code': 'ASR_FAILED',
            'message': 'Speech recognition timeout',
        },
    }


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: mark test as a unit test"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as an integration test"
    )
    config.addinivalue_line(
        "markers", "hardware: mark test as requiring hardware (skip in CI)"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip hardware tests unless --hardware flag is provided."""
    if not config.getoption("--hardware", default=False):
        skip_hardware = pytest.mark.skip(reason="need --hardware option to run")
        for item in items:
            if "hardware" in item.keywords:
                item.add_marker(skip_hardware)


def pytest_addoption(parser):
    """Add custom command-line options."""
    parser.addoption(
        "--hardware",
        action="store_true",
        default=False,
        help="run tests that require actual hardware",
    )

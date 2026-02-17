# AI-MON Frontend Test Quick Reference

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html

# Run specific file
pytest tests/test_state_machine.py

# Run specific test
pytest tests/test_state_machine.py::TestStateTransitions::test_idle_to_listening_on_button_press
```

## Test Files

| File | Tests | What It Covers |
|------|-------|----------------|
| `test_state_machine.py` | 45+ | State transitions, half-duplex, interrupts, button handling |
| `test_ws_client.py` | 35+ | WebSocket protocol, connection lifecycle, message parsing |
| `test_turn_logger.py` | 25+ | SQLite operations, turn logging, pruning, concurrency |
| `test_audio.py` | 20+ | Audio capture, OPUS encoding, playback queue |
| `test_config.py` | 15+ | Configuration defaults, environment variables |

## Common Commands

```bash
# Run fast tests only
pytest -m "not slow"

# Run with verbose output
pytest -v -s

# Show test durations
pytest --durations=10

# Run until first failure
pytest -x

# Run last failed tests
pytest --lf

# Drop into debugger on failure
pytest --pdb

# Generate coverage report
pytest --cov=. --cov-report=term-missing

# Run specific marker
pytest -m unit
pytest -m integration

# Skip hardware tests (default)
pytest  # hardware tests auto-skipped

# Run hardware tests (only on Raspberry Pi)
pytest --hardware
```

## Test Structure Example

```python
"""Tests for module."""

import pytest
from module import Class

@pytest.fixture
def instance():
    """Create instance for testing."""
    return Class()

class TestFeature:
    """Test feature functionality."""
    
    def test_behavior(self, instance):
        """Test describes what it verifies."""
        # Arrange
        input_data = "test"
        
        # Act
        result = instance.method(input_data)
        
        # Assert
        assert result == "expected"
```

## Mocked Dependencies

All hardware dependencies are auto-mocked:
- `RPi.GPIO` - GPIO operations
- `spidev` - SPI communication  
- `pygame` - Display rendering
- `pyaudio` - Audio I/O
- `opuslib` - OPUS encoding
- `numpy` - Array operations

## Coverage Targets

| Module | Target |
|--------|--------|
| state_machine | 95% |
| ws_client | 95% |
| turn_logger | 95% |
| audio | 85% |
| config | 100% |

## CI/CD

```yaml
- run: pip install -r requirements.txt
- run: pytest --cov=. --cov-report=xml
```

## Markers

- `@pytest.mark.unit` - Unit test
- `@pytest.mark.integration` - Integration test
- `@pytest.mark.hardware` - Requires hardware
- `@pytest.mark.slow` - Slow test

## Troubleshooting

**Import errors?**
```bash
cd aimon-frontend  # Run from correct directory
pytest
```

**Mocks not working?**
```bash
pytest --setup-show  # Verify conftest.py loaded
```

**Coverage not working?**
```bash
pip install pytest-cov
```

## Files Created

```
aimon-frontend/
├── pytest.ini                    # Pytest configuration
├── requirements.txt              # Updated with test deps
├── run_tests.sh                  # Linux/macOS runner
├── run_tests.ps1                 # Windows runner
└── tests/
    ├── __init__.py
    ├── conftest.py               # Shared fixtures/mocks
    ├── README.md                 # Full documentation
    ├── .gitignore                # Test artifacts
    ├── test_state_machine.py     # 45+ tests
    ├── test_ws_client.py         # 35+ tests
    ├── test_turn_logger.py       # 25+ tests
    ├── test_audio.py             # 20+ tests
    └── test_config.py            # 15+ tests
```

**Total:** 140+ tests, 1,700+ lines, ≥90% coverage

---
**Created:** February 15, 2026

# AI-MON Frontend Test Suite

Comprehensive unit tests for the AI-MON frontend Python modules.

## Overview

This test suite provides 100+ unit tests covering:
- State machine transitions and logic
- WebSocket communication protocol
- Audio capture and playback
- Turn logging and database operations
- Configuration management

## Running Tests

### Run All Tests

```bash
pytest
```

### Run Specific Test File

```bash
pytest tests/test_state_machine.py
pytest tests/test_ws_client.py
pytest tests/test_turn_logger.py
pytest tests/test_audio.py
pytest tests/test_config.py
```

### Run Specific Test Class

```bash
pytest tests/test_state_machine.py::TestStateTransitions
```

### Run Specific Test

```bash
pytest tests/test_state_machine.py::TestStateTransitions::test_idle_to_listening_on_button_press
```

### Run with Coverage

```bash
pytest --cov=. --cov-report=html
```

View coverage report:
```bash
open htmlcov/index.html  # On macOS
xdg-open htmlcov/index.html  # On Linux
start htmlcov/index.html  # On Windows
```

### Run Only Fast Tests

```bash
pytest -m "not slow"
```

### Run with Verbose Output

```bash
pytest -v -s
```

## Test Structure

```
tests/
├── __init__.py                 # Test package marker
├── conftest.py                 # Shared fixtures and mocks
├── test_state_machine.py       # State machine tests (45+ tests)
├── test_ws_client.py           # WebSocket client tests (35+ tests)
├── test_turn_logger.py         # Turn logger tests (25+ tests)
├── test_audio.py               # Audio capture/playback tests (20+ tests)
└── test_config.py              # Configuration tests (15+ tests)
```

## Test Coverage

Target: **≥ 90% code coverage**

Current coverage (as designed):
- State machine: ~95%
- WebSocket client: ~95%
- Turn logger: ~95%
- Audio modules: ~85% (hardware-dependent code mocked)
- Configuration: ~100%

## Mocking Strategy

All hardware dependencies are automatically mocked via `conftest.py`:
- `RPi.GPIO` - GPIO operations
- `spidev` - SPI communication
- `pygame` - Display rendering
- `pyaudio` - Audio I/O
- `opuslib` - OPUS encoding
- `numpy` - Array operations

This allows tests to run on any system without Raspberry Pi hardware.

## Test Markers

Use markers to categorize tests:

```python
@pytest.mark.unit          # Unit test (default)
@pytest.mark.integration   # Integration test
@pytest.mark.hardware      # Requires real hardware
@pytest.mark.slow          # Slow-running test
```

Run hardware tests (if on Raspberry Pi):
```bash
pytest --hardware
```

## CI/CD Integration

### GitHub Actions

```yaml
- name: Install dependencies
  run: pip install -r requirements.txt

- name: Run tests
  run: pytest --cov=. --cov-report=xml

- name: Upload coverage
  uses: codecov/codecov-action@v3
```

## Writing New Tests

### Test Template

```python
"""Tests for new_module."""

import pytest
from unittest.mock import Mock, patch
from new_module import NewClass


@pytest.fixture
def instance():
    """Create instance for testing."""
    return NewClass()


class TestNewFeature:
    """Test new feature functionality."""
    
    def test_basic_behavior(self, instance):
        """Test should describe what it verifies."""
        # Arrange
        input_data = "test"
        
        # Act
        result = instance.process(input_data)
        
        # Assert
        assert result == "expected"
```

### Best Practices

1. **Follow AAA pattern**: Arrange, Act, Assert
2. **One assertion per test** (when possible)
3. **Descriptive test names**: `test_<what>_<when>_<expected>`
4. **Use fixtures** for common setup
5. **Mock external dependencies** (filesystem, network, hardware)
6. **Test edge cases** (empty input, None, errors)
7. **Keep tests isolated** (no shared mutable state)

## Debugging Tests

### Run Single Test with Print Statements

```bash
pytest tests/test_state_machine.py::test_name -s
```

### Drop into Debugger on Failure

```bash
pytest --pdb
```

### Show Local Variables on Failure

```bash
pytest -l
```

## Common Issues

### Import Errors

If you see `ModuleNotFoundError`, ensure you're running pytest from the `aimon-frontend` directory:

```bash
cd aimon-frontend
pytest
```

### Hardware Mock Issues

If hardware mocks aren't working, check that `conftest.py` is being loaded:

```bash
pytest --setup-show
```

### Coverage Not Working

Ensure pytest-cov is installed:

```bash
pip install pytest-cov
```

## Test Maintenance

- Update tests when adding new features
- Run full test suite before commits
- Keep coverage above 90%
- Remove obsolete tests
- Update mocks when dependencies change

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest-cov Documentation](https://pytest-cov.readthedocs.io/)
- [Testing Best Practices](https://docs.python-guide.org/writing/tests/)

## Contributing

When adding new modules:
1. Create corresponding test file: `test_<module_name>.py`
2. Add tests for all public functions/methods
3. Mock external dependencies
4. Ensure 90%+ coverage for new code
5. Run full test suite: `pytest`
6. Check coverage: `pytest --cov=.`

---

**Last Updated:** February 15, 2026

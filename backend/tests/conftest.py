"""Test configuration"""
import pytest


@pytest.fixture(autouse=True)
def reset_state():
    """Reset global state between tests"""
    # Clear rate limit state
    try:
        from backend.rate_limit import _rate_limits
        _rate_limits.clear()
    except ImportError:
        pass
    
    # Clear auth sessions
    try:
        from backend.auth import _sessions
        _sessions.clear()
    except ImportError:
        pass
    
    yield
    
    # Cleanup after test
    try:
        from backend.rate_limit import _rate_limits
        _rate_limits.clear()
    except ImportError:
        pass
    
    try:
        from backend.auth import _sessions
        _sessions.clear()
    except ImportError:
        pass

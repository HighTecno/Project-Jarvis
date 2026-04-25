"""Tests for authentication"""
import pytest
import tempfile
import os
from backend.auth import (
    generate_api_key,
    verify_api_key,
    create_session,
    verify_session,
)


def test_generate_api_key():
    """Test API key generation"""
    key1 = generate_api_key()
    key2 = generate_api_key()
    
    assert len(key1) > 20
    assert len(key2) > 20
    assert key1 != key2  # Should be unique


def test_verify_api_key():
    """Test API key verification"""
    # Create temp key file
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("test-key-123\n")
        f.write("test-key-456\n")
        temp_file = f.name
    
    try:
        # Monkey patch the keys file location
        import backend.auth as auth_module
        old_file = auth_module.API_KEYS_FILE
        auth_module.API_KEYS_FILE = temp_file
        
        # Valid key
        assert verify_api_key("test-key-123")
        assert verify_api_key("test-key-456")
        
        # Invalid key
        assert not verify_api_key("invalid-key")
        
        # Restore
        auth_module.API_KEYS_FILE = old_file
    finally:
        os.unlink(temp_file)


def test_session_lifecycle():
    """Test session creation and verification"""
    # Create session
    token = create_session("test-api-key")
    assert len(token) > 20
    
    # Verify valid session
    assert verify_session(token)
    
    # Verify invalid session
    assert not verify_session("invalid-token")

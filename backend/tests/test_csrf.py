"""Tests for CSRF protection"""
import pytest
import time
from backend.csrf import (
    generate_csrf_token,
    validate_csrf_token,
    _cleanup_expired_tokens,
    _csrf_tokens,
    get_token_info,
)
from fastapi import HTTPException


class TestCSRFProtection:
    def setup_method(self):
        """Clear token store before each test"""
        _csrf_tokens.clear()
    
    def test_generate_token(self):
        """Should generate a valid token"""
        token = generate_csrf_token()
        assert isinstance(token, str)
        assert len(token) > 0
        assert token in _csrf_tokens
    
    def test_tokens_are_unique(self):
        """Should generate unique tokens"""
        token1 = generate_csrf_token()
        token2 = generate_csrf_token()
        assert token1 != token2
    
    def test_token_has_expiry(self):
        """Generated tokens should have expiry timestamp"""
        token = generate_csrf_token()
        assert token in _csrf_tokens
        expiry = _csrf_tokens[token]
        assert expiry > time.time()
    
    def test_cleanup_expired_tokens(self):
        """Should remove expired tokens"""
        # Add some expired tokens
        _csrf_tokens["expired1"] = time.time() - 100
        _csrf_tokens["expired2"] = time.time() - 200
        _csrf_tokens["valid"] = time.time() + 1000
        
        _cleanup_expired_tokens()
        
        assert "expired1" not in _csrf_tokens
        assert "expired2" not in _csrf_tokens
        assert "valid" in _csrf_tokens
    
    def test_validate_valid_token(self):
        """Should accept valid token"""
        token = generate_csrf_token()
        
        # Should not raise exception
        result = validate_csrf_token(x_csrf_token=token)
        assert result is True
    
    def test_validate_missing_token(self):
        """Should reject missing token"""
        with pytest.raises(HTTPException) as exc_info:
            validate_csrf_token(x_csrf_token=None)
        
        assert exc_info.value.status_code == 403
        assert "missing" in exc_info.value.detail.lower()
    
    def test_validate_invalid_token(self):
        """Should reject invalid token"""
        with pytest.raises(HTTPException) as exc_info:
            validate_csrf_token(x_csrf_token="invalid_token_12345")
        
        assert exc_info.value.status_code == 403
        assert "invalid" in exc_info.value.detail.lower()
    
    def test_validate_expired_token(self):
        """Should reject expired token"""
        token = "test_token"
        _csrf_tokens[token] = time.time() - 100  # Expired
        
        with pytest.raises(HTTPException) as exc_info:
            validate_csrf_token(x_csrf_token=token)
        
        assert exc_info.value.status_code == 403
        assert "expired" in exc_info.value.detail.lower()
        
        # Token should be removed after validation attempt
        assert token not in _csrf_tokens
    
    def test_get_token_info(self):
        """Should return token store information"""
        generate_csrf_token()
        generate_csrf_token()
        
        info = get_token_info()
        assert info["active_tokens"] == 2
        assert info["max_tokens"] > 0
        assert info["token_expiry_seconds"] > 0
    
    def test_max_tokens_limit(self):
        """Should not exceed max tokens limit"""
        from backend.csrf import MAX_TOKENS
        
        # Try to generate more than max tokens
        for i in range(MAX_TOKENS + 10):
            generate_csrf_token()
        
        # Should clean up and stay within limit
        assert len(_csrf_tokens) <= MAX_TOKENS


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

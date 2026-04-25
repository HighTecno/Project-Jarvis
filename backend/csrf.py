"""CSRF (Cross-Site Request Forgery) protection middleware"""
import os
import secrets
import time
from typing import Dict, Optional
from fastapi import HTTPException, Header, status
from datetime import datetime, timedelta


# In-memory token store (in production, use Redis or database)
_csrf_tokens: Dict[str, float] = {}  # token -> expiry_timestamp
TOKEN_EXPIRY_SECONDS = 3600  # 1 hour
MAX_TOKENS = 10000  # Prevent memory exhaustion
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() == "true"


def generate_csrf_token() -> str:
    """Generate a new CSRF token"""
    token = secrets.token_urlsafe(32)
    expiry = time.time() + TOKEN_EXPIRY_SECONDS
    
    # Clean up old tokens if we're at the limit
    if len(_csrf_tokens) >= MAX_TOKENS:
        _cleanup_expired_tokens()
    
    _csrf_tokens[token] = expiry
    return token


def _cleanup_expired_tokens():
    """Remove expired tokens from the store"""
    current_time = time.time()
    expired_tokens = [
        token for token, expiry in _csrf_tokens.items()
        if expiry < current_time
    ]
    for token in expired_tokens:
        del _csrf_tokens[token]
    
    # If still at max, remove oldest tokens
    if len(_csrf_tokens) >= MAX_TOKENS:
        # Sort by expiry and remove oldest
        sorted_tokens = sorted(_csrf_tokens.items(), key=lambda x: x[1])
        tokens_to_remove = sorted_tokens[:len(sorted_tokens) - MAX_TOKENS + 100]
        for token, _ in tokens_to_remove:
            del _csrf_tokens[token]


def validate_csrf_token(
    x_csrf_token: Optional[str] = Header(None, alias="X-CSRF-Token")
) -> bool:
    """
    Validate CSRF token from request header.
    
    Args:
        x_csrf_token: CSRF token from X-CSRF-Token header
        
    Returns:
        bool: True if valid
        
    Raises:
        HTTPException: If token is missing or invalid
    """
    if not AUTH_ENABLED:
        return True

    if x_csrf_token is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token missing - include X-CSRF-Token header"
        )
    
    # Check if token exists
    expiry = _csrf_tokens.get(x_csrf_token)
    if expiry is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token"
        )
    
    # Check if expired
    current_time = time.time()
    if expiry < current_time:
        # Token expired - remove it
        del _csrf_tokens[x_csrf_token]
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF token expired"
        )
    
    # Clean up expired tokens periodically (after successful validation)
    _cleanup_expired_tokens()
    
    # Token is valid
    return True


def get_token_info() -> dict:
    """Get information about token store (for monitoring)"""
    _cleanup_expired_tokens()
    return {
        "active_tokens": len(_csrf_tokens),
        "max_tokens": MAX_TOKENS,
        "token_expiry_seconds": TOKEN_EXPIRY_SECONDS
    }

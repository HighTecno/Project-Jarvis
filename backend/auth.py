"""Authentication and authorization for Jarvis API"""
import os
import secrets
import hashlib
import threading
from typing import Optional
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials


# Security configuration
AUTH_ENABLED = os.getenv("AUTH_ENABLED", "true").lower() == "true"
API_KEYS_FILE = os.path.expanduser(os.getenv("API_KEYS_FILE", "~/.jarvis/api_keys.txt"))
SESSION_TIMEOUT_HOURS = int(os.getenv("SESSION_TIMEOUT_HOURS", "24"))

# In-memory session store (in production, use Redis)
_sessions = {}
_cleanup_thread = None
_cleanup_stop_event = threading.Event()

security = HTTPBearer(auto_error=False)


def _load_api_keys() -> set:
    """Load API keys from file"""
    if not os.path.exists(API_KEYS_FILE):
        return set()
    
    with open(API_KEYS_FILE, "r") as f:
        return {line.strip() for line in f if line.strip() and not line.startswith("#")}


def _hash_key(key: str) -> str:
    """Hash an API key for comparison"""
    return hashlib.sha256(key.encode()).hexdigest()


def generate_api_key() -> str:
    """Generate a new API key"""
    return secrets.token_urlsafe(32)


def verify_api_key(key: str) -> bool:
    """Verify an API key against stored keys using constant-time comparison"""
    if not AUTH_ENABLED:
        return True
    
    valid_keys = _load_api_keys()
    # Use constant-time comparison to prevent timing attacks
    return any(secrets.compare_digest(key, valid_key) for valid_key in valid_keys)


def create_session(api_key: str) -> str:
    """Create a new session token"""
    session_token = secrets.token_urlsafe(32)
    _sessions[session_token] = {
        "api_key": api_key,
        "created_at": datetime.now(timezone.utc),
        "last_used": datetime.now(timezone.utc),
    }
    return session_token


def verify_session(token: str) -> bool:
    """Verify a session token"""
    if not AUTH_ENABLED:
        return True
    
    if token not in _sessions:
        return False
    
    session = _sessions[token]
    age = datetime.now(timezone.utc) - session["created_at"]
    
    # Check if session expired
    if age > timedelta(hours=SESSION_TIMEOUT_HOURS):
        del _sessions[token]
        return False
    
    # Update last used
    session["last_used"] = datetime.now(timezone.utc)
    return True


def cleanup_expired_sessions():
    """Remove expired sessions"""
    if not AUTH_ENABLED:
        return
    
    now = datetime.now(timezone.utc)
    expired = [
        token for token, session in _sessions.items()
        if now - session["created_at"] > timedelta(hours=SESSION_TIMEOUT_HOURS)
    ]
    
    for token in expired:
        del _sessions[token]


async def verify_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security),
) -> bool:
    """
    Verify authentication credentials
    
    Raises:
        HTTPException: If authentication fails
    
    Returns:
        True if authenticated
    """
    if not AUTH_ENABLED:
        return True
    
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    # Try as API key first
    if verify_api_key(token):
        return True
    
    # Try as session token
    if verify_session(token):
        return True
    
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def init_auth():
    """Initialize authentication system"""
    if not AUTH_ENABLED:
        print("[AUTH] Authentication is DISABLED")
        return
    
    os.makedirs(os.path.dirname(API_KEYS_FILE), exist_ok=True)
    
    # Create default API key if file doesn't exist
    if not os.path.exists(API_KEYS_FILE):
        default_key = generate_api_key()
        with open(API_KEYS_FILE, "w") as f:
            f.write(f"# Jarvis API Keys\n")
            f.write(f"# Add one key per line\n")
            f.write(f"{default_key}\n")
        print(f"[AUTH] Created default API key: {default_key}")
        print(f"[AUTH] Keys stored in: {API_KEYS_FILE}")
    else:
        key_count = len(_load_api_keys())
        print(f"[AUTH] Loaded {key_count} API key(s) from {API_KEYS_FILE}")
    
    # Start background session cleanup
    start_cleanup_thread()


def _background_session_cleanup():
    """Background thread to periodically clean up expired sessions"""
    while not _cleanup_stop_event.wait(timeout=3600):  # Run every hour
        try:
            cleanup_expired_sessions()
        except Exception:
            # Silently continue on error to keep cleanup running
            pass


def start_cleanup_thread():
    """Start the background cleanup thread"""
    global _cleanup_thread
    if _cleanup_thread is None or not _cleanup_thread.is_alive():
        _cleanup_stop_event.clear()
        _cleanup_thread = threading.Thread(target=_background_session_cleanup, daemon=True)
        _cleanup_thread.start()


def stop_cleanup_thread():
    """Stop the background cleanup thread"""
    _cleanup_stop_event.set()
    if _cleanup_thread is not None:
        _cleanup_thread.join(timeout=5)

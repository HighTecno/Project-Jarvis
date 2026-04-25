"""Rate limiting for API endpoints using in-memory storage"""
import time
import os
import threading
from collections import defaultdict
from typing import Dict, Tuple, List
from fastapi import HTTPException, Request, status

# Configuration
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").lower() == "true"
RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "60"))  # requests per window
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW", "60"))  # window in seconds

# In-memory store: {client_id: [timestamps...]}
_rate_limits: Dict[str, List[float]] = defaultdict(list)
_lock = threading.Lock()
_cleanup_thread = None
_cleanup_stop_event = threading.Event()

def _get_client_id(request: Request) -> str:
    """Extract client identifier from request"""
    # Try to get from X-Forwarded-For header first (for proxied requests)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    # Fall back to direct client IP
    if request.client:
        return request.client.host
    
    # Last resort
    return "unknown"

async def check_rate_limit(request: Request) -> bool:
    """
    Check if request should be rate limited.
    Uses in-memory storage.
    
    Args:
        request: FastAPI request object
    
    Raises:
        HTTPException: If rate limit exceeded
    
    Returns:
        True if request is allowed
    """
    if not RATE_LIMIT_ENABLED:
        return True
    
    client_id = _get_client_id(request)
    current_time = time.time()
    window_start = current_time - RATE_LIMIT_WINDOW
    
    with _lock:
        # Clean up old timestamps for this client
        _rate_limits[client_id] = [ts for ts in _rate_limits[client_id] if ts > window_start]
        
        if len(_rate_limits[client_id]) >= RATE_LIMIT_REQUESTS:
            # Calculate retry-after time
            oldest_entry = _rate_limits[client_id][0]
            retry_after = max(1, int(RATE_LIMIT_WINDOW - (current_time - oldest_entry)))
            
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
                headers={"Retry-After": str(retry_after)},
            )
        
        # Add current request timestamp
        _rate_limits[client_id].append(current_time)
        
    return True

def get_rate_limit_status(request: Request) -> Tuple[int, int, int]:
    """
    Get current rate limit status for client
    
    Returns:
        Tuple of (requests_made, requests_remaining, window_reset_seconds)
    """
    if not RATE_LIMIT_ENABLED:
        return (0, RATE_LIMIT_REQUESTS, 0)
    
    client_id = _get_client_id(request)
    current_time = time.time()
    window_start = current_time - RATE_LIMIT_WINDOW
    
    with _lock:
        # Clean up old timestamps for this client
        _rate_limits[client_id] = [ts for ts in _rate_limits[client_id] if ts > window_start]
        
        requests_made = len(_rate_limits[client_id])
        remaining = max(0, RATE_LIMIT_REQUESTS - requests_made)
        
        # Calculate when window resets
        if _rate_limits[client_id]:
            oldest_entry = _rate_limits[client_id][0]
            reset_in = max(1, int(RATE_LIMIT_WINDOW - (current_time - oldest_entry)))
        else:
            reset_in = RATE_LIMIT_WINDOW
            
    return (requests_made, remaining, reset_in)

def _background_cleanup():
    """Background thread to periodically clean up expired rate limit entries"""
    while not _cleanup_stop_event.wait(timeout=RATE_LIMIT_WINDOW * 2):
        current_time = time.time()
        window_start = current_time - RATE_LIMIT_WINDOW
        
        with _lock:
            clients_to_remove = []
            for client_id in list(_rate_limits.keys()):
                _rate_limits[client_id] = [ts for ts in _rate_limits[client_id] if ts > window_start]
                if not _rate_limits[client_id]:
                    clients_to_remove.append(client_id)
            
            for client_id in clients_to_remove:
                _rate_limits.pop(client_id, None)

def start_cleanup_thread():
    """Start the background cleanup thread"""
    global _cleanup_thread
    if _cleanup_thread is None or not _cleanup_thread.is_alive():
        _cleanup_stop_event.clear()
        _cleanup_thread = threading.Thread(target=_background_cleanup, daemon=True)
        _cleanup_thread.start()

def stop_cleanup_thread():
    """Stop the background cleanup thread"""
    _cleanup_stop_event.set()
    if _cleanup_thread is not None:
        _cleanup_thread.join(timeout=5)

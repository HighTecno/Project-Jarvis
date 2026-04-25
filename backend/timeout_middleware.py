"""Request timeout middleware to prevent long-running requests"""
import asyncio
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.responses import JSONResponse

try:
    from backend.logger import get_logger
except ImportError:
    try:
        from logger import get_logger
    except ImportError:
        from .logger import get_logger

logger = get_logger("timeout")

# Default timeout (5 minutes)
DEFAULT_REQUEST_TIMEOUT = 300


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce request timeout"""
    
    def __init__(self, app, timeout: float = DEFAULT_REQUEST_TIMEOUT):
        super().__init__(app)
        self.timeout = timeout
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        try:
            # Wrap the request with timeout
            response = await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout
            )
            return response
            
        except asyncio.TimeoutError:
            logger.warning(
                f"Request timeout exceeded ({self.timeout}s)",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "timeout": self.timeout
                }
            )
            
            return JSONResponse(
                status_code=408,  # Request Timeout
                content={
                    "error": "Request timeout",
                    "message": f"Request exceeded timeout of {self.timeout} seconds",
                    "timeout_seconds": self.timeout
                }
            )

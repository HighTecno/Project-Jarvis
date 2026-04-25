"""Middleware for collecting HTTP metrics"""
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time

try:
    from backend.metrics import record_request_start, record_request_end
except ImportError:
    try:
        from metrics import record_request_start, record_request_end
    except ImportError:
        from .metrics import record_request_start, record_request_end


class MetricsMiddleware(BaseHTTPMiddleware):
    """Middleware to collect HTTP request metrics"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Record request start
        record_request_start()
        start_time = time.time()
        
        # Process request
        response = await call_next(request)
        
        # Calculate endpoint (simplified path without IDs)
        endpoint = request.url.path
        
        # Record request end
        record_request_end(
            method=request.method,
            endpoint=endpoint,
            status_code=response.status_code
        )
        
        # Add duration to response headers
        duration = time.time() - start_time
        response.headers['X-Response-Time'] = f"{duration:.3f}"
        
        return response

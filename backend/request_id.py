"""Request ID middleware for tracking requests across the system"""
import uuid
from typing import Callable, Optional
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from contextvars import ContextVar

# Context variables for distributed tracing
request_id_var: ContextVar[str] = ContextVar('request_id', default='')
correlation_id_var: ContextVar[str] = ContextVar('correlation_id', default='')
trace_id_var: ContextVar[str] = ContextVar('trace_id', default='')


def get_request_id() -> str:
    """Get the current request ID from context"""
    return request_id_var.get()


def get_correlation_id() -> str:
    """Get the current correlation ID from context"""
    return correlation_id_var.get()


def get_trace_id() -> str:
    """Get the current trace ID from context"""
    return trace_id_var.get()


def get_tracing_headers() -> dict:
    """Get all tracing headers for propagation to downstream services"""
    headers = {}
    
    request_id = get_request_id()
    if request_id:
        headers['X-Request-ID'] = request_id
    
    correlation_id = get_correlation_id()
    if correlation_id:
        headers['X-Correlation-ID'] = correlation_id
    
    trace_id = get_trace_id()
    if trace_id:
        headers['X-Trace-ID'] = trace_id
    
    return headers


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware to add request ID and distributed tracing headers"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Get or generate request ID (unique per request)
        request_id = request.headers.get('X-Request-ID')
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # Get or generate correlation ID (groups related requests)
        correlation_id = request.headers.get('X-Correlation-ID')
        if not correlation_id:
            correlation_id = request_id  # Use request ID as correlation ID if not provided
        
        # Get or generate trace ID (for distributed tracing systems like Jaeger/Zipkin)
        trace_id = request.headers.get('X-Trace-ID')
        if not trace_id:
            trace_id = str(uuid.uuid4())
        
        # Store in context variables for access in route handlers
        request_id_var.set(request_id)
        correlation_id_var.set(correlation_id)
        trace_id_var.set(trace_id)
        
        # Add to request state for easy access
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id
        request.state.trace_id = trace_id
        
        # Process request
        response = await call_next(request)
        
        # Add tracing headers to response
        response.headers['X-Request-ID'] = request_id
        response.headers['X-Correlation-ID'] = correlation_id
        response.headers['X-Trace-ID'] = trace_id
        
        return response

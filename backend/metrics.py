"""Prometheus metrics for monitoring Jarvis"""
import time
from typing import Dict, Optional
from prometheus_client import Counter, Histogram, Gauge, generate_latest, REGISTRY, CollectorRegistry
from prometheus_client.exposition import CONTENT_TYPE_LATEST
from fastapi import Response
from contextvars import ContextVar

# Use default registry
_registry = REGISTRY

# Request metrics
http_requests_total = Counter(
    'jarvis_http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status'],
    registry=_registry
)

http_request_duration_seconds = Histogram(
    'jarvis_http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=_registry
)

# Agent/LLM metrics
agent_requests_total = Counter(
    'jarvis_agent_requests_total',
    'Total agent requests',
    ['status'],
    registry=_registry
)

agent_duration_seconds = Histogram(
    'jarvis_agent_duration_seconds',
    'Agent request duration in seconds',
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0),
    registry=_registry
)

llm_requests_total = Counter(
    'jarvis_llm_requests_total',
    'Total LLM API calls',
    ['status'],
    registry=_registry
)

llm_duration_seconds = Histogram(
    'jarvis_llm_duration_seconds',
    'LLM API call duration in seconds',
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    registry=_registry
)

# Tool execution metrics
tool_executions_total = Counter(
    'jarvis_tool_executions_total',
    'Total tool executions',
    ['tool_name', 'status'],
    registry=_registry
)

tool_duration_seconds = Histogram(
    'jarvis_tool_duration_seconds',
    'Tool execution duration in seconds',
    ['tool_name'],
    buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0),
    registry=_registry
)

# System metrics
active_requests = Gauge(
    'jarvis_active_requests',
    'Number of currently active requests',
    registry=_registry
)

# Authentication metrics
auth_attempts_total = Counter(
    'jarvis_auth_attempts_total',
    'Total authentication attempts',
    ['status'],
    registry=_registry
)

# Rate limiting metrics
rate_limit_exceeded_total = Counter(
    'jarvis_rate_limit_exceeded_total',
    'Total rate limit exceeded events',
    registry=_registry
)

# Context variable for tracking request start time
request_start_time: ContextVar[Optional[float]] = ContextVar('request_start_time', default=None)


def record_request_start():
    """Record the start time of a request"""
    request_start_time.set(time.time())
    active_requests.inc()


def record_request_end(method: str, endpoint: str, status_code: int):
    """Record the end of a request and calculate duration"""
    start_time = request_start_time.get()
    if start_time:
        duration = time.time() - start_time
        http_request_duration_seconds.labels(method=method, endpoint=endpoint).observe(duration)
    
    http_requests_total.labels(method=method, endpoint=endpoint, status=status_code).inc()
    active_requests.dec()


def record_agent_request(duration: float, status: str = 'success'):
    """Record an agent request"""
    agent_requests_total.labels(status=status).inc()
    agent_duration_seconds.observe(duration)


def record_llm_call(duration: float, status: str = 'success'):
    """Record an LLM API call"""
    llm_requests_total.labels(status=status).inc()
    llm_duration_seconds.observe(duration)


def record_tool_execution(tool_name: str, duration: float, status: str = 'success'):
    """Record a tool execution"""
    tool_executions_total.labels(tool_name=tool_name, status=status).inc()
    tool_duration_seconds.labels(tool_name=tool_name).observe(duration)


def record_auth_attempt(status: str):
    """Record an authentication attempt"""
    auth_attempts_total.labels(status=status).inc()


def record_rate_limit_exceeded():
    """Record a rate limit exceeded event"""
    rate_limit_exceeded_total.inc()


def get_metrics() -> Response:
    """Generate Prometheus metrics response"""
    metrics_data = generate_latest(_registry)
    return Response(content=metrics_data, media_type=CONTENT_TYPE_LATEST)


def get_metrics_summary() -> Dict:
    """Get a summary of key metrics for health checks"""
    return {
        "active_requests": active_requests._value.get(),
        "total_requests": sum(
            sample.value for family in _registry.collect()
            if family.name == 'jarvis_http_requests_total'
            for sample in family.samples
        ),
        "total_agent_requests": sum(
            sample.value for family in _registry.collect()
            if family.name == 'jarvis_agent_requests_total'
            for sample in family.samples
        )
    }

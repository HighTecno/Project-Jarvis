"""Structured logging configuration for Jarvis"""
import logging
import sys
import json
from datetime import datetime
from typing import Any, Dict


def _get_tracing_context() -> Dict[str, str]:
    """Get current tracing context (request_id, correlation_id, trace_id) if available"""
    context = {}
    try:
        from backend.request_id import get_request_id, get_correlation_id, get_trace_id
        request_id = get_request_id()
        correlation_id = get_correlation_id()
        trace_id = get_trace_id()
    except (ImportError, LookupError):
        try:
            from request_id import get_request_id, get_correlation_id, get_trace_id
            request_id = get_request_id()
            correlation_id = get_correlation_id()
            trace_id = get_trace_id()
        except (ImportError, LookupError):
            return context
    
    if request_id:
        context["request_id"] = request_id
    if correlation_id:
        context["correlation_id"] = correlation_id
    if trace_id:
        context["trace_id"] = trace_id
    
    return context


class JSONFormatter(logging.Formatter):
    """Format logs as JSON for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add tracing context if available
        tracing_context = _get_tracing_context()
        if tracing_context:
            log_data.update(tracing_context)
        
        # Add exception info if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        if hasattr(record, "extra_fields"):
            log_data.update(record.extra_fields)
        
        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(level: str = "INFO", json_format: bool = True) -> logging.Logger:
    """
    Configure root logger with structured output
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_format: Use JSON formatter if True, otherwise use simple format
    
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger("jarvis")
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    logger.handlers.clear()
    
    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper()))
    
    # Set formatter
    if json_format:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
    
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with the given name"""
    return logging.getLogger(f"jarvis.{name}")


class LogContext:
    """Context manager for adding extra fields to log records"""
    
    def __init__(self, logger: logging.Logger, **fields):
        self.logger = logger
        self.fields = fields
        self.old_factory = None
    
    def __enter__(self):
        self.old_factory = logging.getLogRecordFactory()
        
        def record_factory(*args, **kwargs):
            record = self.old_factory(*args, **kwargs)
            if not hasattr(record, "extra_fields"):
                record.extra_fields = {}
            record.extra_fields.update(self.fields)
            return record
        
        logging.setLogRecordFactory(record_factory)
        return self
    
    def __exit__(self, *args):
        logging.setLogRecordFactory(self.old_factory)

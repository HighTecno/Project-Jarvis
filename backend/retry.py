"""Retry logic with exponential backoff for transient failures"""
import time
import functools
from typing import Callable, TypeVar, Any, Tuple, Type
import logging

try:
    from backend.logger import get_logger
except ImportError:
    try:
        from logger import get_logger
    except ImportError:
        from .logger import get_logger

logger = get_logger("retry")

T = TypeVar('T')

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 1.0  # seconds
DEFAULT_MAX_DELAY = 60.0  # seconds
DEFAULT_BACKOFF_FACTOR = 2.0

# Exceptions that should trigger retries (transient failures)
RETRIABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,
)


def exponential_backoff(attempt: int, base_delay: float, max_delay: float, backoff_factor: float) -> float:
    """
    Calculate exponential backoff delay.
    
    Args:
        attempt: Current attempt number (0-indexed)
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        backoff_factor: Backoff multiplier
    
    Returns:
        Delay in seconds
    """
    delay = base_delay * (backoff_factor ** attempt)
    return min(delay, max_delay)


def retry_with_backoff(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    retriable_exceptions: Tuple[Type[Exception], ...] = RETRIABLE_EXCEPTIONS,
    on_retry: Callable[[Exception, int, float], None] = None
):
    """
    Decorator for retrying a function with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        base_delay: Base delay between retries in seconds
        max_delay: Maximum delay between retries in seconds
        backoff_factor: Factor to multiply delay by on each retry
        retriable_exceptions: Tuple of exception types that should trigger retries
        on_retry: Optional callback function called on each retry attempt
    
    Example:
        @retry_with_backoff(max_retries=3, base_delay=1.0)
        def call_api():
            # code that might fail transiently
            pass
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    
                    # Log successful retry
                    if attempt > 0:
                        logger.info(
                            f"Function {func.__name__} succeeded after {attempt} retries",
                            extra={"function": func.__name__, "attempts": attempt}
                        )
                    
                    return result
                    
                except retriable_exceptions as e:
                    last_exception = e
                    
                    # If this was the last attempt, raise the exception
                    if attempt >= max_retries:
                        logger.error(
                            f"Function {func.__name__} failed after {max_retries} retries",
                            extra={
                                "function": func.__name__,
                                "max_retries": max_retries,
                                "error": str(e)
                            }
                        )
                        raise
                    
                    # Calculate delay and wait
                    delay = exponential_backoff(attempt, base_delay, max_delay, backoff_factor)
                    
                    logger.warning(
                        f"Function {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay:.2f}s",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt + 1,
                            "max_attempts": max_retries + 1,
                            "delay": delay,
                            "error": str(e)
                        }
                    )
                    
                    # Call retry callback if provided
                    if on_retry:
                        try:
                            on_retry(e, attempt, delay)
                        except Exception as callback_error:
                            logger.warning(
                                f"Retry callback failed: {callback_error}",
                                extra={"error": str(callback_error)}
                            )
                    
                    time.sleep(delay)
            
            # This should never be reached, but just in case
            if last_exception:
                raise last_exception
            
        return wrapper
    return decorator


async def async_retry_with_backoff(
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
    backoff_factor: float = DEFAULT_BACKOFF_FACTOR,
    retriable_exceptions: Tuple[Type[Exception], ...] = RETRIABLE_EXCEPTIONS
):
    """
    Async version of retry_with_backoff decorator.
    
    Use this for async functions.
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    result = await func(*args, **kwargs)
                    
                    if attempt > 0:
                        logger.info(
                            f"Async function {func.__name__} succeeded after {attempt} retries",
                            extra={"function": func.__name__, "attempts": attempt}
                        )
                    
                    return result
                    
                except retriable_exceptions as e:
                    last_exception = e
                    
                    if attempt >= max_retries:
                        logger.error(
                            f"Async function {func.__name__} failed after {max_retries} retries",
                            extra={
                                "function": func.__name__,
                                "max_retries": max_retries,
                                "error": str(e)
                            }
                        )
                        raise
                    
                    delay = exponential_backoff(attempt, base_delay, max_delay, backoff_factor)
                    
                    logger.warning(
                        f"Async function {func.__name__} failed (attempt {attempt + 1}/{max_retries + 1}), "
                        f"retrying in {delay:.2f}s",
                        extra={
                            "function": func.__name__,
                            "attempt": attempt + 1,
                            "delay": delay,
                            "error": str(e)
                        }
                    )
                    
                    import asyncio
                    await asyncio.sleep(delay)
            
            if last_exception:
                raise last_exception
            
        return wrapper
    return decorator

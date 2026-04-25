"""Circuit breaker pattern for preventing cascading failures"""
import time
import threading
from enum import Enum
from typing import Callable, TypeVar, Any
from dataclasses import dataclass

try:
    from backend.logger import get_logger
except ImportError:
    try:
        from logger import get_logger
    except ImportError:
        from .logger import get_logger

logger = get_logger("circuit_breaker")

T = TypeVar('T')


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Circuit is open, requests fail fast
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker"""
    failure_threshold: int = 5  # Number of failures before opening circuit
    recovery_timeout: float = 30.0  # Seconds to wait before trying half-open
    success_threshold: int = 2  # Successful calls in half-open before closing
    timeout: float = 10.0  # Request timeout in seconds


class CircuitBreakerError(Exception):
    """Exception raised when circuit breaker is open"""
    pass


class CircuitBreaker:
    """
    Circuit breaker implementation to prevent cascading failures.
    
    States:
    - CLOSED: Normal operation, requests pass through
    - OPEN: Too many failures, requests fail immediately  
    - HALF_OPEN: Testing if service recovered, limited requests allowed
    
    Example:
        breaker = CircuitBreaker(name="ollama_api")
        
        def call_api():
            with breaker:
                return make_api_call()
    """
    
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None
        self.lock = threading.Lock()
    
    def _should_attempt_reset(self) -> bool:
        """Check if we should attempt to reset from OPEN to HALF_OPEN"""
        if self.state != CircuitState.OPEN:
            return False
        
        if self.last_failure_time is None:
            return False
        
        elapsed = time.time() - self.last_failure_time
        return elapsed >= self.config.recovery_timeout
    
    def _record_success(self):
        """Record a successful call"""
        with self.lock:
            self.failure_count = 0
            
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                logger.info(
                    f"Circuit breaker '{self.name}': success in HALF_OPEN state "
                    f"({self.success_count}/{self.config.success_threshold})",
                    extra={"circuit": self.name, "success_count": self.success_count}
                )
                
                if self.success_count >= self.config.success_threshold:
                    self._transition_to_closed()
            elif self.state == CircuitState.OPEN:
                # Should not happen, but handle gracefully
                self._transition_to_half_open()
    
    def _record_failure(self):
        """Record a failed call"""
        with self.lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            
            if self.state == CircuitState.HALF_OPEN:
                logger.warning(
                    f"Circuit breaker '{self.name}': failure in HALF_OPEN state, reopening circuit",
                    extra={"circuit": self.name}
                )
                self._transition_to_open()
            
            elif self.state == CircuitState.CLOSED:
                logger.warning(
                    f"Circuit breaker '{self.name}': failure count {self.failure_count}/{self.config.failure_threshold}",
                    extra={"circuit": self.name, "failure_count": self.failure_count}
                )
                
                if self.failure_count >= self.config.failure_threshold:
                    self._transition_to_open()
    
    def _transition_to_open(self):
        """Transition to OPEN state"""
        self.state = CircuitState.OPEN
        self.success_count = 0
        logger.error(
            f"Circuit breaker '{self.name}': OPENED after {self.failure_count} failures",
            extra={
                "circuit": self.name,
                "state": "OPEN",
                "failure_count": self.failure_count
            }
        )
    
    def _transition_to_half_open(self):
        """Transition to HALF_OPEN state"""
        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
        self.failure_count = 0
        logger.info(
            f"Circuit breaker '{self.name}': entering HALF_OPEN state for testing",
            extra={"circuit": self.name, "state": "HALF_OPEN"}
        )
    
    def _transition_to_closed(self):
        """Transition to CLOSED state"""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        logger.info(
            f"Circuit breaker '{self.name}': CLOSED, service recovered",
            extra={"circuit": self.name, "state": "CLOSED"}
        )
    
    def call(self, func: Callable[..., T], *args, **kwargs) -> T:
        """
        Execute a function with circuit breaker protection.
        
        Args:
            func: Function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func
        
        Returns:
            Result of func
        
        Raises:
            CircuitBreakerError: If circuit is open
        """
        # Check if we should attempt reset
        if self._should_attempt_reset():
            self._transition_to_half_open()
        
        # Check current state
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is OPEN. "
                f"Service unavailable, will retry in {self.config.recovery_timeout}s"
            )
        
        # Execute function
        try:
            result = func(*args, **kwargs)
            self._record_success()
            return result
        except Exception as e:
            self._record_failure()
            raise
    
    def __enter__(self):
        """Context manager entry"""
        if self._should_attempt_reset():
            self._transition_to_half_open()
        
        if self.state == CircuitState.OPEN:
            raise CircuitBreakerError(
                f"Circuit breaker '{self.name}' is OPEN"
            )
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if exc_type is None:
            self._record_success()
        else:
            self._record_failure()
        return False
    
    def get_state(self) -> dict:
        """Get current circuit breaker state"""
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time
        }


# Global circuit breaker for LLM calls
llm_circuit_breaker = CircuitBreaker(
    name="llm_api",
    config=CircuitBreakerConfig(
        failure_threshold=5,
        recovery_timeout=30.0,
        success_threshold=2
    )
)

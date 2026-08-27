import time
from enum import Enum
from typing import Optional, Callable, Any
from fastapi import HTTPException, status


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenException(HTTPException):
    def __init__(self, message: str = "Service is temporarily experiencing technical difficulties; your request will not be retried synchronously to prevent duplicate actions."):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=message
        )


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        rolling_window_seconds: float = 30.0,
        cooldown_seconds: float = 60.0
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.rolling_window_seconds = rolling_window_seconds
        self.cooldown_seconds = cooldown_seconds
        self.state: CircuitState = CircuitState.CLOSED
        self.consecutive_failures: int = 0
        self.failure_timestamps: list[float] = []
        self.last_state_change: float = time.time()
        self.half_open_probe_in_flight: bool = False

    def can_execute(self) -> bool:
        now = time.time()
        if self.state == CircuitState.OPEN:
            if (now - self.last_state_change) >= self.cooldown_seconds:
                self.state = CircuitState.HALF_OPEN
                self.last_state_change = now
                self.half_open_probe_in_flight = True
                return True
            return False
        elif self.state == CircuitState.HALF_OPEN:
            if not self.half_open_probe_in_flight:
                self.half_open_probe_in_flight = True
                return True
            return False
        return True

    def record_success(self):
        self.consecutive_failures = 0
        self.failure_timestamps.clear()
        if self.state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
            self.state = CircuitState.CLOSED
            self.last_state_change = time.time()
        self.half_open_probe_in_flight = False

    def record_failure(self):
        now = time.time()
        self.consecutive_failures += 1
        self.failure_timestamps.append(now)
        self.half_open_probe_in_flight = False

        # Clean timestamps older than rolling window
        self.failure_timestamps = [
            t for t in self.failure_timestamps if (now - t) <= self.rolling_window_seconds
        ]

        if self.state == CircuitState.HALF_OPEN:
            # Probe failed, trip back to OPEN
            self.state = CircuitState.OPEN
            self.last_state_change = now
        elif self.state == CircuitState.CLOSED:
            if self.consecutive_failures >= self.failure_threshold or len(self.failure_timestamps) >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.last_state_change = now

    def reset(self):
        self.state = CircuitState.CLOSED
        self.consecutive_failures = 0
        self.failure_timestamps.clear()
        self.last_state_change = time.time()
        self.half_open_probe_in_flight = False


workweek_breaker = CircuitBreaker("workweek_hcm")
itsm_breaker = CircuitBreaker("serviceimmediately_itsm")

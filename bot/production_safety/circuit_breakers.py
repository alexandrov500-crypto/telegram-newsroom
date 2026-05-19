from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class BreakerState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


@dataclass
class CircuitBreaker:
    name: str
    failure_threshold: int = 5
    recovery_sec: float = 120.0
    state: BreakerState = BreakerState.CLOSED
    failures: int = 0
    opened_at: float = 0.0

    def record_success(self) -> None:
        self.failures = 0
        if self.state == BreakerState.HALF_OPEN:
            self.state = BreakerState.CLOSED
            logger.info("event=circuit_breaker_closed name=%s", self.name)

    def record_failure(self) -> None:
        self.failures += 1
        if self.failures >= self.failure_threshold and self.state == BreakerState.CLOSED:
            self.state = BreakerState.OPEN
            self.opened_at = time.monotonic()
            logger.warning("event=circuit_breaker_open name=%s failures=%d", self.name, self.failures)

    def allow_request(self) -> bool:
        if self.state == BreakerState.CLOSED:
            return True
        if self.state == BreakerState.OPEN:
            if time.monotonic() - self.opened_at >= self.recovery_sec:
                self.state = BreakerState.HALF_OPEN
                return True
            return False
        return True


@dataclass
class CircuitBreakerRegistry:
    """Unified breakers for OpenAI, Telegram, RSS."""

    openai: CircuitBreaker = field(default_factory=lambda: CircuitBreaker("openai", 8, 180.0))
    telegram: CircuitBreaker = field(default_factory=lambda: CircuitBreaker("telegram", 10, 90.0))
    rss: CircuitBreaker = field(default_factory=lambda: CircuitBreaker("rss", 15, 300.0))

    def snapshot(self) -> dict[str, str]:
        return {
            "openai": self.openai.state.value,
            "telegram": self.telegram.state.value,
            "rss": self.rss.state.value,
        }

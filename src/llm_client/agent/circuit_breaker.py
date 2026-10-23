"""Per-provider circuit breaker (ADR-015 Phase 3).

Reads Prometheus llm_error_rate_5m gauge (updated by background
task from real Prometheus scrape). When error rate > threshold →
breaker open, LLMRouter falls back to alternative provider.

Architecture: ARCHITECT.md v1.3.0 §5.2.3.
TRIZ: Standard 5.1.1 (Prometheus as external substance);
principle #16 (partial/excessive — partial fallback 30%).
"""
import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum

from ..config import settings

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"  # normal operation
    OPEN = "open"      # circuit breaker tripped, fallback
    HALF_OPEN = "half_open"  # trial period after open


@dataclass
class CircuitStatus:
    provider: str
    state: CircuitState
    error_rate_5m: float
    last_state_change: float  # unix timestamp
    consecutive_trial_successes: int


class CircuitBreaker:
    """Per-provider circuit breaker. State machine: CLOSED → OPEN
    (on error_rate > threshold) → HALF_OPEN (after cooldown) →
    CLOSED (if trial succeeds)."""

    COOLDOWN_SECONDS = 60  # 1 min cooldown before HALF_OPEN
    TRIAL_SUCCESS_THRESHOLD = 3  # 3 successful calls in HALF_OPEN → CLOSED

    def __init__(self, error_threshold: float | None = None) -> None:
        self._states: dict[str, CircuitStatus] = {}
        self._lock = asyncio.Lock()
        self._error_threshold = error_threshold or settings.llm_circuit_breaker_error_threshold

    async def check(self, provider: str) -> CircuitStatus:
        """Returns current CircuitStatus for provider. Updates state
        based on Prometheus gauge."""
        async with self._lock:
            now = time.time()
            status = self._states.get(provider)
            if status is None:
                status = CircuitStatus(
                    provider=provider,
                    state=CircuitState.CLOSED,
                    error_rate_5m=0.0,
                    last_state_change=now,
                    consecutive_trial_successes=0,
                )
                self._states[provider] = status

            # Read current error rate from in-process gauge
            current_error_rate = await self._read_error_rate(provider)
            status.error_rate_5m = current_error_rate

            # State transitions
            if status.state == CircuitState.CLOSED:
                if current_error_rate >= self._error_threshold:
                    status.state = CircuitState.OPEN
                    status.last_state_change = now
                    logger.warning(
                        "Circuit OPEN for provider %s (error rate %.1f%%)",
                        provider, current_error_rate * 100,
                    )
            elif status.state == CircuitState.OPEN:
                if now - status.last_state_change > self.COOLDOWN_SECONDS:
                    status.state = CircuitState.HALF_OPEN
                    status.last_state_change = now
                    logger.info(
                        "Circuit HALF_OPEN for provider %s (cooldown elapsed)",
                        provider,
                    )
            elif status.state == CircuitState.HALF_OPEN and status.consecutive_trial_successes >= self.TRIAL_SUCCESS_THRESHOLD:
                    status.state = CircuitState.CLOSED
                    status.consecutive_trial_successes = 0
                    status.last_state_change = now
                    logger.info(
                        "Circuit CLOSED for provider %s (trial succeeded)",
                        provider,
                    )

            return status

    async def record_success(self, provider: str) -> None:
        """Called after successful LLM call."""
        async with self._lock:
            status = self._states.get(provider)
            if status and status.state == CircuitState.HALF_OPEN:
                status.consecutive_trial_successes += 1

    async def record_failure(self, provider: str) -> None:
        """Called after failed LLM call."""
        async with self._lock:
            status = self._states.get(provider)
            if status:
                status.consecutive_trial_successes = 0  # reset on failure
                if status.state == CircuitState.HALF_OPEN:
                    status.state = CircuitState.OPEN
                    status.last_state_change = time.time()
                    logger.warning(
                        "Circuit re-OPEN for provider %s (trial failed)",
                        provider,
                    )

    async def _read_error_rate(self, provider: str) -> float:
        """Read llm_error_rate_5m{provider} from in-process gauge."""
        try:
            from ..observability.llm_metrics import LLM_ERROR_RATE
            return float(LLM_ERROR_RATE.labels(provider=provider)._value.get())
        except (AttributeError, RuntimeError, KeyError, TypeError):
            logger.warning("Failed to read Prometheus gauge")
            return 0.0


_breaker: CircuitBreaker | None = None


def get_circuit_breaker(error_threshold: float | None = None) -> CircuitBreaker:
    """Get singleton CircuitBreaker instance."""
    global _breaker
    if _breaker is None:
        _breaker = CircuitBreaker(error_threshold)
    return _breaker
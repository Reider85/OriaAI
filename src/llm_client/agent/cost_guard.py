"""Monthly cost guard (ADR-015 Phase 3).

Wraps LLMRouter budget tracking. At 80% threshold, auto-switches
to cheapest model (Блок C-2). Exposes usage to Prometheus.

Architecture: ARCHITECT.md v1.3.0 §5.2.3.
TRIZ: principle #23 (feedback — real-time cost metering);
Standard 5.1.1 (Prometheus gauge).
"""

import logging
from datetime import UTC, datetime

from ..config import settings
from ..observability.llm_metrics import update_budget_usage
from .router import LLMRouter, get_llm_router

logger = logging.getLogger(__name__)


class CostGuard:
    """Monthly budget enforcement."""

    def __init__(self, router: LLMRouter) -> None:
        self._router = router
        self._month_start = datetime.now(UTC).replace(
            day=1,
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )

    async def record_spend(self, cost_usd: float) -> bool:
        """Record a LLM call cost. Returns True if cost guard
        triggered (>=80% budget)."""
        await self._router.record_cost(cost_usd)
        budget_ratio = (
            self._router._spent_usd / self._router._budget if self._router._budget > 0 else 0.0
        )
        update_budget_usage(self._router._spent_usd, self._router._budget)

        # Use settings threshold instead of hardcoded 0.8
        threshold = settings.llm_router_cost_guard_threshold
        if budget_ratio >= threshold and budget_ratio - cost_usd / self._router._budget < threshold:
            logger.warning(
                "Cost guard triggered at %.1f%% — switching to cheapest model",
                budget_ratio * 100,
            )
            # The LLMRouter.route() will automatically pick cheapest
            # from now on (verified in C-2 test).
            return True
        return False

    def is_over_budget(self) -> bool:
        """Returns True if monthly spend >= 100% budget."""
        return self._router._spent_usd >= self._router._budget

    def remaining_budget(self) -> float:
        """Returns remaining budget in USD."""
        return max(0.0, self._router._budget - self._router._spent_usd)

    def month_start(self) -> datetime:
        """Returns the start of the current billing month."""
        return self._month_start

    async def reset_monthly(self) -> None:
        """Admin-only: reset spent_usd to 0 (called via admin
        script on 1st of month)."""
        async with self._router._lock:
            self._router._spent_usd = 0.0
            self._month_start = datetime.now(UTC).replace(
                day=1,
                hour=0,
                minute=0,
                second=0,
                microsecond=0,
            )
            update_budget_usage(0.0, self._router._budget)
            logger.info("Monthly budget reset to 0 / %s", self._router._budget)


_guard: CostGuard | None = None


def get_cost_guard() -> CostGuard:
    global _guard
    if _guard is None:
        _guard = CostGuard(get_llm_router())
    return _guard

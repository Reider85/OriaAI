"""Logger for LLMRouter decisions (ADR-015 Phase 3).

Writes every RoutingDecision to operational stream (ADR-014) for
audit + Grafana dashboards.

Architecture: ARCHITECT.md v1.3.0 §5.2.3 (LLM Provider Layer),
§5.2.7 (Observability Layer).
TRIZ: Standard 2.2.4 (measuring vepol — router decisions measured).
"""
import logging
from datetime import UTC, datetime

from ..observability.operational_writer import get_operational_writer

logger = logging.getLogger(__name__)


class RouterMetricsLogger:
    """Logs routing decisions to operational stream."""

    def __init__(self) -> None:
        # Writer resolved per call for testability (patching works)
        pass

    async def log_decision(self, decision, request_id: str | None = None) -> None:
        """Log a RoutingDecision (Блок C-2 RoutingDecision dataclass)."""
        event = {
            "event_type": "router_decision",
            "timestamp": datetime.now(UTC).isoformat(),
            "request_id": request_id,
            "provider": decision.provider,
            "model": decision.model,
            "policy": decision.policy.value if hasattr(decision.policy, "value") else str(decision.policy),
            "reason": decision.reason,
            "budget_ratio": decision.budget_ratio_at_decision,
            "circuit_breaker_active": decision.circuit_breaker_active,
        }
        # Resolve writer per call (allows patching operational_writer.get_operational_writer)
        writer = get_operational_writer()
        if writer is not None:
            await writer.write(event)
        else:
            logger.info(
                "Router decision (no operational writer): provider=%s model=%s policy=%s reason=%s budget=%.1f%% cb=%s",
                decision.provider, decision.model,
                event["policy"], decision.reason,
                decision.budget_ratio_at_decision * 100,
                decision.circuit_breaker_active,
            )
        # Record Prometheus counter (independent of stream)
        from .llm_metrics import record_router_decision
        record_router_decision(
            provider=decision.provider,
            model=decision.model,
            policy=event["policy"],
            reason=decision.reason,
            circuit_breaker_active=decision.circuit_breaker_active,
        )
        logger.info(
            "Router decision: provider=%s model=%s policy=%s reason=%s budget=%.1f%% cb=%s",
            decision.provider, decision.model,
            event["policy"], decision.reason,
            decision.budget_ratio_at_decision * 100,
            decision.circuit_breaker_active,
        )

    async def log_shadow_decision(self, decision, actual_provider: str | None,
                                  actual_model: str | None, request_id: str | None = None) -> None:
        """Log shadow-mode comparison: what router WOULD have chosen
        vs what was actually used."""
        event = {
            "event_type": "router_shadow_comparison",
            "timestamp": datetime.now(UTC).isoformat(),
            "request_id": request_id,
            "router_would_choose_provider": decision.provider,
            "router_would_choose_model": decision.model,
            "router_would_choose_reason": decision.reason,
            "actual_provider": actual_provider,
            "actual_model": actual_model,
            "match": (decision.provider == actual_provider and decision.model == actual_model),
        }
        writer = get_operational_writer()
        if writer is not None:
            await writer.write(event)
        else:
            logger.info(
                "SHADOW_MODE: would=%s/%s actual=%s/%s match=%s",
                decision.provider, decision.model,
                actual_provider, actual_model,
                event["match"],
            )


_logger: RouterMetricsLogger | None = None


def get_router_metrics_logger() -> RouterMetricsLogger:
    global _logger
    if _logger is None:
        _logger = RouterMetricsLogger()
    return _logger
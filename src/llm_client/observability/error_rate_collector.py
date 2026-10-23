"""Background task: every 30s, query for last 5min
error rate per provider, update llm_error_rate_5m gauge.

This is the bridge between TokenUsageTracker callback data flow
and circuit breaker check (per-request).

Architecture: Phase 3 ADR-015. TRIZ: Standard 5.1.1
(Prometheus as external substance) via in-process REGISTRY.
"""
import asyncio
import logging

from ..observability.llm_metrics import update_error_rate

logger = logging.getLogger(__name__)


async def collect_error_rates() -> None:
    """For each provider, count errors and total calls in last 5
    minutes from in-process REGISTRY, compute error rate, update
    gauge."""
    from ..observability.llm_metrics import REGISTRY
    from prometheus_client import generate_latest
    from prometheus_client.parser import text_string_to_metric_families
    
    latest = generate_latest(REGISTRY).decode()

    # Aggregate per-provider
    provider_stats: dict[str, dict[str, int]] = {}  # provider -> {errors, total}
    for family in text_string_to_metric_families(latest):
        if family.name == "llm_call_total":
            for sample in family.samples:
                provider = sample.labels.get("provider", "unknown")
                status = sample.labels.get("status", "unknown")
                count = int(sample.value)
                provider_stats.setdefault(provider, {"errors": 0, "total": 0})
                provider_stats[provider]["total"] += count
                if status in ("error", "timeout"):
                    provider_stats[provider]["errors"] += count

    for provider, stats in provider_stats.items():
        update_error_rate(provider, stats["errors"], stats["total"])


async def run_collector_loop(interval_seconds: int = 30) -> None:
    """Run error rate collection loop."""
    logger.info("Circuit breaker metrics collector started (interval=%ds)", interval_seconds)
    while True:
        try:
            await collect_error_rates()
        except Exception as e:
            logger.error("Circuit breaker metrics collection failed: %s", e)
        await asyncio.sleep(interval_seconds)
"""Background task: every 30s, query for last 5min
error rate per provider, update llm_error_rate_5m gauge.

This is the bridge between TokenUsageTracker callback data flow
and circuit breaker check (per-request).

Architecture: Phase 3 ADR-015. TRIZ: Standard 5.1.1
(Prometheus as external substance) via in-process REGISTRY.
"""
import asyncio
import logging

from llm_client.observability.error_rate_collector import run_collector_loop

logger = logging.getLogger(__name__)


if __name__ == "__main__":
    asyncio.run(run_collector_loop())
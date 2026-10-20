"""Prometheus metrics for LLM calls (Phase 3 — ADR-015 circuit breaker input).

Reuses TokenUsageTracker callback (AG-2 Phase 1) data flow:
TokenUsageTracker.on_llm_end already writes to operational stream;
here we also expose the same metrics to Prometheus for ADR-015
router circuit breaker.

Architecture: ARCHITECT.md v1.3.0 §5.2.3, §5.2.7 (Observability
Layer). TRIZ Standard 5.1.1 — Prometheus as external substance
for circuit breaker.
"""
import logging

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

REGISTRY = CollectorRegistry(auto_describe=True)

# Counters
LLM_CALLS_TOTAL = Counter(
    "llm_call_total",
    "Total LLM calls by provider/model/status",
    labelnames=("provider", "model", "status", "mode"),
    registry=REGISTRY,
)
# status: "success" | "error" | "timeout" | "cancelled"
# mode: "native" | "react" | "hybrid" (per ADR-016 ToolCallingMode)

LLM_TOKENS_TOTAL = Counter(
    "llm_tokens_total",
    "Total tokens consumed by provider/model/type",
    labelnames=("provider", "model", "token_type"),
    registry=REGISTRY,
)
# token_type: "prompt" | "completion"

LLM_COST_TOTAL = Counter(
    "llm_cost_usd_total",
    "Total LLM cost in USD by provider/model",
    labelnames=("provider", "model"),
    registry=REGISTRY,
)

# Histograms
LLM_LATENCY = Histogram(
    "llm_call_latency_seconds",
    "LLM call latency in seconds",
    labelnames=("provider", "model"),
    buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
    registry=REGISTRY,
)

# Gauges (for circuit breaker — ADR-015)
LLM_ERROR_RATE = Gauge(
    "llm_error_rate_5m",
    "Rolling 5-min error rate per provider (circuit breaker input)",
    labelnames=("provider",),
    registry=REGISTRY,
)

LLM_MONTHLY_BUDGET_USAGE = Gauge(
    "llm_monthly_budget_usage_ratio",
    "Current monthly budget usage ratio (0.0–1.0+); cost guard at 0.8",
    registry=REGISTRY,
)

SEMANTIC_CACHE_HITS = Counter(
    "semantic_cache_hits_total",
    "Semantic cache hits/misses (ADR-011)",
    labelnames=("status",),  # "hit" | "miss" | "stale"
    registry=REGISTRY,
)


def record_llm_call(
    provider: str,
    model: str,
    status: str,
    mode: str,
    latency_seconds: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cost_usd: float = 0.0,
) -> None:
    """Record one LLM call. Called from TokenUsageTracker callback
    (Phase 1, AG-2) — see src/llm_client/agent/provider.py
    TokenUsageTracker.on_llm_end.
    """
    LLM_CALLS_TOTAL.labels(
        provider=provider, model=model, status=status, mode=mode
    ).inc()
    if prompt_tokens:
        LLM_TOKENS_TOTAL.labels(
            provider=provider, model=model, token_type="prompt"
        ).inc(prompt_tokens)
    if completion_tokens:
        LLM_TOKENS_TOTAL.labels(
            provider=provider, model=model, token_type="completion"
        ).inc(completion_tokens)
    if cost_usd > 0:
        LLM_COST_TOTAL.labels(provider=provider, model=model).inc(cost_usd)
    LLM_LATENCY.labels(provider=provider, model=model).observe(latency_seconds)


def update_error_rate(provider: str, error_count_5m: int, total_count_5m: int) -> None:
    """Called periodically (e.g. every 30s) from background task."""
    rate = (error_count_5m / total_count_5m) if total_count_5m > 0 else 0.0
    LLM_ERROR_RATE.labels(provider=provider).set(rate)


def update_budget_usage(used_usd: float, budget_usd: float) -> None:
    """Called from CostGuard (Блок C-3) on every cost update."""
    ratio = (used_usd / budget_usd) if budget_usd > 0 else 0.0
    LLM_MONTHLY_BUDGET_USAGE.set(ratio)


def record_cache_hit(status: str) -> None:
    """Called from SemanticAnswerCache (Блок B-1)."""
    SEMANTIC_CACHE_HITS.labels(status=status).inc()


def get_cache_hit_counts() -> dict[str, int]:
    """Get current counts of semantic cache hits/misses/stale.
    
    Returns:
        Dict with "hit", "miss", "stale" counts (all values ≥ 0).
        Used by A/B test framework (B-6) to distinguish stale vs miss.
    """
    return {
        "hit": int(SEMANTIC_CACHE_HITS.labels(status="hit")._value.get()),
        "miss": int(SEMANTIC_CACHE_HITS.labels(status="miss")._value.get()),
        "stale": int(SEMANTIC_CACHE_HITS.labels(status="stale")._value.get()),
    }
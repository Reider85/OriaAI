"""A/B test for ADR-015 LLMRouter shadow mode (Phase 3 — E-2).

Runs traffic in parallel with existing LLMProviderFactory.create() calls;
each request also calls router.route_shadow, which logs the (provider, model)
the router WOULD have chosen via RouterMetricsLogger (Блок C-7).

Pilot criteria (ROADMAP §14.1):
- Cost predictability ±10% (stdev of (actual - predicted)/predicted <= 0.10)
- Cost overrun <20% (per-request: actual > predicted * 1.2 in <=20% requests;
  requests with predicted == 0 — free-model routing — are excluded)
- Switching decisions logged (every shadow decision -> operational stream)

Rollback: cost overrun >20% OR unacceptable routing decisions.

Usage:
    python scripts/ab_test_router_shadow_mode.py --duration-minutes 60
    python scripts/ab_test_router_shadow_mode.py --offline --duration-minutes 0 --max-requests 5 --interval-seconds 0
    python scripts/ab_test_router_shadow_mode.py --queries-file queries.jsonl --output report.json
"""

import argparse
import asyncio
import json
import statistics
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from llm_client.agent.model_cost_table import (
    ModelCostTable,
    compute_call_cost,
    get_model_cost_table,
)
from llm_client.agent.provider import LLMProviderFactory
from llm_client.agent.router import RoutingPolicy, get_llm_router
from llm_client.config import settings

COST_PREDICTABILITY_THRESHOLD = 0.10  # ROADMAP §14.1: ±10%
COST_OVERRUN_TOLERANCE = 0.20  # ROADMAP §14.1: per-request overrun >20%

DEFAULT_QUERIES = [
    "Summarize the key points of quarterly revenue reports.",
    "What are the main risks identified in the latest audit?",
    "Draft a short email asking for the project status update.",
    "Explain the difference between vector and hybrid retrieval.",
    "List action items from today's engineering standup.",
]


@dataclass
class ShadowModeResult:
    total_requests: int
    router_predicted_costs: list[float]
    actual_costs: list[float]
    switching_decisions_logged: int
    cost_overrun_count: int  # requests where router decision led to overrun

    def cost_predictability(self) -> float:
        """Returns standard deviation of (actual - predicted) /
        predicted ratios. Lower = more predictable."""
        if not self.router_predicted_costs:
            return 0.0
        ratios = []
        for pred, actual in zip(self.router_predicted_costs, self.actual_costs):
            if pred > 0:
                ratios.append((actual - pred) / pred)
        return statistics.stdev(ratios) if len(ratios) > 1 else 0.0

    def cost_overrun_rate(self) -> float:
        return self.cost_overrun_count / self.total_requests if self.total_requests else 0.0

    def pilot_pass(self) -> bool:
        return (
            self.cost_predictability() <= COST_PREDICTABILITY_THRESHOLD  # ±10%
            and self.cost_overrun_rate() <= COST_OVERRUN_TOLERANCE  # <20% overrun
            and self.switching_decisions_logged == self.total_requests
        )

    def rollback_required(self) -> bool:
        return self.cost_overrun_rate() > COST_OVERRUN_TOLERANCE


class _ShadowEventCounter:
    """Operational-stream writer wrapper counting router_shadow_comparison events.

    Delegates to the real writer (if any) so shadow events still reach the
    operational stream (ADR-014) during the pilot run.
    """

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.shadow_events = 0

    async def write(self, event: dict[str, Any]) -> None:
        if event.get("event_type") == "router_shadow_comparison":
            self.shadow_events += 1
        if self._inner is not None:
            await self._inner.write(event)


def _install_shadow_event_counter() -> tuple[_ShadowEventCounter, Any]:
    """Patch RouterMetricsLogger's writer resolver with a counting wrapper."""
    from llm_client.observability import router_metrics_logger as rml_module

    original = rml_module.get_operational_writer
    counter = _ShadowEventCounter(original())
    rml_module.get_operational_writer = lambda: counter  # type: ignore[assignment]
    return counter, original


def _restore_shadow_event_counter(original: Any) -> None:
    from llm_client.observability import router_metrics_logger as rml_module

    rml_module.get_operational_writer = original


def _resolve_actual_model(provider: str) -> str:
    """Mirror service._resolve_model (service.py) for the actual provider path."""
    provider_key = provider.upper()
    match provider_key:
        case "ANTHROPIC":
            return settings.anthropic_model
        case "CUSTOM-OPENAI":
            return settings.custom_openai_model
        case "ZAI":
            return settings.zai_model
        case _:
            return settings.openai_model


def _estimate_tokens(text: str) -> tuple[int, int]:
    """Rough token estimate (~4 chars/token) when usage metadata is absent."""
    prompt_tokens = max(1, len(text) // 4)
    completion_tokens = max(1, len(text) // 8)
    return prompt_tokens, completion_tokens


def _extract_token_usage(response: Any, query: str) -> tuple[int, int]:
    """Extract (prompt_tokens, completion_tokens) from an AIMessage response."""
    usage = getattr(response, "usage_metadata", None)
    if isinstance(usage, dict):
        prompt_tokens = usage.get("input_tokens") or 0
        completion_tokens = usage.get("output_tokens") or 0
        if prompt_tokens or completion_tokens:
            return prompt_tokens, completion_tokens
    elif usage is not None:
        prompt_tokens = getattr(usage, "input_tokens", 0) or 0
        completion_tokens = getattr(usage, "output_tokens", 0) or 0
        if prompt_tokens or completion_tokens:
            return prompt_tokens, completion_tokens

    response_metadata = getattr(response, "response_metadata", None) or {}
    token_usage = response_metadata.get("token_usage") or {}
    prompt_tokens = token_usage.get("prompt_tokens", 0) or 0
    completion_tokens = token_usage.get("completion_tokens", 0) or 0
    if prompt_tokens or completion_tokens:
        return prompt_tokens, completion_tokens

    # Last resort: estimate from query and response content lengths
    content = str(getattr(response, "content", "") or "")
    estimated_prompt = max(1, len(query) // 4)
    estimated_completion = max(1, len(content) // 4)
    return estimated_prompt, estimated_completion


def _create_actual_llm():
    """Create the LLM for the actual (non-router) path — mirrors service.py."""
    provider_key = settings.llm_provider.upper()
    model = _resolve_actual_model(provider_key)
    match provider_key:
        case "CUSTOM-OPENAI":
            return LLMProviderFactory.create(
                provider="CUSTOM-OPENAI",
                model=model,
                api_key=settings.custom_openai_api_key,
                base_url=settings.custom_openai_base_url,
                streaming=False,
            )
        case "ZAI":
            if settings.orya_proxy_url:
                return LLMProviderFactory.create(
                    provider="ZAI",
                    model=model,
                    api_key=settings.zai_api_key,
                    base_url=settings.zai_base_url,
                    streaming=False,
                    orya_proxy_url=settings.orya_proxy_url,
                    orya_proxy_key=settings.orya_proxy_key or None,
                )
            return LLMProviderFactory.create(
                provider="ZAI",
                model=model,
                api_key=settings.zai_api_key,
                base_url=settings.zai_base_url,
                streaming=False,
            )
        case "ANTHROPIC":
            return LLMProviderFactory.create(
                provider="anthropic",
                model=model,
                api_key=settings.anthropic_api_key,
                streaming=False,
            )
        case _:
            return LLMProviderFactory.create(
                provider="openai",
                model=model,
                api_key=settings.openai_api_key,
                streaming=False,
            )


def _predicted_cost(
    cost_table: ModelCostTable,
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Router-predicted cost for the chosen (provider, model). Unknown models -> 0.0."""
    model_cost = cost_table.get_cost(provider, model)
    if model_cost is None:
        return 0.0
    return model_cost.cost_for(prompt_tokens, completion_tokens)


async def run_shadow_mode(
    duration_minutes: int = 60,
    *,
    queries: list[str] | None = None,
    interval_seconds: float = 60.0,
    max_requests: int | None = None,
    offline: bool = False,
) -> ShadowModeResult:
    """Run shadow mode for `duration_minutes` minutes. Each request
    routed via existing LLMProviderFactory, but router.route_shadow
    called in parallel.

    offline=True skips real LLM calls: predicted/actual costs are both
    computed from ModelCostTable on estimated token counts (price-only
    divergence; useful for smoke runs without API spend).

    max_requests (when set) takes precedence over duration_minutes as
    the stop condition — the run executes exactly max_requests requests.
    """
    router = get_llm_router()
    cost_table = get_model_cost_table()
    actual_provider = settings.llm_provider.lower()
    actual_model = _resolve_actual_model(settings.llm_provider)
    query_list = list(queries) if queries else list(DEFAULT_QUERIES)

    predicted_costs: list[float] = []
    actual_costs: list[float] = []
    overrun_count = 0

    llm = None if offline else _create_actual_llm()

    counter, original_writer = _install_shadow_event_counter()
    try:
        deadline = time.monotonic() + duration_minutes * 60
        idx = 0
        while True:
            if max_requests is not None and len(predicted_costs) >= max_requests:
                break
            # Duration bound applies only when max_requests is not set.
            # Always execute at least one request so empty results are impossible.
            if max_requests is None and predicted_costs and time.monotonic() >= deadline:
                break

            query = query_list[idx % len(query_list)]
            idx += 1
            request_id = str(uuid.uuid4())

            decision = await router.route_shadow(
                query=query,
                policy=RoutingPolicy.COST,
                actual_provider=actual_provider,
                actual_model=actual_model,
                request_id=request_id,
            )

            if offline:
                prompt_tokens, completion_tokens = _estimate_tokens(query)
            else:
                response = await llm.ainvoke(query)
                prompt_tokens, completion_tokens = _extract_token_usage(response, query)

            predicted = _predicted_cost(
                cost_table, decision.provider, decision.model, prompt_tokens, completion_tokens
            )
            actual = compute_call_cost(
                actual_provider, actual_model, prompt_tokens, completion_tokens
            )
            predicted_costs.append(predicted)
            actual_costs.append(actual)

            # Per-request overrun: actual cost exceeded router prediction by >20%.
            # Skipped when predicted == 0: COST policy may route to free models
            # (custom-openai/default), and a $0 prediction cannot be "exceeded
            # by 20%" — counting it would flag every request as overrun.
            if predicted > 0 and actual > predicted * (1 + COST_OVERRUN_TOLERANCE):
                overrun_count += 1

            if interval_seconds > 0:
                await asyncio.sleep(interval_seconds)
    finally:
        _restore_shadow_event_counter(original_writer)

    return ShadowModeResult(
        total_requests=len(predicted_costs),
        router_predicted_costs=predicted_costs,
        actual_costs=actual_costs,
        switching_decisions_logged=counter.shadow_events,
        cost_overrun_count=overrun_count,
    )


def main() -> None:
    # Windows cp1251 consoles cannot encode verdict emojis (✅/❌/⚠️)
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass

    parser = argparse.ArgumentParser(description="ADR-015 LLMRouter shadow-mode pilot test")
    parser.add_argument("--duration-minutes", type=int, default=60)
    parser.add_argument("--queries-file", help='JSONL file with {"query": ...} entries')
    parser.add_argument(
        "--interval-seconds", type=float, default=60.0, help="Pause between requests (default: 60)"
    )
    parser.add_argument(
        "--max-requests",
        type=int,
        default=None,
        help="Stop after N requests (takes precedence over --duration-minutes)",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Simulate costs from ModelCostTable without real LLM calls",
    )
    parser.add_argument("--output", help="Output JSON report file path")
    args = parser.parse_args()

    queries: list[str] | None = None
    if args.queries_file:
        with open(args.queries_file, encoding="utf-8") as f:
            queries = [json.loads(line)["query"] for line in f if line.strip()]

    result = asyncio.run(
        run_shadow_mode(
            duration_minutes=args.duration_minutes,
            queries=queries,
            interval_seconds=args.interval_seconds,
            max_requests=args.max_requests,
            offline=args.offline,
        )
    )

    print("=== ADR-015 Pilot: LLMRouter Shadow Mode ===")
    print(f"Total requests: {result.total_requests}")
    print(f"Cost predictability (stdev of ratios): {result.cost_predictability():.3f}")
    print(f"Cost overrun rate: {result.cost_overrun_rate():.1%}")
    print(f"Switching decisions logged: {result.switching_decisions_logged}")

    if args.output:
        report = {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "total_requests": result.total_requests,
            "cost_predictability": result.cost_predictability(),
            "cost_overrun_rate": result.cost_overrun_rate(),
            "switching_decisions_logged": result.switching_decisions_logged,
            "pilot_criteria": {
                "predictability_threshold": COST_PREDICTABILITY_THRESHOLD,
                "overrun_tolerance": COST_OVERRUN_TOLERANCE,
            },
            "pilot_pass": result.pilot_pass(),
            "rollback_required": result.rollback_required(),
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    if result.rollback_required():
        print("❌ ROLLBACK REQUIRED (cost overrun >20%)")
        sys.exit(1)
    elif result.pilot_pass():
        print("✅ PILOT PASS — ADR-015 Approved")
        sys.exit(0)
    else:
        print("⚠️  PILOT PARTIAL")
        sys.exit(2)


if __name__ == "__main__":
    main()

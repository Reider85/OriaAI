"""Cost-Aware LLM Router (ADR-015 Phase 3).

Replaces ADR-005 fallback_chain. Routes per-request to a
(provider, model) based on:
- policy (cost / latency / quality / privacy)
- provider circuit breaker (Prometheus llm_error_rate_5m)
- monthly budget spend (cost guard at 80%)
- model capability matrix (ADR-016, Блок D-1)
- privacy requirements (zero-retention policy)

Architecture: ARCHITECT.md v1.3.0 §5.2.3.
TRIZ: Standard 2.2.4 (transition to measuring vepol —
LLMCallMetrics feedback); principle #13 (inverse — load
balancing by default, fallback at edges).
"""
import asyncio
import logging
from dataclasses import dataclass
from enum import Enum
from typing import ClassVar

from langchain_core.language_models import BaseChatModel

from ..config import settings
from ..observability.llm_metrics import LLM_ERROR_RATE
from .model_cost_table import ModelCostTable, get_model_cost_table
from .provider import LLMProviderFactory

logger = logging.getLogger(__name__)


class RoutingPolicy(str, Enum):
    COST = "cost_priority"
    LATENCY = "latency_priority"
    QUALITY = "quality_priority"
    PRIVACY = "privacy_priority"


@dataclass
class RoutingDecision:
    provider: str
    model: str
    policy: RoutingPolicy
    reason: str  # human-readable explanation for observability
    budget_ratio_at_decision: float
    circuit_breaker_active: bool


class LLMRouter:
    """Central routing class. Wraps LLMProviderFactory."""

    DEFAULT_TRAFFIC_SPLIT: ClassVar[dict[tuple[str, str], float]] = {
        # 70% to primary (cost_priority: gpt-4o-mini),
        # 30% to secondary (latency_priority: gpt-4o for quality)
        # — load balancing по умолчанию
        ("openai", "gpt-4o-mini"): 0.7,
        ("openai", "gpt-4o"): 0.3,
    }

    BUDGET_THRESHOLD_CHEAPEST = 0.8  # 80% of monthly budget

    def __init__(
        self,
        provider_factory: type[LLMProviderFactory],
        cost_table: ModelCostTable,
        budget_usd: float = 100.0,  # configurable
    ) -> None:
        self._factory = provider_factory
        self._cost_table = cost_table
        self._budget = budget_usd
        self._spent_usd = 0.0
        self._lock = asyncio.Lock()

    async def route(
        self,
        query: str | None = None,
        policy: RoutingPolicy = RoutingPolicy.COST,
        privacy_required: bool = False,
    ) -> RoutingDecision:
        """Decide (provider, model) for next LLM call."""
        async with self._lock:
            budget_ratio = self._spent_usd / self._budget if self._budget > 0 else 0.0
            # Update Prometheus gauge
            from ..observability.llm_metrics import update_budget_usage
            update_budget_usage(self._spent_usd, self._budget)

            # 1. Cost guard: at 80% budget → switch to cheapest
            if budget_ratio >= self.BUDGET_THRESHOLD_CHEAPEST:
                cheapest = self._cost_table.cheapest_model()
                if cheapest:
                    provider, model = cheapest
                    return RoutingDecision(
                        provider=provider,
                        model=model,
                        policy=RoutingPolicy.COST,
                        reason=f"Budget at {budget_ratio:.0%} — switched to cheapest",
                        budget_ratio_at_decision=budget_ratio,
                        circuit_breaker_active=False,
                    )

            # 2. Privacy: if required → use Ollama or zero-retention
            if privacy_required:
                # Phase 4: full Ollama support; Phase 3 stub returns
                # custom-openai with zero-retention policy
                return RoutingDecision(
                    provider="custom-openai",
                    model="default",
                    policy=RoutingPolicy.PRIVACY,
                    reason="Privacy required — zero-retention provider",
                    budget_ratio_at_decision=budget_ratio,
                    circuit_breaker_active=False,
                )

            # 3. Policy-based routing
            if policy == RoutingPolicy.COST:
                cheapest = self._cost_table.cheapest_model() or ("openai", "gpt-4o-mini")
                provider, model = cheapest
                reason = "Cost priority — cheapest available"
            elif policy == RoutingPolicy.LATENCY:
                # Pick model with lowest p50 latency (Phase 4 reads
                # ModelCapabilityMatrix; Phase 3 stub: gpt-4o-mini)
                provider, model = "openai", "gpt-4o-mini"
                reason = "Latency priority — gpt-4o-mini"
            elif policy == RoutingPolicy.QUALITY:
                provider, model = "openai", "gpt-4o"
                reason = "Quality priority — gpt-4o"
            elif policy == RoutingPolicy.PRIVACY:
                provider, model = "custom-openai", "default"
                reason = "Privacy priority — zero-retention"
            else:
                provider, model = "openai", "gpt-4o-mini"
                reason = f"Unknown policy {policy} — default"

            # 4. Circuit breaker check via Prometheus
            cb_active = await self._check_circuit_breaker(provider)
            if cb_active:
                # Fallback to alternative provider
                alt = self._fallback_provider(provider)
                if alt:
                    provider, model = alt
                    reason += f"; circuit breaker active on primary — fallback to {alt}"

            return RoutingDecision(
                provider=provider,
                model=model,
                policy=policy,
                reason=reason,
                budget_ratio_at_decision=budget_ratio,
                circuit_breaker_active=cb_active,
            )

    async def create_llm(self, decision: RoutingDecision) -> BaseChatModel:
        """Create BaseChatModel based on routing decision."""
        # Normalize provider case for LLMProviderFactory.create()
        provider = decision.provider
        model = decision.model
        
        # Custom-openai requires base_url from settings
        if provider == "custom-openai":
            base_url = settings.custom_openai_base_url
            # For custom-openai, normalize to "CUSTOM-OPENAI" case
            provider = "CUSTOM-OPENAI"
            return LLMProviderFactory.create(
                provider=provider,
                model=model,
                api_key=settings.custom_openai_api_key,
                base_url=base_url,
            )
        else:
            # Use _get_api_key for other providers
            api_key: str | None = self._get_api_key(provider, settings)
            return LLMProviderFactory.create(
                provider=provider,
                model=model,
                api_key=api_key,
            )

    async def record_cost(self, cost_usd: float) -> None:
        """Called from TokenUsageTracker (after LLM call) to update
        monthly spend tracker."""
        async with self._lock:
            self._spent_usd += cost_usd
            logger.info(
                "LLM cost recorded: $%.4f (total $%.2f / $%.2f = %.1f%%)",
                cost_usd, self._spent_usd, self._budget,
                (self._spent_usd / self._budget * 100) if self._budget else 0,
            )
            # Update Prometheus budget usage gauge
            from llm_client.observability.llm_metrics import update_budget_usage
            update_budget_usage(self._spent_usd, self._budget)

    async def _check_circuit_breaker(self, provider: str) -> bool:
        """Check Prometheus llm_error_rate_5m gauge for provider.
        If >0.5 (50% error rate) → circuit breaker active."""
        # Phase 3: read from in-process gauge (direct access)
        try:
            # Use direct gauge access for simplicity and performance
            gauge_value = LLM_ERROR_RATE.labels(provider=provider)._value.get()
            return gauge_value > 0.5
        except Exception as e:
            logger.warning("Circuit breaker check failed: %s", e)
            return False

    def _fallback_provider(self, primary: str) -> tuple[str, str] | None:
        """Returns fallback (provider, model) if primary is down."""
        fallbacks = {
            "openai": ("anthropic", "claude-3-haiku"),
            "anthropic": ("openai", "gpt-4o-mini"),
            "custom-openai": ("openai", "gpt-4o-mini"),
        }
        return fallbacks.get(primary)

    def _get_api_key(self, provider: str, settings) -> str | None:
        """Get API key for provider from settings."""
        if provider == "openai":
            return settings.openai_api_key
        elif provider == "anthropic":
            return settings.anthropic_api_key
        elif provider in ("custom-openai", "zai"):
            return settings.openai_api_key  # CUSTOM-OPENAI uses OpenAI key
        elif provider == "ollama":
            return None  # Ollama is local, no API key
        return None


_router: LLMRouter | None = None


def get_llm_router() -> LLMRouter:
    """Singleton LLMRouter. Initialized with default budget from
    Settings (LLM_MONTHLY_BUDGET_USD env var)."""
    global _router
    if _router is not None:
        return _router
    # Lazy access settings to avoid import-time validation failure
    _router = LLMRouter(
        provider_factory=LLMProviderFactory,
        cost_table=get_model_cost_table(),
        budget_usd=settings.llm_monthly_budget_usd,
    )
    return _router
"""Configurable model cost table (Phase 3 — ADR-015).

Replaces the ``_COST_PER_1M`` hardcode (Phase 1, AG-2).  Loaded from a YAML
config file (``MODEL_COSTS_CONFIG_PATH`` env var) or built-in defaults.  Used by
``LLMRouter`` (C-2) and ``CostGuard`` (C-3) for cost-aware routing decisions.

Architecture: ARCHITECT.md v1.3.0 §5.2.3.
TRIZ: principle #35 (change of physical properties — hardcode → configurable).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

__all__ = ["ModelCost", "ModelCostTable", "compute_call_cost", "get_model_cost_table"]


# ── Model cost (USD per 1M tokens) ────────────────────────────────────────────


class ModelCost(BaseModel):
    """Cost for one model, per 1M tokens, USD."""

    model_config = ConfigDict(frozen=True)

    prompt: float = Field(..., ge=0.0, description="USD per 1M prompt tokens")
    completion: float = Field(..., ge=0.0, description="USD per 1M completion tokens")

    def cost_for(self, prompt_tokens: int, completion_tokens: int) -> float:
        """Compute USD cost for a single call."""
        return (prompt_tokens / 1_000_000) * self.prompt + (
            completion_tokens / 1_000_000
        ) * self.completion


# ── Cost table (provider → model → ModelCost) ────────────────────────────────


class ModelCostTable(BaseModel):
    """Mapping of (provider, model) → ModelCost.

    Loaded from a YAML config file.  Can be overridden via
    ``MODEL_COSTS_CONFIG_PATH`` env var pointing to a production YAML.
    """

    costs: dict[str, dict[str, ModelCost]] = Field(
        default_factory=dict,
        description="Outer key = provider, inner key = model",
    )

    def get_cost(self, provider: str, model: str) -> ModelCost | None:
        """Return ModelCost for (provider, model) or None if unknown.

        Provider is normalized to lowercase (Settings stores it uppercase
        after validation, YAML keys are lowercase).
        """
        provider_table = self.costs.get(provider.lower())
        if provider_table is None:
            return None
        return provider_table.get(model)

    def list_models(self, provider: str | None = None) -> list[tuple[str, str]]:
        """List all (provider, model) pairs, optionally filtered by provider."""
        if provider:
            return [(provider.lower(), m) for m in self.costs.get(provider.lower(), {})]
        return [(p, m) for p, models in self.costs.items() for m in models]

    def cheapest_model(self, provider: str | None = None) -> tuple[str, str] | None:
        """Return (provider, model) with lowest avg cost (prompt + completion)/2.

        Used by CostGuard (C-3) when the monthly budget guard triggers at 80%.
        """
        candidates = self.list_models(provider)
        if not candidates:
            return None

        def avg_cost(pm: tuple[str, str]) -> float:
            c = self.get_cost(*pm)
            return (c.prompt + c.completion) / 2 if c else float("inf")

        return min(candidates, key=avg_cost)


# ── Default costs (fallback when MODEL_COSTS_CONFIG_PATH is unset) ───────────

DEFAULT_COSTS_YAML = """
# Default model costs (USD per 1M tokens); override via YAML config
# MODEL_COSTS_CONFIG_PATH or env vars.
openai:
  gpt-4o-mini:
    prompt: 0.15
    completion: 0.60
  gpt-4o:
    prompt: 2.50
    completion: 10.00
  gpt-4-turbo:
    prompt: 10.00
    completion: 30.00
anthropic:
  claude-3-5-sonnet:
    prompt: 3.00
    completion: 15.00
  claude-3-haiku:
    prompt: 0.25
    completion: 1.25
custom-openai:
  # Self-hosted OpenAI-compatible (e.g. vLLM, LM Studio) — assume $0
  default:
    prompt: 0.0
    completion: 0.0
ollama:
  # Local LLM via Ollama — Phase 4 full integration; Phase 3 stub
  llama3.1-8b:
    prompt: 0.0
    completion: 0.0
zai:
  # ZAI-hosted LLM (existing CUSTOM-OPENAI provider case)
  glm-4.5:
    prompt: 0.10
    completion: 0.40
  glm-4-flash:
    prompt: 0.10
    completion: 0.40
"""


# ── Singleton + convenience API ───────────────────────────────────────────────

_table: ModelCostTable | None = None


def get_model_cost_table() -> ModelCostTable:
    """Singleton ModelCostTable.  Loads from YAML config or defaults (once)."""
    global _table
    if _table is not None:
        return _table
    config_path = os.environ.get("MODEL_COSTS_CONFIG_PATH")
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            data = yaml.safe_load(f)
        _table = ModelCostTable.model_validate({"costs": data})
        logger.info("Loaded model costs from %s", config_path)
    else:
        data = yaml.safe_load(DEFAULT_COSTS_YAML)
        _table = ModelCostTable.model_validate({"costs": data})
        logger.info("Loaded default model costs (built-in)")
    return _table


def compute_call_cost(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Return estimated cost in USD for a single LLM call.

    Called from ``TokenUsageTracker.on_llm_end`` (Phase 1 AG-2).  Unknown
    (provider, model) pairs return 0.0 with a warning log.
    """
    table = get_model_cost_table()
    cost = table.get_cost(provider, model)
    if cost is None:
        logger.warning(
            "Unknown model %s/%s — cost estimate $0.0",
            provider,
            model,
        )
        return 0.0
    return cost.cost_for(prompt_tokens, completion_tokens)
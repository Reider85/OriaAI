"""Model Capability Matrix (ADR-016 Phase 3).

Per-model declarations: supports_native_tools, supports_streaming,
supports_vision, context_window, cost_per_1m_tokens, latency_p50,
latency_p99. Loaded from YAML config.

Architecture: ARCHITECT.md v1.3.0 §5.2.3.
TRIZ: principle #25 (self-service — models self-declare);
Standard 3.1.4 (field splitting — NativeToolCalling vs ReActToolCalling).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


__all__ = ["ModelCapabilities", "ModelCapabilityMatrix", "get_capability_matrix"]


# ── Model capabilities (per-model declarations) ─────────────────────────────────


class ModelCapabilities(BaseModel):
    """Capabilities for one (provider, model) pair."""

    model_config = ConfigDict(frozen=True)

    supports_native_tools: bool = Field(
        default=False, description="True if model supports OpenAI-style function calling",
    )
    supports_streaming: bool = Field(
        default=True, description="True if model supports SSE streaming",
    )
    supports_vision: bool = Field(
        default=False, description="True if model supports image input",
    )
    context_window: int = Field(
        default=4096, ge=128, description="Max tokens in context",
    )
    cost_per_1m_tokens: dict[str, float] = Field(
        default_factory=lambda: {"prompt": 0.0, "completion": 0.0},
        description="USD per 1M tokens: {prompt, completion}",
    )
    latency_p50_ms: int = Field(
        default=500, ge=10, description="Median latency in ms (non-streaming first token)",
    )
    latency_p99_ms: int = Field(
        default=2000, ge=100, description="P99 latency in ms",
    )
    supports_react_emulation: bool = Field(
        default=True, description="True if ReAct prompt-based tool calling works (most LLMs)",
    )
    notes: str = Field(default="", description="Free-form notes about this model")


# ── Capability matrix (provider → model → ModelCapabilities) ────────────────


class ModelCapabilityMatrix(BaseModel):
    """Mapping of (provider, model) -> ModelCapabilities.

    Loaded from a YAML config file.  Can be overridden via
    ``MODEL_CAPABILITIES_CONFIG_PATH`` env var pointing to a production YAML.
    """

    capabilities: dict[str, dict[str, ModelCapabilities]] = Field(
        default_factory=dict,
        description="Outer key = provider, inner key = model",
    )

    def get_capabilities(self, provider: str, model: str) -> ModelCapabilities | None:
        """Returns ModelCapabilities for (provider, model) or None."""
        # Normalize provider to lowercase (Settings stores it uppercase after validation)
        provider_table = self.capabilities.get(provider.lower())
        if provider_table is None:
            return None
        return provider_table.get(model)

    def list_models_supporting_native_tools(self) -> list[tuple[str, str]]:
        """Returns list of (provider, model) pairs supporting native tool calling."""
        result = []
        for provider, models in self.capabilities.items():
            for model, caps in models.items():
                if caps.supports_native_tools:
                    result.append((provider, model))
        return result

    def list_models_supporting_vision(self) -> list[tuple[str, str]]:
        """Returns list of (provider, model) pairs supporting vision input."""
        result = []
        for provider, models in self.capabilities.items():
            for model, caps in models.items():
                if caps.supports_vision:
                    result.append((provider, model))
        return result

    def find_model_for_context_length(self, min_tokens: int) -> tuple[str, str] | None:
        """Returns first (provider, model) with context_window >= min_tokens."""
        for provider, models in self.capabilities.items():
            for model, caps in models.items():
                if caps.context_window >= min_tokens:
                    return (provider, model)
        return None


# ── Default capabilities (fallback when MODEL_CAPABILITIES_CONFIG_PATH is unset) ─

DEFAULT_CAPABILITIES_YAML = """
# Default model capabilities; override via MODEL_CAPABILITIES_CONFIG_PATH
openai:
  gpt-4o-mini:
    supports_native_tools: true
    supports_streaming: true
    supports_vision: false
    context_window: 128000
    cost_per_1m_tokens:
      prompt: 0.15
      completion: 0.60
    latency_p50_ms: 500
    latency_p99_ms: 1500
    supports_react_emulation: true
    notes: "Default cost-aware choice; good for tool calling"
  gpt-4o:
    supports_native_tools: true
    supports_streaming: true
    supports_vision: true
    context_window: 128000
    cost_per_1m_tokens:
      prompt: 2.50
      completion: 10.00
    latency_p50_ms: 800
    latency_p99_ms: 3000
    supports_react_emulation: true
    notes: "Quality choice; supports vision + native tools"
anthropic:
  claude-3-5-sonnet:
    supports_native_tools: true
    supports_streaming: true
    supports_vision: true
    context_window: 200000
    cost_per_1m_tokens:
      prompt: 3.00
      completion: 15.00
    latency_p50_ms: 1000
    latency_p99_ms: 4000
    supports_react_emulation: true
    notes: "Quality alternative; long context"
  claude-3-haiku:
    supports_native_tools: true
    supports_streaming: true
    supports_vision: false
    context_window: 200000
    cost_per_1m_tokens:
      prompt: 0.25
      completion: 1.25
    latency_p50_ms: 400
    latency_p99_ms: 1200
    supports_react_emulation: true
    notes: "Cost-aware Anthropic alternative"
ollama:
  llama3.1-8b:
    supports_native_tools: false  # No native function calling in Llama 3.1 base
    supports_streaming: true
    supports_vision: false
    context_window: 128000
    cost_per_1m_tokens:
      prompt: 0.0
      completion: 0.0
    latency_p50_ms: 200  # Local inference is fast (no network)
    latency_p99_ms: 1000
    supports_react_emulation: true
    notes: "Phase 4 full integration; ReAct mode required for tools"
custom-openai:
  default:
    supports_native_tools: true  # Assume self-hosted OpenAI-compatible supports tools
    supports_streaming: true
    supports_vision: false
    context_window: 4096
    cost_per_1m_tokens:
      prompt: 0.0
      completion: 0.0
    latency_p50_ms: 300
    latency_p99_ms: 1500
    supports_react_emulation: true
    notes: "Self-hosted via vLLM/LM Studio; capability depends on host"
zai:
  glm-4.5:
    supports_native_tools: true
    supports_streaming: true
    supports_vision: false
    context_window: 128000
    cost_per_1m_tokens:
      prompt: 0.10
      completion: 0.40
    latency_p50_ms: 600
    latency_p99_ms: 2500
    supports_react_emulation: true
    notes: "Zhipu AI GLM-4.5; supports native function calling"
  glm-4-flash:
    supports_native_tools: true
    supports_streaming: true
    supports_vision: false
    context_window: 128000
    cost_per_1m_tokens:
      prompt: 0.10
      completion: 0.40
    latency_p50_ms: 400
    latency_p99_ms: 1800
    supports_react_emulation: true
    notes: "Zhipu AI GLM-4-Flash; faster version"
"""


# ── Singleton + convenience API ───────────────────────────────────────────────

_matrix: ModelCapabilityMatrix | None = None


def get_capability_matrix() -> ModelCapabilityMatrix:
    """Singleton ModelCapabilityMatrix.  Loads from YAML config or defaults (once)."""
    global _matrix
    if _matrix is not None:
        return _matrix
    config_path = os.environ.get("MODEL_CAPABILITIES_CONFIG_PATH")
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            data = yaml.safe_load(f)
        _matrix = ModelCapabilityMatrix.model_validate({"capabilities": data})
        logger.info("Loaded model capabilities from %s", config_path)
    else:
        data = yaml.safe_load(DEFAULT_CAPABILITIES_YAML)
        _matrix = ModelCapabilityMatrix.model_validate({"capabilities": data})
        logger.info("Loaded default model capabilities (built-in)")
    return _matrix
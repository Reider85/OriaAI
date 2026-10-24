"""Unit tests for ModelCapabilityMatrix (Phase 3 ADR-016).

Tests capability loading, provider normalization, filtering, and singleton behavior.
"""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from llm_client.agent.capability_matrix import (
    ModelCapabilities,
    ModelCapabilityMatrix,
    get_capability_matrix,
)

# ── Test fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def custom_caps_path(tmp_path: Path) -> str:
    """Return path to a custom capabilities YAML file for testing."""
    custom_yaml = """
openai:
  gpt-4o-mini:
    supports_native_tools: true
    supports_streaming: true
    supports_vision: false
    context_window: 128000
    cost_per_1m_tokens: {prompt: 0.99, completion: 1.99}
    latency_p50_ms: 300
    latency_p99_ms: 800
    supports_react_emulation: true
    notes: "Test override"
anthropic:
  claude-test:
    supports_native_tools: true
    supports_streaming: true
    supports_vision: true
    context_window: 500000
    cost_per_1m_tokens: {prompt: 1.00, completion: 2.00}
    latency_p50_ms: 200
    latency_p99_ms: 600
    supports_react_emulation: true
    notes: "Test vision model"
"""
    custom_file = tmp_path / "custom_caps.yaml"
    custom_file.write_text(custom_yaml)
    return str(custom_file)


@pytest.fixture(autouse=True)
def reset_capability_matrix_singleton():
    """Reset the singleton between tests."""
    # Clear env var if set by test
    if "MODEL_CAPABILITIES_CONFIG_PATH" in os.environ:
        del os.environ["MODEL_CAPABILITIES_CONFIG_PATH"]
    yield
    # Also clear env var after test
    if "MODEL_CAPABILITIES_CONFIG_PATH" in os.environ:
        del os.environ["MODEL_CAPABILITIES_CONFIG_PATH"]


# ── ModelCapabilities tests ──────────────────────────────────────────────────


def test_model_capabilities_frozen():
    """ModelCapabilities instances should be immutable (frozen=True)."""
    caps = ModelCapabilities(
        supports_native_tools=True,
        context_window=128000,
        cost_per_1m_tokens={"prompt": 0.15, "completion": 0.60}
    )
    with pytest.raises(ValidationError, match="Instance is frozen"):
        caps.supports_native_tools = False


def test_cost_per_1m_tokens_default():
    """ModelCapabilities should have default cost_per_1m_tokens."""
    caps = ModelCapabilities()
    assert caps.cost_per_1m_tokens == {"prompt": 0.0, "completion": 0.0}


# ── ModelCapabilityMatrix tests ───────────────────────────────────────────────


def test_get_capabilities_returns_known_model():
    """get_capabilities should return ModelCapabilities for known (provider, model)."""
    matrix = get_capability_matrix()
    caps = matrix.get_capabilities("openai", "gpt-4o-mini")
    assert caps is not None
    assert caps.supports_native_tools is True
    assert caps.context_window == 128000
    assert caps.cost_per_1m_tokens["prompt"] == 0.15


def test_get_capabilities_returns_none_for_unknown():
    """get_capabilities should return None for unknown (provider, model)."""
    matrix = get_capability_matrix()
    caps = matrix.get_capabilities("openai", "gpt-5")
    assert caps is None


def test_get_capabilities_normalizes_provider_case():
    """get_capabilities should normalize provider to lowercase."""
    matrix = get_capability_matrix()
    # Settings stores provider as UPPERCASE, YAML keys are lowercase
    assert matrix.get_capabilities("OPENAI", "gpt-4o") == matrix.get_capabilities("openai", "gpt-4o")
    assert matrix.get_capabilities("OpenAI", "gpt-4o") == matrix.get_capabilities("openai", "gpt-4o")


def test_list_models_supporting_native_tools():
    """list_models_supporting_native_tools should return all (provider, model) pairs with native tools."""
    matrix = get_capability_matrix()
    models = matrix.list_models_supporting_native_tools()
    # Should include: openai gpt-4o-mini, openai gpt-4o, anthropic claude-3-5-sonnet, anthropic claude-3-haiku, custom-openai default, zai glm-4.5, zai glm-4-flash (7 total)
    assert len(models) == 7
    assert ("openai", "gpt-4o-mini") in models
    assert ("openai", "gpt-4o") in models
    assert ("anthropic", "claude-3-5-sonnet") in models
    assert ("anthropic", "claude-3-haiku") in models
    assert ("custom-openai", "default") in models
    assert ("zai", "glm-4.5") in models
    assert ("zai", "glm-4-flash") in models
    # Should NOT include ollama llama3.1-8b (native=false)
    assert ("ollama", "llama3.1-8b") not in models


def test_list_models_supporting_vision():
    """list_models_supporting_vision should return only vision-capable models."""
    matrix = get_capability_matrix()
    models = matrix.list_models_supporting_vision()
    # Should be exactly: openai gpt-4o, anthropic claude-3-5-sonnet (2 total)
    assert len(models) == 2
    assert ("openai", "gpt-4o") in models
    assert ("anthropic", "claude-3-5-sonnet") in models
    # Should NOT include others
    assert ("openai", "gpt-4o-mini") not in models
    assert ("anthropic", "claude-3-haiku") not in models
    assert ("zai", "glm-4.5") not in models


def test_find_model_for_context_length():
    """find_model_for_context_length should return first model with sufficient context."""
    matrix = get_capability_matrix()
    # 150000 tokens: gpt-4o-mini/claude-3-5-sonnet have 128k/200k; claude-3-5-sonnet is first in iteration order
    result = matrix.find_model_for_context_length(150000)
    assert result == ("anthropic", "claude-3-5-sonnet")
    
    # 200000 tokens: claude-3-5-sonnet is exact match
    result = matrix.find_model_for_context_length(200000)
    assert result == ("anthropic", "claude-3-5-sonnet")
    
    # 300000 tokens: no model has this much context
    result = matrix.find_model_for_context_length(300000)
    assert result is None
    
    # 1000 tokens: gpt-4o-mini is first (128k >= 1000)
    result = matrix.find_model_for_context_length(1000)
    assert result == ("openai", "gpt-4o-mini")


def test_ollama_llama_no_native_tools():
    """ollama/llama3.1-8b should not support native tools (ReAct mode required)."""
    matrix = get_capability_matrix()
    caps = matrix.get_capabilities("ollama", "llama3.1-8b")
    assert caps is not None
    assert caps.supports_native_tools is False
    assert caps.supports_react_emulation is True


def test_load_from_yaml_config_path(custom_caps_path: str):
    """Should load from MODEL_CAPABILITIES_CONFIG_PATH when set."""
    # Ensure no env var is set
    if "MODEL_CAPABILITIES_CONFIG_PATH" in os.environ:
        del os.environ["MODEL_CAPABILITIES_CONFIG_PATH"]

    # Set env var and load
    os.environ["MODEL_CAPABILITIES_CONFIG_PATH"] = custom_caps_path
    try:
        # Force reload by resetting (global variable)
        import llm_client.agent.capability_matrix as cm
        cm._matrix = None
        matrix = get_capability_matrix()
        # Should have loaded custom values, not defaults
        caps = matrix.get_capabilities("openai", "gpt-4o-mini")
        assert caps is not None
        assert caps.cost_per_1m_tokens["prompt"] == 0.99  # Not 0.15 (default)
        assert caps.supports_vision is False  # Override from custom_caps
        # Should have custom vision model
        vision_caps = matrix.get_capabilities("anthropic", "claude-test")
        assert vision_caps is not None
        assert vision_caps.supports_vision is True
        assert vision_caps.context_window == 500000
        # Should not have default zai models
        assert matrix.get_capabilities("zai", "glm-4.5") is None
    finally:
        del os.environ["MODEL_CAPABILITIES_CONFIG_PATH"]


def test_load_from_yaml_config_path_file_not_found():
    """Should gracefully handle missing MODEL_CAPABILITIES_CONFIG_PATH file."""
    os.environ["MODEL_CAPABILITIES_CONFIG_PATH"] = "/nonexistent/path/caps.yaml"
    try:
        # Force reload by resetting (global variable)
        import llm_client.agent.capability_matrix as cm
        cm._matrix = None
        matrix = get_capability_matrix()
        # Should load defaults instead
        caps = matrix.get_capabilities("openai", "gpt-4o-mini")
        assert caps is not None
        assert caps.cost_per_1m_tokens["prompt"] == 0.15  # Default value
    finally:
        del os.environ["MODEL_CAPABILITIES_CONFIG_PATH"]


def test_load_default_when_no_env_set():
    """Should load defaults when MODEL_CAPABILITIES_CONFIG_PATH is not set."""
    # Ensure no env var is set
    if "MODEL_CAPABILITIES_CONFIG_PATH" in os.environ:
        del os.environ["MODEL_CAPABILITIES_CONFIG_PATH"]
    # Force reload by resetting (global variable)
    import llm_client.agent.capability_matrix as cm
    cm._matrix = None
    matrix = get_capability_matrix()
    # Should have default values
    caps = matrix.get_capabilities("openai", "gpt-4o-mini")
    assert caps is not None
    assert caps.cost_per_1m_tokens["prompt"] == 0.15
    assert caps.supports_native_tools is True


def test_singleton_behavior():
    """get_capability_matrix should return the same instance (singleton)."""
    matrix1 = get_capability_matrix()
    matrix2 = get_capability_matrix()
    assert matrix1 is matrix2
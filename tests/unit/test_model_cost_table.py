"""Unit tests for ModelCostTable (Phase 3 ADR-015).

Tests cost calculation, loading, provider normalization, and singleton behavior.
"""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from llm_client.agent.model_cost_table import (
    ModelCost,
    ModelCostTable,
    compute_call_cost,
    get_model_cost_table,
)

# ── Test fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def custom_costs_path(tmp_path: Path) -> str:
    """Return path to a custom costs YAML file for testing."""
    custom_yaml = """
openai:
  gpt-4o-mini:
    prompt: 0.99
    completion: 1.99
anthropic:
  claude-test:
    prompt: 1.00
    completion: 2.00
"""
    custom_file = tmp_path / "custom_costs.yaml"
    custom_file.write_text(custom_yaml)
    return str(custom_file)


@pytest.fixture(autouse=True)
def reset_model_cost_table_singleton():
    """Reset the singleton between tests."""
    # Clear env var if set by test
    if "MODEL_COSTS_CONFIG_PATH" in os.environ:
        del os.environ["MODEL_COSTS_CONFIG_PATH"]
    yield
    # Also clear env var after test
    if "MODEL_COSTS_CONFIG_PATH" in os.environ:
        del os.environ["MODEL_COSTS_CONFIG_PATH"]


# ── ModelCost tests ──────────────────────────────────────────────────────────


def test_model_cost_frozen():
    """ModelCost instances should be immutable (frozen=True)."""
    cost = ModelCost(prompt=0.15, completion=0.60)
    with pytest.raises(ValidationError, match="Instance is frozen"):
        cost.prompt = 0.99


def test_cost_for_computes_correctly():
    """ModelCost.cost_for should return the correct USD value."""
    cost = ModelCost(prompt=0.15, completion=0.60)
    # 1M prompt + 500k completion = $0.15 + $0.30 = $0.45
    result = cost.cost_for(1_000_000, 500_000)
    assert abs(result - 0.45) < 1e-10


# ── ModelCostTable tests ─────────────────────────────────────────────────────


def test_get_cost_returns_known_model():
    """get_cost should return ModelCost for known (provider, model)."""
    table = get_model_cost_table()
    cost = table.get_cost("openai", "gpt-4o-mini")
    assert cost is not None
    assert cost.prompt == 0.15
    assert cost.completion == 0.60


def test_get_cost_returns_none_for_unknown():
    """get_cost should return None for unknown (provider, model)."""
    table = get_model_cost_table()
    cost = table.get_cost("openai", "gpt-5")
    assert cost is None


def test_get_cost_normalizes_provider_case():
    """get_cost should normalize provider to lowercase."""
    table = get_model_cost_table()
    # Settings stores provider as UPPERCASE, YAML keys are lowercase
    assert table.get_cost("OPENAI", "gpt-4o") == table.get_cost("openai", "gpt-4o")
    assert table.get_cost("OpenAI", "gpt-4o") == table.get_cost("openai", "gpt-4o")


def test_list_models_all_pairs():
    """list_models should return all (provider, model) pairs."""
    table = get_model_cost_table()
    models = table.list_models()
    # Default has openai (3), anthropic (2), custom-openai (1), ollama (1), zai (2)
    assert len(models) == 9
    assert ("openai", "gpt-4o-mini") in models
    assert ("anthropic", "claude-3-5-sonnet") in models
    assert ("zai", "glm-4.5") in models


def test_list_models_filtered_by_provider():
    """list_models should filter by provider when specified."""
    table = get_model_cost_table()
    openai_models = table.list_models("openai")
    assert all(p == "openai" for p, _ in openai_models)
    assert len(openai_models) == 3
    assert ("openai", "gpt-4o-mini") in openai_models
    assert ("openai", "gpt-4o") in openai_models
    assert ("openai", "gpt-4-turbo") in openai_models


def test_cheapest_model_returns_zero_cost():
    """cheapest_model should return zero-cost model (custom-openai default)."""
    table = get_model_cost_table()
    cheapest = table.cheapest_model()
    assert cheapest == ("custom-openai", "default")
    # Double-check it's actually the cheapest
    cost = table.get_cost(*cheapest)
    assert cost is not None
    assert cost.prompt == 0.0
    assert cost.completion == 0.0


def test_cheapest_model_filtered_by_provider():
    """cheapest_model should work when provider is specified."""
    table = get_model_cost_table()
    cheapest_openai = table.cheapest_model("openai")
    assert cheapest_openai == ("openai", "gpt-4o-mini")
    # Check it's not the overall cheapest (which is ollama)
    assert cheapest_openai != table.cheapest_model()


def test_cheapest_model_no_models():
    """cheapest_model should return None when no models exist."""
    empty_table = ModelCostTable()
    assert empty_table.cheapest_model() is None


# ── compute_call_cost tests ──────────────────────────────────────────────────


def test_compute_call_cost_known_model():
    """compute_call_cost should return correct cost for known model."""
    cost = compute_call_cost("openai", "gpt-4o-mini", 1000, 500)
    # 1000 prompt * $0.15/1M = $0.00015
    # 500 completion * $0.60/1M = $0.00030
    # Total = $0.00045
    assert abs(cost - 0.00045) < 1e-10


def test_compute_call_cost_zero_for_unknown_model(caplog):
    """compute_call_cost should return 0.0 for unknown model with warning."""
    cost = compute_call_cost("unknown", "mystery-model", 1000, 500)
    assert cost == 0.0
    assert "Unknown model unknown/mystery-model" in caplog.text


def test_compute_call_cost_unknown_provider(caplog):
    """compute_call_cost should return 0.0 for unknown provider with warning."""
    cost = compute_call_cost("nonexistent", "gpt-4o", 1000, 500)
    assert cost == 0.0
    assert "Unknown model nonexistent/gpt-4o" in caplog.text


# ── Loading tests ───────────────────────────────────────────────────────────


def test_load_from_yaml_config_path(custom_costs_path: str):
    """Should load from MODEL_COSTS_CONFIG_PATH when set."""
    # Ensure no env var is set
    if "MODEL_COSTS_CONFIG_PATH" in os.environ:
        del os.environ["MODEL_COSTS_CONFIG_PATH"]
    
    # Set env var and load
    os.environ["MODEL_COSTS_CONFIG_PATH"] = custom_costs_path
    try:
        # Force reload by resetting (global variable)
        import llm_client.agent.model_cost_table as mct
        mct._table = None
        table = get_model_cost_table()
        # Should have loaded custom values, not defaults
        cost = table.get_cost("openai", "gpt-4o-mini")
        assert cost is not None
        assert cost.prompt == 0.99  # Not 0.15 (default)
        assert cost.completion == 1.99  # Not 0.60 (default)
        # Should not have default zai models
        assert table.get_cost("zai", "glm-4.5") is None
    finally:
        del os.environ["MODEL_COSTS_CONFIG_PATH"]


def test_load_from_yaml_config_path_file_not_found():
    """Should gracefully handle missing MODEL_COSTS_CONFIG_PATH file."""
    os.environ["MODEL_COSTS_CONFIG_PATH"] = "/nonexistent/path/costs.yaml"
    try:
        table = get_model_cost_table()
        # Should load defaults instead
        cost = table.get_cost("openai", "gpt-4o-mini")
        assert cost is not None
        assert cost.prompt == 0.15  # Default value
    finally:
        del os.environ["MODEL_COSTS_CONFIG_PATH"]


def test_load_default_when_no_env_set():
    """Should load defaults when MODEL_COSTS_CONFIG_PATH is not set."""
    # Ensure no env var is set
    if "MODEL_COSTS_CONFIG_PATH" in os.environ:
        del os.environ["MODEL_COSTS_CONFIG_PATH"]
    table = get_model_cost_table()
    # Should have default values
    cost = table.get_cost("openai", "gpt-4o-mini")
    assert cost is not None
    assert cost.prompt == 0.15
    assert cost.completion == 0.60


def test_singleton_behavior():
    """get_model_cost_table should return the same instance (singleton)."""
    table1 = get_model_cost_table()
    table2 = get_model_cost_table()
    assert table1 is table2



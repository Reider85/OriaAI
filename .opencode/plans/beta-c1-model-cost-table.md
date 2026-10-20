# План: BETA-PROMPTS.md C-1 — `ModelCostTable`

Статус: план принят пользователем, ожидает выхода из plan mode для реализации.

## Ключевые решения

| Вопрос | Решение | Почему |
|---|---|---|
| Имена ключей цен | `prompt`/`completion` (как в спеке), не `input`/`output` как в живом hardcode | Совпадают с `prompt_tokens`/`completion_tokens` в `compute_call_cost` и метками `token_type` в `llm_metrics.py` |
| `_COST_PER_1M` + `_estimate_cost` | Удалить полностью, обновить 2 теста `TestCostEstimation` → `compute_call_cost` | Антипаттерн спеки; числовая точность для gpt-4o-mini/gpt-4o сохраняется |
| Provider-нормализация | `get_cost`/`compute_call_cost` нормализуют provider через `.lower()` | `Settings` нормализует `llm_provider` в UPPERCASE, YAML-ключи lowercase |
| Путь конфига | `os.environ.get("MODEL_COSTS_CONFIG_PATH")` (как в спеке), без нового поля Settings | Модуль самодостаточен; C-2/C-3 добавят router-настройки в Settings |
| ZAI-модели в дефолтном YAML | Добавить `glm-4.5` (default в Settings) плюс `glm-4-flash` из спеки | Иначе дефолтная ZAI-модель даст "unknown model" warning |

## Изменения по файлам

### 1. Новый `src/llm_client/agent/model_cost_table.py`

Содержимое (полный код):

```python
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
```

### 2. `src/llm_client/agent/provider.py`

- Удалить строки 31–44 (секция `_COST_PER_1M` + `_estimate_cost`), заменив на комментарий-указатель:
  ```python
  # ── Cost estimation — Phase 3 ADR-015: see model_cost_table.compute_call_cost ──
  ```
- В `TokenUsageTracker.on_llm_end` (строка 93) заменить:
  ```python
  cost = _estimate_cost(model, prompt_tokens, completion_tokens)
  ```
  на:
  ```python
  from .model_cost_table import compute_call_cost

  cost = compute_call_cost(self._provider, model, prompt_tokens, completion_tokens)
  ```
- Остальное (operational stream write, Prometheus `record_llm_call`) — не трогать.

### 3. Новый `config/model_costs.yaml`

```yaml
# Model costs (USD per 1M tokens) — production override
# Update monthly based on provider pricing pages.
openai:
  gpt-4o-mini:
    prompt: 0.15
    completion: 0.60
  gpt-4o:
    prompt: 2.50
    completion: 10.00
anthropic:
  claude-3-5-sonnet:
    prompt: 3.00
    completion: 15.00
  claude-3-haiku:
    prompt: 0.25
    completion: 1.25
ollama:
  llama3.1-8b:
    prompt: 0.0
    completion: 0.0
```

Директории `config/` сейчас нет — создать.

### 4. `pyproject.toml`

Добавить `"pyyaml>=6.0",` в `[project] dependencies` (после `prometheus-client>=0.20.0`, строка 36) — сейчас отсутствует.

### 5. `src/llm_client/agent/test_provider.py` — `TestCostEstimation`

```python
class TestCostEstimation:
    def test_known_model_cost(self):
        from llm_client.agent.model_cost_table import compute_call_cost

        cost = compute_call_cost("openai", "gpt-4o-mini", 1000, 500)
        # gpt-4o-mini: prompt $0.15/1M, completion $0.60/1M
        expected = (1000 * 0.15 + 500 * 0.60) / 1_000_000
        assert abs(cost - expected) < 1e-10

    def test_unknown_model_cost_zero(self):
        from llm_client.agent.model_cost_table import compute_call_cost

        cost = compute_call_cost("unknown", "mystery-model", 1000, 500)
        assert cost == 0.0
```

### 6. Новый `tests/unit/test_model_cost_table.py`

Фикстура: сброс синглтона `_table` (monkeypatch на None) + очистка `MODEL_COSTS_CONFIG_PATH` после каждого теста.

Тесты:
- `test_get_cost_returns_known_model` — `("openai", "gpt-4o-mini")` → `ModelCost(prompt=0.15, completion=0.60)`.
- `test_get_cost_returns_none_for_unknown` — `("openai", "gpt-5")` → `None`.
- `test_get_cost_normalizes_provider_case` — `("OPENAI", "gpt-4o")` == `("openai", "gpt-4o")`.
- `test_cost_for_computes_correctly` — 1M prompt + 500k completion → `0.45`.
- `test_list_models_filtered_by_provider` — ровно 3 openai-пары.
- `test_cheapest_model_returns_zero_cost` — `("ollama", "llama3.1-8b")`.
- `test_load_from_yaml_config_path` — env `MODEL_COSTS_CONFIG_PATH` на фикстуру `tests/fixtures/custom_costs.yaml`; проверить загруженные значения (не дефолт).
- `test_compute_call_cost_zero_for_unknown_model` — `0.0` + warning (caplog).
- `test_model_cost_frozen` — `ModelCost` immutable (pydantic `ValidationError` при попытке изменения).

Фикстура `tests/fixtures/custom_costs.yaml`:

```yaml
# Test fixture — custom model costs
openai:
  gpt-4o-mini:
    prompt: 0.99
    completion: 1.99
anthropic:
  claude-test:
    prompt: 1.00
    completion: 2.00
```

## Верификация

```bash
.\.venv\Scripts\python.exe -m pytest tests/unit/test_model_cost_table.py src/llm_client/agent/test_provider.py tests/unit/test_llm_metrics.py -v
ruff check src tests && ruff format --check src tests && mypy src/llm_client
.\.venv\Scripts\python.exe -m pytest tests/unit -v
```

Критерий: `compute_call_cost("openai", "gpt-4o", …)` возвращает те же значения, что и старый hardcode; регрессии `test_provider.py`/`test_llm_metrics.py` исключены.

## Антипаттерны спеки (контроль)

- ✅ hardcode удалён, не fallback
- ✅ цены только в YAML/DEFAULT_COSTS_YAML
- ✅ `ModelCost` frozen (`ConfigDict(frozen=True)`)
- ✅ `cheapest_model()` реализован (для C-3 CostGuard)
- ✅ `ge=0.0` guard на полях
- ✅ YAML грузится один раз (синглтон `_table`)

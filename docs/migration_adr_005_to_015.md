# Migration Plan: ADR-005 fallback_chain → ADR-015 LLMRouter

**Supersedes**: ADR-005 (fallback_chain part — упраздняется, replaced by ADR-015 cost-aware routing).
**Reason**: ADR-005 fallback_chain не поддерживает cost predictability (C-7 contradiction), load balancing, cost guard на 80% budget. ADR-015 решает все эти проблемы.

## Migration steps

### Step 1 (Phase 3 начало): Shadow mode
- `LLMRouter` развёрнут в **shadow mode**: каждый LLM call идёт через существующий `LLMProviderFactory.create()` (без изменений),
  но параллельно `LLMRouter.route()` вычисляется и логируется (не используется для routing).
- Сравнение: что router выбрал бы vs что фактически было.
- Длительность: 1 месяц (per ROADMAP §14.1 pilot criterion).

### Step 2 (Phase 3 середина): Gradual cutover
- 5% трафика routed via `LLMRouter` (feature flag `LLM_ROUTER_ENABLED=true`, `LLM_ROUTER_TRAFFIC_PERCENT=5`).
- Мониторинг: error rate, latency, cost. Если error rate +2pct → rollback to 0%.

### Step 3 (Phase 3 конец): Full cutover
- 100% трафика via `LLMRouter`. `LLMProviderFactory.create()` вызывается только через `LLMRouter.create_llm(decision)`.
- Прямые вызовы `LLMProviderFactory.create()` в graph code заменены на `router.create_llm(decision)`.
- `fallback_chain` pattern (hardcoded openai→anthropic в `provider.py`) удалён (или deprecated comment).

### Step 4 (Phase 4): Cleanup
- Deprecated comment "fallback_chain — Phase 3 (ADR-015)" удалён из `provider.py` строка 422.
- `_COST_PER_1M` hardcode (строки 32-35) удалён (Блок C-1 `ModelCostTable` полностью заменил).

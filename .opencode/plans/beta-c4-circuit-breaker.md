# План: BETA-PROMPTS.md C-4 — `CircuitBreaker`

Статус: план принят пользователем, реализация начата.

## Ключевые решения

| Вопрос | Решение | Почему |
|---|---|---|
| Чтение gauge | Прямой доступ `LLM_ERROR_RATE.labels(provider=...)._value.get()` вместо exposition-парсинга из спеки | O(1) в hot path (антипаттерн: не блокировать check); уже так делает существующий C-2; отсутствующая метка автоматически даёт 0.0 (graceful) |
| Порог 0.5 | Новое поле Settings `llm_circuit_breaker_error_threshold: float = 0.5` + валидация `0 < x <= 1` | Антипаттерн спеки: «НЕ хардкодь 0.5 threshold» |
| Поле `consecutive_failures` | Переименовать в `consecutive_trial_successes` (в HALF_OPEN считает успехи) | В спеке поле называется failures, но `record_success` его инкрементирует — семантически неверно; DoD не фиксирует имена полей |
| Где живёт collector-логика | `src/llm_client/observability/error_rate_collector.py`; `scripts/circuit_breaker_metrics_collector.py` — тонкая CLI-обёртка | Dockerfile.agent копирует только `src/`+`migrations/` — service не может импортировать `scripts/` |
| Запуск collector | `asyncio.create_task` в `service.py:_startup`, хранить на `app.state`, cancel в `_shutdown` | Спека разрешает Phase 3 create_task на startup (Celery — Phase 4) |
| `record_success`/`record_failure` | Вызовы из `TokenUsageTracker.on_llm_end` / `on_llm_error` (try/except debug) | Антипаттерн: без них breaker застрянет в OPEN/HALF_OPEN forever |
| Известное огранишение | Collector считает error rate из кумулятивных counter'ов (весь uptime), не true rolling 5m | Ровно так делает код спеки; true rolling window — Phase 4 (Prometheus HTTP API), заявлено в «Расширяется в» |

## Изменения по файлам

### 1. Новый `src/llm_client/agent/circuit_breaker.py`
Код из спеки (§ C-4 задача 1) с правками:
- `CircuitState` (CLOSED/OPEN/HALF_OPEN), `CircuitStatus` dataclass (`provider`, `state`, `error_rate_5m`, `last_state_change`, `consecutive_trial_successes`)
- `CircuitBreaker`: `ERROR_RATE_THRESHOLD` берётся из `settings.llm_circuit_breaker_error_threshold` (лениво в `__init__`), `COOLDOWN_SECONDS=60`, `TRIAL_SUCCESS_THRESHOLD=3`; методы `check()` / `record_success()` / `record_failure()`; `_read_error_rate()` — прямой gauge access
- Синглтон `get_circuit_breaker()`

### 2. Новый `src/llm_client/observability/error_rate_collector.py`
`collect_error_rates()` (агрегация `llm_call_total` по provider → `update_error_rate`) + `run_collector_loop(interval_seconds=30)` с graceful exit.

### 3. Новый `scripts/circuit_breaker_metrics_collector.py`
Тонкая обёртка: `asyncio.run(run_collector_loop())`.

### 4. `src/llm_client/config.py`
+ `llm_circuit_breaker_error_threshold: float = 0.5` (блок Phase 3 ADR-015, строка ~98) + валидация в `_validate_environment` (аналогично `llm_router_cost_guard_threshold`).

### 5. `.env.example`
+ `LLM_CIRCUIT_BREAKER_ERROR_THRESHOLD=0.5` (после router-секции, строка ~49).

### 6. `src/llm_client/agent/router.py`
`_check_circuit_breaker` → `status = await get_circuit_breaker().check(provider); return status.state == CircuitState.OPEN`. Удалить неиспользуемый import `LLM_ERROR_RATE` (строка 25).

### 7. `src/llm_client/agent/provider.py`
В `TokenUsageTracker.on_llm_end` → `await get_circuit_breaker().record_success(self._provider)`; в `on_llm_error` → `record_failure(...)`. Обёрнуто в try/except debug (как существующие вызовы).

### 8. `src/llm_client/agent/service.py`
В `_startup()`: `app.state.cb_collector_task = asyncio.create_task(run_collector_loop())`. В `_shutdown()`: cancel + await с подавлением `CancelledError`.

### 9. Новый `tests/unit/test_circuit_breaker.py`
Тесты по DoD (с фикстурой сброса синглтона `_breaker = None` и очисткой gauge):
- `test_check_returns_closed_initial_state`
- `test_check_opens_on_high_error_rate` (gauge=0.6 → OPEN)
- `test_check_half_open_after_cooldown` (подмена времени или ручной сдвиг `last_state_change`)
- `test_record_success_in_half_open_closes_after_3`
- `test_record_failure_in_half_open_reopens`
- `test_read_gauge_returns_zero_on_missing`
- `test_collector_updates_gauge` (интеграционный: `record_llm_call` ошибок → `collect_error_rates` → gauge > 0)

### 10. Обновить существующие тесты (регрессионный риск!)
Они патчат `llm_client.agent.router.LLM_ERROR_RATE`, который перестанет использоваться:
- `tests/unit/test_llm_router.py:111` `test_circuit_breaker_active_falls_back_to_alternative` — вместо патча ставить реальный gauge `LLM_ERROR_RATE.labels(provider="openai").set(0.6)` + сброс синглтона breaker
- `tests/integration/test_llm_router_integration.py:240` `test_integration_error_handling_circuit_breaker` — адаптировать под новый путь чтения

## Верификация

```bash
.\.venv\Scripts\python.exe -m pytest tests/unit/test_circuit_breaker.py tests/unit/test_llm_router.py tests/integration/test_llm_router_integration.py tests/unit/test_llm_metrics.py -v
ruff check src tests && ruff format --check src tests && mypy src/llm_client
.\.venv\Scripts\python.exe -m pytest tests/unit -v
```

## Антипаттерны спеки (контроль)
- ✅ check() — async, in-memory lock, без HTTP
- ✅ COOLDOWN=60s ≤ 5min; TRIAL_SUCCESS=3 ≤ 5
- ✅ threshold из Settings, не хардкод
- ✅ record_success/record_failure заведены в TokenUsageTracker
- ✅ collector — create_task на startup, не в hot path
- ✅ НЕ пишет в forensic stream; НЕ трогает ADR-010/013
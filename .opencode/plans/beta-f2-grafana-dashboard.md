# Plan: BETA-PROMPTS.md F-2 — Grafana dashboard `llm-cost-router.json` (Phase 3 control point)

**Prompt:** `analytics/BETA-PROMPTS.md` §8, F-2 (lines 7350–7506)
**DoD target:** dashboard с 9 панелями в папке "Phase 3", provider.yml обновлён, 3+ unit-теста зелёные.

## Текущее состояние (предусловия выполнены)

| Предусловие | Статус |
|---|---|
| A-2: `src/llm_client/observability/llm_metrics.py` — все метрики | ✅ готово (`llm_call_total`, `llm_tokens_total`, `llm_cost_usd_total`, `llm_call_latency_seconds`, `llm_error_rate_5m`, `llm_monthly_budget_usage_ratio`, `semantic_cache_hits_total`, `router_decisions_total`) |
| C-7: `record_router_decision` + `router_metrics_logger.py` | ✅ готово |
| `/metrics` endpoint экспонирует llm_metrics REGISTRY | ✅ `service.py:499` |
| F-1: ARCHITECT.md v1.4.0 | ✅ выполнен (незакоммичен) |
| idealidad exporter поддерживает Phase 3 | ✅ `idealidad.py`: `PHASE_CAPABILITIES["Phase 3"]` = 4, `PHASE_NEW_COMPLEXITY["Phase 3"]` = 2 → `llm_client_idealidad_ratio{phase="Phase 3"}` = 2.0 |
| `ops/grafana/dashboards/llm-cost-router.json` | ⚠️ заглушка C-7: 3 панели, нет uid/gridPos/datasource/id — F-2 расширяет до 9 панелей |
| `tests/unit/test_grafana_dashboard_llm_cost_router.py` | ❌ отсутствует — создать |

**Проблемы наивного sketch из промпта (будут исправлены):**
1. Невалидный PromQL: `sum(...[24h])` / `sum by (policy) (router_decisions_total[1h])` → `sum(increase(...[24h]))` / `sum by (policy) (increase(...[1h]))`
2. Panel type `"bar"` не существует в Grafana → `barchart`
3. Второй provider с тем же путём (task 2 промпта) → конфликт uid → **заменено** на реструктуризацию в подпапки (согласовано с пользователем)

## Согласованные решения

1. **Folder strategy:** реструктуризация `ops/grafana/dashboards/` в подпапки `Architecture/` + `Phase 3/`, один provider с `foldersFromFilesStructure: true` — папки ровно "Architecture" и "Phase 3", без дублей uid.
2. **Ideality panel:** реальная метрика `llm_client_idealidad_ratio{phase="Phase 3"}` (как Phase 2 в `idealidad.json`), а не hardcoded `4/2`.

## Шаги

### 1. Реструктуризация dashboard-папок

- `git mv` (сохранить историю):
  - `ops/grafana/dashboards/idealidad.json` → `ops/grafana/dashboards/Architecture/idealidad.json`
  - `checkpoint-latency.json`, `checkpoint-recovery.json`, `hybrid-recall.json` →同樣 в `Architecture/`
  - `llm-cost-router.json` → `ops/grafana/dashboards/Phase 3/llm-cost-router.json`
- Обновить `ops/grafana/provisioning/dashboards/provider.yml`:
  ```yaml
  apiVersion: 1
  providers:
    - name: 'Dashboards'
      orgId: 1
      type: file
      disableDeletion: false
      updateIntervalSeconds: 30
      allowUiUpdates: true
      options:
        path: /var/lib/grafana/dashboards
        foldersFromFilesStructure: true
  ```
- Обновить путь в `tests/unit/test_phase2_idealidad_f2.py:20` (`DASHBOARD_PATH` → `Architecture/idealidad.json`) — единственный код-референс на старые пути (проверено grep).

### 2. Полная перезапись `ops/grafana/dashboards/Phase 3/llm-cost-router.json`

Конвенции — по образцу `idealidad.json`/`checkpoint-latency.json`: `uid: "llm-cost-router"`, `schemaVersion: 39`, `timezone: "utc"`, `refresh: "30s"`, `time: now-1h`, tags `["phase-3", "router", "cache", "adr-011", "adr-015", "adr-016"]`, datasource `{"type":"prometheus","uid":"prometheus"}` на каждой target, `id: 1..9`, `refId`, `legendFormat`.

9 панелей (gridPos из prompt sketch, PromQL исправлен):

| # | Title | Type | Expr (исправленный) | gridPos |
|---|---|---|---|---|
| 1 | Router Decisions by Policy (last 1h) | pie | `sum by (policy) (increase(router_decisions_total[1h]))` | h8 w6 x0 y0 |
| 2 | Cost Guard Triggers (last 24h) | stat | `sum(increase(router_decisions_total{reason=~".*Budget.*"}[24h]))` | h4 w4 x6 y0 |
| 3 | Circuit Breaker Activations (last 1h) | stat | `sum(increase(router_decisions_total{circuit_breaker_active="true"}[1h]))` | h4 w4 x10 y0 |
| 4 | Monthly Budget Usage | gauge | `llm_monthly_budget_usage_ratio`; thresholds: base green, 0.8 orange, 1.0 red | h4 w4 x14 y0 |
| 5 | LLM Calls by Provider/Model (last 1h) | barchart (не "bar") | `sum by (provider, model) (increase(llm_call_total[1h]))` | h8 w12 x0 y8 |
| 6 | LLM Latency p50/p99 | timeseries | `histogram_quantile(0.5, sum by (le) (rate(llm_call_latency_seconds_bucket[5m])))` + p99 | h8 w12 x12 y8 |
| 7 | Semantic Cache Hit/Miss/Stale Rate | timeseries | 3 expr: `sum(rate(semantic_cache_hits_total{status="hit"}[5m])) / sum(rate(semantic_cache_hits_total[5m]))` (+ miss, stale), legendFormat hit/miss/stale | h8 w12 x0 y16 |
| 8 | Tool Calling Mode Distribution | pie | `sum by (mode) (increase(llm_call_total[1h]))` | h8 w12 x12 y16 |
| 9 | Phase 3 Ideality Metric (Δф/Δсложности) | stat | `llm_client_idealidad_ratio{phase="Phase 3"}` (+ опц. `llm_client_phase_min_required{phase="Phase 3"}`); thresholds: base red, 1.0 yellow, 1.5 green | h4 w6 x0 y24 |

Antipattern-соответствие: только относительные ranges (`[5m]`,`[1h]`,`[24h]`); `refresh: 30s`; ideality — stat panel с реальной метрикой (не const PromQL).

### 3. Тесты `tests/unit/test_grafana_dashboard_llm_cost_router.py`

По образцу `test_phase2_idealidad_f2.py::TestGrafanaDashboardF2` (json load + structural asserts):

- `test_dashboard_json_valid` — JSON парсится, есть `panels`/`uid`/`schemaVersion`.
- `test_dashboard_contains_required_panels` — titles содержат: "Router Decisions", "Cost Guard", "Circuit Breaker", "Budget Usage", "LLM Calls", "Latency", "Semantic Cache", "Tool Calling Mode", "Ideality Metric"; ровно 9 панелей.
- `test_panels_have_valid_prometheus_queries` — каждый target: непустой `expr`, есть `datasource.uid == "prometheus"`, `refId`.
- `test_dashboard_structure_conventions` — uid `"llm-cost-router"`, tags содержат `"phase-3"`, `refresh == "30s"`, все `id` уникальны 1..9, нет абсолютных time ranges в expr (regex `[0-9]{4}-` отсутствует).
- `test_metric_names_match_llm_metrics_module` — имена метрик в expr существуют в `llm_client.observability.llm_metrics` / idealidad exporter: `llm_call_total`, `router_decisions_total`, `llm_monthly_budget_usage_ratio`, `semantic_cache_hits_total`, `llm_client_idealidad_ratio` — защита от drift.
- `test_provider_yml_folders_from_files_structure` — `provider.yml` содержит `foldersFromFilesStructure: true` и `path: /var/lib/grafana/dashboards`.
- `test_phase3_folder_contains_dashboard` — файл существует именно в `ops/grafana/dashboards/Phase 3/`.

### 4. Верификация

1. `ruff check tests` + `ruff format --check` (затронуты только ops JSON/YAML + tests; src не меняется)
2. `.\.venv\Scripts\python.exe -m pytest tests/unit/test_grafana_dashboard_llm_cost_router.py tests/unit/test_phase2_idealidad_f2.py -v` — все зелёные (регрессия Phase 2 дашборда проверена)
3. Опционально (если Docker доступен): `docker-compose up -d grafana prometheus` → `curl` Grafana API `http://localhost:3000/api/search?query=Cost-Aware` → verify folder "Phase 3"; затем откатить контейнеры, если не были запущены.

## Изменяемые файлы (полный список)

| Файл | Действие |
|---|---|
| `ops/grafana/dashboards/Architecture/{idealidad,checkpoint-latency,checkpoint-recovery,hybrid-recall}.json` | git mv |
| `ops/grafana/dashboards/Phase 3/llm-cost-router.json` | git mv + полная перезапись (9 panels) |
| `ops/grafana/provisioning/dashboards/provider.yml` | rewrite (foldersFromFilesStructure) |
| `tests/unit/test_grafana_dashboard_llm_cost_router.py` | create |
| `tests/unit/test_phase2_idealidad_f2.py` | edit DASHBOARD_PATH (1 строка) |

**Не трогаем:** `llm_metrics.py` (полон), alerting rules, `service.py`, docker-compose (монтирование `./ops/grafana/dashboards` рекурсивно уже работает).

## Out of scope

- Коммиты (не запрошены; в рабочем дереве уже есть незакоммиченный Phase 3 WIP — не смешивать)
- Phase 3 alerting rules (не в F-2)
- Изменения src/ (F-2 — чисто ops + tests)

## Risks

- Пробел в имени папки `Phase 3` — поддержан Grafana и Docker mounts; юнит-тесты читают через `pathlib` (пробелы ок).
- `foldersFromFilesStructure: true` переносит существующие дашборды в папку "Architecture" (поведение подтверждено документацией Grafana 11; текущий provider уже назначал эту папку явно — визуально ничего не меняется).
- Незакоммиченный WIP в дереве: изменения F-2 изолированы в 5 файлах выше, не пересекаются с WIP-файлами.

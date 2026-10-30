# Migration Plan: ADR-005 fallback_chain → ADR-015 LLMRouter

**Supersedes**: ADR-005 (fallback_chain part — упраздняется, replaced by ADR-015 cost-aware routing).
**Reason**: ADR-005 fallback_chain не поддерживает cost predictability (C-7 contradiction), load balancing, cost guard на 80% budget. ADR-015 решает все эти проблемы.

**Owner**: OriaAI Dev (oriaai@dev.local)
**Status**: Step 1 pending (start 2026-11-03)

## Schedule

| Step | Название | Окно | Gate для перехода |
|------|----------|------|-------------------|
| 1 | Shadow Mode (1 месяц чистого shadow) | 2026-11-03 → 2026-12-01 | PILOT PASS (`exit code 0`) per ROADMAP §14.1 |
| 2 | Gradual Cutover (5% → 50%) | 2026-12-02 → 2026-12-15 | error rate Δ ≤ +2pct, p99 Δ ≤ +20ms на обоих этапах |
| 3 | Full Cutover (100%) | 2026-12-16 | 2 недели стабильных метрик при 100% |
| 4 | Cleanup (Phase 4) | TBD (после стабилизации Step 3) | grep-критерии cleanup (см. Step 4) |

Примечание: ramp-up таблица из `docs/adr_015_pilot.md` описывает обзорную последовательность ревью. Канонический порядок шагов и длительности — настоящий runbook (Step 1 = 1 месяц **чистого** shadow per ROADMAP §14.1; live-трафик 5%/50%/100% — Steps 2–3 строго после вердикта пилота).

## Feature flags (env toggles)

| Flag | Default | Step 1 | Step 2 | Step 3 | Step 4 |
|------|---------|--------|--------|--------|--------|
| `LLM_ROUTER_ENABLED` | `false` | `false` | `true` | `true` | `true` |
| `LLM_ROUTER_SHADOW_MODE` | `true` | `true` | `true` | `false` | `false` |
| `LLM_ROUTER_TRAFFIC_PERCENT` | `0` | `0` | `5` → `50` | `100` | `100` |
| `LLM_ROUTER_DEFAULT_POLICY` | `cost_priority` | без изменений | без изменений | без изменений | без изменений |
| `LLM_ROUTER_COST_GUARD_THRESHOLD` | `0.8` | без изменений | без изменений | без изменений | без изменений |

Применение на staging:

```bash
# 1. Обновить .env (staging deploy)
# 2. Перезапустить agent-service
docker-compose restart agent-service

# Проверка применённых флагов
docker-compose exec agent-service env | grep LLM_ROUTER
```

Rollback на любом шаге — единственный источник правды `.env` staging; изменения флагов не требуют redeploy кода.

## Pre-flight checklist (перед Step 1)

- [ ] Staging deploy `agent-service` жив, `/health` → 200.
- [ ] `LLM_MONTHLY_BUDGET_USD` задан; `LLM_ROUTER_COST_GUARD_THRESHOLD=0.8`.
- [ ] Валидный `OPENAI_API_KEY` (реальный провайдер трафика).
- [ ] Grafana dashboard `Phase 3 — Cost-Aware Router & Cache` (uid `llm-cost-router`, `ops/grafana/dashboards/Phase 3/llm-cost-router.json`) provisioned, панели рендерятся.
- [ ] Offline smoke проходит без API-расхода:

```bash
python scripts/ab_test_router_shadow_mode.py --offline --duration-minutes 0 --max-requests 5 --interval-seconds 0
# exit code 0 (PILOT PASS) обязателен до запуска 30-дневного пилота
```

---

## Step 1 — Shadow Mode (2026-11-03 → 2026-12-01)

### Goal

`LLMRouter` работает **параллельно** существующему пути `LLMProviderFactory.create()`: каждый LLM call идёт по прежнему (Phase 1/2 behavior), но параллельно вычисляется и логируется `route_shadow()` — решение, которое router выбрал бы. Нулевое влияние на трафик; сбор данных для критериев ROADMAP §14.1.

### Configuration (env-toggle)

```bash
LLM_ROUTER_ENABLED=false      # трафик идёт через factory
LLM_ROUTER_SHADOW_MODE=true   # shadow-решения логируются в operational stream
LLM_ROUTER_TRAFFIC_PERCENT=0  # live-routing выключен
```

### Runbook commands

```bash
# 30-дневный пилот (43200 минут), один probe-запрос каждые 5 минут
python scripts/ab_test_router_shadow_mode.py \
  --duration-minutes 43200 \
  --interval-seconds 300 \
  --output test-results/adr015_pilot_report.json

# Exit codes: 0 = PILOT PASS, 1 = ROLLBACK REQUIRED, 2 = PILOT PARTIAL
```

### Validation criteria

- [ ] Exit code `0` (PILOT PASS).
- [ ] Cost predictability (stdev of (actual−predicted)/predicted) ≤ 0.10.
- [ ] Cost overrun rate ≤ 20% (per-request actual > predicted × 1.2; predicted == 0 excluded).
- [ ] Switching decisions logged == total requests (`router_shadow_decision` events в operational stream).
- [ ] JSON-отчёт сохранён в `test-results/adr015_pilot_report.json`.
- [ ] Вердикт перенесён в `docs/adr_015_pilot.md` §Pilot Results (PASS/FAIL/INCONCLUSIVE).
- [ ] Grafana: панель «Router Decisions by Policy (last 1h)» показывает решения; «Monthly Budget Usage» в пределах budget.

### Rollback plan

Shadow не влияет на трафик — «rollback» = остановить логирование и расследовать:

```bash
LLM_ROUTER_SHADOW_MODE=false   # остановить shadow-логирование
# полное отключение:
LLM_ROUTER_ENABLED=false
```

Триггеры: exit code `1` (cost overrun > 20%), неприемлемые routing-решения (cheap model для high-stakes запросов — ручной review панели «Router Decisions by Policy»), провал offline smoke.

---

## Step 2 — Gradual Cutover (2026-12-02 → 2026-12-15)

### Goal

Верифицировать router на реальном трафике: сначала 5% (3 дня), затем 50% недельного трафика. Сравнение error rate / latency / cost routed vs control.

### Configuration (env-toggle)

```bash
LLM_ROUTER_ENABLED=true        # live-routing включён
LLM_ROUTER_SHADOW_MODE=true    # shadow-логирование продолжается для сравнения
LLM_ROUTER_TRAFFIC_PERCENT=5   # первые 3 дня; далее 50
```

Переход 5% → 50% (примерно 2026-12-05) — только после 3 стабильных дней на 5%.

### Runbook commands

```bash
# Применить env-изменение и перезапустить
docker-compose restart agent-service
docker-compose exec agent-service env | grep LLM_ROUTER

# Ежедневный контроль (Grafana, uid llm-cost-router):
# - LLM Latency p50/p99 (router vs baseline)
# - LLM Calls by Provider/Model (last 1h)
# - Cost Guard Triggers (last 24h)
# - Circuit Breaker Activations (last 1h)
```

### Validation criteria

- [ ] Error rate routed-трафика vs control: Δ ≤ +2 percentage points (per BETA-PROMPTS C-6 Step 2).
- [ ] p99 latency router vs fallback: Δ ≤ +20ms (per `docs/adr_015_pilot.md`).
- [ ] Cost в пределах `LLM_MONTHLY_BUDGET_USD`; Cost Guard срабатывает предсказуемо на 80% budget (reason `Budget` в «Cost Guard Triggers»).
- [ ] 0 unacceptable routing decisions (review «Router Decisions by Policy»: policy соответствует контексту запросов).
- [ ] 3 стабильных дня на 5% → повышение до 50%; 5 дней стабильности на 50% → готовность к Step 3.

### Rollback plan

```bash
LLM_ROUTER_TRAFFIC_PERCENT=0  # live-routing off; shadow-логирование продолжается
docker-compose restart agent-service
```

Триггеры: error rate Δ > +2pct, p99 Δ > +20ms, cost overrun на routed-трафике, circuit breaker flapping («Circuit Breaker Activations» аномальна). После rollback — инцидент-разбор, затем повтор Step 2 с дефолтной политикой `cost_priority` (без смены policy вручную).

---

## Step 3 — Full Cutover (2026-12-16)

### Goal

100% трафика через `LLMRouter.create_llm(decision)`. `LLMProviderFactory.create()` остаётся в codebase как legacy-ветка (`else` в `service.py`) до Step 4, но в нормальном пути не вызывается.

### Configuration (env-toggle)

```bash
LLM_ROUTER_ENABLED=true
LLM_ROUTER_SHADOW_MODE=false   # shadow-логирование выключено — решения реально применяются
LLM_ROUTER_TRAFFIC_PERCENT=100
```

### Runbook commands

```bash
docker-compose restart agent-service
docker-compose exec agent-service env | grep LLM_ROUTER

# Подтверждение пути (логи agent-service): каждый запрос логирует
# "LLMRouter decision: provider=... model=... policy=... reason=..."
```

### Validation criteria

- [ ] `LLM Calls by Provider/Model (last 1h)` показывает router-выбранные модели (traffic split 70/30 openai:gpt-4o-mini / gpt-4o либо текущий `LLM_ROUTER_TRAFFIC_SPLIT`).
- [ ] Error rate и latency стабильны vs baseline Step 2 (нет регрессии).
- [ ] `LLM_ROUTER_SHADOW_MODE=false` применён (нет дублирующих shadow-событий).
- [ ] 2 недели стабильных метрик (до ~2026-12-30) — gate для Step 4.

### Rollback plan

```bash
LLM_ROUTER_ENABLED=false  # service.py ветка else → прямой LLMProviderFactory.create()
docker-compose restart agent-service
```

Триггеры: любая регрессия error rate/latency/cost, недоступность router-решений (exception в `router.route()`). Legacy-ветка factory целенаправленно сохраняется до Step 4 — rollback без redeploy.

---

## Step 4 — Cleanup (Phase 4, TBD)

### Goal

Удалить deprecated-остатки ADR-005 и закрыть метрику идеальности честным −1 (BUG-BETA-06). Запускается только после 2 недель стабильного Step 3.

### Configuration (env-toggle)

```bash
# .env.example: дефолты переключаются на router-first
LLM_ROUTER_ENABLED=true       # was false
LLM_ROUTER_SHADOW_MODE=false  # was true
LLM_ROUTER_TRAFFIC_PERCENT=100  # was 0
```

### Runbook commands

```bash
# 1. Удалить deprecated-комментарий fallback_chain из provider.py
#    (docstring LLMProviderFactory.create: "Deprecated (ADR-015, cutover in progress)...")
# 2. Удалить legacy else-ветку LLMProviderFactory.create() в service.py,
#    если pilot PASS подтверждён (иначе оставить до Phase 4 exit)
# 3. Обновить idealidad.py: −1 за fallback_chain подтверждается фактическим удалением
# 4. Обновить ARCHITECT.md §8 trade-off C-7: fallback fully removed

# Контрольные grep-критерии:
grep "fallback_chain" src/llm_client/agent/provider.py
# → 0 совпадений
grep "_COST_PER_1M" src/llm_client/agent/provider.py
# → 0 совпадений (уже выполнено — переподтвердить)
```

### Validation criteria

- [ ] `grep "fallback_chain" src/llm_client/agent/provider.py` → 0.
- [ ] `grep "_COST_PER_1M" src/llm_client/agent/provider.py` → 0 (статус: уже выполнено в Phase 3, переподтвердить).
- [ ] `.env.example`: `LLM_ROUTER_ENABLED=true`, `LLM_ROUTER_SHADOW_MODE=false`, `LLM_ROUTER_TRAFFIC_PERCENT=100`.
- [ ] `idealidad.py` Phase 3 metric корректно считает Δсложности (−1 за fallback_chain реален).
- [ ] `analytics/ARCHITECT.md` §8: trade-off C-7 отмечает полное удаление fallback_chain.
- [ ] Phase 1/2 regression suite (`pytest tests/unit -v`) зелёный после удаления legacy-ветки.

### Rollback plan

```bash
git revert <cleanup-commit>   # восстановить legacy-ветку factory
docker-compose restart agent-service
```

Cleanup-коммит не мержить в main без green regression suite; rollback — revert, без data migrations.

---

## Communication plan

| Событие | Канал | Когда |
|---------|-------|-------|
| Kickoff Step 1 (пилот стартует) | Slack #engineering | 2026-11-03 |
| Ежедневный review Grafana (Step 2/3) | Grafana dashboard `llm-cost-router` | ежедневно в рабочие дни |
| Step-boundary check-in (вердикт PASS/ROLLBACK) | Slack #engineering + ссылка на JSON-отчёт | 2026-12-01, 2026-12-15, 2026-12-30 |
| Rollback / инцидент | Slack #engineering (immediate) + postmortem-заметка в отчёте | по триггеру |
| Step 4 cleanup announcement | Slack #engineering | после merge cleanup-коммита |

## Related documents

- `docs/adr_015_pilot.md` — pilot procedure; Step 1 = этот пилот (критерии, exit codes, ramp-up обзор).
- `scripts/ab_test_router_shadow_mode.py` — measurement tool (CLI: `--duration-minutes`, `--interval-seconds`, `--max-requests`, `--offline`, `--queries-file`, `--output`).
- `analytics/ROADMAP.md` §14.1 — pilot metrics and rollback criteria.
- `analytics/BETA-PROMPTS.md` C-6 (migration plan) / C-7 (shadow-mode metrics logger) — спеки, реализующие этот runbook.
- `analytics/ARCHITECT.md` §5.2.3 / ADR-015 — architecture context (Supersedes ADR-005 fallback_chain).
- `ops/grafana/dashboards/Phase 3/llm-cost-router.json` — мониторинг Steps 1–3.

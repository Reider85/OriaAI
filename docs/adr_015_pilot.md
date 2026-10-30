# ADR-015 Pilot Procedure (Phase 3) — Cost-Aware LLMRouter Shadow Mode

**ADR**: ADR-015 (Cost-Aware Routing — `LLMRouter` + `CostGuard` + shadow mode migration).
**Source**: `ROADMAP.md` §14.1 (pilot: 1 month shadow mode), `BETA-PROMPTS.md` E-2, `docs/migration_adr_005_to_015.md` (Step 1 = this pilot).

## Pilot criteria (ROADMAP §14.1)

| Criterion | Threshold | Verdict |
|---|---|---|
| Cost predictability (stdev of (actual − predicted)/predicted) | ≤ 0.10 (±10%) | PASS |
| Cost overrun (per-request: actual > predicted × 1.2; predicted = $0 free-model routing excluded) | ≤ 20% of requests | PASS |
| Switching decisions logged | == total requests | PASS |
| Cost overrun | > 20% of requests | **ROLLBACK** |
| Routing decisions | unacceptable (e.g. cheap model for high-stakes request) | **ROLLBACK** |

## Prerequisites

- Staging deploy of `agent-service`.
- `LLM_ROUTER_SHADOW_MODE=true` (default) — router decisions logged, traffic not switched.
- `LLM_MONTHLY_BUDGET_USD` set (cost guard threshold `LLM_ROUTER_COST_GUARD_THRESHOLD=0.8`).
- Valid API key for the actual provider (`OPENAI_API_KEY` / `ZAI_API_KEY` / ...).
- Grafana: router metrics available (`router_decisions_total`, `llm_monthly_budget_usage_ratio` via `agent-service:8000/metrics`).

## Shadow-mode measurement (`scripts/ab_test_router_shadow_mode.py`)

Month-long pilot run — **scheduled via external cron, not in regular CI**:

```bash
# 30-day pilot (43200 minutes), one probe request every 5 minutes
python scripts/ab_test_router_shadow_mode.py \
  --duration-minutes 43200 \
  --interval-seconds 300 \
  --output test-results/adr015_pilot_report.json
```

Short smoke run (no API spend — costs simulated from `ModelCostTable`):

```bash
python scripts/ab_test_router_shadow_mode.py --offline --duration-minutes 0 --max-requests 5 --interval-seconds 0
```

CLI options: `--queries-file` (JSONL with `{"query": ...}`), `--interval-seconds`, `--max-requests`, `--offline`, `--output` (JSON report).

Exit codes: `0` = PILOT PASS, `1` = ROLLBACK REQUIRED, `2` = PILOT PARTIAL.

## Traffic ramp-up schedule

| Days | Traffic | Configuration | What is measured |
|---|---|---|---|
| 1–7 | 0% (shadow only) | `LLM_ROUTER_SHADOW_MODE=true` | Predictability, overrun rate, decision logging |
| 8–14 | 5% via router | `LLM_ROUTER_ENABLED=true`, `LLM_ROUTER_TRAFFIC_PERCENT=5` | Error rate, latency, cost on real routed traffic |
| 15–21 | 50% via router | `LLM_ROUTER_TRAFFIC_PERCENT=50` | Same metrics; compare vs control |
| 22–28 | 100% via router | `LLM_ROUTER_TRAFFIC_PERCENT=100` | Full-cutover readiness (only if no rollback) |
| 28–30 | — | Review | Decision: Approved / Needs revision / rollback |

Rollback at any stage: set `LLM_ROUTER_TRAFFIC_PERCENT=0` (shadow logging can continue).

## Verdict

Script output interpretation:

- `✅ PILOT PASS — ADR-015 Approved` — criteria met; proceed with ramp-up and full rollout.
- `⚠️ PILOT PARTIAL` — review criteria (e.g. logging gaps or borderline predictability); tune `ModelCostTable` / policies, re-run.
- `❌ ROLLBACK REQUIRED (cost overrun >20%)` — ADR-015 rollback per `ROADMAP.md` §14.1; investigate routing decisions in operational stream (`router_shadow_comparison` events).

## Pilot Results

**Run date**: 2026-10-30 — offline smoke (pre-flight only, не полный пилот).
**Configuration**: `--offline --duration-minutes 0 --max-requests 5 --interval-seconds 0` — costs simulated from `ModelCostTable`, 0 API spend.
**Report**: `test-results/adr015_smoke_20261030.json` (копия: `reports/adr015_smoke_20261030.json`).

### Metrics (offline smoke)

- Total requests: **5**
- Cost predictability (stdev of ratios): **0.000** (threshold ≤ 0.10) — ✅
- Cost overrun rate: **0.0%** (threshold ≤ 20%) — ✅
- Switching decisions logged: **5/5** (`router_shadow_comparison` events) — ✅
- Exit code: **0 (PILOT PASS)** — pre-flight gate по `docs/migration_adr_005_to_015.md` выполнен.

### Verdict

**INCONCLUSIVE** — offline smoke PASSED, но это только pre-flight: ROADMAP §14.1 требует **1 месяц shadow mode** с реальным трафиком. Полный пилот по расписанию Step 1: **2026-11-03 → 2026-12-01** (см. `docs/migration_adr_005_to_015.md`); финальный вердикт PASS/ROLLBACK будет зафиксирован по его результатам.

### Issues encountered

- Нет (smoke-прогон без API-расхода; системных ошибок не наблюдалось).

### Sign-off

- [x] Engineering: OriaAI Dev — offline smoke 2026-10-30
- [ ] SRE: <name>
- [ ] Architecture: <name> — вердикт после полного пилота (2026-12-01)

## Related documents

- `docs/migration_adr_005_to_015.md` — migration plan (Step 1 = this pilot).
- `analytics/ROADMAP.md` §14.1 — pilot metrics and rollback criteria.
- `analytics/BETA-PROMPTS.md` E-2 — the prompt this procedure implements.

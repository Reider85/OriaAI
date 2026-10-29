# BUGFIXES-BETA.md

**Источник**: аудит реализации против `analytics/MVP-PROMPTS.md` (v1.0.0, 28 спек),
`analytics/ALPHA-PROMPTS.md` (v1.1.0, 36 спек), `analytics/BETA-PROMPTS.md`
(v1.0.0, 37 спек). Репозиторий: <https://github.com/Reider85/OriaAI>.

**Дата аудита**: 2026-10-28.

**Цель файла**: единый реестр всех 🟡 PARTIAL и ❌ MISSING пунктов + тревожных
сигналов, выявленных при сверке спек с кодом. Каждый баг имеет приоритет, ссылку
на спеку, доказательство в коде, рекомендуемый фикс и критерий приёмки.

**Всего заведено 19 багов**: 6 в MVP (Phase 1), 6 в ALPHA (Phase 2), 7 в BETA (Phase 3).
Из них: 2 релиз-блокера, 6 high, 8 medium, 3 low.

---

## Сводная таблица

| ID | Приоритет | Фаза | Спека | Краткое описание | Файл/доказательство |
|----|-----------|------|-------|------------------|---------------------|
| BUG-MVP-01 | 🔴 BLOCKER | MVP | D-3 | ForensicStreamWriter пишет не в тот S3 bucket | `observability/forensic_writer.py:46,121`; `api.py:60-66`; `service.py:395` |
| BUG-MVP-02 | 🟠 HIGH | MVP | D-3 | Нет S3 lifecycle policy для 90-дневного retention forensic | `docker-compose.yml` (init-контейнер без `mc ilm`) |
| BUG-MVP-03 | 🟠 HIGH | MVP | E-4 | `AccessLogIngestor` не подключён к startup, нет env в compose | `observability/access_log_ingestor.py`; `api.py`; `service.py`; `docker-compose.yml` |
| BUG-MVP-04 | 🟡 MEDIUM | MVP | B-2 | Quick Win intermediate state (`STORAGE_BACKEND`) пропущен — сразу перешли к E-2 | `storage/factory.py` |
| BUG-MVP-05 | 🟡 MEDIUM | MVP | C-6 | Тесты forensic-логгинга проверяют только 5 из 8 полей | `tests/unit/test_cancel_forensic_logging.py` |
| BUG-MVP-06 | 🟢 LOW | MVP | C-3 | Тест asserts `latency_ms < 500` вместо спечного `<5 ms` | `tests/integration/test_redis_cancel.py:45` |
| BUG-ALPHA-01 | 🟠 HIGH | ALPHA | A-1 | `redis/redis.conf` нарушает Phase 2 spec (`512mb`+`noeviction` → `1gb`+`allkeys-lru`) | `redis/redis.conf` |
| BUG-ALPHA-02 | 🟠 HIGH | ALPHA | E-5 | Phase 3 джоб `phase3-adr011-staging` запускается в `phase2-nightly.yml` (scope creep) | `.github/workflows/phase2-nightly.yml:431-475` |
| BUG-ALPHA-03 | 🟡 MEDIUM | ALPHA | H-2 | `pipeline_singleton.py:153-165` — мёртвый код после `return` | `src/llm_client/rag/pipeline_singleton.py:153-165` |
| BUG-ALPHA-04 | 🟡 MEDIUM | ALPHA | H-2 | `RagPipeline.retrieve(query, top_k=…)` молча игнорирует `top_k` | `src/llm_client/rag/pipeline.py:461` |
| BUG-ALPHA-05 | 🟡 MEDIUM | ALPHA | C-6 | `MockRetrievalPipeline` захардкожен в `RAGEvaluator` вместо `RagPipeline` | `src/llm_client/rag/eval/evaluator.py:9-10` |
| BUG-ALPHA-06 | 🟢 LOW | ALPHA | A-3 | Миграция `008_fix_documents_search_schema.py` — фикс сломанной `007` | `migrations/versions/008_fix_documents_search_schema.py` |
| BUG-BETA-01 | 🔴 BLOCKER | BETA | F-1 | `ARCHITECT.md` остался на v1.3.0 — Phase 3 не отражён в документации | `analytics/ARCHITECT.md` header line 5, §8 line 1013 |
| BUG-BETA-02 | 🟠 HIGH | BETA | C-6 | `docs/migration_adr_005_to_015.md` — стаб в 25 строк вместо runbook | `docs/migration_adr_005_to_015.md` |
| BUG-BETA-03 | 🟠 HIGH | BETA | E-2 / E-3 | `docs/adr_015_pilot.md` (70 строк) и `docs/adr_016_pilot.md` (78 строк) — процедурные стабы без результатов | `docs/adr_015_pilot.md`, `docs/adr_016_pilot.md` |
| BUG-BETA-04 | 🟡 MEDIUM | BETA | H-2 | `agent_run` tool упомянут в спеке H-1, но не зарегистрирован | `src/llm_client/mcp/tool_registry.py` `register_default_tools()` |
| BUG-BETA-05 | 🟡 MEDIUM | BETA | B-1 | `SemanticAnswerCache._evict_if_needed = pass` — soft cap `max_entries=10000` не проверяется | `src/llm_client/rag/semantic_cache.py:209` |
| BUG-BETA-06 | 🟡 MEDIUM | BETA | C-6 | `fallback_chain` из ADR-005 не удалён — метрика идеальности Phase 3 оптимистична | `src/llm_client/agent/provider.py` |
| BUG-BETA-07 | 🟢 LOW | BETA | E-5 | Нет отдельного `phase3-ci.yml` workflow — Phase 3 живёт в Phase 2 nightly | `.github/workflows/` |

---

# MVP (Phase 1) — Багфиксы

## 🔴 BUG-MVP-01 — ForensicStreamWriter: баг с bucket

- **Спека**: MVP-PROMPTS D-3 + ADR-014 (изоляция forensic bucket от files bucket)
- **Приоритет**: 🔴 BLOCKER (релиз-блокер для Phase 1 exit-критерия §5.6 п.5 «forensic stream доступен security officer»)

### Проблема

`ForensicStreamWriter.__init__` принимает параметр `bucket` и сохраняет его в
`self._bucket` (строка 46), но метод `_flush()` на строке 121 вызывает
`self._s3.save(body, key)` **без передачи `bucket`**. В production-конфигурации
(`api.py:60-66`, `service.py:395`) `_create_file_storage()` возвращает
`S3CompatibleStorage()` с дефолтным значением env `S3_BUCKET=llm-client-files`.

**Результат**: зашифрованные forensic-записи (с полным PII, IP, partial answer,
last node, message count) пишутся в бакет `llm-client-files`, а не в
`llm-client-forensic`. Это прямое нарушение ADR-014, обещающего:

- отдельные бакеты для forensic и files;
- отдельный RBAC (security officer + аудит-комитет vs обычные пользователи);
- разные retention policies (90+ дней forensic vs 30 дней operational).

E2E-тест `test_forensic_stream_e2e.py:73-82` обходит баг, конструируя
`S3CompatibleStorage` напрямую с `bucket=settings.s3_forensic_bucket`, поэтому
CI не ловит нарушение.

### Доказательство

```python
# src/llm_client/observability/forensic_writer.py
class ForensicStreamWriter:
    def __init__(self, ..., bucket: str, ...):
        ...
        self._bucket = bucket          # line 46 — сохранено

    async def _flush(self, batch: list[...]) -> None:
        ...
        await self._s3.save(body, key) # line 121 — bucket НЕ ИСПОЛЬЗУЕТСЯ
```

```python
# src/llm_client/agent/service.py:395 (аналогично в api.py:60-66)
_create_file_storage()  # возвращает S3CompatibleStorage() с дефолтным S3_BUCKET
build_forensic_writer(storage=..., bucket=settings.s3_forensic_bucket, ...)
# bucket передаётся, но игнорируется
```

### Рекомендуемый фикс

Вариант A (предпочтительный — forensic не зависит от production storage):

```python
# src/llm_client/observability/forensic_writer.py
class ForensicStreamWriter:
    def __init__(self, ..., bucket: str, kms: KMSKeyProvider, ...):
        self._s3 = S3CompatibleStorage(
            endpoint_url=settings.s3_endpoint_url,
            access_key=settings.s3_access_key,
            secret_key=settings.s3_secret_key,
            bucket=bucket,                # ← передаём явно
        )
        self._bucket = bucket             # для логов и метаданных
```

Вариант B (минимальная правка):

```python
# src/llm_client/observability/forensic_writer.py:121
await self._s3.save(body, key, bucket=self._bucket)
#                          ^^^^^^^^^^^^^^^^^^^^^^
# (потребует расширения сигнатуры S3CompatibleStorage.save())
```

### Критерий приёмки

- [ ] Тест `test_forensic_writer.py` обновлён: использует production-путь
      построения `ForensicStreamWriter` (через `build_forensic_writer()`), а не
      ручную инстанциацию `S3CompatibleStorage(bucket=...)`.
- [ ] Новый тест `test_forensic_writer_writes_to_correct_bucket`: после `put()`
      проверяет, что объект лежит в `llm-client-forensic`, а НЕ в
      `llm-client-files` (через `mc ls local/llm-client-forensic/...`).
- [ ] Регрессионный тест: попытка прочитать forensic-объект через клиента с
      доступом только к `llm-client-files` должна падать с `AccessDenied`.
- [ ] `grep "self._bucket" src/llm_client/observability/forensic_writer.py`
      показывает, что поле используется минимум один раз.

---

## 🟠 BUG-MVP-02 — Нет S3 lifecycle policy для forensic retention

- **Спека**: MVP-PROMPTS D-3 DoD: «retention 90 дней настроен в S3 lifecycle
  policy (проверка через `aws s3api get-bucket-lifecycle-configuration`)»
- **Приоритет**: 🟠 HIGH (нарушает DoD, но не блокирует запуск)

### Проблема

Init-контейнер `minio-init` в `docker-compose.yml` создаёт бакеты командой
`mc mb --ignore-existing local/llm-client-forensic`, но не настраивает ILM
(information lifecycle management) правило для retention 90+ дней. Spec MVP D-3
DoD требует lifecycle policy.

### Доказательство

```bash
# docker-compose.yml, контейнер minio-init (lines 79-101)
mc mb --ignore-existing local/llm-client-files
mc mb --ignore-existing local/llm-client-forensic
# mc ilm — отсутствует
```

### Рекомендуемый фикс

Добавить в `minio-init` скрипт настройку ILM:

```bash
# 90-дневная экспирация для forensic bucket
mc ilm rule add local/llm-client-forensic \
  --expire-days 90 \
  --noncurrent-expire-days 90

# 30-дневная экспирация для operational bucket (если требуется)
mc ilm rule add local/llm-client-files \
  --expire-days 30
```

Для AWS S3 в продакшене — эквивалент через `aws s3api put-bucket-lifecycle-configuration`.

### Критерий приёмки

- [ ] `docker-compose exec minio mc ilm rule list local/llm-client-forensic`
      показывает правило с `expire-days=90`.
- [x] Интеграционный тест `tests/integration/test_minio_lifecycle.py` проверяет,
      что правило применено.
- [x] README раздел «Vault — проверка шифрования» дополнен командой проверки ILM.

---

## 🟠 BUG-MVP-03 — AccessLogIngestor не подключён

- **Спека**: MVP-PROMPTS E-4 — «S3 access logs → forensic stream»
- **Приоритет**: 🟠 HIGH (функционал заявлен в спеке, но не работает)

### Проблема

Класс `AccessLogIngestor` (`src/llm_client/observability/access_log_ingestor.py`,
198 строк) реализован: читает префикс `_access_logs/` каждые 5 минут, парсит
AWS S3 Server Access Log, передаёт события в `ForensicStreamWriter`, при
несанкционированном доступе (requester не в allow-list) шлёт Slack-алерт.
Тесты есть (`tests/unit/test_access_log_ingestor.py`, 4 теста).

Но:

1. Класс не инстанциируется в `api.py` или `service.py` — нет wiring в startup.
2. В `docker-compose.yml` не проставлена env `MINIO_SERVER_LOGGING_TARGET`
   (спека: «В docker-compose MinIO добавь env...»).
3. Нет обёртки над `mc admin trace` для dev-режима (fallback спеки).

### Рекомендуемый фикс

**Шаг 1 — wiring в startup**:

```python
# src/llm_client/agent/service.py (или api.py, в startup)
if settings.forensic_stream_enabled and settings.access_log_ingest_enabled:
    ingestor = AccessLogIngestor(
        storage=file_storage,
        forensic_writer=forensic_writer,
        allowlist=settings.s3_access_log_allowlist,
        alert_webhook_url=settings.security_alert_webhook_url,
    )
    app.state.access_log_ingestor = ingestor
    app.state.access_log_task = asyncio.create_task(ingestor.run_loop())
```

**Шаг 2 — env в compose**:

```yaml
# docker-compose.yml, сервис minio
environment:
  MINIO_SERVER_LOGGING_TARGET: "http://minio:9000/_access_logs"
```

**Шаг 3 — обёртка для dev**:

```bash
# scripts/dev_minio_trace.sh
docker-compose exec minio mc admin trace local/llm-client-files \
  --call access --json > /tmp/_access_logs/trace.jsonl
```

### Критерий приёмки

- [x] При `FORENSIC_STREAM_ENABLED=true` и `ACCESS_LOG_INGEST_ENABLED=true`
      ingestor запускается в фоне при старте приложения.
- [x] Интеграционный тест `tests/integration/test_access_log_ingestor_e2e.py`
      шлёт запрос к MinIO с неавторизованным `User-Agent`, ждёт 5+ минут,
      проверяет, что в forensic bucket появилась запись с `event_type=s3_access`
      и в Slack-вебхук ушёл алерт.
      *(Адаптация: ожидание 5+ мин заменено на прямой `ingest_once()` +
      загрузку AWS-формат log-строки в `_access_logs/` — тот же код-путь,
      event-driven, без sleep; webhook проверяется через httpx.MockTransport.)*
- [x] В `docker-compose.yml` добавлена env `MINIO_SERVER_LOGGING_TARGET`.
      *(Примечание: MinIO игнорирует этот env — нет нативного AWS-формата;
      фактический dev-путь — `scripts/dev_minio_trace.sh` через `mc admin
      trace`, как требует DoD E-4.)*

---

## 🟡 BUG-MVP-04 — Quick Win B-2 intermediate state пропущен

- **Спека**: MVP-PROMPTS B-2 — Quick Win с feature-flag `STORAGE_BACKEND=local|s3`
- **Приоритет**: 🟡 MEDIUM (финальный стейт корректен, но промежуточный
  deliverable B-2 как отдельный шаг не сохранён)

### Проблема

Спека B-2 явно требовала: «НЕ удаляй LocalFileStorage в этом Quick Win —
переключение через `STORAGE_BACKEND=local|s3`. Удаление — в полном расш. ADR-008
(Блок E).» Разработка сразу перешла к E-2 (LocalFileStorage удалён, флаг
упразднён). Финальный стейт корректен, но B-2 как отдельный «quick win»
deliverable не сохранён.

### Рекомендуемый фикс

Опционально — добавить в git history тег `mvp-B-2-snapshot` на коммите, где
`STORAGE_BACKEND` ещё существовал (если такой коммит был). Если нет —
зафиксировать в `analytics/ARCHITECT.md` §12 changelog, что B-2 был объединён
с E-2 по решению архитектора (с датой и обоснованием).

### Критерий приёмки

- [ ] `analytics/ARCHITECT.md` §12 changelog явно отмечает, что B-2 merged с E-2.
- [ ] Либо git-тег `mvp-B-2-snapshot` создан.

---

## 🟡 BUG-MVP-05 — Тесты forensic-логгинга проверяют 5/8 полей

- **Спека**: MVP-PROMPTS C-6 — 8 полей forensic-события
- **Приоритет**: 🟡 MEDIUM (тест не ловит регрессии удаления полей)

### Проблема

`tests/unit/test_cancel_forensic_logging.py:test_cancel_event_handler_receives_full_event`
проверяет: `event_type`, `session_id`, `reason`, `user_id`, `duration_ms`,
`timestamp`. Не проверяет: `partial_answer_size_bytes`, `last_node_executed`,
`messages_count`. Регрессия, дропающая одно из этих полей, не будет поймана.

### Рекомендуемый фикс

Расширить assert:

```python
# tests/unit/test_cancel_forensic_logging.py
assert event["event_type"] == "cancel"
assert event["session_id"] == session_id
assert event["reason"] == "user_cancelled"
assert "user_id" in event
assert event["duration_ms"] >= 0
assert "timestamp" in event
# + добавить:
assert "partial_answer_size_bytes" in event
assert isinstance(event["partial_answer_size_bytes"], int)
assert "last_node_executed" in event
assert event["last_node_executed"]  # не None и не пустая строка
assert "messages_count" in event
assert isinstance(event["messages_count"], int)
assert event["messages_count"] >= 0
```

### Критерий приёмки

- [ ] Все 8 полей из спеки C-6 явно ассертятся.
- [ ] При прогоне `pytest tests/unit/test_cancel_forensic_logging.py -v` 6 тестов
      проходят.

---

## 🟢 BUG-MVP-06 — Лимит latency assertion в 100 раз слабее спеки

- **Спека**: MVP-PROMPTS C-3 — pub/sub round-trip `< 5 ms`
- **Приоритет**: 🟢 LOW (тест есть, но не обеспечивает спеку)

### Проблема

`tests/integration/test_redis_cancel.py:45` ассертит `latency_ms < 500` (500ms).
Спека C-3 DoD требует `< 5 ms` round-trip на локальном loopback. В 100 раз
слабее.

### Рекомендуемый фикс

```python
# tests/integration/test_redis_cancel.py:45
- assert latency_ms < 500, f"latency {latency_ms}ms > 500ms"
+ assert latency_ms < 5, f"pub/sub round-trip {latency_ms}ms > 5ms (spec C-3)"
```

Если наблюдаются flaky-провалы >5ms на CI-раннере, добавить decorrelation:
запускать 100 итераций, ассертить p99 < 5ms, среднее < 2ms.

### Критерий приёмки

- [ ] Assertion соответствует спеке C-3 (`<5 ms`).
- [ ] При flaky-провалах CI трекает их как реальные регрессии, а не глушит.

---

# ALPHA (Phase 2) — Багфиксы

## 🟠 BUG-ALPHA-01 — redis.conf нарушает Phase 2 spec A-1

- **Спека**: ALPHA-PROMPTS A-1 — `maxmemory 512mb`, `maxmemory-policy noeviction`
  для DB 1 (checkpoint-WAL)
- **Приоритет**: 🟠 HIGH (нарушает DoD Phase 2)

### Проблема

Phase 3 ADR-011 сделал eviction безопасным (composite checkpointer → read-through
в Postgres), и `redis/redis.conf` переключили на `maxmemory 1gb` +
`maxmemory-policy allkeys-lru` с комментарием, что DB 1 теперь «keys evictable
but safe». Однако это противоречит Phase 2 spec A-1, чей DoD прямо требует:

```bash
docker-compose exec redis redis-cli -n 1 INFO memory | grep maxmemory_policy
# → noeviction
```

Phase 2 DoD-критерий больше не проходит. Любой аудит против
`ALPHA-PROMPTS.md v1.1.0` флагнёт это.

### Рекомендуемый фикс

Выбрать одну из стратегий:

**Вариант A — задокументировать как явное расш. Phase 2** (предпочтительно):

```bash
# redis/redis.conf
# Phase 2 (ADR-010): maxmemory 512mb, maxmemory-policy noeviction
# Phase 3 (ADR-011): maxmemory 1gb, maxmemory-policy allkeys-lru
#                   (eviction safe due to composite checkpointer read-through)
# Phase 2 DoD-A-1 superseded by ADR-011 — see analytics/ARCHITECT.md §8 Q-2.
maxmemory 1gb
maxmemory-policy allkeys-lru
```

И в `analytics/ARCHITECT.md` §8 явно отметить: `A-1 DoD superseded by ADR-011
(Phase 3) — eviction now safe.`

**Вариант B — восстановить Phase 2 контракт** (если ADR-011 ещё не активирован
в prod): вернуть `512mb` + `noeviction`, удалить Phase 3 scope creep.

### Критерий приёмки

- [ ] Решение зафиксировано в `analytics/ARCHITECT.md` §8 Q-2.
- [ ] README Phase 1+2 «Проверка eviction (alert)» обновлён: либо warns о
      новом поведении, либо DoD A-1 выполнен.

---

## 🟠 BUG-ALPHA-02 — Phase 3 джоб в phase2-nightly.yml (scope creep)

- **Спека**: ALPHA-PROMPTS E-5 — «НЕ добавляй Phase 3 metrics (semantic cache,
  cost-aware router)»
- **Приоритет**: 🟠 HIGH (нарушает явный anti-pattern spec'и)

### Проблема

В `.github/workflows/phase2-nightly.yml:431-475` определён джоб
`phase3-adr011-staging`, который запускает Phase 3 тесты:
`test_stale_answer_guard.py`, `test_semantic_cache_integration.py`,
`test_cache_aware_llm_integration.py`, `test_facts_extractor_integration.py`.
Спека E-5 прямо это запрещала.

Регрессия Phase 3 будет репортиться как Phase 2 фейл, что «пачкает» signal/noise.

### Рекомендуемый фикс

Перенести джоб в новый `.github/workflows/phase3-nightly.yml`:

```yaml
# .github/workflows/phase3-nightly.yml
name: Phase 3 Nightly
on:
  schedule:
    - cron: "0 2 * * *"
  workflow_dispatch:

jobs:
  phase3-adr011-staging:
    runs-on: ubuntu-latest
    # ... (вынести из phase2-nightly.yml целиком)
```

Удалить блок `phase3-adr011-staging` из `phase2-nightly.yml`.

### Критерий приёмки

- [ ] `.github/workflows/phase2-nightly.yml` не содержит джобов с префиксом
      `phase3-`.
- [ ] Создан `.github/workflows/phase3-nightly.yml` со всем Phase 3 scope.
- [ ] README «Phase 2 CI Pipeline» обновлён (раздел Nightly Pipeline больше
      не упоминает Phase 3).

---

## 🟡 BUG-ALPHA-03 — pipeline_singleton.py мёртвый код

- **Спека**: ALPHA-PROMPTS H-2 — Tier-3 pipeline build
- **Приоритет**: 🟡 MEDIUM (не функциональный баг, code smell)

### Проблема

В `src/llm_client/rag/pipeline_singleton.py:153-165` блок
`# Tier 3: Build new pipeline with overrides` стоит в ветке
`if key in _override_cache:` *после* `return` — недостижим. Реальная логика
Tier-3 живёт в `try:` блоке ниже (строка 167+). Функция работает, но misplaced
indentation — это code quality smell, который не пройдёт ревью.

### Доказательство

```python
# src/llm_client/rag/pipeline_singleton.py
def get_pipeline_for_request(...):
    ...
    if key in _override_cache:
        cached = _override_cache[key]
        if cached is not None:
            return cached                    # ← return here
        # Tier 3: Build new pipeline with overrides  # ← мёртвый блок
        logger.info("Building new pipeline (Tier 3)...")
        ...
    # реальная логика Tier 3 тут:
    try:
        ...
```

### Рекомендуемый фикс

Удалить мёртвый блок (строки 153-165) или перенести логику в правильную ветку.

### Критерий приёмки

- [ ] `ruff check src/llm_client/rag/pipeline_singleton.py` — 0 ошибок.
- [ ] Тест `test_pipeline_singleton.py` не зависит от удалённого блока.

---

## 🟡 BUG-ALPHA-04 — RagPipeline.retrieve игнорирует top_k

- **Спека**: ALPHA-PROMPTS H-2 — `pipeline.retrieve(query, top_k=top_k)`
- **Приоритет**: 🟡 MEDIUM (вводящий в заблуждение API)

### Проблема

`RagPipeline.retrieve(query, top_k=5, user_id=None)` в
`src/llm_client/rag/pipeline.py:461` принимает `top_k`, но не передаёт его в
`rerank_after_fusion` — использует `self._config.reranker_top_k`.

UI G-4 даёт пользователю ползунок `top_k`, override доходит через
`RetrieverConfig.reranker_top_k` (в `pipeline_singleton._apply_retriever_overrides`),
так что функционально работает. Но сигнатура `retrieve(query, top_k=…)` вводит
в заблуждение.

### Рекомендуемый фикс

```python
# src/llm_client/rag/pipeline.py
async def retrieve(
    self,
    query: str,
    top_k: int | None = None,   # если None — берём из config
    user_id: str | None = None,
) -> list[Document]:
    effective_top_k = top_k if top_k is not None else self._config.reranker_top_k
    ...
    return await rerank_after_fusion(
        ...,
        top_k=effective_top_k,
    )
```

### Критерий приёмки

- [ ] Передача `top_k=10` в `retrieve()` реально меняет кол-во возвращаемых
      результатов (покрыть тестом `test_rag_pipeline.py::test_retrieve_respects_top_k`).
- [ ] В дашборде Grafana видно разное число возвращаемых документов при разных
      `top_k` (smoke-тест).

---

## 🟡 BUG-ALPHA-05 — MockRetrievalPipeline захардкожен в RAGEvaluator

- **Спека**: ALPHA-PROMPTS C-6 — `RAGEvaluator(pipeline: RAGPipeline)`
- **Приоритет**: 🟡 MEDIUM (юнит-тестирование идёт против мока, слабее чем спека)

### Проблема

`src/llm_client/rag/eval/evaluator.py:9-10` импортирует `MockRetrievalPipeline`
и использует его как `self.pipeline`. Спека C-6 требовала принимать реальный
`RagPipeline`. A/B-скрипты (`ab_test_reranker.py`, `ab_test_hybrid_rag.py`) —
это реальный integration path, но юнит-тесты против мока не ловят регрессии
самого `RagPipeline`.

### Рекомендуемый фикс

```python
# src/llm_client/rag/eval/evaluator.py
class RAGEvaluator:
    def __init__(self, pipeline: RAGPipeline, ...):  # ← принимать интерфейс
        self.pipeline = pipeline
        ...

# tests/unit/test_rag_evaluator.py
@pytest.fixture
def real_pipeline():
    return RagPipeline.from_settings_with_overrides(...)

def test_recall_at_5_with_real_pipeline(real_pipeline):
    evaluator = RAGEvaluator(pipeline=real_pipeline, ...)
    ...
```

Оставить `MockRetrievalPipeline` только для случаев, когда реальный pipeline
недоступен (CI без PG/MinIO), но добавить маркер `pytest.mark.integration` для
тестов с реальным.

### Критерий приёмки

- [ ] Юнит-тесты с реальным `RagPipeline` помечены `@pytest.mark.integration`.
- [ ] В CI Phase 2 integration-dev джоб запускает их против реального PG+MinIO.

---

## 🟢 BUG-ALPHA-06 — Миграция 008 — фикс сломанной 007

- **Спека**: ALPHA-PROMPTS A-3 — миграция `search_vector` должна пройти без
  блокировки >1 сек
- **Приоритет**: 🟢 LOW (исторический артефакт, но стоит задокументировать)

### Проблема

`migrations/versions/008_fix_documents_search_schema.py` существует
исключительно, чтобы починить сломанную 007 («Broken 007 typed search_vector as
Text() with server_default»). A-3 DoD «Migration passes without blocking
writes >1 sec» был когда-то нарушен — fix-up миграция это workaround.

### Рекомендуемый фикс

- [ ] Добавить комментарий в `007_add_tsvector_to_documents.py` со ссылкой на
      `008_fix_documents_search_schema.py` и описанием, почему 008 существует.
- [ ] В `AGENTS.md` раздел «Migrations» дополнить пояснением: «На свежих DB
      достаточно 007 + 008; 008 репеарит DB, на которые была накачена сломанная
      007».

### Критерий приёмки

- [ ] Документация миграций явно отмечает 008 как fix-up.
- [ ] Test `test_migration_009_chain.py` покрывает цепочку `004 → 005 → 006 →
      007 → 008 → 009` (если не покрывает — добавить).

---

# BETA (Phase 3) — Багфиксы

## 🔴 BUG-BETA-01 — ARCHITECT.md не обновлён до v1.4.0

- **Спека**: BETA-PROMPTS F-1 — `ARCHITECT.md` v1.3.0 → v1.4.0 с отражением
  Phase 3 изменений
- **Приоритет**: 🔴 BLOCKER (релиз-блокер для ROADMAP §7.7 exit-критерия #6
  «Документация обновлена»)

### Проблема

`analytics/ARCHITECT.md` остался на v1.3.0 (header line 5). Phase 3 изменения
**не отражены**:

1. §4 компонентная диаграмма: не добавлены `LLMRouter`, `ToolCallingAdapter`,
   `SemanticAnswerCache`, `McpServer`.
2. §7 ADRs: 011/015/016 не переведены из `Proposed` в `Approved`; ADR-004
   acceleration не отмечен.
3. §8 Trade-offs: line 1013 всё ещё пишет «ADR-011 в Phase 3 — cost component
   **pending**» — но код уже реализован.
4. §12 changelog: нет записи про Phase 3.
5. §12 Q-5: всё ещё `[PARTIALLY CLOSED … ADR-011 в Phase 3 — full closure]` —
   должен быть `[CLOSED]`.

Без этого фикса формально Phase 3 не «done» по ROADMAP §7.7.

### Рекомендуемый фикс

**Шаг 1 — bump версии**:

```markdown
| Версия документа | 1.4.0 |
| Дата             | 2026-MM-DD |
| Автор            | ... |
```

**Шаг 2 — §4 компонентная диаграмма**: добавить 4 новых компонента:

- `LLMRouter` (ADR-015) — между `Agent` и `LLMProviderFactory`, помечен
  `Phase 3 / cost-aware routing`.
- `ToolCallingAdapter` (ADR-016) — между `Agent` и `LLM`, помечен
  `Phase 3 / native-react-hybrid`.
- `SemanticAnswerCache` (ADR-011) — Tier-3 в RAG pipeline, между
  `CacheAwareLLMClient` и Redis DB 2.
- `McpServer` (ADR-004 accel.) — FastAPI sub-app, exposes tools via SSE.

**Шаг 3 — §7 ADRs**: перевести ADR-011/015/016 в `Approved` с датой и
обоснованием; добавить запись про ADR-004 acceleration.

**Шаг 4 — §8 Trade-offs**: обновить trade-off про cost component: вместо
«pending» написать «RESOLVED by ADR-015 in Phase 3 — `LLMRouter` + `CostGuard` +
`CircuitBreaker` operational, shadow-mode pilot running».

**Шаг 5 — §12 changelog**: добавить запись:

```markdown
### v1.4.0 — Phase 3 (BETA)
- ADR-011 (semantic cache) — implemented
- ADR-015 (cost-aware router) — implemented, shadow-mode pilot pending
- ADR-016 (tool capability adapter) — implemented, ollama pilot pending
- ADR-004 acceleration (MCP server) — implemented as preview
- Q-5 CLOSED
```

**Шаг 6 — §12 Q-5**: заменить `[PARTIALLY CLOSED]` на `[CLOSED in Phase 3]`.

### Критерий приёмки

- [ ] `analytics/ARCHITECT.md` header: `1.4.0`.
- [ ] `grep "1.3.0" analytics/ARCHITECT.md` возвращает 0 совпадений.
- [ ] §4 компонентная диаграмма содержит `LLMRouter`, `ToolCallingAdapter`,
      `SemanticAnswerCache`, `McpServer`.
- [ ] §7 ADR-011/015/016 — `Approved`.
- [ ] §8 line ~1013 не содержит слово `pending` для ADR-011.
- [ ] §12 changelog содержит запись `v1.4.0 — Phase 3 (BETA)`.
- [ ] §12 Q-5 — `[CLOSED]`.

---

## 🟠 BUG-BETA-02 — migration_adr_005_to_015.md — стаб вместо runbook

- **Спека**: BETA-PROMPTS C-6 — «4-step migration plan (Shadow → Gradual
  cutover → Full cutover → Cleanup)»
- **Приоритет**: 🟠 HIGH (документ есть, но не годится как операционный runbook)

### Проблема

`docs/migration_adr_005_to_015.md` — 25 строк, по сути copy-paste спеки.
Структура 4 шагов есть, но каждая секция — один буллет. Нет:

- Owner (кто ведет миграцию).
- Schedule (даты начала/окончания каждого шага).
- Rollback plan (что делать при провале).
- Communication plan (уведомления пользователей, чек-пойнты).
- Validation criteria per step.
- Runbook команд (конкретные CLI/env toggle).

### Рекомендуемый фикс

Расширить до полноценного runbook (~200 строк):

```markdown
# Migration Plan: ADR-005 (fallback_chain) → ADR-015 (LLMRouter)

**Owner**: <name>
**Schedule**:
- Step 1 (Shadow): 2026-MM-DD → 2026-MM-DD
- Step 2 (Gradual cutover): 2026-MM-DD → 2026-MM-DD
- Step 3 (Full cutover): 2026-MM-DD
- Step 4 (Cleanup): 2026-MM-DD → 2026-MM-DD

## Step 1 — Shadow Mode (2 weeks)

**Goal**: LLMRouter работает параллельно fallback_chain, логирует решения, не
влияет на трафик.

**Steps**:
1. Установить env:
   ```bash
   LLM_ROUTER_ENABLED=true
   LLM_ROUTER_SHADOW_MODE=true
   LLM_ROUTER_TRAFFIC_PERCENT=0
   ```
2. Запустить `python scripts/ab_test_router_shadow_mode.py --duration=14d`
3. Ежедневно проверять Grafana panel «Router Decisions by Policy»
4. Rollback criteria: >5% решений приводят к ошибкам → отключить
   `LLM_ROUTER_ENABLED=false`

**Validation**:
- [ ] 0 cost overrun в shadow режиме (Grafana panel показывает Δcost <5%)
- [ ] 0 latency regression (p99 router vs fallback < +5ms)
- [ ] Все metrics логируются

## Step 2 — Gradual Cutover (1 week)
...
```

### Критерий приёмки

- [ ] `docs/migration_adr_005_to_015.md` расширен до полноценного runbook.
- [ ] Каждый из 4 шагов имеет: goal, env-toggle, validation criteria, rollback
      plan.
- [ ] Указан owner и schedule.

---

## 🟠 BUG-BETA-03 — Pilot docs — процедурные стабы без результатов

- **Спека**: BETA-PROMPTS E-2 (adr_015_pilot.md), E-3 (adr_016_pilot.md)
- **Приоритет**: 🟠 HIGH (документы есть, но пилот не запускали)

### Проблема

- `docs/adr_015_pilot.md` (70 строк) — процедурный документ для 30-дневного
  shadow-mode пилота cost-aware router'а. Структура есть, но нет результатов
  реального запуска: нет вердикта вроде «ran 2026-MM-DD: 78% hit rate, 0.5%
  stale, p99 +12ms».
- `docs/adr_016_pilot.md` (78 строк) — то же для ReAct-адаптера на
  Ollama+Llama 3.1. Пилот не запускался.

Без результатов пилота нельзя сделать обоснованный cutover.

### Рекомендуемый фикс

**Шаг 1 — запустить пилоты**:

```bash
# adr_015 pilot
python scripts/ab_test_router_shadow_mode.py --duration=30d \
  --output reports/adr_015_pilot_YYYYMMDD.json

# adr_016 pilot
python scripts/pilot_ollama_react.py \
  --ollama-url http://localhost:11434 \
  --model llama3.1-8b \
  --output reports/adr_016_pilot_YYYYMMDD.json
```

**Шаг 2 — добавить секцию Results в каждый pilot doc**:

```markdown
## Pilot Results

**Run dates**: 2026-MM-DD → 2026-MM-DD
**Configuration**: LLM_ROUTER_SHADOW_MODE=true, 100% shadow traffic

### Metrics
- Cost predictability: 78% (target ≥70%) — ✅ PASS
- Cost overrun rate: 0.5% (target ≤2%) — ✅ PASS
- p99 latency delta: +12ms (target ≤+20ms) — ✅ PASS
- Circuit breaker activations: 2 (provider: openai, reason: rate_limit) —
  expected behavior

### Verdict
**PASS** — proceed to Step 2 (Gradual Cutover) per migration_adr_005_to_015.md.

### Issues encountered
- ... (описание всех аномалий)

### Sign-off
- [ ] Engineering: <name>
- [ ] SRE: <name>
- [ ] Architecture: <name>
```

### Критерий приёмки

- [ ] В `reports/` лежат JSON-файлы с результатами пилотов.
- [ ] `docs/adr_015_pilot.md` содержит секцию `## Pilot Results` с вердиктом.
- [ ] `docs/adr_016_pilot.md` — то же.
- [ ] Вердикт явно говорит PASS/FAIL/INCONCLUSIVE.

---

## 🟡 BUG-BETA-04 — agent_run tool не зарегистрирован

- **Спека**: BETA-PROMPTS H-1 — «exposes rag_query, file_export, web_search,
  **agent_run**»
- **Приоритет**: 🟡 MEDIUM (спека упомянута, реализация отсутствует)

### Проблема

`src/llm_client/mcp/tool_registry.py:register_default_tools()` регистрирует 3
инструмента: `rag_query`, `file_export`, `web_search`. Спека H-1 явно упоминает
`agent_run` как 4-й — делегирование long-running agent-задач через MCP. В коде
этого tool'а нет нигде: `grep agent_run src/` возвращает 0 совпадений.

### Рекомендуемый фикс

**Вариант A — реализовать `agent_run`** (если спека актуальна):

```python
# src/llm_client/mcp/agent_run_tool.py
async def agent_run_handler(
    prompt: str,
    user_id: str,
    tools: list[str] | None = None,
    max_iterations: int = 10,
) -> AsyncIterator[dict]:
    """Run long-running agent task, stream progress via SSE."""
    graph = build_agent_graph(...)
    async for event in graph.astream(...):
        yield {"type": "progress", "event": event}
    yield {"type": "done", "final_answer": ...}

# tool_registry.py:register_default_tools()
registry.register(ExposedTool(
    name="agent_run",
    description="Long-running agent execution with streaming progress",
    handler=agent_run_handler,
    streaming=True,
))
```

**Вариант B — удалить упоминание из спеки** (если `agent_run` отложен в Phase 4):

В `analytics/BETA-PROMPTS.md` H-1 убрать `agent_run` из списка и явно отметить
«deferred to Phase 4».

### Критерий приёмки

- [x] Либо `agent_run` зарегистрирован и покрыт тестом
      `test_mcp_server_agent_run.py`.
- [ ] Либо `analytics/BETA-PROMPTS.md` H-1 явно отмечает `agent_run` как
      deferred to Phase 4.

---

## 🟡 BUG-BETA-05 — SemanticAnswerCache._evict_if_needed — stub

- **Спека**: BETA-PROMPTS B-1 — soft cap `max_entries=10000`
- **Приоритет**: 🟡 MEDIUM (спека предусматривает, но cap не проверяется)

### Проблема

`src/llm_client/rag/semantic_cache.py:209`:
`async def _evict_if_needed(self) -> None: pass` — стаб с комментарием
«Phase 3: placeholder — rely on Redis allkeys-lru». Спека B-1 явно
предусматривает это для Phase 3 (Redis LRU сам управляет eviction), но soft cap
`max_entries=10000` в процессе не проверяется. Если по каким-то причинам Redis
LRU не активирован (misconfiguration), cache будет расти без ограничений.

### Рекомендуемый фикс

Добавить in-process soft cap:

```python
async def _evict_if_needed(self) -> None:
    """Soft cap — log warning if exceeded; Redis LRU is the real safety net."""
    count = await self._redis.dbsize()  # приблизительно
    if count > self._max_entries:
        # Только warn — Redis allkeys-lru реально подчистит
        logger.warning(
            "semantic_cache: %d entries > soft cap %d — Redis LRU will evict",
            count, self._max_entries,
        )
        # Записать метрику для алерта
        record_cache_event("soft_cap_exceeded", count=count)
```

### Критерий приёмки

- [ ] Тест `test_semantic_cache_soft_cap.py` проверяет, что при превышении
      `max_entries` пишется warning и метрика.
- [ ] Grafana panel «Semantic Cache» показывает alert при `soft_cap_exceeded`.

---

## 🟡 BUG-BETA-06 — fallback_chain (ADR-005) не удалён

- **Спека**: BETA-PROMPTS C-6 — миграция ADR-005 → ADR-015
- **Приоритет**: 🟡 MEDIUM (метрика идеальности Phase 3 оптимистична)

### Проблема

Спека C-6 требовала заменить `fallback_chain` на `LLMRouter`. Реализация
добавила `LLMRouter` параллельно через feature-flag `LLM_ROUTER_ENABLED=false`
(дефолт), старый путь `fallback_chain` в `provider.py` остался. Из-за этого
`idealidad.py` считает `Δсложности=2` (4 абстракции − 1 удалённая), но «−1» на
самом деле не случился — метрика 4/2=2.0 оптимистична.

### Доказательство

```python
# src/llm_client/agent/provider.py
# fallback_chain остался как backup
if settings.llm_router_enabled:
    decision = llm_router.route(...)
    ...
else:
    # старый путь fallback_chain
    for model in fallback_chain:
        ...
```

### Рекомендуемый фикс

**После успешного пилота (BUG-BETA-03 PASS)**:

1. Установить `LLM_ROUTER_ENABLED=true` по дефолту в `.env.example`.
2. Удалить `fallback_chain` из `provider.py`.
3. Удалить env `LLM_PROVIDER_FALLBACK_CHAIN` (если есть).
4. Обновить `idealidad.py`: явно убрать `-1` за `fallback_chain` удаление,
   либо добавить `+1` за `LLMRouter` как Approved.
5. Бамп ARCHITECT.md §8 trade-off про fallback.

### Критерий приёмки

- [ ] `grep fallback_chain src/llm_client/agent/provider.py` возвращает 0.
- [ ] `LLM_ROUTER_ENABLED=true` в `.env.example`.
- [ ] `idealidad.py` Phase 3 metric корректно считает Δсложности.

---

## 🟢 BUG-BETA-07 — Нет phase3-ci.yml workflow

- **Спека**: BETA-PROMPTS E-5 — Phase 3 CI pipeline extension
- **Приоритет**: 🟢 LOW (CI работает, но структура запутана)

### Проблема

`.github/workflows/` содержит только `phase1-ci.yml`, `phase2-ci.yml`,
`phase1-nightly.yml`, `phase2-nightly.yml`, `checkpoint-nightly.yml`.
Phase 3 PR-time тесты живут внутри `phase2-ci.yml` и `phase2-nightly.yml`
(см. также BUG-ALPHA-02). Спека E-5 не требует отдельного workflow файла, но
естественная структура — `phase3-ci.yml` + `phase3-nightly.yml`. Текущая
структура сбивает с толку при ревью Phase 3.

### Рекомендуемый фикс

После фикса BUG-ALPHA-02 — создать:

```yaml
# .github/workflows/phase3-ci.yml
name: Phase 3 CI
on:
  push:
    branches: [main]
  pull_request:

jobs:
  unit-tests-phase3:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install -e ".[dev]"
      - run: pytest tests/unit -m "phase3" -v

  integration-dev-phase3:
    runs-on: ubuntu-latest
    services:
      redis: ...
      minio: ...
      postgres: ...
    steps:
      - run: pytest tests/integration -m "phase3" -v
```

```yaml
# .github/workflows/phase3-nightly.yml
name: Phase 3 Nightly
on:
  schedule:
    - cron: "0 2 * * *"
  workflow_dispatch:

jobs:
  semantic-cache-ab-test: ...
  router-shadow-mode-ab-test: ...
  ollama-react-pilot: ...
  mcp-server-probe: ...
```

### Критерий приёмки

- [ ] Созданы `.github/workflows/phase3-ci.yml` и `phase3-nightly.yml`.
- [ ] В Phase 2 nightly больше нет джобов с префиксом `phase3-`.
- [ ] README Phase 2 CI обновлён, добавлен раздел «Phase 3 CI».

---

# Рекомендуемый порядок работ

## Sprint 1 (релиз-блокеры и high-priority blockers)

1. **BUG-MVP-01** — ForensicStreamWriter bucket bug (релиз-блокер Phase 1).
2. **BUG-BETA-01** — ARCHITECT.md bump до v1.4.0 (релиз-блокер Phase 3).
3. **BUG-MVP-02** — S3 lifecycle policy для forensic bucket.
4. **BUG-MVP-03** — AccessLogIngestor wiring в startup.
5. **BUG-ALPHA-01** — redis.conf: задокументировать supersession.
6. **BUG-ALPHA-02** — вынести Phase 3 джобы из phase2-nightly.yml.
7. **BUG-BETA-02** — расширить migration_adr_005_to_015.md до runbook.
8. **BUG-BETA-03** — запустить пилоты ADR-015 и ADR-016, дописать Results.

## Sprint 2 (medium priority)

9. **BUG-MVP-04** — задокументировать merge B-2 ↔ E-2 в ARCHITECT.md.
10. **BUG-MVP-05** — расширить assert в test_cancel_forensic_logging.
11. **BUG-ALPHA-03** — удалить мёртвый код в pipeline_singleton.py.
12. **BUG-ALPHA-04** — починить RagPipeline.retrieve top_k.
13. **BUG-ALPHA-05** — RAGEvaluator принимает реальный RagPipeline.
14. **BUG-BETA-04** — реализовать или defer agent_run tool.
15. **BUG-BETA-05** — soft cap warning в SemanticAnswerCache.
16. **BUG-BETA-06** — удалить fallback_chain после пилота.

## Sprint 3 (low priority, cleanup)

17. **BUG-MVP-06** — tighten latency assertion до <5ms.
18. **BUG-ALPHA-06** — задокументировать миграцию 008 как fix-up.
19. **BUG-BETA-07** — создать phase3-ci.yml + phase3-nightly.yml.

---

# Глоссарий статусов

- 🔴 **BLOCKER** — релиз-блокер, должен быть исправлен до exit-критерия фазы.
- 🟠 **HIGH** — серьёзное нарушение спеки или DoD, требует исправления в этом спринте.
- 🟡 **MEDIUM** — code smell, тест-провал или слабое место, исправить в следующем спринте.
- 🟢 **LOW** — косметика или документация, можно отложить.

---

*Файл сгенерирован по результатам аудита реализации OriaAI (llm-client) против
`analytics/MVP-PROMPTS.md`, `analytics/ALPHA-PROMPTS.md`, `analytics/BETA-PROMPTS.md`
от 2026-10-28.*

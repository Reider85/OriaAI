# ALPHA-PROMPTS.md — Промпты для этапа Alpha (Phase 2)

| Атрибут | Значение |
|---|---|
| Версия документа | 1.0.0 |
| Дата | 2026-09-23 |
| Источники | `ROADMAP.md` v1.1.0 §6 (Phase 2 — Alpha), §12, §15.2, §18.1; `TRIZ-ANALYSIS.md` v1.0.0 §5.2 (C-2), §6.1 (C-6), §8.1 (стандарт 1.1.5), §10 (матрица противоречий), §11 (драфты ADR-010/017/020); `ARCHITECT.md` v1.1.0 §5.2.2 (Checkpointer), §5.2.5 (RAG Layer), §6 (`agent_checkpoints`/`documents` таблицы), §7 ADR-001/003/005 |
| Этап | Phase 2 — Alpha (14 чел-дн ADR-работы + 2.5 чел-дн тесты/CI/доки = 16.5 чел-дн) |
| ADR в области | ADR-010 (Async Checkpoint Write-Behind Log), ADR-017 (Reranker Model in RAG), ADR-020 (Hybrid BM25+Vector RAG default) |
| Резолвит противоречия | C-2 (PG checkpoint vs latency) — полностью; C-6 (long RAG context vs cost) — полностью (вместе ADR-017 + ADR-020; ADR-011 в Phase 3 закроет cost-составляющую) |
| Целевой LLM | Универсальные (Cursor / Copilot / Claude Code / ChatGPT) |
| Гранулярность | Микро-промпты (1 промпт = 1 файл / 1 класс / 1 подзадача) |
| Предусловие | Phase 1 завершена (`ROADMAP.md` §5.6): Redis в docker-compose (Блок A-1 `MVP-PROMPTS`), PostgreSQL, `S3CompatibleStorage` (расш. ADR-008), ADR-013 (cancel), ADR-014 (DualStreamLogger), `UIClient` abstraction (UI-2) — все Approved. ARCHITECT.md v1.1.0 |
| Связанные документы | `MVP-PROMPTS.md` v1.0.0 (контракты Phase 1, не переопределяются), `UI-PROMPTS.md` v1.0.0 (UI-3 Streamlit fragments — может помочь в latency-тесте B-6), `BACKLOG.md` v1.0.0 (UI-работы Phase 1, не входят в Phase 2) |

---

## 0. Как пользоваться документом

Каждый промпт — самостоятельный блок, огороженный ` ``` `-код-блоком, готовый к копи-пасту в любой код-ассистент. Промпты сгруппированы в шесть блоков **A–F**, идущих в порядке зависимостей:

```
A. Инфра ──┬──→ B. ADR-010 (RedisPostgresCheckpointer) ──┐
           │                                              ├─→ E. Тесты/CI ──→ F. Документация
           ├──→ C. ADR-017 (Reranker) ─────────────────────┤
           └──→ D. ADR-020 (Hybrid BM25+Vector RAG) ───────┘
                                                       │
                                                       └──→ D-5 зависит от C-4 (reranker применяется после fusion)
```

**Конвенции** (наследуются из `MVP-PROMPTS.md` §0):

- Имена классов, методов, эндпоинтов — на английском (как в `ARCHITECT.md`).
- Имена ADR и противоречий — в формате `ADR-010`, `C-2` (как в `TRIZ-ANALYSIS.md` §10).
- Раздел `Definition of Done` — конкретные измеримые критерии готовности.
- Раздел `Антипаттерны` — что LLM НЕ должен делать; если предложит — отбраковывать.
- Раздел `Связанные ADR` — какие ADR затрагивает (не ломает / упраздняет / требует).
- Все env vars / class names / interface signatures — **продолжают** контракты Phase 1; не переопределяют, не дублируют. Существующие `BaseCheckpointSaver` (LangGraph), `VectorStoreFactory`/`VectorStoreRegistry` (ADR-003 / драфт ADR-009), `RetrieverConfig` (`ARCHITECT.md` §5.2.5), `PostgresSaver` (ADR-001), `agent_checkpoints` / `documents` таблицы (`ARCHITECT.md` §6) — **не переопределяются**; Phase 2 их расширяет.

Полный прогон блоков A→F занимает 14 чел-дн (ADR-работы по `ROADMAP.md` §6.2) + 2.5 чел-дн (тесты/CI/доки). Параллелизация (см. §8) — 9–10 чел-дн при команде из 2 разработчиков. Критерии выхода из Phase 2 — в Приложении §7.

**Фазировка противоречий** (из `TRIZ-ANALYSIS.md` §10): Phase 2 резолвит C-2 (полностью через ADR-010) и C-6 (полностью через ADR-017 + ADR-020 — качественная составляющая retrieval; cost-составляющая C-6 остаётся для ADR-011 в Phase 3). Связанные законы развития ТРИЗ (§4 `TRIZ-ANALYSIS.md`): закон 4.3 (согласование ритмики частей системы) — ADR-010 развязывает ритмику node-execution и persistence; стандарт 1.1.5 (введение второго поля в веполь) — ADR-020 вводит BM25 как второе поле retrieval; стандарт 2.2.2 (переход к более динамичной веполи) — ADR-017 вводит cross-encoder как более сильное поле переранжировки.

---

## 1. Блок A. Инфра-подготовка Phase 2

**Источник**: `ROADMAP.md` v1.1.0 §6.2 (зависимости: Redis, bge-reranker, PostgreSQL tsvector). Разворачивается параллельно с архитектурным ревью ADR-010/017/020, до старта кодирования Блоков B/C/D.

Phase 1 уже оставила Redis в docker-compose (Блок A-1 `MVP-PROMPTS`), но в режиме pub/sub + AOF — без ADR-010 checkpoint-функции. Phase 2 расширяет конфигурацию Redis (dedicated DB 1 для checkpoint-WAL, `maxmemory-policy=noeviction`, `notify-keyspace-events` для eviction-мониторинга), добавляет две новые инфра-зависимости: локальную ML-модель `bge-reranker-base` (для C-2) и PostgreSQL `tsvector`-индекс на таблице `documents` (для D-2/D-3). Все три работы — независимы, параллелятся между собой и с архитектурным ревью драфтов ADR-010/017/020.

### A-1. Redis WAL configuration (расширение Блока A-1 `MVP-PROMPTS`)

```
Ты — DevOps-инженер команды LLM Client. Расширь Redis-конфигурацию из Блока A-1
MVP-PROMPTS для Phase 2: Redis теперь не только pub/sub для ADR-013, но и
synchronous WAL для ADR-010 (Блок B), и eviction-мониторинг.

Контекст:
- Блок A-1 MVP-PROMPTS уже поднял Redis 7+ с AOF-persistence (appendonly yes),
  healthcheck через redis-cli ping.
- ADR-010 (TRIZ-ANALYSIS.md §11, ROADMAP.md §6.3) использует Redis как
  synchronous checkpoint layer: каждый node transition графа пишет в Redis
  (latency <1 мс, TTL=24h). Background-flusher (Блок B-4) сбрасывает в
  PostgreSQL каждые 5 сек или N checkpoints.
- Существующий Redis DB 0 уже занят pub/sub для ADR-013 (канал
  session:{id}:cancel). Checkpoint-WAL должен идти в отдельный DB чтобы
  maxmemory-policy и TTL не конфликтовали с pub/sub.
- ТРИЗ-принцип 35 (изменение физических свойств): hot state (Redis, низколатентный)
  отделён от cold state (PostgreSQL, персистентный). DB-изоляция — это разделение
  в пределах одного Redis-инстанса.
- ТРИЗ-принцип 9 (предварительное противодействие): eviction policy
  `noeviction` для checkpoint-DB — Redis падает с OOM, не теряет checkpoint-ы
  тихо; это предпочтительнее тихой потери данных.

Задача:
1. Обнови docker-compose.yml для сервиса `redis` (Блок A-1 MVP):
   - Добавь команду `redis-server --appendonly yes --databases 16` (по умолчанию
     16, явно для документации).
   - Добавь volume `./redis/redis.conf:/usr/local/etc/redis/redis.conf:ro` с
     конфиг-файлом redis.conf (см. п.2).
   - Оставь healthcheck и networks из Блока A-1 MVP без изменений.
2. Создай файл `redis/redis.conf` со следующими настройками:
   - `appendonly yes` (наследовано из Phase 1).
   - `appendfsync everysec` (баланс между durability и throughput; ADR-010
     требует loss-window не более 1 сек при отказе Redis).
   - `maxmemory 512mb` (хватает для 24h-checkpoint-ов при типовой нагрузке
     50 RPS × 10 nodes × 5KB per checkpoint = 2.5GB / 24h; maxmemory 512mb
     с noeviction = OOM-защита, не задерживает checkpoint-write).
   - `maxmemory-policy noeviction` (CRITICAL: checkpoint-ы не вытесняются,
     Redis падает с OOM вместо тихой потери).
   - `notify-keyspace-events ""` (отключить по умолчанию; включается отдельным
     `CONFIG SET` в Блоке B-4 если нужно мониторить eviction в future).
   - `dir /data` (наследовано).
   - `save ""` (snapshotting отключён — AOF покрывает; snapshots добавили бы
     sync-write latency, противоречит C-2).
3. В .env.example обнови переменные (добавь, не заменяй):
   - REDIS_URL=redis://redis:6379/0 (для pub/sub ADR-013, без изменений).
   - REDIS_CHECKPOINT_URL=redis://redis:6379/1 (для ADR-010, отдельный DB).
   - REDIS_CHECKPOINT_TTL_SECONDS=86400 (24h, default).
   - REDIS_CHECKPOINT_MAXMEMORY_POLICY=noeviction (для документации).
4. В README обнови раздел "Phase 1 infra" → "Phase 1+2 infra":
   - Добавь параграф: "Redis DB 0 — ADR-013 pub/sub; Redis DB 1 — ADR-010
     checkpoint-WAL. Не переключай DB без необходимости — pub/sub не работает
     кросс-DB в одном connection."
   - Добавь проверку: `redis-cli -n 1 INFO memory | grep used_memory_human` —
     должно показывать 0 после старта, расти по мере выполнения графов.
   - Добавь проверку eviction: `redis-cli -n 1 INFO stats | grep evicted_keys`
     должно быть 0; если не 0 — alert (checkpoint-теряется, OOM imminent).

Definition of Done:
- `docker-compose up redis` поднимает сервис за <3 сек (как в Phase 1).
- `redis-cli -n 1 ping` возвращает PONG (DB 1 доступен).
- `redis-cli -n 0 INFO keyspace` показывает db0 с keys (после теста pub/sub).
- `redis-cli -n 1 INFO memory | grep maxmemory_policy` возвращает "noeviction".
- `redis-cli -n 1 INFO persistence | grep aof_enabled` возвращает 1.
- Appendfsync everysec подтверждается через `redis-cli CONFIG GET appendfsync`.
- AOF-файл `appendonly.aof` растёт в volume `redis-data` по мере checkpoint-ов
  в DB 1 (после интеграции с Блоком B-1).
- README обновлён с проверками Phase 1+2.

Антипаттерны:
- НЕ используй DB 0 для checkpoint-ов — он занят pub/sub ADR-013,
  cross-DB в одном redis-connection не работает с pub/sub корректно.
- НЕ включай `maxmemory-policy allkeys-lru` для checkpoint-DB — это приведёт
  к тихой потере checkpoint-ов под нагрузкой, что нарушает ADR-010 durability.
- НЕ поднимай отдельный Redis-инстанс для checkpoint-ов — это +1 точка отказа,
  +1 service to manage; DB-изоляция достаточна для Phase 2 single-instance.
  (Phase 5 multi-instance рассмотрит Redis Cluster — см. ROADMAP §9.5.)
- НЕ включай RDB snapshots (`save 900 1` и т.д.) — это sync write на диск, ломает
  C-2 latency. AOF everysec — достаточный durability для checkpoint-WAL.
- НЕ хардкодь DB-индекс в коде — только через REDIS_CHECKPOINT_URL env var.
- НЕ настраивай TLS на Redis — внутренний трафик docker-compose, до Phase 5
  (наследовано из Блока A-1 MVP).

Связанные ADR:
- Расширяет инфру из: Блок A-1 MVP-PROMPTS (Redis 7+), ADR-013 (pub/sub DB 0).
- Подготавливает для: ADR-010 (Блок B, checkpoint-WAL в DB 1).
- Не затрагивает: ADR-014 (forensic — отдельный MinIO bucket), расш. ADR-008.
```

### A-2. `bge-reranker-base` in-process ML model setup

```
Ты — ML-инженер команды LLM Client. Подготовь `bge-reranker-base` (BAAI, ~278M
параметров, ~600MB в памяти) как локальную ML-модель для ADR-017 (Блок C).
Модель должна загружаться in-process при старте приложения, без external API.

Контекст:
- ADR-017 (TRIZ-ANALYSIS.md §11, ROADMAP.md §6.4) требует cross-encoder reranker
  в RAG pipeline. Default reranker — `bge-reranker-base`, опционально —
  Cohere Rerank API (Блок C-3).
- bge-reranker-base: BAAI/bge-reranker-base, 278M параметров, ~600MB RAM при
  загрузке, CPU-inference 50–200 мс на 20 чанков, GPU-inference <50 мс (опционально).
- ТРИЗ-принцип 25 (самообслуживание): модель in-process, не external API —
  нет network latency, нет vendor lock-in, нет cost-per-call.
- ТРИЗ-принцип 3 (местное качество): bge-reranker специализирован для retrieval
  reranking, не general-purpose LLM — точнее на RAG-задачах, дешевле Cohere.
- В Phase 4 (Local LLM) модель будет переиспользована — установка сейчас
  готовит инфру для Phase 4.

Задача:
1. Добавь в requirements.txt (или pyproject.toml) зависимости:
   - `sentence-transformers>=2.7.0` (фреймворк для загрузки cross-encoder-ов).
   - `torch>=2.2.0` (бэкенд для inference).
   - `transformers>=4.40.0` (model loading).
   - Для GPU (опционально): `torch>=2.2.0+cu121` (CUDA 12.1).
2. Создай директорию `models/bge-reranker-base/` в проекте для кэширования
   модели (gitignored, скачивается при первом старте или CI-build).
3. Создай скрипт `scripts/download_bge_reranker.py`:
   - Использует `huggingface_hub.snapshot_download` для скачивания модели в
     `models/bge-reranker-base/`.
   - В README добавь инструкцию: `python scripts/download_bge_reranker.py`
     выполняется один раз после `pip install`.
   - В CI (Блок E-5) — шаг "Download bge-reranker-base", кэшируется в
     `~/.cache/huggingface` между запусками.
4. Env vars в .env.example:
   - `RERANKER_MODEL_NAME=BAAI/bge-reranker-base` (HuggingFace model id).
   - `RERANKER_MODEL_DIR=./models/bge-reranker-base` (локальный кэш).
   - `RERANKER_DEVICE=cpu|cuda` (default: cpu; cuda если доступен).
   - `RERANKER_MAX_LENGTH=512` (max sequence length, bge-reranker-base
     поддерживает до 512 токенов).
   - `RERANKER_BATCH_SIZE=8` (batch для inference; 8 для CPU, 32 для GPU).
5. В docker-compose.yml добавь volume `./models:/app/models:ro` для
   монтирования локально скачанной модели в контейнер agent-service.
6. В README раздел "Phase 2 ML models":
   - Инструкция по скачиванию: `python scripts/download_bge_reranker.py`.
   - RAM-профиль: ~600MB после загрузки, ~1.2GB пиковая при inference на 20
     чанков с batch_size=8.
   - CPU vs GPU сравнение: типовой reranking 20 чанков — 150 мс CPU vs 30 мс
     GPU; для Phase 2 staging — CPU достаточно (latency budget 200 мс по
     ADR-017 критерию готовности).

Definition of Done:
- `python scripts/download_bge_reranker.py` скачивает модель (~600MB) в
  `models/bge-reranker-base/` за <5 минут на типичном broadband.
- После скачивания `ls models/bge-reranker-base/` содержит `config.json`,
  `pytorch_model.bin` (или `model.safetensors`), `tokenizer.json`,
  `tokenizer_config.json`, `special_tokens_map.json`.
- Простой smoke-тест (в `scripts/download_bge_reranker.py` в конце):
  `CrossEncoder(model_dir).predict([("query", "doc1"), ("query", "doc2")])`
  возвращает 2 float-числа (reranking scores) за <500 мс на CPU.
- `docker-compose up agent-service` с примонтированным `./models` запускается
  без повторного скачивания модели.
- В CI (Блок E-5) кэш HuggingFace переиспользуется между запусками (через
  actions/cache или эквивалент).
- RAM при inference на 20 чанков не превышает 1.5 GB (проверка через
  `docker stats agent-service` во время smoke-теста).

Антипаттерны:
- НЕ хардкодь `BAAI/bge-reranker-base` в коде — только через RERANKER_MODEL_NAME
  env var. Cohere или другая модель может заменить bge в будущем (Блок C-3,
  C-5).
- НЕ загружай модель в hot path запроса — только при старте приложения
  (lazy singleton в Блоке C-2). Загрузка 600MB-модели в hot path = 5+ сек
  latency на первый запрос.
- НЕ скачивай модель в docker build (multi-GB layer, slow CI). Скачивание —
  отдельный шаг, монтируется volume.
- НЕ используй `bge-reranker-large` (1.2GB, более медленный) без явного ADR
  update — ADR-017 фиксирует `bge-reranker-base` как default.
- НЕ включай CUDA-зависимости по умолчанию — Docker image растёт на 4GB.
  CUDA — через `--device cuda` в docker-compose или `RERANKER_DEVICE=cuda`,
  только если staging/prod имеет GPU.
- НЕ делай inference на CPU с batch_size > 16 — latency превысит 200 мс budget
  ADR-017. Батч-настройка CPU=8, GPU=32 — см. п.4.

Связанные ADR:
- Подготавливает для: ADR-017 (Блок C, bge-reranker in-process).
- Будет переиспользован в: Phase 4 (Local LLM) — `BGEEmbeddings` для retrieval
  индексации (`ARCHITECT.md` §5.2.5 строка 461 упоминает BGEEmbeddings как
  Phase 4 опцию).
- Не затрагивает: ADR-010, ADR-020.
```

### A-3. PostgreSQL tsvector column + GIN index на `documents`

```
Ты — Backend/Database-разработчик LLM Client. Добавь полнотекстовый индекс
PostgreSQL на таблицу `documents` для ADR-020 (Блок D): tsvector column +
GIN index, parallel с существующим vector index.

Контекст:
- ADR-020 (TRIZ-ANALYSIS.md §11, ROADMAP.md §6.5) делает hybrid retrieval
  (BM25 + vector) default. PostgreSQL `tsvector` — реализация BM25-индекса
  для Phase 2 (альтернатива — OpenSearch, но +1 сервис; tsvector в существующей
  PostgreSQL — нулевая новая зависимость, ТРИЗ-принцип 5 (объединение)).
- Существующая таблица `documents` (ARCHITECT.md §6 строки 559–567):
  ```sql
  CREATE TABLE documents (
      id UUID PRIMARY KEY,
      user_id UUID NOT NULL REFERENCES users(id),
      source_type TEXT NOT NULL,
      source_uri TEXT,
      content_hash TEXT NOT NULL,
      content TEXT NOT NULL,        -- полный текст документа
      metadata JSONB DEFAULT '{}',
      created_at TIMESTAMPTZ NOT NULL DEFAULT now()
  );
  ```
- ТРИЗ-стандарт 1.1.5 (введение второго поля в веполь): к существующему
  vector-индексу добавляется tsvector-поле, оба индекса строятся параллельно
  при индексации документа (Блок D-2).
- ТРИЗ-принцип 28 (замена механической схемы): вместо отдельного OpenSearch
  сервиса — PostgreSQL tsvector, нулевая новая зависимость.
- PostgreSQL конфигурация: default text search config — `english` для
  английских документов; для русской поддержки нужен `pg_trgm` extension
  (fuzzy matching) и/или `rum` (better GIN). Phase 2 — `english` default,
  `pg_trgm` для Unicode fuzzy (опционально).

Задача:
1. Создай Alembic migration `phase2_add_tsvector_to_documents.py`:
   ```sql
   -- Enable extensions
   CREATE EXTENSION IF NOT EXISTS pg_trgm;

   -- Add tsvector column (computed from content + metadata.title if exists)
   ALTER TABLE documents ADD COLUMN search_vector tsvector
     GENERATED ALWAYS AS (
       setweight(to_tsvector('english', coalesce(content, '')), 'A') ||
       setweight(to_tsvector('english', coalesce(metadata->>'title', '')), 'B')
     ) STORED;

   -- GIN index for fast tsvector queries
   CREATE INDEX idx_documents_search_vector ON documents USING GIN(search_vector);

   -- Trigram index for fuzzy matching (optional, для русских терминов)
   CREATE INDEX idx_documents_content_trgm ON documents USING GIN (content gin_trgm_ops);

   -- Add tsvector_length for ranking
   CREATE INDEX idx_documents_ts_rank ON documents (ts_rank(search_vector,
     websearch_to_tsquery('english', ''))) WHERE search_vector IS NOT NULL;
   ```
   Замечания:
   - `GENERATED ALWAYS AS ... STORED` — PostgreSQL 12+ автоматически
     пересчитывает tsvector при UPDATE content или metadata.
   - `setweight` 'A' для content (тело документа), 'B' для title (заголовок)
     — title весом ниже, но всё ещё значимым для BM25-ранжирования.
   - `websearch_to_tsquery` (вместо `plainto_tsquery`) — поддерживает
     google-стиль запросов ("exact phrase" -exclude OR alt).
2. Обнови `documents` schema в ARCHITECT.md §6 (добавь описание search_vector
   колонки в комментарии, как сделано для content_hash, metadata).
3. В .env.example добавь:
   - `PG_TEXT_SEARCH_CONFIG=english` (default; для русских документов —
     `russian` или кастомный конфиг).
   - `PG_FUZZY_MATCHING_ENABLED=true|false` (default: false; если true —
     используется pg_trgm индекс для fuzzy).
4. В README раздел "Phase 2 PostgreSQL full-text search":
   - Проверка tsvector: `SELECT id, search_vector FROM documents LIMIT 5;`
   - Проверка GIN: `EXPLAIN ANALYZE SELECT * FROM documents WHERE
     search_vector @@ websearch_to_tsquery('english', 'error code 1234');`
     — должно использовать `Bitmap Index Scan on idx_documents_search_vector`.
   - Проверка trigram: `EXPLAIN ANALYZE SELECT * FROM documents WHERE
     content % 'приер'` (опечатка в "пример") — должно использовать
     `Bitmap Index Scan on idx_documents_content_trgm`.
5. Benchmark перед commit:
   - На staging с 10k документов: `EXPLAIN ANALYZE` hybrid query
     (vector + tsvector) должен выполняться <50 мс (latency budget ADR-020).
   - Если >50 мс — рассмотреть `rum` extension (fast tsvector rank) или
     денормализацию.

Definition of Done:
- Migration проходит на staging без блокировки writes >1 сек (используй
  `CREATE INDEX CONCURRENTLY` для GIN, если таблица большая).
- После миграции `SELECT search_vector FROM documents WHERE content LIKE
  '%error%' LIMIT 5` возвращает tsvector с лемматизированными терминами.
- `EXPLAIN ANALYZE SELECT * FROM documents WHERE search_vector @@
  websearch_to_tsquery('english', 'hello world')` использует GIN index
  (не Seq Scan).
- pg_trgm extension доступна (`SELECT extversion FROM pg_extension WHERE
  extname = 'pg_trgm'`).
- Fuzzy matching `content % 'приер'` работает (после включения
  PG_FUZZY_MATCHING_ENABLED=true).
- Hybrid query latency <50 мс на 10k документов (benchmark в README).
- ARCHITECT.md §6 обновлён с описанием search_vector колонки.

Антипаттерны:
- НЕ используй `tsvector` без `GENERATED ALWAYS AS STORED` — иначе
  приложение должно поддерживать tsvector в sync с content, что приведёт к
  рассинхронизации и битым индексам.
- НЕ используй `to_tsvector('simple', ...)` — это отключает лемматизацию,
  что хуже BM25. Конфиг `english` (или `russian` для RU) обязателен.
- НЕ создавай GIN-индекс без `CONCURRENTLY` на production — блокирует
  writes. Включай `CREATE INDEX CONCURRENTLY` в migration.
- НЕ делай tsvector на `metadata` целиком (JSONB) — `to_tsvector` не умеет
  JSONB напрямую, нужны явные `metadata->>'field'`. Только title на Phase 2.
- НЕ добавляй tsvector для каждого поля документа — это +memory per row.
  content + title достаточно для ADR-020 recall@exact-term.
- НЕ включай `pg_trgm` extension если PG_FUZZY_MATCHING_ENABLED=false —
  индекс занимает место, не нужен без fuzzy. Создавай по env-флагу в
  migration (через `DO $$ ... IF ... END IF; $$`).
- НЕ используй OpenSearch / Elasticsearch — это +1 сервис, нарушает принцип
  5 (объединение). tsvector в PostgreSQL покрывает ADR-020 требования.

Связанные ADR:
- Подготавливает для: ADR-020 (Блок D, BM25 через tsvector).
- Расширяет таблицу: `documents` из `ARCHITECT.md` §6.
- Не затрагивает: ADR-010 (checkpoint, отдельная таблица agent_checkpoints),
  ADR-017 (reranker — separate, не использует tsvector).
- Зависит от: PostgreSQL 12+ (для GENERATED ALWAYS AS STORED), pg_trgm
  extension (если PG_FUZZY_MATCHING_ENABLED=true).
```

---

## 2. Блок B. ADR-010: Async Checkpoint Write-Behind Log — микро-декомпозиция

**Источник**: `ROADMAP.md` v1.1.0 §6.3, `TRIZ-ANALYSIS.md` v1.0.0 §5.2 (C-2), §11 (ADR-010 драфт), §8.1 (веполь `LangGraph → Redis → PostgreSQL`), §10 (матрица 31×25). Резолвит противоречие **C-2** (PG checkpoint vs latency) — полностью. Принципы ТРИЗ: 9 (предварительное противодействие — sync Redis + async PG), 19 (периодическое действие — flush каждые 5 сек/N checkpoints), 28 (замена механической схемы — WAL вместо sync SQL), 35 (изменение физических свойств — hot/cold state разделение). Полная реализация: 6 подзадач, 5 чел-дн (`ROADMAP.md` §6.2 п.6.2.1).

**Контекст ADR-010**: ADR-001 использует `PostgresSaver` для LangGraph checkpointer с синхронной записью в `agent_checkpoints` (`ARCHITECT.md` §6 строки 584–592) на каждом node transition. Это добавляет 10–50 мс на каждый переход, суммарно 50–200 мс на типовой агентский цикл (5–10 nodes), что становится bottleneck при росте RPS. Решение — composite checkpointer `RedisPostgresCheckpointer` с двухуровневой схемой: Redis = synchronous write (latency <1 мс, TTL=24h), PostgreSQL = asynchronous batched write (background task каждые 5 сек или N checkpoints). `BaseCheckpointSaver` interface LangGraph остаётся совместимым — composite реализует тот же интерфейс, граф не знает о двухуровневости.

**Эффект ADR-010** (из `TRIZ-ANALYSIS.md` §11):
- (+) Latency checkpointing снижается с 10–50 мс до <1 мс.
- (+) PostgreSQL не нагружается на каждом node transition.
- (+) Resume-after-restart сохраняется (Redis snapshot + PostgreSQL durable).
- (-) Добавляется Redis как mandatory dependency для checkpointing (раньше опциональный, поднимался в Phase 1 для ADR-013 pub/sub).
- (-) Возможна потеря последних 5 сек checkpoint-ов при одновременном отказе Redis и PostgreSQL (acceptable risk по `ROADMAP.md` §6.3).
- (-) Сложнее тестировать (два хранилища вместо одного — компенсируется Блоком B-6).

### B-1. `RedisCheckpointer` (synchronous write, TTL=24h)

```
Ты — Backend-разработчик LLM Client. Создай `RedisCheckpointer` — синхронный
write-layer для ADR-010 (Блок B). Реализует `BaseCheckpointSaver` interface
LangGraph, пишет checkpoint-ы в Redis DB 1 (Блок A-1) с TTL=24h.

Контекст:
- ADR-010 (TRIZ-ANALYSIS.md §11): RedisCheckpointer — synchronous write,
  latency <1 мс, TTL=24h (86400 сек).
- Блок A-1 подготовил Redis с DB 1 (REDIS_CHECKPOINT_URL), maxmemory=512mb,
  maxmemory-policy=noeviction, AOF everysec.
- LangGraph 0.2+ `BaseCheckpointSaver` interface (см. langgraph.checkpoint.base):
  - `aput(config, checkpoint, metadata, new_versions) -> RunnableConfig`
  - `aget(config) -> Optional[Checkpoint]`
  - `alist(config, filter, before, limit) -> Iterator[Checkpoint]`
  - `aput_writes(config, writes, task_id) -> None`
- Существующий `PostgresSaver` (ADR-001) реализует тот же interface —
  RedisCheckpointer — независимая реализация, не наследник PostgresSaver.
- ТРИЗ-принцип 9 (предварительное противодействие): TTL=24h — защита от
  неограниченного роста checkpoint-ов в Redis; 24h достаточно для типичной
  сессии (если сессия живёт дольше — flush в PG покрывает).

Задача:
1. Создай класс `RedisCheckpointer` в `src/llm_client/orchestration/checkpointers/
   redis_checkpointer.py`:
   - `__init__(redis_client: redis.asyncio.Redis, ttl_seconds: int = 86400)`:
     * `redis_client` — соединение с DB 1 (REDIS_CHECKPOINT_URL из Блока A-1).
     * `ttl_seconds` — TTL для checkpoint-записей, default 86400 (24h).
   - Реализуй методы `BaseCheckpointSaver`:
     * `aput(config, checkpoint, metadata, new_versions) -> RunnableConfig`:
       - Сериализует checkpoint через `json.dumps` (или pickle для совместимости
         с LangGraph `Checkpoint` type).
       - Ключ: `checkpoint:{thread_id}:{checkpoint_id}` (thread_id из config).
       - Значение: serialized checkpoint + metadata.
       - `SET key value EX ttl_seconds` (atomic set + TTL).
       - Возвращает обновлённый config (не меняет его, просто pass-through).
     * `aget(config) -> Optional[Checkpoint]`:
       - Достаёт последний checkpoint по thread_id (через `LIST` pattern
         или отдельный ключ `checkpoint:{thread_id}:latest`).
       - Десериализует, возвращает `Checkpoint` объект.
       - Возвращает None если нет checkpoint-а.
     * `alist(config, filter, before, limit) -> Iterator[Checkpoint]`:
       - `SCAN checkpoint:{thread_id}:*` с фильтрами.
       - Возвращает iterator (lazy), не загружает все сразу.
     * `aput_writes(config, writes, task_id) -> None`:
       - Записывает writes (промежуточные tool-call результаты) в отдельный
         ключ `writes:{thread_id}:{task_id}` с TTL.
2. Connection management:
   - Используй `redis.asyncio.Redis.from_url(REDIS_CHECKPOINT_URL)` (async).
   - Не создавай новый клиент на каждый вызов — singleton в DI-контейнере.
   - При потере соединения — retry 3 раза с экспоненциальной задержкой (1ms,
     2ms, 4ms), затем raise `CheckpointWriteError`.
3. TTL strategy:
   - При каждом `aput` — `EXPIRE key ttl_seconds` (обновление TTL на каждом
     write, не только при создании — active sessions не вытесняются).
   - `aput_writes` — тот же TTL (24h), write-key удаляется вместе с
     checkpoint-ом.
4. Serialization:
   - Default: `pickle` (LangGraph `Checkpoint` — dataclass, pickle совместим).
   - Опционально: `json` через `Checkpoint.model_dump()` если LangGraph
     поддерживает pydantic-модель (проверь в `langgraph.checkpoint.base`).
   - json предпочтительнее (pickle — security risk при десериализации
     untrusted data, но checkpoint-ы наши собственные — OK).

Definition of Done:
- `aput` выполняется за <1 мс в 99% случаев (без Redis latency spikes).
- `aget` возвращает checkpoint, записанный через `aput`, корректно.
- TTL обновляется на каждом `aput` (проверка через `redis-cli -n 1 TTL
  checkpoint:{thread_id}:{checkpoint_id}` после второго write).
- При потере Redis-соединения retry отрабатывает 3 попытки, затем raises
  `CheckpointWriteError` (граф должен корректно обработать через
  try/except — см. Блок B-3).
- 1000 параллельных `aput` на разных thread_id не вызывают race condition
  (asyncio.gather test).
- Unit-тест с mock redis-клиентом (fakeredis или unittest.mock) покрывает
  все 4 метода.
- Integration-тест с реальным Redis (Блок A-1) — round-trip put→get.

Антипаттерны:
- НЕ используй sync `redis.Redis` — только `redis.asyncio.Redis`, иначе
  блокируется event loop LangGraph (контр-пример из `MVP-PROMPTS.md` C-4).
- НЕ хардкодь DB-индекс в коде — только через REDIS_CHECKPOINT_URL env var
  (Блок A-1).
- НЕ сериализуй checkpoint в JSON если LangGraph `Checkpoint` — dataclass
  (не pydantic); проверь type перед сериализацией, fallback на pickle.
- НЕ создавай отдельный redis-клиент на каждый вызов `aput`/`aget` —
  singleton в DI-контейнере, переиспользуем.
- НЕ включай `SET key value` без `EX ttl_seconds` — без TTL checkpoint-ы
  копятся в Redis до OOM, что противоречит noeviction-policy (Блок A-1).
- НЕ храни writes в том же ключе что и checkpoint — отдельный ключ
  `writes:{thread_id}:{task_id}`, иначе `aput` перезатирает writes.
- НЕ делай `aput_writes` синхронным с `aput` — writes отдельные, не блокируют
  node-execution.

Связанные ADR:
- Реализует: ADR-010 (sync layer).
- Зависит от: Блок A-1 (Redis WAL config).
- Использует interface: LangGraph `BaseCheckpointSaver`.
- Используется в: B-3 (RedisPostgresCheckpointer composite).
- Не затрагивает: ADR-001 (PostgresSaver остаётся, используется в B-2), ADR-013
  (pub/sub — отдельный DB 0).
```

### B-2. `PostgresCheckpointer` (asynchronous batched write)

```
Ты — Backend-разработчик LLM Client. Создай `PostgresCheckpointer` — async
write-layer для ADR-010 (Блок B). Реализует `BaseCheckpointSaver` interface
LangGraph, но асинхронно — через buffer + background flusher.

Контекст:
- ADR-010 (TRIZ-ANALYSIS.md §11): PostgresCheckpointer — asynchronous batched
  write, background task каждые 5 сек или N checkpoints (default N=50).
- Существующий `PostgresSaver` (ADR-001, ARCHITECT.md §5.2.2 строка 395) —
  синхронная реализация, пишет в `agent_checkpoints` таблицу
  (ARCHITECT.md §6 строки 584–592). PostgresCheckpointer — НЕ наследник
  PostgresSaver, а новая реализация с async-batch-behaviour.
- ТРИЗ-принцип 19 (периодическое действие): не каждый node, а batch через 5
  сек или N checkpoints. Это снижает RPS на PostgreSQL в 50× (при типовой
  нагрузке 10 nodes/sec → 1 batch/5sec).
- ТРИЗ-принцип 28 (замена механической схемы): вместо sync SQL `INSERT` на
  каждый node — batched `INSERT ... ON CONFLICT DO UPDATE` (upsert) с
  executemany.
- Buffer должен переживать потерю приложения (crash) — см. B-4 (flusher
  запускается отдельной таской, переживает handler-restart через
  buffer-in-Redis).

Задача:
1. Создай класс `PostgresCheckpointer` в `src/llm_client/orchestration/
   checkpointers/postgres_checkpointer.py`:
   - `__init__(pg_pool: asyncpg.Pool, flush_interval_seconds: int = 5,
     flush_batch_size: int = 50)`:
     * `pg_pool` — существующий connection pool (из ADR-005 / ARCHITECT.md
       §5.2.6, переиспользуется).
     * `flush_interval_seconds` — max интервал между flush-ами, default 5.
     * `flush_batch_size` — max checkpoints per flush, default 50.
   - Реализуй `BaseCheckpointSaver`:
     * `aput(config, checkpoint, metadata, new_versions) -> RunnableConfig`:
       - Добавляет checkpoint в `self._buffer: dict[str, Checkpoint]` (ключ —
         `checkpoint_id`).
       - НЕ пишет в PostgreSQL синхронно.
       - Если `len(self._buffer) >= flush_batch_size` — триггерит немедленный
         flush (через `asyncio.create_task(self._flush())`).
       - Возвращает config как есть (pass-through).
     * `aget(config) -> Optional[Checkpoint]`:
       - Сначала проверяет `self._buffer` (если checkpoint там — возвращает).
       - Иначе — `SELECT` из `agent_checkpoints` по thread_id, latest
         checkpoint_id.
     * `alist(config, filter, before, limit) -> Iterator[Checkpoint]`:
       - `SELECT * FROM agent_checkpoints WHERE thread_id = $1` с filter/
         before/limit.
     * `aput_writes(config, writes, task_id) -> None`:
       - Записывает writes в `self._writes_buffer` (отдельный от checkpoint).
2. `_flush()` метод (internal, не входит в `BaseCheckpointSaver`):
   - Атомарный batched write через `asyncpg.exectutemany` или
     `INSERT ... ON CONFLICT (thread_id, checkpoint_id) DO UPDATE`:
     ```sql
     INSERT INTO agent_checkpoints (thread_id, checkpoint_id, parent_id,
       state, metadata, created_at)
     VALUES ($1, $2, $3, $4, $5, $6)
     ON CONFLICT (thread_id, checkpoint_id) DO UPDATE SET
       state = EXCLUDED.state, metadata = EXCLUDED.metadata,
       created_at = EXCLUDED.created_at;
     ```
   - После успешного flush — очищает `self._buffer` для записанных
     checkpoint_id-ов.
   - При ошибке (PG недоступна) — оставляет buffer, retry на следующем
     flush (см. B-4 recovery).
   - Логирует в operational stream (Блок D-2 `MVP-PROMPTS.md`):
     `{"event": "checkpoint_flush", "count": N, "duration_ms": ...}`.
3. Background flusher (запускается в B-4, не здесь — но метод `_flush_loop`
   здесь):
   - `async def _flush_loop(self): while True: await asyncio.sleep(
     self.flush_interval_seconds); await self._flush()`.
   - Метод публичный (вызывается из B-4), не запускается в `__init__`.
4. Buffer sizing:
   - `self._buffer: dict[str, Checkpoint]` — in-memory.
   - Max buffer size: `flush_batch_size * 10` (500 checkpoints). Если buffer
     переполняется — `aput` блокирует (await), ждёт освобождения. Это
     backpressure-механизм.
   - При OOM-риске (например, RPS spike) — логируется warning, buffer
     переходит в "panic mode" — flush на каждом `aput`.

Definition of Done:
- `aput` выполняется за <1 мс (только buffer append, без PG I/O) в 99%.
- `_flush` пишет 50 checkpoints за <200 мс (batched INSERT).
- При RPS 100 checkpoint/sec — PostgreSQL получает 1 batch/5sec (50 records),
  не 100 INSERT/sec (50× снижение RPS).
- Buffer-overflow backpressure работает: при 500+ buffer size `aput`
  блокирует, ждёт flush.
- При потере PG-соединения — buffer не теряется (retry на следующем flush).
- Unit-тест с mock asyncpg.Pool покрывает все методы + `_flush` + buffer
  overflow.
- Integration-тест с реальной PG (Блок A-3 расширяет `documents`, но
  `agent_checkpoints` уже есть из ADR-001): round-trip put → flush → get.

Антипаттерны:
- НЕ пиши в PG синхронно в `aput` — это ровно то, что ADR-010 устраняет
  (10–50 мс latency на каждый node).
- НЕ делай `_flush` синхронным с `aput` — `aput` только добавляет в buffer,
  flush отдельная таска (B-4).
- НЕ используй синхронный `psycopg2` — только `asyncpg` или
  `psycopg.AsyncConnection`, иначе блокируется event loop.
- НЕ храни buffer в Redis (отдельный от checkpoint-WAL Redis из B-1) —
  Redis-checkpointer (B-1) уже хранит последние checkpoint-ы для read;
  buffer PostgresCheckpointer — только pending writes, in-memory OK.
- НЕ очищай buffer при ошибке flush — оставляет данные для retry, иначе
  потеря checkpoint-ов.
- НЕ делай `agent_checkpoints` schema-изменения — таблица из ADR-001
  (ARCHITECT.md §6 строки 584–592) остаётся, PostgresCheckpointer использует
  её как есть.
- НЕ используй `INSERT` без `ON CONFLICT` — при retry flush возможны
  дубликаты checkpoint_id, нужно upsert.

Связанные ADR:
- Реализует: ADR-010 (async layer).
- Расширяет таблицу: `agent_checkpoints` из ADR-001 (`ARCHITECT.md` §6).
- Зависит от: Блок A-3 (PostgreSQL setup — но не tsvector, переиспользует
  существующий `agent_checkpoints`).
- Использует interface: LangGraph `BaseCheckpointSaver`.
- Используется в: B-3 (RedisPostgresCheckpointer composite), B-4 (flusher
  task).
- Не затрагивает: ADR-005 (PostgreSQL primary datastore, переиспользуется).
```

### B-3. `RedisPostgresCheckpointer` (composite, `BaseCheckpointSaver` impl)

```
Ты — Backend-разработчик LLM Client. Создай `RedisPostgresCheckpointer` —
composite checkpointer для ADR-010 (Блок B). Реализует `BaseCheckpointSaver`
interface LangGraph, делегирует в RedisCheckpointer (B-1, sync) и
PostgresCheckpointer (B-2, async). Граф не знает о двухуровневости.

Контекст:
- ADR-010 (TRIZ-ANALYSIS.md §11): composite = sync Redis + async PG.
- LangGraph `StateGraph` получает один checkpointer в конструктор:
  `graph = StateGraph(...); graph.compile(checkpointer=RedisPostgresCheckpointer(...))`.
- ТРИЗ-принцип 5 (объединение): composite скрывает два layer-а за одним
  interface — граф не модифицируется.
- ТРИЗ-принцип 17 (переход в другое измерение): read-path и write-path
  разведены — write идёт в оба layer-а (sync Redis, async PG), read — из Redis
  (быстрее), fallback на PG если Redis не имеет (после restart, см. B-5).
- ТРИЗ-стандарт 2.2.1 (веполь LangGraph → Redis → PostgreSQL, см.
  `TRIZ-ANALYSIS.md` §8.1 строка 819) — composite именно эта веполь.

Задача:
1. Создай класс `RedisPostgresCheckpointer` в `src/llm_client/orchestration/
   checkpointers/composite.py`:
   - `__init__(redis_checkpointer: RedisCheckpointer,
     postgres_checkpointer: PostgresCheckpointer)`:
     * Принимает уже созданные instance-ы (DI-контейнер собирает).
     * Не создаёт новые connection-ы — переиспользует.
   - Реализуй `BaseCheckpointSaver`:
     * `aput(config, checkpoint, metadata, new_versions) -> RunnableConfig`:
       - Сначала `await redis_checkpointer.aput(...)` (sync, latency <1 мс).
       - Затем `await postgres_checkpointer.aput(...)` (buffer append, latency
         <1 мс).
       - Возвращает config (pass-through).
       - Если Redis `aput` падает — НЕ блокирует PG `aput` (PG — durable layer,
         важнее); логирует error, продолжает. Если PG `aput` падает — НЕ
         блокирует Redis (Redis — primary read layer); логирует error.
     * `aget(config) -> Optional[Checkpoint]`:
       - Сначала `redis_checkpointer.aget(config)` (быстрее, <1 мс).
       - Если Redis возвращает None (TTL истёк, restart) — fallback на
         `postgres_checkpointer.aget(config)` (durable, может быть 10–50 мс).
       - Если PG тоже None — возвращает None (новая сессия).
     * `alist(config, filter, before, limit) -> Iterator[Checkpoint]`:
       - Дедупликация: scan Redis + scan PG, merge по checkpoint_id, sort by
         created_at.
       - Возвращает merged iterator (lazy).
     * `aput_writes(config, writes, task_id) -> None`:
       - Делегирует в оба (sync Redis, buffer PG).
2. Error handling:
   - `RedisCheckpointWriteError` — не пробрасывается наверх, логируется в
     operational stream (Блок D-2 `MVP-PROMPTS.md`):
     `{"event": "checkpoint_redis_write_failed", "thread_id": ...,
     "error": str, "fallback": "pg_only"}`.
   - `PostgresCheckpointWriteError` — аналогично, fallback на Redis-only.
   - Если оба падают — raise `CheckpointError`, граф должен остановить
     сессию (см. integration с ADR-013 cancel flow — graf-cancel на
     checkpoint-failure как safety net).
3. Metrics (через существующий `LLMCallMetrics` или новый
   `CheckpointMetrics`):
   - `checkpoint_write_redis_latency_ms` (histogram).
   - `checkpoint_write_pg_buffer_latency_ms` (histogram).
   - `checkpoint_read_redis_hit_count` (counter) vs
     `checkpoint_read_pg_fallback_count` (counter) — ratio показывает
     Redis-эффективность.
   - `checkpoint_write_redis_error_count`, `checkpoint_write_pg_error_count`.
4. DI-контейнер (расширь существующий, не создавай новый):
   ```python
   # src/llm_client/di/container.py (или эквивалент)
   redis_cp = RedisCheckpointer(redis_client=redis_checkpoint_client)
   pg_cp = PostgresCheckpointer(pg_pool=pg_pool)
   composite_cp = RedisPostgresCheckpointer(redis_cp, pg_cp)
   graph = build_langgraph_with_checkpointer(composite_cp)
   # Запуск background flusher (Блок B-4)
   await pg_cp.start_flush_loop()
   ```
5. В .env.example добавь:
   - `CHECKPOINT_BACKEND=redis_postgres` (default), `redis_only` (для тестов),
     `postgres_only` (для dev без Redis).
   - При `redis_only` — composite деградирует в RedisCheckpointer.
   - При `postgres_only` — composite деградирует в PostgresCheckpointer
     (sync режим, для dev/тестов).

Definition of Done:
- Граф LangGraph компилируется с `RedisPostgresCheckpointer` без изменений
  в node-функциях или conditional edges.
- `aput` пишет в Redis (sync) и в PG-buffer (async append) — оба в 99%
  случаев <1 мс общей latency.
- `aget` в 95% случаев читает из Redis (hit rate), 5% — fallback на PG
  (после Redis restart).
- При отключении Redis (CHECKPOINT_BACKEND=postgres_only) — граф работает,
  но `aput` latency = 10–50 мс (как до ADR-010).
- При отключении PG (CHECKPOINT_BACKEND=redis_only) — граф работает, но
  durability = 24h (TTL Redis); после restart checkpoint-ы теряются.
- Metrics экспортируются в Prometheus (через существующий metrics-exporter
  из Phase 1 или новый).
- Unit-тест с mock обоих checkpointer-ов покрывает все 4 метода + error
  handling (Redis fail, PG fail, both fail).
- Integration-тест с реальными Redis (Блок A-1) + PG: restart Redis во
  время write → read работает через PG fallback; restart PG во время
  write → write работает через Redis.

Антипаттерны:
- НЕ делай `RedisPostgresCheckpointer` наследником `PostgresSaver` — это
  composite, не расширение. Реализуй `BaseCheckpointSaver` напрямую.
- НЕ блокируй `aput` на PG-write — PG должен быть async (через buffer в B-2).
  Sync PG-write = regression к ADR-001.
- НЕ делай `aget` всегда из PG "для consistency" — это убивает ADR-010
  цель (latency <1 мс). Redis — primary read layer, PG — fallback.
- НЕ дублируй serialization в composite — делегируй в B-1 и B-2, они сами
  сериализуют.
- НЕ забывай metrics — без ratio Redis-hit/PG-fallback невозможно понять,
  работает ли ADR-010 (если ratio <50% — Redis не используется эффективно,
  надо debug).
- НЕ запускай PG-flusher в `__init__` composite — это ответственность B-4
  (отдельный startup шаг), иначе `__init__` становится long-running.

Связанные ADR:
- Реализует: ADR-010 (composite, public interface).
- Зависит от: B-1 (RedisCheckpointer), B-2 (PostgresCheckpointer), Блок A-1
  (Redis WAL), ADR-005 (PostgreSQL pool).
- Используется в: ADR-001 (LangGraph graph.compile), Блок B-4 (flusher
  startup), Блок B-5 (recovery protocol).
- Не затрагивает: ADR-013 (cancel — отдельный Redis DB 0), ADR-014 (forensic
  — отдельный S3 bucket).
```

### B-4. Background flusher (5 сек / N checkpoints)

```
Ты — Backend-разработчик LLM Client. Реализуй background flusher для
PostgresCheckpointer (B-2): запускается при старте приложения, каждые 5
сек (или N checkpoints) вызывает `_flush()`, корректно останавливается
при shutdown.

Контекст:
- ADR-010 (TRIZ-ANALYSIS.md §11): "background task каждые 5 сек или N
  checkpoints" — flusher именно этот механизм.
- ТРИЗ-принцип 19 (периодическое действие): snapshot не каждый node, а
  каждые 5 сек или N — снижает PG RPS в ~50× (10 nodes/sec → 0.2 batch/sec).
- ТРИЗ-принцип 9 (предварительное противодействие): flusher запускается
  ДО первого checkpoint-write (в startup), не ждёт первого checkpoint-а —
  иначе первый checkpoint ждёт 5 сек до flush.
- Существующий `MVP-PROMPTS.md` Блок F-4 описывает CI pipeline с
  `make ci-local` и shutdown-tests; flusher должен корректно
  останавливаться на `docker-compose down` без потери pending checkpoint-ов
  в buffer (см. shutdown protocol ниже).

Задача:
1. Расширь `PostgresCheckpointer` (B-2) методом `start_flush_loop()`:
   - `async def start_flush_loop(self) -> None`:
     * Создаёт `self._flush_task = asyncio.create_task(self._flush_loop())`.
     * Логирует startup: "PostgresCheckpointer flush loop started,
       interval=5s, batch_size=50".
   - `async def _flush_loop(self) -> None`:
     ```python
     while not self._stopping:
         try:
             await asyncio.wait_for(
                 asyncio.sleep(self.flush_interval_seconds),
                 timeout=self.flush_interval_seconds + 1
             )
             await self._flush()
         except asyncio.CancelledError:
             # Shutdown signal — final flush before exit
             await self._flush()
             break
         except Exception as e:
             # Log error, continue loop (flusher is critical, never dies)
             log_error("checkpoint_flush_failed", error=str(e))
             await asyncio.sleep(1)  # backoff before retry
     ```
2. Добавь `stop_flush_loop()` метод:
   - `async def stop_flush_loop(self) -> None`:
     * `self._stopping = True`.
     * `self._flush_task.cancel()` — триггерит `CancelledError` в
       `_flush_loop`, который делает final flush (см. except-branch).
     * `await asyncio.wait_for(self._flush_task, timeout=10)` — ждёт
       завершения, max 10 сек (не блокирует shutdown дольше).
     * Логирует: "PostgresCheckpointer flush loop stopped, final flush
       done, N pending in buffer" (N=0 если final flush успешен).
3. Integration с application lifecycle:
   - В `src/llm_client/main.py` (или эквивалент startup):
     ```python
     async def lifespan(app):
         # Startup
         pg_cp = app.state.postgres_checkpointer
         await pg_cp.start_flush_loop()
         yield
         # Shutdown
         await pg_cp.stop_flush_loop()
     ```
   - FastAPI `lifespan` context manager (или Streamlit startup hook).
4. Trigger по N checkpoints (опционально, конфиг):
   - В `PostgresCheckpointer.aput` (B-2) — после добавления в buffer:
     ```python
     if len(self._buffer) >= self.flush_batch_size:
         asyncio.create_task(self._flush())  # immediate flush
     ```
   - Это дополнительный триггер — вместе с time-based loop, whichever fires
     first.
   - При high RPS (>10 nodes/sec) — N-триггер сработает раньше time-триггера,
     что хорошо (PG не ждёт 5 сек, чтобы записать 100 checkpoint-ов разом).
5. Failure scenarios:
   - PG недоступна 5+ минут — flusher продолжает retry каждые 5 сек
     (`_flush` падает, loop ловит exception, sleep 1 сек, retry).
   - Buffer переполняется (>500) — `aput` блокирует (backpressure в B-2),
     flusher должен успевать сбрасывать. Если нет — flusher увеличивает
     `flush_interval` до 1 сек (adaptive backoff, см. п.6).
6. Adaptive backoff (опциональный enhancement, не required для ADR-010):
   - Если `_flush` latency >500 мс (PG slow) — flusher уменьшает
     `flush_interval` до 1 сек (чаще flush-и, меньше buffer).
   - Если `_flush` latency <50 мс (PG fast) — flusher возвращается к 5 сек.
   - Логируется в metrics: `checkpoint_flush_interval_seconds` (gauge).

Definition of Done:
- При старте приложения в логах: "PostgresCheckpointer flush loop started".
- Каждые 5 сек (или раньше при buffer-overflow) — `_flush` выполняется,
  visible в логах: `{"event": "checkpoint_flush", "count": N, "duration_ms": ...}`.
- При `docker-compose down` — flusher делает final flush, логи:
  "PostgresCheckpointer flush loop stopped, final flush done, 0 pending
  in buffer".
- При SIGTERM во время flush — ждёт завершения flush (max 10 сек), затем
  shutdown.
- При PG-недоступности 5 минут — flusher не падает, retry каждые 1 сек
  (после initial failure), логирует errors.
- При buffer-overflow (>500) — flusher переходит в "panic mode" (flush
  каждые 1 сек), RPS на PG растёт, но buffer не переполняется (проверка
  через integration-тест с 100 RPS checkpoint-write в течение 60 сек).
- Metrics: `checkpoint_flush_count`, `checkpoint_flush_duration_ms`,
  `checkpoint_flush_error_count`, `checkpoint_buffer_size` (gauge).

Антипаттерны:
- НЕ запускай flusher в `__init__` PostgresCheckpointer — это side-effect в
  конструкторе, тестируемость падает. Явный `start_flush_loop()` из startup.
- НЕ делай flusher singleton с global state — instance-метод на
  PostgresCheckpointer, управляется DI-контейнером.
- НЕ проглатывай `asyncio.CancelledError` — это shutdown signal, нужно
  final flush и exit. Проглатывание = pending checkpoint-ы теряются.
- НЕ делай `asyncio.sleep(5)` без timeout-обёртки — при shutdown `Cancelled`
  не сработает сразу, ждёт 5 сек. Используй `asyncio.wait_for` или проверяй
  `self._stopping` в loop.
- НЕ делай flusher "неубиваемым" — при критической ошибке (PG corruption)
  лучше уронить приложение, чем тихо терять checkpoint-ы. После N
  consecutive failures (default 10) — raise `CheckpointFatalError`,
  приложение падает.
- НЕ хардкодь 5 сек и 50 — через env vars (PROMPTFLUSHER_INTERVAL_SECONDS,
  PROMPTFLUSHER_BATCH_SIZE) или constructor args, для тестов с меньшими
  значениями.
- НЕ запускай flusher в тестах по умолчанию — в unit-тестах flusher
  выключен (`CHECKPOINT_BACKEND=postgres_only` + `FLUSHER_ENABLED=false`),
  тесты явно вызывают `_flush()`.

Связанные ADR:
- Реализует: ADR-010 (background flusher).
- Зависит от: B-2 (PostgresCheckpointer._flush).
- Используется в: B-3 (composite startup), B-5 (recovery protocol),
  application lifecycle (FastAPI lifespan / Streamlit startup).
- Не затрагивает: ADR-013 (cancel — отдельный механизм).
```

### B-5. Recovery protocol (snapshot из PG + replay из Redis)

```
Ты — Backend-разработчик LLM Client. Реализуй recovery protocol для ADR-010
(Блок B): при restart приложения система сначала восстанавливает последнее
состояние из PostgreSQL (snapshot), затем догоняет delta из Redis (если
Redis жив и имеет более новые checkpoint-ы).

Контекст:
- ADR-010 (TRIZ-ANALYSIS.md §11 строка 951): "Восстановление при restart:
  сначала из PostgreSQL (snapshot), затем replay из Redis (delta)."
- Сценарий 1 (planned restart, `docker-compose restart`): Redis и PG
  живы. При restart приложения — read из PG (последний snapshot),
  read из Redis (последние checkpoint-ы за 5 сек до restart) — Redis
  имеет более новые, чем PG (PG flushes every 5 sec, possible lag).
- Сценарий 2 (Redis crash + app restart): Redis потерян (TTL истёк или
  flush не успел), PG имеет snapshot — восстановление только из PG.
  Потеря <=5 сек checkpoint-ов (acceptable по ADR-010).
- Сценарий 3 (PG crash + app restart): PG восстановлен из backup (PITR),
  Redis имеет более новые checkpoint-ы (24h TTL) — восстановление из PG
  (старый snapshot) + replay из Redis (24h delta). Это сильнее, чем
  только PG-восстановление.
- Сценарий 4 (одновременный отказ Redis+PG, маловероятно): потеря <=5 сек
  checkpoint-ов (acceptable risk по ROADMAP.md §6.3).
- ТРИЗ-принцип 23 (обратная связь): recovery protocol — это feedback-loop
  между двумя layer-ами, не "один источник правды".

Задача:
1. Создай метод `recover()` в `RedisPostgresCheckpointer` (B-3):
   - `async def recover(self) -> dict[str, int]`:
     * Возвращает `{"pg_checkpoints_recovered": N, "redis_delta_replayed": M,
       "conflicts_resolved": K}`.
     * Алгоритм:
       1. Загрузить все `thread_id`-ы из PG (SELECT DISTINCT thread_id FROM
          agent_checkpoints WHERE created_at > NOW() - INTERVAL '24 hours').
       2. Для каждого thread_id:
          - Получить последний checkpoint из PG: `SELECT * FROM
            agent_checkpoints WHERE thread_id = $1 ORDER BY created_at DESC
            LIMIT 1`.
          - Получить последний checkpoint из Redis: `redis_checkpointer.aget(
            config_with_thread_id)` — может быть None (TTL истёк) или
            более новый (timestamp > PG).
          - Если Redis имеет более новый — записать его в PG через
            `postgres_checkpointer.aput(...)` (replay delta).
          - Логировать: `{"event": "checkpoint_recovery", "thread_id": ...,
            "pg_checkpoint_id": ..., "redis_checkpoint_id": ...,
            "delta_replayed": true|false}`.
       3. Возвращает summary.
2. Запуск recovery при старте приложения:
   - В `lifespan` (FastAPI) или startup hook (Streamlit):
     ```python
     # После start_flush_loop (B-4):
     recovery_stats = await composite_checkpointer.recover()
     log_info("checkpoint_recovery_done", **recovery_stats)
     ```
   - Recovery должен завершиться ДО приёма первого запроса (иначе новый
     запрос создаст новый checkpoint, который пересекается с unrecovered
     thread_id-ом).
   - Timeout: 30 сек max. Если recovery не успевает — стартовать с partial
     recovery (log warning, "N threads not recovered, will use PG snapshot
     only").
3. Conflict resolution (если Redis и PG имеют разные checkpoint-ы для
   одного thread_id с одинаковым timestamp — крайне редкий случай):
   - Стратегия: Redis wins (если timestamp Redis > timestamp PG — см. п.1).
   - Если timestamps равны, но content разный — PG wins (durable layer,
     более trustworthy), Redis-запись перезаписывается.
   - Логировать conflict: `{"event": "checkpoint_conflict", "thread_id":
     ..., "winner": "pg|redis", "reason": "timestamp|content_diff"}`.
4. Validation после recovery:
   - Для каждого восстановленного thread_id — graph.aget(thread_id) должен
     вернуть валидный state (не None, не corrupted).
   - Если state corrupted — log error, mark thread as "needs human review",
     не пытаться replay (для forensics).
5. Тest recovery scenarios:
   - **Test 1** (planned restart): write 10 checkpoint-ов, kill app (SIGTERM),
     wait 3 сек (Redis has newer), restart app, verify recovery replayed
     3–5 delta-checkpoint-ов из Redis.
   - **Test 2** (Redis crash): write 10 checkpoint-ов, kill Redis
     (`docker-compose stop redis`), wait 10 сек (TTL не истёк, но Redis
     down), restart app, verify recovery только из PG (Redis
     `redis_delta_replayed=0`).
   - **Test 3** (PG crash + Redis alive): write 10 checkpoint-ов, kill
     PostgreSQL (`docker-compose stop postgres`), wait 10 сек, restart
     PostgreSQL (PITR или WAL replay), restart app, verify recovery
     "redis_delta_replayed = 10 - last_pg_checkpoint" (Redis догоняет PG).
   - **Test 4** (одновременный отказ): kill Redis + PG одновременно, restart
     оба (PG из PITR), verify потеря <=5 сек checkpoint-ов (last 5 sec
     not recovered).

Definition of Done:
- Recovery при planned restart завершается за <10 сек для 100 active
  thread_id-ов (типовая staging-нагрузка).
- Recovery replayed delta из Redis в сценарии 1 (Redis имеет более новые
  checkpoint-ы).
- Recovery не падает при Redis-down (сценарий 2) — fallback на PG-only.
- Recovery не падает при PG-down (сценарий 3) — Redis replayed после PG
  restart.
- В сценарии 4 (одновременный отказ) — потеря <=5 сек checkpoint-ов
  (подтверждается test 4).
- Конфликты (одинаковый timestamp, разный content) логируются и
  разрешаются PG-wins (см. п.3).
- Validation после recovery помечает corrupted state как "needs human
  review", не падает.
- Все 4 test-scenarios проходят в integration-тесте (Блок E-2).

Антипаттерны:
- НЕ пропускай recovery при старте — иначе новый запрос создаст checkpoint
  для unrecovered thread_id, который "потеряет" предыдущую сессию.
- НЕ делай recovery синхронно с первым запросом — recovery должен
  завершиться ДО приёма запросов (block startup).
- НЕ удаляй Redis checkpoint-ы после recovery — они остаются как
  read-cache, TTL истечёт естественно. Удаление = потеря быстрого read-
  path.
- НЕ пиши Redis checkpoint-ы обратно в PG при каждом recovery (только если
  Redis имеет более новые) — иначе recovery writes = duplicate writes.
- НЕ пытайся восстановить corrupted state автоматически — mark как
  "needs human review", log full forensic event (через ADR-014 forensic
  stream из Phase 1).
- НЕ блокируй startup бесконечно при recovery timeout — после 30 сек
  partial recovery, log warning, стартовать (лучше partial state, чем
  полный downtime).
- НЕ делай recovery для thread_id-ов старше 24h — они уже потеряны в
  Redis (TTL), recovery из PG-only не имеет смысла (старые сессии
  неактуальны).

Связанные ADR:
- Реализует: ADR-010 (recovery protocol).
- Зависит от: B-1 (RedisCheckpointer), B-2 (PostgresCheckpointer), B-3
  (composite).
- Используется в: application startup (FastAPI lifespan), Блок E-2 (тест
  recovery).
- Связан с: ADR-014 (forensic stream для corrupted state logging).
```

### B-6. Latency + durability test (одновременный отказ Redis+PG)

```
Ты — QA/Automation-разработчик LLM Client. Создай integration-тест для
ADR-010, проверяющий оба критерия готовности: (1) latency checkpoint <2 мс
в 99% случаев на staging; (2) потеря состояния при одновременном отказе
Redis+PG не происходит в пилотной неделе (Блок B-5 сценарий 4 в controlled
условиях).

Контекст:
- ROADMAP.md §6.3 (ADR-010 критерий готовности): "latency checkpoint <2 мс
  в 99% случаев на staging; восстановление при restart корректно; потеря
  состояния при одновременном отказе Redis+PG не происходит в пилотной
  неделе".
- MVP-PROMPTS.md Блок F-1 — аналог для ADR-013 (cancel latency test);
  переиспользуй паттерн: pytest-asyncio + 1000 сэмплов + p50/p95/p99
  отчёт.
- Staging-нагрузка: 50 параллельных сессий, 10 RPS новых сессий, каждая
  сессия 30–60 сек (5–10 nodes). Чекпоинты: ~50 RPS × 10 nodes = 500
  checkpoint-write/sec.

Задача:
1. Создай pytest-asyncio integration-тест `test_checkpoint_latency`:
   - Поднимает dev-окружение с Redis (Блок A-1) + PG + agent-service
     (использует `docker-compose up` из Phase 1 CI).
   - Запускает 50 параллельных LLM-сессий через `POST /sessions` (с test
     fixtures, не реальные LLM — mock LLM provider с 100 мс latency).
   - Для каждой сессии — замеряет latency checkpoint-write:
     * timestamp перед `graph.astream(...)` iteration → timestamp после
       node-execution (после `aput`).
     * Это latency одной итерации, не end-to-end.
   - Собирает 1000 сэмплов checkpoint-write latency, считает p50, p95, p99.
   - PASS: p99 <2 мс (критерий ADR-010).
2. Создай integration-тест `test_checkpoint_recovery` (Блок B-5 scenarios
   1–4):
   - Использует pytest fixtures: `redis_container`, `pg_container`,
     `app_container` (через testcontainers-python или docker-compose).
   - Для каждого сценария (planned restart, Redis crash, PG crash,
     simultaneous crash):
     * Setup: write 10 checkpoint-ов через `aput`.
     * Trigger: kill service (Redis/PG/app), wait, restart.
     * Verify: `recover()` replays delta, state consistent, потеря данных
       соответствует ADR-010 acceptable risk (<=5 сек).
   - PASS: все 4 сценария проходят без потери данных сверх acceptable risk.
3. Создай durability-тест `test_checkpoint_durability_7days` (pilot week
   simulation, не буквально 7 дней):
   - Симулирует 7 дней работы в fast-forward mode (время ускорено 100×):
     * Каждая "неделя" = 7 * 24 * 60 / 100 = ~100 минут реального времени.
     * Записывает 10000 checkpoint-ов (1000 сессий × 10 nodes).
     * Каждые 5 "часов" (= 3 минуты реального) — planned restart app.
     * Каждые 24 "часа" (= 14 минут реального) — Redis restart (AOF
       replay).
     * Каждые 7 "дней" (= 1 раз за тест) — simultaneous crash Redis+PG,
       recovery из PITR (PG WAL).
   - PASS: 0 потерянных checkpoint-ов за пределами acceptable risk
     (>=99.9% durability).
4. CI интеграция (расширяет Phase 1 CI из MVP-PROMPTS.md Блок F-4):
   - `test_checkpoint_latency` — nightly job на staging (как F-1 в Phase 1).
   - `test_checkpoint_recovery` — nightly + on-demand (перед релизом Phase 2).
   - `test_checkpoint_durability_7days` — weekly (долго выполняется, ~100
     минут).
   - Все 3 теста — staging-only (не unit, не dev), требуют реальные Redis+PG.
5. Отчёт:
   - JSON-отчёт в CI-артефактах: latency percentiles, recovery scenarios
     PASS/FAIL, durability score.
   - При FAIL — alert в Slack #architecture (по аналогии с G-2
     MVP-PROMPTS.md, метрика идеальности).

Definition of Done:
- `test_checkpoint_latency` собирает 1000 сэмплов за <10 минут на staging.
- p99 checkpoint-write latency <2 мс в 100% runs (PASS criterion).
- p50, p95 reported в JSON-артефакте.
- При FAIL (p99 >2 мс) — CI exit code != 0, alert в Slack.
- `test_checkpoint_recovery` покрывает 4 сценария (B-5): все PASS.
- `test_checkpoint_durability_7days` — 7-дневная симуляция за ~100 минут
  реального времени, durability >=99.9%.
- Все 3 теста проходят на staging в CI nightly.
- В CI-артефактах: latency report (JSON), recovery scenarios summary
  (JSON), durability score (JSON).

Антипаттерны:
- НЕ замеряй latency только на стороне приложения — это skip network
  latency Redis. Используй `time.perf_counter()` вокруг `aput` и включай
  Redis round-trip.
- НЕ запускай `test_checkpoint_latency` в unit-тестах — нужны реальные
  Redis+PG. Только staging.
- НЕ уменьшай sample size для скорости — 1000 сэмплов нужно для p99
  статистики.
- НЕ пропускай `test_checkpoint_durability_7days` "потому что долго" —
  это единственный способ поймать редкие edge-cases (Redis AOF corruption,
  PG WAL gap).
- НЕ эмулируй одновременный отказ через `docker-compose stop redis
  postgres` одновременно — это неэффективно (PG shutdown long). Используй
  `docker kill` (SIGKILL) для обоих сразу, затем `docker-compose up -d`.
- НЕ пиши отчёт в stdout только — JSON-артефакт для последующего анализа
  трендов (см. Блок F-2 Grafana dashboard).
- НЕ делай durability-тест literally 7 дней — никто не будет ждать. Fast-
  forward с ускорением времени — стандартный подход (см. Chaos Engineering
  практики, Gremlin).

Связанные ADR:
- Тестирует: ADR-010 (Блок B).
- Зависит от: Блок A-1 (Redis WAL), ADR-005 (PG), Блок B-1..B-5 (реализация).
- Расширяет: Блок F-1 MVP-PROMPTS.md (cancel latency test) — паттерн
  переиспользуется.
- Используется в: Блок E-5 (Phase 2 CI pipeline).
```

---

## 3. Блок C. ADR-017: Reranker Model in RAG — микро-декомпозиция

**Источник**: `ROADMAP.md` v1.1.0 §6.4, `TRIZ-ANALYSIS.md` v1.0.0 §6.1 (C-6 часть 1 — precision), §8.1 (стандарт 2.2.2 — переход к динамичной веполи, cross-encoder как более сильное поле переранжировки), §11 (ADR-017 драфт). Резолвит часть противоречия **C-6** (long RAG context vs cost) — качественная составляющая retrieval (precision ↑, recall@5 ↑ ≥15%). Принципы ТРИЗ: 16 (частичное/избыточное действие — сначала 20 чанков, потом reranker оставляет 5), 21 (сканирование вперёд — pre-compute через cross-encoder на top-K), 9 (предварительное противодействие — кэш эмбеддингов на индекс-тайм), 17 (другое измерение — cross-encoder vs bi-encoder как более сильное поле). Полная реализация: 6 подзадач, 4 чел-дн (`ROADMAP.md` §6.2 п.6.2.2).

**Контекст ADR-017**: §5.2.5 `ARCHITECT.md` (строка 484) упоминает `MMR rerank -> top-8` через `vector_store.as_retriever(search_type="mmr", k=8, fetch_k=20)`. MMR — внутри-vector-store эвристика (без ML-reranker), хорошо diversifies, но не улучшает precision. Cross-encoder reranker (`bge-reranker-base`) — модель, которая принимает пару (query, doc) и возвращает relevance score; типично даёт +20–30% recall@5 vs MMR-only. Решение — ввести cross-encoder reranker в RAG pipeline **после** fusion (Блок D-5), не вместо MMR (MMR остаётся для diversification, reranker — для precision). Reranker pluggable через `RerankerRegistry` (как `VectorStoreRegistry` в драфте ADR-009 из `TRIZ-ANALYSIS.md` §5.3).

**Эффект ADR-017** (из `TRIZ-ANALYSIS.md` §11):
- (+) Значительное улучшение precision и recall (типично +20–30% recall@5).
- (+) Снижение контекста LLM (5 качественных чанков вместо 20 шумных).
- (-) Дополнительная latency (50–200 мс на reranking 20 чанков).
- (-) bge-reranker-base требует ~600MB RAM для in-process (Блок A-2 готовит).
- (-) Cohere Rerank (опциональный) — внешняя зависимость с отдельной стоимостью.

### C-1. `Reranker` interface + `RerankerRegistry` (entrypoints)

```
Ты — Backend/ML-разработчик LLM Client. Создай `Reranker` interface и
`RerankerRegistry` для ADR-017 (Блок C). Pluggable-архитектура как
`VectorStoreRegistry` (драфт ADR-009, TRIZ-ANALYSIS.md §5.3).

Контекст:
- ADR-017 (TRIZ-ANALYSIS.md §11): "Reranker — pluggable через RerankerRegistry
  (как VectorStore в ADR-009)."
- TRIZ-принцип 25 (самообслуживание): adapters self-register через entrypoints
  (`pyproject.toml [project.entry-points]`), factory исчезает — вместо него
  `RerankerRegistry.get(name)`.
- TRIZ-принцип 1 (дробление): каждый reranker специализирован (bge — локальный
  cross-encoder, Cohere — API, identity — no-op для тестов).
- В Phase 2 — две реализации: BgeRerankerAdapter (C-2), CohereRerankAdapter
  (C-3). В Phase 5+ может добавиться ColBERT, Voyager и др.
- Существующий `VectorStoreRegistry` (драфт ADR-009) — паттерн для подражания,
  не зависимость.

Задача:
1. Создай `Reranker` ABC в `src/llm_client/rag/rerankers/base.py`:
   ```python
   from abc import ABC, abstractmethod
   from typing import Sequence
   from dataclasses import dataclass

   @dataclass
   class RerankResult:
       doc_id: str
       score: float  # higher = more relevant
       original_index: int  # position in input list

   class Reranker(ABC):
       @abstractmethod
       async def rerank(
           self,
           query: str,
           documents: Sequence[dict],  # each dict has at least "content" key
           top_k: int = 5,
           batch_size: int = 8,
       ) -> list[RerankResult]:
           """Returns top_k documents ranked by relevance to query."""
           ...

       @property
       @abstractmethod
       def name(self) -> str:
           """Unique name for registry (e.g. 'bge-reranker-base')."""
           ...

       @abstractmethod
       async def health_check(self) -> bool:
           """Returns True if reranker is ready to serve."""
           ...
   ```
2. Создай `RerankerRegistry` в `src/llm_client/rag/rerankers/registry.py`:
   - Используй `importlib.metadata.entry_points` для discovery:
     ```python
     # pyproject.toml entrypoint (декларация в каждом adapter-пакете):
     [project.entry-points."llm_client.rerankers"]
     bge = "llm_client.rag.rerankers.bge:BgeRerankerAdapter"
     cohere = "llm_client.rag.rerankers.cohere:CohereRerankAdapter"
     identity = "llm_client.rag.rerankers.identity:IdentityReranker"
     ```
   - `RerankerRegistry.get(name: str) -> Reranker` — возвращает instance (lazy
     singleton, создаётся при первом обращении, кэшируется).
   - `RerankerRegistry.list_available() -> list[str]` — список зарегистрированных.
   - `RerankerRegistry.get_default() -> Reranker` — по env `RERANKER_DEFAULT`
     (default: "bge"), fallback на первый available.
3. Создай `IdentityReranker` в `src/llm_client/rag/rerankers/identity.py`:
   - No-op reranker для тестов и dev (когда model не скачана).
   - `rerank(query, documents, top_k=5)` возвращает первые top_k documents без
     переранжировки (original_index = 0..top_k-1, score = 1.0).
   - `health_check()` всегда True.
4. Конфигурация через env:
   - `RERANKER_DEFAULT=bge|cohere|identity` (default: "bge").
   - При `RERANKER_DEFAULT=identity` — используем identity, latency=0 (для
     dev/test без ML-модели).
5. В .env.example добавь все три опции с комментариями.

Definition of Done:
- `Reranker` ABC существует в `src/llm_client/rag/rerankers/base.py`.
- `RerankerRegistry.get("bge")` возвращает `BgeRerankerAdapter` instance (после
  C-2).
- `RerankerRegistry.get("identity")` возвращает `IdentityReranker` instance.
- `RerankerRegistry.get("unknown")` raises `RerankerNotFoundError`.
- `RerankerRegistry.list_available()` возвращает ["bge", "cohere", "identity"]
  (после C-2, C-3).
- Entry-points зарегистрированы в pyproject.toml.
- `pip install -e .` подхватывает entrypoints (проверка через
  `python -c "from importlib.metadata import entry_points; print(list(
  entry_points(group='llm_client.rerankers')))"`).
- Unit-тест с IdentityReranker: `rerank(query, [doc1, doc2], top_k=1)` возвращает
  `[RerankResult(doc_id=doc1, score=1.0, original_index=0)]`.

Антипаттерны:
- НЕ делай `RerankerRegistry` god-object — только `get`, `list_available`,
  `get_default`. Никаких "config-loader", "metrics-aggregator" в registry.
- НЕ создавай instance-ы в registry-`__init__` — lazy singleton, при первом
  `get(name)`. Иначе приложение стартует дольше (загрузка bge-модели 5+ сек).
- НЕ хардкодь "bge" как default в коде — только через env RERANKER_DEFAULT.
  В dev без модели — RERANKER_DEFAULT=identity.
- НЕ делай `Reranker.rerank` sync — все adapter-ы async (даже bge, который
  загружен in-process, для единообразия interface).
- НЕ передавай `score` выше как проперти документов — `RerankResult` отдельный
  объект, чтобы caller мог map обратно к документам через `original_index`.
- НЕ включай `Reranker.health_check` в `rerank()` — health_check отдельный метод,
  вызывается startup-ом, не на каждый запрос.

Связанные ADR:
- Реализует: ADR-017 (interface + registry).
- Паттерн из: драфт ADR-009 (VectorStoreRegistry, TRIZ-ANALYSIS.md §5.3) —
  не зависит, но копирует паттерн.
- Используется в: C-2 (BgeRerankerAdapter), C-3 (CohereRerankAdapter), C-4
  (pipeline integration), C-5 (fallback chain).
- Не затрагивает: ADR-001, ADR-010, ADR-020.
```

### C-2. `BgeRerankerAdapter` (in-process cross-encoder)

```
Ты — ML/Backend-разработчик LLM Client. Создай `BgeRerankerAdapter` —
in-process реализацию `Reranker` interface (C-1) через `bge-reranker-base`
(Блок A-2). Загружается один раз при старте, singleton.

Контекст:
- ADR-017 (TRIZ-ANALYSIS.md §11): default reranker — bge-reranker-base,
  локальная модель, нет external API, ~600MB RAM.
- Блок A-2 подготовил: модель скачана в `models/bge-reranker-base/`,
  env vars RERANKER_MODEL_NAME, RERANKER_MODEL_DIR, RERANKER_DEVICE,
  RERANKER_MAX_LENGTH, RERANKER_BATCH_SIZE.
- sentence-transformers `CrossEncoder` — стандартная API для cross-encoder
  inference.
- ТРИЗ-принцип 25 (самообслуживание): модель in-process, нет network latency,
  нет cost-per-call (Cohere платит per request).
- ТРИЗ-принцип 3 (местное качество): bge-reranker специализирован для retrieval
  reranking (cross-encoder trained on MS-MARCO + multilingual datasets), не
  general-purpose LLM.
- Latency budget: 50–200 мс на 20 чанков (ADR-017 критерий готовности:
  latency retrieval ↑ <100 мс).

Задача:
1. Создай `BgeRerankerAdapter` в `src/llm_client/rag/rerankers/bge.py`:
   ```python
   from sentence_transformers import CrossEncoder
   from llm_client.rag.rerankers.base import Reranker, RerankResult

   class BgeRerankerAdapter(Reranker):
       def __init__(
           self,
           model_name: str = "BAAI/bge-reranker-base",
           model_dir: str = "./models/bge-reranker-base",
           device: str = "cpu",
           max_length: int = 512,
           batch_size: int = 8,
       ):
           self._model: CrossEncoder | None = None  # lazy load
           self._model_name = model_name
           self._model_dir = model_dir
           self._device = device
           self._max_length = max_length
           self._batch_size = batch_size

       @property
       def name(self) -> str:
           return "bge-reranker-base"

       async def _ensure_loaded(self):
           if self._model is None:
               # Load in thread to avoid blocking event loop
               self._model = await asyncio.to_thread(
                   CrossEncoder,
                   self._model_dir if os.path.exists(self._model_dir)
                     else self._model_name,
                   device=self._device,
                   max_length=self._max_length,
               )
           return self._model

       async def rerank(
           self,
           query: str,
           documents: Sequence[dict],
           top_k: int = 5,
           batch_size: int | None = None,
       ) -> list[RerankResult]:
           model = await self._ensure_loaded()
           bs = batch_size or self._batch_size
           # Build (query, doc_content) pairs
           pairs = [(query, doc["content"][:self._max_length]) for doc in documents]
           # Predict in thread (sync operation)
           scores = await asyncio.to_thread(
               model.predict, pairs, batch_size=bs
           )
           # Sort by score descending
           indexed = [(i, float(s)) for i, s in enumerate(scores)]
           indexed.sort(key=lambda x: x[1], reverse=True)
           return [
               RerankResult(
                   doc_id=documents[i]["id"] if "id" in documents[i] else str(i),
                   score=s,
                   original_index=i,
               )
               for i, s in indexed[:top_k]
           ]

       async def health_check(self) -> bool:
           try:
               await self._ensure_loaded()
               return True
           except Exception:
               return False
   ```
2. Lazy loading:
   - Модель НЕ загружается в `__init__` (для тестов, для fast startup).
   - Загружается при первом `rerank()` вызове через `_ensure_loaded()`.
   - В startup приложения (Блок B-4 lifespan) — pre-warm через
     `await registry.get_default()._ensure_loaded()` (опционально, для
     прогнозируемой latency первого запроса).
3. Threading:
   - `model.predict()` — sync (PyTorch), блокирует event loop.
   - Wrap в `asyncio.to_thread()` (Python 3.11+, стандартный способ).
   - Не используй `run_in_executor` — `to_thread` более явный, без
     ThreadPoolExecutor.
4. Memory management:
   - `_model` — singleton, не пересоздаётся.
   - При shutdown — `_model` не выгружается явно (Python GC + container
     shutdown). Если нужно — `del self._model` в `health_check` если
     detected OOM-превентивный scenario.
5. В `pyproject.toml` добавь entrypoint (см. C-1):
   ```toml
   [project.entry-points."llm_client.rerankers"]
   bge = "llm_client.rag.rerankers.bge:BgeRerankerAdapter"
   ```
6. DI-контейнер: BgeRerankerAdapter создаётся с env-config (Блок A-2),
   регистрируется в RerankerRegistry при import.

Definition of Done:
- `BgeRerankerAdapter.rerank(query, [20 documents], top_k=5)` возвращает 5
  `RerankResult` объектов с scores, отсортированными по убыванию.
- First `rerank()` вызов загружает модель (5–10 сек на CPU, 1–2 сек на GPU),
  subsequent — <200 мс на 20 чанков CPU, <50 мс GPU.
- `health_check()` после первого `rerank()` возвращает True.
- 1000 параллельных `rerank()` вызовов не блокируют event loop (asyncio.to_thread
  корректно использует thread pool).
- RAM при inference на 20 чанков с batch_size=8 не превышает 1.5 GB
  (Блок A-2 готовит, проверка через `docker stats`).
- Unit-тест с mock `CrossEncoder` (mock predict возвращает [0.9, 0.1, ...])
  покрывает rerank + health_check + lazy loading.
- Integration-тест с реальной моделью (Блок A-2): `rerank("error code 1234",
  [{"content": "doc with error 1234"}, {"content": "unrelated doc"}],
  top_k=1)` возвращает первый doc с score >0.5.
- Entry-point зарегистрирован, `RerankerRegistry.get("bge")` возвращает
  BgeRerankerAdapter instance.

Антипаттерны:
- НЕ загружай модель в `__init__` — это блокирует startup на 5–10 сек и
  усложняет тестирование (mock не может перехватить загрузку).
- НЕ делай `model.predict()` синхронно без `asyncio.to_thread` — это
  блокирует event loop, остальные запросы ждут.
- НЕ хардкодь device ("cpu"/"cuda") — через env RERANKER_DEVICE (Блок A-2).
- НЕ обрезай doc_content без max_length — CrossEncoder упадёт на длинном
  документе. Всегда `[:self._max_length]`.
- НЕ создавай новый `CrossEncoder` instance на каждый `rerank` — singleton,
  иначе 5 сек latency на каждый запрос + memory leak.
- НЕ логируй scores в operational stream (Блок D-2 MVP-PROMPTS) — это
  metadata, не PII, но засоряет логи. Только в debug level.
- НЕ используй GPU без явного env — CUDA-зависимости добавляют 4GB к Docker
  image. Только если staging/prod имеет GPU (Блок A-2).

Связанные ADR:
- Реализует: ADR-017 (default reranker).
- Зависит от: C-1 (Reranker interface + RerankerRegistry), Блок A-2 (bge-reranker
  model setup).
- Используется в: C-4 (pipeline integration), C-5 (fallback chain — primary),
  C-6 (A/B test).
- Будет переиспользован в: Phase 4 (Local LLM) — `BGEEmbeddings` для retrieval
  индексации (ARCHITECT.md §5.2.5).
- Не затрагивает: ADR-010, ADR-020.
```

### C-3. `CohereRerankAdapter` (external API, опциональный)

```
Ты — Backend/разработчик LLM Client. Создай `CohereRerankAdapter` —
опциональную реализацию `Reranker` interface (C-1) через Cohere Rerank API.
Используется если RERANKER_DEFAULT=cohere (например, bge-reranker недоступен
на staging, или команда предпочитает managed API для production).

Контекст:
- ADR-017 (TRIZ-ANALYSIS.md §11): "Опционально — Cohere Rerank API (если
  доступен и budget позволяет)".
- Cohere Rerank API: POST https://api.cohere.com/v1/rerank, принимает
  query + documents[], возвращает scores.
- Cost: ~$2/1000 rerank requests (на 2026-09). Для типичной нагрузки
  1000 RAG queries/day — $2/day, $60/month. Acceptable для staging/prod,
  не для dev (там bge-reranker).
- ТРИЗ-принцип 35 (изменение параметров): Cohere — альтернативная физическая
  реализация того же interface; переключение через env, не через код.
- ТРИЗ-принцип 28 (замена механической схемы): вместо локальной модели —
  external API (обратный принцип 25, но для production-quality это
  оправдано — Cohere rerank-2 лучше bge-reranker-base на ~5–10% recall@5).

Задача:
1. Добавь зависимость `cohere>=5.0.0` в pyproject.toml.
2. Создай `CohereRerankAdapter` в `src/llm_client/rag/rerankers/cohere.py`:
   ```python
   import cohere
   from llm_client.rag.rerankers.base import Reranker, RerankResult

   class CohereRerankAdapter(Reranker):
       def __init__(
           self,
           api_key: str,  # from env COHERE_API_KEY
           model: str = "rerank-multilingual-v3.0",
           timeout_seconds: int = 10,
       ):
           self._client: cohere.AsyncClient | None = None  # lazy
           self._api_key = api_key
           self._model = model
           self._timeout = timeout_seconds

       @property
       def name(self) -> str:
           return "cohere-rerank"

       async def _ensure_client(self):
           if self._client is None:
               self._client = cohere.AsyncClient(self._api_key)
           return self._client

       async def rerank(
           self,
           query: str,
           documents: Sequence[dict],
           top_k: int = 5,
           batch_size: int | None = None,  # ignored, Cohere API handles batching
       ) -> list[RerankResult]:
           client = await self._ensure_client()
           docs_text = [doc["content"][:5000] for doc in documents]
           response = await client.rerank(
               model=self._model,
               query=query,
               documents=docs_text,
               top_n=top_k,
               return_documents=False,
           )
           return [
               RerankResult(
                   doc_id=documents[r.index]["id"] if "id" in documents[r.index]
                     else str(r.index),
                   score=r.relevance_score,
                   original_index=r.index,
               )
               for r in response.results
           ]

       async def health_check(self) -> bool:
           try:
               client = await self._ensure_client()
               # Cheap API call to check connectivity
               await client.models.list()
               return True
           except Exception:
               return False
   ```
3. Env vars:
   - `COHERE_API_KEY` — API ключ (из Cohere dashboard).
   - `COHERE_RERANK_MODEL=rerank-multilingual-v3.0` (default; mono-lingual:
     `rerank-english-v3.0`).
   - `COHERE_TIMEOUT_SECONDS=10` (default).
4. Error handling:
   - `cohere.AsyncClient.rerank` падает с `cohere.errors.TooManyRequestsError`
     на rate limit — retry 3 раза с экспоненциальной задержкой (1с, 2с, 4с),
     затем raise `RerankerError`.
   - `cohere.errors.UnauthorizedError` — не retry, raise immediately (config
     error, не transient).
   - Network timeout — retry, затем fallback на bge (см. C-5).
5. Cost tracking:
   - Каждый вызов логирует в `LLMCallMetrics` (существующий из Phase 1):
     `{"event": "cohere_rerank_call", "doc_count": N, "cost_estimate":
     N * 0.002}`.
   - Monthly budget: COHERE_MONTHLY_BUDGET=50 (USD); при достижении 80% —
     alert в Slack (по аналогии с ADR-015 cost guard, который будет в
     Phase 3).
6. Entry-point в pyproject.toml:
   ```toml
   [project.entry-points."llm_client.rerankers"]
   cohere = "llm_client.rag.rerankers.cohere:CohereRerankAdapter"
   ```

Definition of Done:
- `CohereRerankAdapter.rerank(query, [20 documents], top_k=5)` возвращает 5
  `RerankResult` объектов с Cohere scores.
- First `rerank()` инициализирует AsyncClient (быстро, <100 мс), subsequent —
  latency = Cohere API round-trip (100–500 мс).
- `health_check()` через `client.models.list()` возвращается True если API
  ключ валиден.
- Rate limit (429) — retry 3 раза, затем raise.
- 401 (Unauthorized) — немедленный raise без retry.
- Cost tracking: каждый rerank пишет в metrics с cost_estimate.
- Unit-тест с mock `cohere.AsyncClient` покрывает rerank + rate limit retry +
  health_check.
- Integration-тест с реальным COHERE_API_KEY (skip если не задан в env):
  `rerank("error code 1234", [...])` возвращает валидные scores.
- Entry-point зарегистрирован, `RerankerRegistry.get("cohere")` возвращает
  CohereRerankAdapter instance.

Антипаттерны:
- НЕ используй sync `cohere.Client` — только `cohere.AsyncClient`, иначе
  блокируется event loop.
- НЕ хардкодь API ключ в коде — только через env COHERE_API_KEY.
- НЕ делай retry на 401 (Unauthorized) — это config error, не transient.
- НЕ передавай документы >5000 символов — Cohere API обрежет, но это implicit,
  лучше обрезать явно в adapter.
- НЕ логируй query в operational stream (potentially PII) — только doc_count
  и cost. Forensic stream (Блок D-3 MVP-PROMPTS) — full trace OK.
- НЕ делай fallback на bge внутри CohereRerankAdapter — это ответственность
  C-5 (chain), не adapter-а. Adapter должен fail чисто, chain решает fallback.
- НЕ используй `rerank-english-v3.0` для multilingual корпуса —
  `rerank-multilingual-v3.0` доступен и поддерживает русский.

Связанные ADR:
- Реализует: ADR-017 (optional reranker).
- Зависит от: C-1 (Reranker interface + RerankerRegistry).
- Используется в: C-4 (pipeline integration), C-5 (fallback chain —
  alternative to bge).
- Связан с: будущий ADR-015 (Cost-aware router, Phase 3) — COHERE_MONTHLY_BUDGET
  будет учитываться в cost guard.
- Не затрагивает: ADR-010, ADR-020.
```

### C-4. Pipeline integration (reranker применяется после fusion)

```
Ты — Backend/разработчик LLM Client. Интегрируй reranker (C-1..C-3) в RAG
pipeline: reranker применяется ПОСЛЕ fusion (Блок D-5), не вместо MMR.

Контекст:
- ADR-017 (TRIZ-ANALYSIS.md §11): "Pipeline: vector retrieval (top-20) →
  BM25 retrieval (top-20) → fusion (RRF, top-50) → reranker (top-5)".
- ADR-020 (Блок D) делает hybrid retrieval default: vector top-20 + BM25
  top-20 → RRF fusion → top-50.
- После fusion — 50 чанков, нужно переранжировать для top-5 в LLM context.
- MMR (в `vector_store.as_retriever(search_type="mmr")`) — diversifies внутри
  vector-retrieval, не после fusion. Reranker (cross-encoder) — после fusion,
  финальная precision.
- ТРИЗ-принцип 16 (частичное/избыточное действие): сначала "избыточно" — 50
  чанков после fusion, потом "частично" — reranker оставляет 5.
- ТРИЗ-стандарт 2.2.2 (переход к динамичной веполи): cross-encoder как более
  сильное поле, заменяет bi-encoder similarity scores.

Задача:
1. Расширь `RetrieverConfig` (ARCHITECT.md §5.2.5, `RetrieverConfig` dataclass)
   новыми полями:
   - `reranker_name: str = "bge"` — имя reranker из RerankerRegistry.
   - `reranker_top_k: int = 5` — финальное число чанков для LLM context.
   - `reranker_enabled: bool = True` — toggle (False = no reranking, fusion
     top-5 напрямую в LLM).
2. Создай функцию `rerank_after_fusion` в `src/llm_client/rag/pipeline.py`:
   ```python
   async def rerank_after_fusion(
       query: str,
       fused_docs: list[dict],  # top-50 after RRF
       config: RetrieverConfig,
   ) -> list[dict]:
       if not config.reranker_enabled or len(fused_docs) <= config.reranker_top_k:
           return fused_docs[:config.reranker_top_k]
       reranker = RerankerRegistry.get(config.reranker_name)
       results = await reranker.rerank(
           query=query,
           documents=fused_docs,
           top_k=config.reranker_top_k,
       )
       # Map back to original docs by original_index
       return [fused_docs[r.original_index] for r in results]
   ```
3. В pipeline (после fusion Блока D-5):
   ```python
   vector_docs = await vector_retriever.aget_relevant_documents(query, k=20)
   bm25_docs = await bm25_retriever.aget_relevant_documents(query, k=20)
   fused_docs = rrf_fusion(vector_docs, bm25_docs, top_k=50)  # Блок D-5
   final_docs = await rerank_after_fusion(query, fused_docs, config)
   # final_docs → в LLM context
   ```
4. Metrics:
   - `rag_rerank_latency_ms` (histogram).
   - `rag_rerank_input_count` (gauge — typically 50).
   - `rag_rerank_output_count` (gauge — typically 5).
   - `rag_rerank_error_count` (counter).
5. Observability:
   - В operational stream (Блок D-2 MVP-PROMPTS): `{"event": "rag_rerank",
     "reranker": "bge", "input_count": 50, "output_count": 5, "latency_ms":
     150}`.
   - В forensic stream (Блок D-3 MVP-PROMPTS): full rerank scores (для аудита
     retrieval quality).
6. Конфигурация:
   - `RERANKER_DEFAULT=bge` (default, Блок A-2/C-1).
   - `RERANKER_ENABLED=true|false` (default true; false — skip rerank, fusion
     top-5 напрямую в LLM, для dev/быстрых тестов).

Definition of Done:
- Pipeline: vector top-20 + BM25 top-20 → RRF fusion top-50 → reranker
  top-5 → LLM context.
- Latency end-to-end retrieval: <200 мс в 99% случаев (vector 50ms + BM25 50ms
  + fusion 5ms + rerank 100ms = 205ms, ~tight; проверить ADR-017 критерий
  ↑<100ms над baseline — baseline ~150ms, so +50ms is OK).
- При RERANKER_ENABLED=false — pipeline работает без rerank, latency ~105ms.
- Metrics экспортируются в Prometheus.
- В operational stream логируется каждый rerank event.
- В forensic stream логируется full scores (encrypted).
- Unit-тест с mock reranker (IdentityReranker из C-1) покрывает pipeline.
- Integration-тест с BgeRerankerAdapter (C-2): recall@5 измеряется (Блок C-6
  A/B test framework).

Антипаттерны:
- НЕ применяй reranker до fusion — это убивает смысл ADR-020 (BM25+vector
  нужно сначала объединить, потом rerank).
- НЕ применяй reranker к top-20 vector-only (без BM25) — это partial
  implementation, не ADR-017 (ADR-017 работает с fusion, не вместо fusion).
- НЕ делай reranker последним шагом без fallback (см. C-5) — если reranker
  падает, pipeline должен продолжить с fusion top-5, не уронить запрос.
- НЕ логируй full documents в operational stream (PII risk) — только
  doc_count, latency. Forensic stream — full content OK.
- НЕ хардкодь "bge" в pipeline — через RetrieverConfig.reranker_name.
- НЕ передавай `fused_docs` целиком в reranker если >50 — это не scalable.
  ADR-017 фиксирует top-50 после fusion. Если fusion даёт >50 — отбросить.

Связанные ADR:
- Реализует: ADR-017 (pipeline integration).
- Зависит от: C-1 (RerankerRegistry), C-2 (BgeRerankerAdapter), D-5 (RRF
  fusion).
- Используется в: D-5 (hybrid pipeline), C-6 (A/B test framework), Блок E-3
  (recall@5 test).
- Расширяет: `RetrieverConfig` (ARCHITECT.md §5.2.5).
- Не затрагивает: ADR-001 (LangGraph не модифицируется), ADR-010 (checkpointing
  не связан).
```

### C-5. Fallback chain (Cohere → bge → no reranking)

```
Ты — Backend/разработчик LLM Client. Реализуй fallback chain для reranker:
если default reranker (Cohere или bge) недоступен, переключаемся на
следующий; если все недоступны — pipeline продолжается без reranking
(fusion top-5 напрямую в LLM).

Контекст:
- ADR-017 (TRIZ-ANALYSIS.md §11): reranker — pluggable, default bge,
  optional Cohere.
- TRIZ-ANALYSIS.md §17.1 (Risk mitigation): "Каждая новая зависимость должна
  иметь in-process fallback или degrade-gracefully поведение. Например,
  Cohere Rerank недоступен → fallback на bge-reranker-base."
- ТРИЗ-принцип 35 (изменение параметров): reranker не одно решение, а chain
  с деградацией.
- ТРИЗ-принцип 13 (наоборот): не "fail if primary down" — а "continue with
  degraded quality if primary down".

Задача:
1. Создай `RerankerChain` в `src/llm_client/rag/rerankers/chain.py`:
   ```python
   class RerankerChain(Reranker):
       def __init__(self, rerankers: list[Reranker]):
           self._rerankers = rerankers  # ordered: primary, fallback1, fallback2

       @property
       def name(self) -> str:
           return "chain"

       async def rerank(
           self,
           query: str,
           documents: Sequence[dict],
           top_k: int = 5,
           batch_size: int | None = None,
       ) -> list[RerankResult]:
           errors = []
           for reranker in self._rerankers:
               try:
                   if not await reranker.health_check():
                       errors.append(f"{reranker.name}: unhealthy")
                       continue
                   results = await reranker.rerank(query, documents, top_k, batch_size)
                   if errors:
                       log_warning(
                           "reranker_fallback",
                           primary=self._rerankers[0].name,
                           active=reranker.name,
                           errors=errors,
                       )
                   return results
               except Exception as e:
                   errors.append(f"{reranker.name}: {str(e)}")
                   continue
           # All rerankers failed — return first top_k docs (no reranking)
           log_error("reranker_all_failed", errors=errors)
           return [
               RerankResult(doc_id=str(i), score=1.0, original_index=i)
               for i, doc in enumerate(documents[:top_k])
           ]

       async def health_check(self) -> bool:
           # Healthy if at least one reranker healthy
           for r in self._rerankers:
               if await r.health_check():
                   return True
           return False
   ```
2. Default chain (через env):
   - `RERANKER_CHAIN=cohere,bge,identity` — если Cohere configured, bge loaded,
     identity as final fallback.
   - `RERANKER_CHAIN=bge,identity` — если Cohere не configured (нет API key).
   - `RERANKER_CHAIN=identity` — dev/test, no ML.
3. В DI-контейнере:
   ```python
   chain_rerankers = []
   if os.getenv("COHERE_API_KEY"):
       chain_rerankers.append(CohereRerankAdapter(api_key=...))
   chain_rerankers.append(BgeRerankerAdapter(...))
   chain_rerankers.append(IdentityReranker())
   chain = RerankerChain(chain_rerankers)
   RerankerRegistry.register("chain", chain)
   RerankerRegistry.register("default", chain)  # alias
   ```
4. Metrics:
   - `reranker_fallback_count` (counter, labels: primary, active).
   - `reranker_all_failed_count` (counter).
5. Logging:
   - At fallback: WARNING in operational stream
     `{"event": "reranker_fallback", "primary": "cohere", "active": "bge",
     "errors": ["cohere: 429 Too Many Requests"]}`.
   - At all-failed: ERROR in operational + forensic (full errors list).

Definition of Done:
- При Cohere down (429 после retry) — fallback на bge в <200 мс (retry timeout).
- При bge down (model not loaded) — fallback на identity (no-op, latency 0).
- При all failed — pipeline продолжает с fusion top-5, log ERROR.
- Metrics: `reranker_fallback_count` и `reranker_all_failed_count`
  экспортируются.
- В operational stream логируется каждый fallback event.
- Unit-тест с mock rerankers (primary fails, fallback succeeds) покрывает
  chain logic.
- Integration-тест: stop Cohere mock mid-rerank → bge takes over → success.

Антипаттерны:
- НЕ делай fallback "fail-once, switch forever" — каждый запрос retry primary
  first (Cohere может восстановиться через минуту).
- НЕ исключай identity из chain — это final safety net, без него pipeline
  падает если все ML-rerankers down.
- НЕ делай chain дольше 3 reranker-ов — это лишняя complexity, 3 уровня
  достаточно (Cohere → bge → identity).
- НЕ блокируй pipeline на health_check всех reranker-ов перед каждым
  запросом — health_check в chain.rerank(), не в pipeline. Pipeline
  вызывает chain.rerank(), chain сам выбирает healthy.
- НЕ логируй PII в fallback errors — Cohere error может содержать
  truncated query. Mask через PIIDetector (Блок D-1 MVP-PROMPTS).

Связанные ADR:
- Реализует: ADR-017 (graceful degradation).
- Зависит от: C-1 (RerankerRegistry, IdentityReranker), C-2 (bge), C-3 (cohere).
- Используется в: C-4 (pipeline integration — через RetrieverConfig.
  reranker_name="chain" или default).
- Связан с: §17.1 TRIZ-ANALYSIS risk mitigation policy.
- Не затрагивает: ADR-010, ADR-020.
```

### C-6. A/B test framework (recall@5 metric)

```
Ты — QA/ML-разработчик LLM Client. Создай A/B test framework для ADR-017:
сравнение recall@5 между baseline (MMR-only, без reranker) и treatment
(reranker на top-5), на staging-нагрузке.

Контекст:
- ROADMAP.md §6.4 (ADR-017 критерий готовности): "A/B test 2 недели —
  recall@5 ↑ ≥15% vs baseline; latency retrieval ↑ <100 мс; bge-reranker
  загружается in-process за <5 сек при старте."
- A/B test framework — переиспользуемый для других ADR (ADR-020 в Блоке D-6,
  ADR-011 в Phase 3 — semantic cache hit rate).
- TRIZ-принцип 23 (обратная связь): A/B test — это feedback-loop для
  architecture decisions.
- Источники ground truth:
  - Option 1: human-labeled dataset (50–100 queries с известными relevant
    documents).
  - Option 2: production queries с implicit feedback (click-through rate,
    time-to-answer).
  - Phase 2 — Option 1 (dataset), production-feedback в Phase 3+.

Задача:
1. Создай dataset format `datasets/rag_eval/phase2_eval.jsonl`:
   ```jsonl
   {"query": "error code 1234", "relevant_doc_ids": ["doc_42", "doc_43"],
    "category": "exact_term"}
   {"query": "how to configure redis", "relevant_doc_ids": ["doc_10",
    "doc_11", "doc_12"], "category": "semantic"}
   ```
   - 50–100 queries, по 20 в каждой категории (exact_term, semantic, fuzzy).
   - Ground truth — human-labeled (команда размечает в Phase 1 старте Phase 2).
2. Создай `RAGEvaluator` в `src/llm_client/rag/eval/evaluator.py`:
   ```python
   class RAGEvaluator:
       def __init__(self, rag_pipeline: RAGPipeline, eval_dataset_path: str):
           self._pipeline = rag_pipeline
           self._dataset = self._load_dataset(eval_dataset_path)

       async def evaluate(self, config: RetrieverConfig) -> EvalReport:
           results = []
           for entry in self._dataset:
               retrieved = await self._pipeline.retrieve(entry["query"], config)
               hit_at_5 = any(
                   doc["id"] in entry["relevant_doc_ids"]
                   for doc in retrieved[:5]
               )
               results.append({
                   "query": entry["query"],
                   "category": entry["category"],
                   "retrieved_ids": [d["id"] for d in retrieved[:5]],
                   "relevant_ids": entry["relevant_doc_ids"],
                   "hit_at_5": hit_at_5,
                   "latency_ms": ...,
               })
           return EvalReport(
               recall_at_5=sum(r["hit_at_5"] for r in results) / len(results),
               per_category=self._per_category(results),
               avg_latency_ms=...,
           )
   ```
3. Создай A/B test runner `scripts/ab_test_reranker.py`:
   ```python
   async def main():
       evaluator = RAGEvaluator(pipeline, "datasets/rag_eval/phase2_eval.jsonl")

       baseline_config = RetrieverConfig(reranker_enabled=False, ...)
       treatment_config = RetrieverConfig(reranker_name="bge", ...)

       baseline_report = await evaluator.evaluate(baseline_config)
       treatment_report = await evaluator.evaluate(treatment_config)

       print(f"Baseline recall@5: {baseline_report.recall_at_5:.3f}")
       print(f"Treatment recall@5: {treatment_report.recall_at_5:.3f}")
       improvement = (treatment_report.recall_at_5 - baseline_report.recall_at_5) /
                     baseline_report.recall_at_5 * 100
       print(f"Improvement: {improvement:.1f}%")
       # PASS if improvement >= 15% (ADR-017 criterion)
       # FAIL otherwise
       sys.exit(0 if improvement >= 15 else 1)
   ```
4. Запуск в CI:
   - `scripts/ab_test_reranker.py` — nightly job (на staging с реальной
     моделью bge).
   - Результат сохраняется в `reports/ab_test_reranker_{date}.json`.
   - PASS criterion: improvement >= 15% AND latency overhead <100 мс.
5. Категории в dataset:
   - `exact_term` — запросы с product SKU, error codes, IDs (BM25 должен
     хорошо ловить, reranker добавляет little).
   - `semantic` — концептуальные запросы, без точных терминов (vector должен
     хорошо, reranker добавляет significant).
   - `fuzzy` — опечатки, частичные термины (BM25 с pg_trgm + reranker).
6. Reporting:
   - JSON-отчёт: per-category recall, latency, sample queries.
   - Grafana dashboard (Блок F-2): trend за 6 месяцев.

Definition of Done:
- Dataset из 50+ queries, 3 категории (exact_term, semantic, fuzzy), 20+ в
  каждой.
- `RAGEvaluator.evaluate(config)` возвращает `EvalReport` с recall@5, per-
  category breakdown, avg latency.
- A/B test runner: baseline (no reranker) vs treatment (bge), PASS if
  improvement >=15%.
- Latency overhead измеряется: treatment_avg_latency - baseline_avg_latency
  <100 мс (ADR-017 criterion).
- Запуск nightly в CI (Блок E-5), результат в CI-артефактах.
- При FAIL — alert в Slack #architecture.
- Per-category reporting: exact_term improvement (low, BM25 dominates),
  semantic improvement (high, reranker dominates), fuzzy (medium).
- Trend visible в Grafana (Блок F-2).

Антипаттерны:
- НЕ делай dataset <50 queries — статистически незначимо для recall@5
  comparison.
- НЕ смешивай baseline и treatment в одном run — каждый run чистый, не
  пересекаются.
- НЕ запускай A/B test на unit-тестах (без реальной модели) — нужен staging.
- НЕ считай recall@1 — ADR-017 говорит recall@5 (top-5 в LLM context).
- НЕ пропускай категории — если exact_term improvement <15%, это OK (BM25
  доминирует); но semantic must >=15% для PASS.
- НЕ хардкодь "bge" в A/B test — через RetrieverConfig, чтобы test
  parameterized для разных rerankers (Cohere vs bge vs chain).
- НЕ удаляй dataset после test — нужен для regression tracking (trend в
  Grafana).

Связанные ADR:
- Тестирует: ADR-017 (recall@5 improvement).
- Зависит от: C-1..C-5 (full implementation).
- Переиспользуется в: D-6 (A/B test для ADR-020 exact-term recall), Блок E-3
  (CI integration), Phase 3 (A/B test для ADR-011 semantic cache hit rate).
- Не затрагивает: ADR-010 (checkpoint, не связан с retrieval quality).
```

---

## 4. Блок D. ADR-020: Hybrid (BM25 + Vector) RAG default — микро-декомпозиция

**Источник**: `ROADMAP.md` v1.1.0 §6.5, `TRIZ-ANALYSIS.md` v1.0.0 §6.1 (C-6 часть 2 — recall для точных терминов), §8.1 (стандарт 1.1.5 — введение второго поля в веполь Query↔Embeddings↔VectorStore), §11 (ADR-020 драфт), §10 (матрица противоречий C-6). Резолвит вторую часть противоречия **C-6** (long RAG context vs cost) — recall для точных терминов (product SKU, error codes, IDs) ↑≥30%. Принципы ТРИЗ: стандарт 1.1.5 (введение второго поля — BM25 как второе поле retrieval), 5 (объединение — BM25 в PostgreSQL tsvector, не отдельный сервис). Полная реализация: 6 подзадач, 5 чел-дн (`ROADMAP.md` §6.2 п.6.2.3).

**Контекст ADR-020**: §5.2.5 `ARCHITECT.md` (строка 484) упоминает hybrid search (BM25 + vector) как опцию: "Для гибридного поиска — комбинируем BM25 (через `rank_bm25`) с vector reranking". Но в default-конфигурации — pure vector retrieval через `vector_store.as_retriever(search_type="mmr", k=8, fetch_k=20)`. Pure vector retrieval плохо находит точные совпадения (product SKU `ABC-1234`, error codes `ERR-502`, employee IDs `EMP-123456`) — embeddings близки, но не точны. BM25 (через PostgreSQL `tsvector`, подготовленный в Блоке A-3) — лексический поиск, хорошо ловит точные термины. Решение — сделать hybrid retrieval default: в `RetrieverConfig` добавить `retrieval_strategy: "vector"|"bm25"|"hybrid"` (default `hybrid`), BM25 index строится параллельно с vector index при индексации документа, hybrid retrieval = vector top-20 + BM25 top-20 → RRF fusion → top-50 → reranker (Блок C) → top-5.

**Эффект ADR-020** (из `TRIZ-ANALYSIS.md` §11):
- (+) Значительное улучшение recall для запросов с точными терминами (типично +30–50% для SKU/error codes).
- (+) Best of both worlds: semantic (vector) + lexical (BM25).
- (-) Дополнительное хранилище для BM25 index (Блок A-3 tsvector).
- (-) Latency retrieval возрастает на 30–50% (двойной запрос: vector + BM25).
- (-) Reranker обязателен (без него noise от fusion; см. C-4 — без reranker fusion top-5 содержит шумные BM25-хиты).

### D-1. `RetrieverConfig.retrieval_strategy` enum (default hybrid)

```
Ты — Backend-разработчик LLM Client. Расширь `RetrieverConfig` (ARCHITECT.md
§5.2.5) полем `retrieval_strategy` со значениями "vector"|"bm25"|"hybrid"
(default: "hybrid"). Обратно-совместимо — если не задано, hybrid.

Контекст:
- ADR-020 (TRIZ-ANALYSIS.md §11 строка 1116): "В RetrieverConfig добавить
  retrieval_strategy: 'vector'|'bm25'|'hybrid' (default: 'hybrid')".
- Существующий `RetrieverConfig` (ARCHITECT.md §5.2.5) — dataclass с полями
  `vector_store`, `embedding_model`, `k`, `fetch_k`, `search_type` (vector |
  mmr | hybrid_score), `lambda_mult` (для MMR), `score_threshold`.
- В ARCHITECT.md уже есть `search_type="hybrid"` опция, но это
  внутри-vector-store hybrid (MMR), не vector+BM25 hybrid. Новое поле
  `retrieval_strategy` — orthogonally: какая retrieval-стратегия (vector |
  bm25 | hybrid vector+bm25), `search_type` — как vector-retriever
  internally переранжирует (similarity | mmr).
- ТРИЗ-стандарт 1.1.5 (введение второго поля в веполь): новое поле
  `retrieval_strategy` — явный choice между одной (vector/bm25) или двумя
  стратегиями (hybrid).

Задача:
1. Расширь `RetrieverConfig` dataclass в `src/llm_client/rag/config.py`:
   ```python
   from enum import Enum
   from dataclasses import dataclass

   class RetrievalStrategy(str, Enum):
       VECTOR = "vector"
       BM25 = "bm25"
       HYBRID = "hybrid"  # default

   @dataclass
   class RetrieverConfig:
       # existing fields:
       vector_store: str = "pgvector"
       embedding_model: str = "text-embedding-3-small"
       k: int = 5
       fetch_k: int = 20
       search_type: str = "similarity"  # within vector retriever
       lambda_mult: float = 0.5  # MMR only
       score_threshold: float | None = None

       # NEW fields (Phase 2, ADR-020):
       retrieval_strategy: RetrievalStrategy = RetrievalStrategy.HYBRID
       bm25_weight: float = 0.5  # RRF fusion weight, 0..1
       vector_weight: float = 0.5  # RRF fusion weight, 0..1
       hybrid_top_k: int = 50  # top-K after fusion, before reranker
   ```
2. Обратно-совместимость:
   - Если `retrieval_strategy` не задан в config (например, legacy caller) —
     default `HYBRID` (новое поведение ADR-020).
   - Если caller явно задаёт `VECTOR` — pure vector retrieval (как до ADR-020).
   - Если caller явно задаёт `BM25` — pure BM25 (rare use case, например
     для legal documents где точные термины критичны, semantic не нужен).
3. В .env.example:
   - `RAG_RETRIEVAL_STRATEGY=hybrid|vector|bm25` (default: "hybrid").
   - `RAG_BM25_WEIGHT=0.5` (RRF fusion weight).
   - `RAG_VECTOR_WEIGHT=0.5` (RRF fusion weight).
   - `RAG_HYBRID_TOP_K=50` (top-K after fusion).
4. Валидация:
   - `bm25_weight + vector_weight == 1.0` (если нет — log warning, нормализовать
     к 0.5/0.5).
   - `hybrid_top_k >= k` (если hybrid_top_k=5, k=5 — fusion избыточен, надо
     hybrid_top_k > k, например 50 для reranker → top-5).

Definition of Done:
- `RetrieverConfig.retrieval_strategy` — enum RetrievalStrategy с тремя
  значениями.
- Default при создании RetrieverConfig() без параметров — `retrieval_strategy=
  RetrievalStrategy.HYBRID`.
- При `RAG_RETRIEVAL_STRATEGY=vector` в env — все новые RetrieverConfig-и
  используют vector (для regression testing).
- Валидация weights: если bm25_weight=0.3, vector_weight=0.3 — log warning,
  нормализовать к 0.5/0.5.
- Unit-тест покрывает: default config (hybrid), explicit vector, explicit bm25,
  weights валидация.
- .env.example обновлён с новыми vars.

Антипаттерны:
- НЕ переопределяй существующее `search_type` (mmr | similarity) — это
  orthogonal к retrieval_strategy. search_type — внутри vector-retriever;
  retrieval_strategy — между vector и BM25.
- НЕ делай `bm25_weight = 0.0` дефолтом — это pure vector, ломает ADR-020.
  default 0.5/0.5 — balanced hybrid.
- НЕ удаляй `score_threshold` — он по-прежнему используется в vector-retriever
  (filtering by similarity score).
- НЕ делай `hybrid_top_k` маленьким (5) — fusion теряет смысл, если
  vector top-20 + bm25 top-20 → fusion top-5 сразу (без reranker).
  hybrid_top_k=50 → reranker top-5 (см. C-4) — правильный pipeline.
- НЕ хардкодь "hybrid" в pipeline-коде — через RetrieverConfig.

Связанные ADR:
- Реализует: ADR-020 (config flag).
- Расширяет: RetrieverConfig из ARCHITECT.md §5.2.5.
- Используется в: D-2 (BM25IndexBuilder), D-4 (HybridRetriever), D-5 (RRF
  fusion), C-4 (pipeline integration читает config).
- Не затрагивает: ADR-001 (LangGraph), ADR-010 (checkpoint), ADR-017 (reranker).
```

### D-2. `BM25IndexBuilder` (parallel with vector index)

```
Ты — Backend/разработчик LLM Client. Создай `BM25IndexBuilder`, который
строит BM25-индекс параллельно с vector-индексом при индексации документа.
Использует PostgreSQL tsvector (Блок A-3), не отдельный сервис.

Контекст:
- ADR-020 (TRIZ-ANALYSIS.md §11 строка 1117): "BM25 index строится
  параллельно с vector index при индексации документа."
- Блок A-3 добавил tsvector column + GIN index на documents — это и есть
  BM25-индекс (через PostgreSQL FTS).
- Существующий pipeline (ARCHITECT.md §5.2.5):
  1. Load → 2. Chunk → 3. Embed → 4. Store (vector_store.add_texts) →
  5. Retrieve.
- BM25IndexBuilder встраивается в шаг 4 (Store) — параллельно с vector
  store.add_texts, обновляется tsvector в `documents` таблице.
- ТРИЗ-принцип 5 (объединение): один storage для вектор и BM25 (PostgreSQL
  pgvector + tsvector), не два сервиса.
- ТРИЗ-принцип 9 (предварительное противодействие): индекс строится при
  индексации, не при запросе — query-time latency только от lookup, не от
  build.

Задача:
1. Создай `BM25IndexBuilder` в `src/llm_client/rag/indexing/bm25_indexer.py`:
   ```python
   class BM25IndexBuilder:
       def __init__(self, pg_pool: asyncpg.Pool, text_search_config: str =
         "english"):
           self._pool = pg_pool
           self._tsc = text_search_config

       async def index_document(self, document: Document) -> None:
           """Insert/update document with tsvector (auto-generated)."""
           async with self._pool.acquire() as conn:
               await conn.execute(
                   """
                   INSERT INTO documents (id, user_id, source_type, source_uri,
                     content_hash, content, metadata)
                   VALUES ($1, $2, $3, $4, $5, $6, $7)
                   ON CONFLICT (content_hash) DO UPDATE SET
                     content = EXCLUDED.content,
                     metadata = EXCLUDED.metadata,
                     source_uri = EXCLUDED.source_uri
                   """,
                   document.id, document.user_id, document.source_type,
                   document.source_uri, document.content_hash,
                   document.content, document.metadata
               )
               # tsvector обновляется автоматически через GENERATED ALWAYS AS

       async def index_chunks(self, chunks: list[Chunk]) -> None:
           """For chunked documents, update parent document's tsvector with
           concatenated chunk contents."""
           # ... analogous, but stores chunks in separate table if architecture
           # uses chunk-level indexing (depends on existing schema)

       async def delete_document(self, document_id: str) -> None:
           """Delete document, tsvector удаляется каскадно."""
           async with self._pool.acquire() as conn:
               await conn.execute(
                   "DELETE FROM documents WHERE id = $1", document_id
               )
   ```
2. Параллельность с vector-индексацией:
   - В pipeline индексации:
     ```python
     async def index_document_with_hybrid(document: Document):
         # Parallel: vector + BM25
         await asyncio.gather(
             vector_store.aadd_texts([document.content], metadata=...),
             bm25_indexer.index_document(document),
         )
     ```
   - Если vector_store.aadd_texts падает — BM25 индекс сохраняется (асинхронные
     задачи независимы, ошибка логируется, но не блокирует).
   - Если bm25_indexer падает — vector индекс сохраняется. Retry на следующей
     индексации (через background reindexer, опциональный enhancement).
3. Reindex при изменении документа:
   - `index_document` использует `ON CONFLICT (content_hash) DO UPDATE` —
     если content_hash совпадает, ничего не происходит (idempotent).
   - Если content изменился (content_hash разный) — `DO UPDATE` обновляет
     content, tsvector автоматически пересчитывается (GENERATED ALWAYS AS
     STORED).
4. Оптимизация:
   - Batch indexing (например, для initial bulk load 10k документов):
     `bm25_indexer.index_documents_batch([doc1, doc2, ...])` —
     executemany INSERT, не один INSERT на документ.
   - CONCURRENTLY для GIN-индекса (если миграция Блока A-3 не использовала
     CONCURRENTLY — добавить в reindex script).

Definition of Done:
- `BM25IndexBuilder.index_document(doc)` вставляет/обновляет запись в
  `documents`, tsvector генерируется автоматически (через GENERATED ALWAYS
  AS из Блока A-3).
- После индексации: `SELECT search_vector FROM documents WHERE id =
  'test-doc'` возвращает tsvector с лемматизированными терминами.
- Параллельность: vector и BM25 indexing не блокируют друг друга (через
  asyncio.gather).
- При ошибке vector indexing — BM25 сохраняется, log warning.
- При ошибке BM25 — vector сохраняется, log warning.
- Batch indexing 100 документов за <5 сек (через executemany).
- DELETE document — tsvector удаляется (CASCADE), `SELECT search_vector
  FROM documents WHERE id = 'deleted'` возвращает 0 rows.
- Unit-тест с mock asyncpg.Pool покрывает index_document + delete.
- Integration-тест с реальной PG (Блок A-3): round-trip index → search →
  delete.

Антипаттерны:
- НЕ создавай отдельный OpenSearch / Elasticsearch сервис для BM25 —
  PostgreSQL tsvector (Блок A-3) покрывает ADR-020 требования, принцип 5
  (объединение).
- НЕ обновляй tsvector вручную в коде — GENERATED ALWAYS AS STORED в Блоке
  A-3 автоматически пересчитывает. Ручное обновление — race condition с
  generated-column.
- НЕ делай BM25 indexing синхронно с vector indexing (один await за другим)
  — через asyncio.gather, иначе latency indexing удваивается.
- НЕ хардкодь text_search_config="english" — через env PG_TEXT_SEARCH_CONFIG
  (Блок A-3).
- НЕ храни chunks в отдельной таблице для BM25 (если vector использует
  chunks) — конкатенируй chunks в content документа, индексируй как единый
  tsvector. Иначе BM25 и vector работают на разных уровнях гранулярности,
  fusion некорректен.

Связанные ADR:
- Реализует: ADR-020 (BM25 indexing).
- Зависит от: Блок A-3 (PostgreSQL tsvector + GIN).
- Используется в: indexing pipeline (ARCHITECT.md §5.2.5), D-4 (HybridRetriever
  читает индекс).
- Не затрагивает: ADR-001, ADR-010, ADR-017.
```

### D-3. PostgreSQL tsvector в `documents` (использует A-3)

```
Ты — Backend/разработчик LLM Client. Создай helper-утилиты для работы с
tsvector в `documents` (Блок A-3 добавил колонку): SQL-запросы для
full-text search, ranking, snippet extraction.

Контекст:
- Блок A-3 добавил `search_vector` tsvector column + GIN index на
  `documents`.
- ADR-020 требует: query BM25 через `websearch_to_tsquery` (или
  `plainto_tsquery` для backward compat), ranking через `ts_rank`, snippet
  через `ts_headline`.
- ТРИЗ-принцип 28 (замена механической схемы): вместо ранжирования в
  Python (rank_bm25 library) — нативный PostgreSQL `ts_rank`, быстрее (no
  network round-trip, no Python overhead).
- ТРИЗ-принцип 17 (переход в другое измерение): full-text search выполняется
  в PostgreSQL, не в Python; упрощает код, использует query planner.

Задача:
1. Создай `BM25SearchQueries` (константы SQL-запросов) в
   `src/llm_client/rag/retrieval/bm25_queries.py`:
   ```python
   BM25_SEARCH_SQL = """
   SELECT
       id,
       content,
       metadata,
       ts_rank(search_vector, query) AS bm25_score,
       ts_headline('english', content, query,
         'StartSel=<b>, StopSel=</b>, MaxWords=35, MinWords=10,
         MaxFragments=3') AS snippet
   FROM documents, websearch_to_tsquery($PG_TEXT_SEARCH_CONFIG, $1) AS query
   WHERE search_vector @@ query
     AND user_id = $2
   ORDER BY bm25_score DESC
   LIMIT $3
   """

   BM25_SEARCH_WITH_FUZZY_SQL = """
   SELECT
       d.id, d.content, d.metadata,
       ts_rank(d.search_vector, query) AS bm25_score,
       similarity($1, d.content) AS fuzzy_score,
       ts_headline($PG_TEXT_SEARCH_CONFIG, d.content, query, ...) AS snippet
   FROM documents d, websearch_to_tsquery($PG_TEXT_SEARCH_CONFIG, $1) AS query
   WHERE d.search_vector @@ query
      OR d.content % $1  -- trigram fuzzy
   ORDER BY (bm25_score + fuzzy_score * 0.3) DESC
   LIMIT $2
   """
   ```
2. Создай `BM25Retriever` в `src/llm_client/rag/retrieval/bm25_retriever.py`:
   ```python
   class BM25Retriever:
       def __init__(self, pg_pool: asyncpg.Pool,
         text_search_config: str = "english",
         fuzzy_enabled: bool = False):
           self._pool = pg_pool
           self._tsc = text_search_config
           self._fuzzy = fuzzy_enabled

       async def retrieve(
           self,
           query: str,
           user_id: str,
           top_k: int = 20,
       ) -> list[dict]:
           sql = (BM25_SEARCH_WITH_FUZZY_SQL if self._fuzzy
                  else BM25_SEARCH_SQL)
           async with self._pool.acquire() as conn:
               rows = await conn.fetch(sql, query, user_id, top_k)
               return [
                   {
                       "id": r["id"],
                       "content": r["content"],
                       "metadata": r["metadata"],
                       "score": float(r["bm25_score"]),
                       "snippet": r["snippet"],
                   }
                   for r in rows
               ]
   ```
3. Query parsing:
   - `websearch_to_tsquery` — поддерживает google-стиль ("exact phrase"
     -exclude OR alt), user-friendly.
   - `plainto_tsquery` — simpler, не поддерживает operators; для backward
     compat с legacy callers (если есть).
   - Если query содержит special chars (", -, OR) — websearch_to_tsquery
     handles; plainto_to_tsquery выдаст ошибку.
4. Snippet generation:
   - `ts_headline` — built-in PostgreSQL function для extract relevant
     fragment с highlight (`<b>...</b>`).
   - `MaxFragments=3` — до 3 фрагментов, `MaxWords=35, MinWords=10` —
     размер каждого.
   - Snippet используется в UI для display (preview) и в LLM context (если
     chunk content не fits, snippet короче).
5. Ranking:
   - `ts_rank(search_vector, query)` — standard BM25-подобный ranking в
     PostgreSQL (не настоящий BM25, но сходный — frequency-based).
   - Для true BM25 (с IDF) — нужен `ts_rank_cd` (cover density) или
     кастомная formula. Phase 2 — `ts_rank` достаточно.
6. Filter по user_id (multi-tenancy):
   - Все запросы фильтруются по `user_id = $2` — каждый user видит только
     свои документы.
   - Если admin user — может быть `user_id IS NULL` для shared documents
     (опциональный enhancement, не required ADR-020).

Definition of Done:
- `BM25Retriever.retrieve("error code 1234", user_id, top_k=20)` возвращает
  top-20 документов, отсортированных по `bm25_score` descending.
- `websearch_to_tsquery` корректно парсит "error code 1234" (без quotes)
  и `"error code" 1234` (exact phrase).
- `ts_headline` возвращает snippet с `<b>` highlight.
- При `fuzzy_enabled=True` — fuzzy matching через pg_trgm работает для
  опечаток ("приер" → "пример").
- Filter по user_id — user видит только свои документы (multi-tenancy).
- Unit-тест с mock asyncpg.Pool покрывает retrieve + fuzzy + user_id
  filter.
- Integration-тест с реальной PG (Блок A-3): index 10 документов,
  retrieve по точному термину → top-1 содержит термин.
- EXPLAIN ANALYZE использует GIN index `idx_documents_search_vector`
  (не Seq Scan).

Антипаттерны:
- НЕ используй `plainto_tsquery` по умолчанию — не поддерживает query
  operators (", OR, -), user-experience хуже. websearch_to_tsquery —
  default.
- НЕ делай ranking в Python (rank_bm25 library) — это +network round-trip
  +Python overhead, медленнее PostgreSQL ts_rank. Принцип 28 (замена
  механики).
- НЕ возвращай full content без snippet — full content может быть большой
  (мегабайты), передаётся в LLM context целиком. Snippet — компактный
  preview.
- НЕ пропускай filter по user_id — это multi-tenancy violation, user
  увидит чужие документы.
- НЕ хардкодь "english" в SQL — через $PG_TEXT_SEARCH_CONFIG (Блок A-3),
  для multilingual корпуса — "russian" или "multilingual".
- НЕ используй `LIKE`/`ILIKE` для full-text search — это seq scan, не
  использует GIN index. Только `search_vector @@ query`.

Связанные ADR:
- Реализует: ADR-020 (BM25 retriever).
- Зависит от: Блок A-3 (tsvector + GIN), ADR-005 (PostgreSQL).
- Используется в: D-4 (HybridRetriever), D-5 (RRF fusion — input).
- Не затрагивает: ADR-001, ADR-010, ADR-017.
```

### D-4. `HybridRetriever` (vector top-20 + BM25 top-20)

```
Ты — Backend/разработчик LLM Client. Создай `HybridRetriever` —
композицию vector-retriever + BM25-retriever, параллельный retrieve,
return обоих списков для fusion (D-5).

Контекст:
- ADR-020 (TRIZ-ANALYSIS.md §11): "Hybrid retrieval: vector top-20 + BM25
  top-20 → RRF fusion → top-K."
- Существующий vector-retriever (ARCHITECT.md §5.2.5):
  `vector_store.as_retriever(search_type="mmr", k=8, fetch_k=20)`.
- Новый BM25-retriever (D-3): BM25Retriever.retrieve(query, user_id,
  top_k=20).
- HybridRetriever — НЕ делает fusion, только параллельный retrieve +
  return обоих списков. Fusion — отдельный шаг (D-5).
- ТРИЗ-стандарт 1.1.5 (введение второго поля в веполь): vector — поле
  Embeddings, BM25 — поле Text. Два поля, один query.
- ТРИЗ-принцип 19 (периодическое действие): parallel retrieve (не
  sequential), latency = max(vector, bm25), не sum.

Задача:
1. Создай `HybridRetriever` в `src/llm_client/rag/retrieval/hybrid.py`:
   ```python
   class HybridRetriever:
       def __init__(
           self,
           vector_retriever: VectorStoreRetriever,  # LangChain retriever
           bm25_retriever: BM25Retriever,
       ):
           self._vector = vector_retriever
           self._bm25 = bm25_retriever

       async def aretrieve(
           self,
           query: str,
           user_id: str,
           top_k_per_strategy: int = 20,
       ) -> tuple[list[dict], list[dict]]:
           """Returns (vector_docs, bm25_docs), each up to top_k_per_strategy."""
           vector_task = self._vector.aget_relevant_documents(
               query, k=top_k_per_strategy
           )
           bm25_task = self._bm25_retrieve(query, user_id, top_k_per_strategy)
           vector_docs, bm25_docs = await asyncio.gather(
               vector_task, bm25_task, return_exceptions=True
           )
           # Handle partial failures
           if isinstance(vector_docs, Exception):
               log_warning("hybrid_vector_failed", error=str(vector_docs))
               vector_docs = []
           if isinstance(bm25_docs, Exception):
               log_warning("hybrid_bm25_failed", error=str(bm25_docs))
               bm25_docs = []
           return vector_docs, bm25_docs

       async def _bm25_retrieve(self, query, user_id, top_k):
           return await self._bm25_retriever.retrieve(query, user_id, top_k)
   ```
2. Partial failure handling:
   - Если vector-retriever падает (vector_store недоступен) — продолжаем с
     BM25-only. log warning, fusion (D-5) обработает как vector_docs=[].
   - Если BM25 падает (PG недоступен) — продолжаем с vector-only.
   - Если оба падают — raise `RetrievalError`, graph должен обработать
     (например, ответ "не могу найти документы" через LLM).
3. Mapping результатов:
   - Vector docs: LangChain `Document` objects с `page_content`, `metadata`.
   - BM25 docs: dict с `id`, `content`, `metadata`, `score`, `snippet`.
   - Привести к общему формату для fusion (D-5): `{"id", "content",
     "metadata", "score"}`.
4. Latency:
   - `asyncio.gather` — parallel, latency = max(vector, bm25), не sum.
   - Типичная: vector 50 мс, BM25 30 мс → hybrid = 50 мс (не 80).
   - При RAG_HYBRID_TOP_K=20 — каждый retriever возвращает до 20, total до
     40 (с overlap) → fusion top-50 (D-5).
5. Metrics:
   - `rag_hybrid_vector_latency_ms` (histogram).
   - `rag_hybrid_bm25_latency_ms` (histogram).
   - `rag_hybrid_total_latency_ms` (histogram = max, not sum).
   - `rag_hybrid_vector_failure_count`, `rag_hybrid_bm25_failure_count`.

Definition of Done:
- `HybridRetriever.aretrieve(query, user_id, top_k=20)` возвращает tuple
  (vector_docs, bm25_docs), каждый до 20 элементов.
- Latency = max(vector, bm25), не sum (verify через metrics).
- При vector failure — bm25_docs возвращается, vector_docs=[], log warning.
- При bm25 failure — vector_docs возвращается, bm25_docs=[], log warning.
- При обеих failure — raise RetrievalError.
- Common format для fusion: {"id", "content", "metadata", "score"}.
- Unit-тест с mock retrievers покрывает happy path + partial failure.
- Integration-тест: stop vector_store mid-retrieve → bm25 continues, log
  warning.

Антипаттерны:
- НЕ делай sequential retrieve (vector, then bm25) — это sum latency,
  нарушение ТРИЗ-принципа 19 (периодическое действие / parallel).
- НЕ делай fusion внутри HybridRetriever — это ответственность D-5.
  HybridRetriever — просто композиция, single responsibility.
- НЕ возвращай raw LangChain `Document` для vector — приведи к общему
  dict формату, иначе fusion должен знать про два разных типа.
- НЕ проглатывай exceptions без log — log warning обязательно, иначе
  partial failure останется незамеченным.
- НЕ хардкодь top_k=20 — через RetrieverConfig.hybrid_top_k (D-1) или
  parameter.

Связанные ADR:
- Реализует: ADR-020 (hybrid retriever composition).
- Зависит от: D-3 (BM25Retriever), существующий vector-retriever (ARCHITECT.md
  §5.2.5).
- Используется в: D-5 (RRF fusion — input), C-4 (pipeline integration).
- Не затрагивает: ADR-001, ADR-010, ADR-017.
```

### D-5. RRF fusion (top-50) → reranker (top-5)

```
Ты — Backend/ML-разработчик LLM Client. Реализуй Reciprocal Rank Fusion
(RRF) — алгоритм объединения vector top-20 + BM25 top-20 в единый список
top-50, готовый для reranker (C-4).

Контекст:
- ADR-020 (TRIZ-ANALYSIS.md §11 строка 1118): "Hybrid retrieval: vector
  top-20 + BM25 top-20 → RRF fusion → top-K."
- RRF (Reciprocal Rank Fusion, Cormack et al. 2009) — стандартный алгоритм
  для fusion ranked lists с разными scoring functions:
  RRF(d) = sum(1 / (k + rank_i(d))) for i in retrievers
  где k=60 (typical constant), rank_i(d) — позиция d в retriever i.
- ТРИЗ-принцип 16 (частичное/избыточное действие): fusion "избыточно"
  сохраняет 50 (vs 20 vector-only), потом reranker "частично" оставляет 5.
- ТРИЗ-принцип 5 (объединение): RRF не требует score calibration (в отличие
  от weighted sum), работает с raw ranks — простота.
- Зависимость от reranker: без reranker fusion top-5 будет содержать noise
  (BM25-хиты для semantic queries). Reranker обязателен (см. C-4, где
  ADR-020 требует ADR-017 как prerequisite).

Задача:
1. Создай `RRFFusion` в `src/llm_client/rag/retrieval/fusion.py`:
   ```python
   def rrf_fusion(
       vector_docs: list[dict],
       bm25_docs: list[dict],
       top_k: int = 50,
       k_constant: int = 60,
       vector_weight: float = 0.5,
       bm25_weight: float = 0.5,
   ) -> list[dict]:
       """Fuse two ranked lists using Reciprocal Rank Fusion.
       Returns top_k unique documents sorted by RRF score."""
       scores: dict[str, float] = {}
       docs_by_id: dict[str, dict] = {}

       for rank, doc in enumerate(vector_docs, start=1):
           doc_id = doc["id"]
           scores[doc_id] = scores.get(doc_id, 0) + vector_weight / (k_constant
             + rank)
           docs_by_id[doc_id] = doc

       for rank, doc in enumerate(bm25_docs, start=1):
           doc_id = doc["id"]
           scores[doc_id] = scores.get(doc_id, 0) + bm25_weight / (k_constant
             + rank)
           docs_by_id[doc_id] = doc

       # Sort by RRF score descending
       sorted_ids = sorted(scores.items(), key=lambda x: x[1], reverse=True)
       return [
           {**docs_by_id[doc_id], "rrf_score": score}
           for doc_id, score in sorted_ids[:top_k]
       ]
   ```
2. Deduplication:
   - Документ может быть в обоих списках (vector и BM25 нашли один и тот же
     doc). RRF складывает scores — это правильно (документ, найденный
     двумя retriever-ами, более релевантен).
   - Idempotent: если vector_docs = bm25_docs, RRF-score = sum of both
     weights / (k + rank) — высокий score, документ в top.
3. Weights:
   - `vector_weight` и `bm25_weight` из RetrieverConfig (D-1).
   - default 0.5/0.5 — balanced.
   - Если corpus documentation-heavy (точные термины критичны) —
     bm25_weight=0.7, vector_weight=0.3.
   - Если corpus semantic-heavy (например, knowledge base) —
     vector_weight=0.7, bm25_weight=0.3.
4. K constant:
   - k=60 — standard value (Cormack 2009).
   - Можно настраивать, но для Phase 2 — фиксированное 60 (не трогать без
     ADR update).
5. Pipeline integration:
   ```python
   # In RAG pipeline after D-4:
   vector_docs, bm25_docs = await hybrid_retriever.aretrieve(query, user_id,
     top_k=20)
   fused_docs = rrf_fusion(vector_docs, bm25_docs, top_k=50,
     vector_weight=config.vector_weight, bm25_weight=config.bm25_weight)
   final_docs = await rerank_after_fusion(query, fused_docs, config)  # C-4
   ```
6. Metrics:
   - `rag_fusion_latency_ms` (histogram, typically <5ms — pure Python).
   - `rag_fusion_input_count` (gauge, vector + bm25 count, typically 40).
   - `rag_fusion_output_count` (gauge, after dedup, typically 30–50).
   - `rag_fusion_overlap_count` (gauge, docs in both vector and bm25).

Definition of Done:
- `rrf_fusion([doc1, doc2], [doc2, doc3], top_k=2)` возвращает 2 уникальных
  документа, отсортированных по RRF score.
- Документ в обоих списках (doc2) имеет score = vector_weight/(60+2) +
  bm25_weight/(60+2) — выше, чем документ только в одном списке.
- 50 документов после fusion — типичный output (если 20+20 без overlap, 40
  уникальных; с overlap — меньше).
- Latency <5 мс для 20+20 docs (pure Python, no I/O).
- Weights работают: bm25_weight=0.7 поднимает BM25-хиты в top.
- K constant 60 — фиксированное, не настраиваемое (без ADR update).
- Metrics: fusion latency, input/output count, overlap count.
- Unit-тест: пустые списки, один список пустой, full overlap, no overlap.

Антипаттерны:
- НЕ используй weighted sum scores (vector_score * w1 + bm25_score * w2) —
  vector_score и bm25_score имеют разные масштабы (cosine 0..1, ts_rank
  0..∞), calibration сложная. RRF работает с ranks, не scores — проще и
  robust.
- НЕ хардкодь k=60 в pipeline — передавай в rrf_fusion параметром, для
  тестов с другими значениями.
- НЕ удаляй дубликаты (документ в обоих списках) — RRF должен сложить scores
  для дубликатов, это правильное поведение (документ, найденный двумя
  retriever-ами, более релевантен).
- НЕ делай fusion в SQL (PostgreSQL) — это сложно (vector + tsvector в одном
  query), RRF в Python проще и достаточно fast (<5ms).
- НЕ пропускай fusion если vector_docs или bm25_docs пустой — RRF с пустым
  списком работает (returns other list as-is), это правильно для partial
  failure (D-4).
- НЕ хардкодь top_k=50 — через RetrieverConfig.hybrid_top_k (D-1).

Связанные ADR:
- Реализует: ADR-020 (RRF fusion).
- Зависит от: D-4 (HybridRetriever — input), D-1 (RetrieverConfig — weights).
- Используется в: C-4 (rerank_after_fusion — input), Блок E-4 (A/B test).
- Не затрагивает: ADR-001, ADR-010, ADR-017.
```

### D-6. A/B test для exact-term recall (product SKU / error codes)

```
Ты — QA/ML-разработчик LLM Client. Создай A/B test для ADR-020: сравнение
recall для exact-term запросов (product SKU, error codes, IDs) между
baseline (vector-only) и treatment (hybrid vector+BM25).

Контекст:
- ROADMAP.md §6.5 (ADR-020 критерий готовности): "A/B test 1 неделя —
  recall ↑ для точных терминов ≥30%; latency retrieval ↑ <50%; BM25 index
  строится синхронно с vector index при индексации."
- A/B test framework — переиспользуется из C-6 (RAGEvaluator, dataset
  format).
- Категория `exact_term` в dataset (C-6 п.1) — релевантная категория для
  ADR-020. Дополнительные категории: SKU-format, error-code-format,
  ID-format.
- TRIZ-принцип 23 (обратная связь): A/B test — feedback-loop для ADR-020.

Задача:
1. Расширь dataset (C-6 п.1) дополнительными exact-term категориями:
   ```jsonl
   {"query": "product SKU ABC-1234", "relevant_doc_ids": ["doc_42"],
    "category": "exact_term", "subtype": "sku"}
   {"query": "error ERR-502 in checkout", "relevant_doc_ids": ["doc_10"],
    "category": "exact_term", "subtype": "error_code"}
   {"query": "employee EMP-123456", "relevant_doc_ids": ["doc_5"],
    "category": "exact_term", "subtype": "employee_id"}
   ```
   - 30 exact_term queries, 10 per subtype (sku, error_code, employee_id).
   - Ground truth — human-labeled.
2. Создай A/B test runner `scripts/ab_test_hybrid_rag.py` (расширяет C-6):
   ```python
   async def main():
       evaluator = RAGEvaluator(pipeline, "datasets/rag_eval/phase2_eval.jsonl")

       baseline_config = RetrieverConfig(
           retrieval_strategy=RetrievalStrategy.VECTOR,
           reranker_enabled=False,  # no reranker, pure vector baseline
       )
       treatment_config = RetrieverConfig(
           retrieval_strategy=RetrievalStrategy.HYBRID,
           reranker_enabled=True,  # with reranker (C-4), full ADR-017+020
           reranker_name="bge",
       )

       baseline_report = await evaluator.evaluate(baseline_config)
       treatment_report = await evaluator.evaluate(treatment_config)

       # Focus on exact_term category
       baseline_exact = baseline_report.per_category["exact_term"]
       treatment_exact = treatment_report.per_category["exact_term"]

       improvement = ((treatment_exact.recall_at_5 - baseline_exact.recall_at_5)
                       / baseline_exact.recall_at_5 * 100)
       latency_overhead = (treatment_exact.avg_latency_ms -
                           baseline_exact.avg_latency_ms)

       print(f"Exact-term recall@5: {baseline_exact.recall_at_5:.3f} → "
             f"{treatment_exact.recall_at_5:.3f} ({improvement:.1f}%)")
       print(f"Latency overhead: {latency_overhead:.1f}ms")
       # PASS if improvement >= 30% AND latency overhead <50% (relative)
       # FAIL otherwise
   ```
3. PASS criteria (ADR-020):
   - recall@5 ↑ ≥30% для exact_term категории.
   - Latency overhead <50% relative (baseline 50ms → treatment <75ms; tighter
     than C-6 reranker criterion <100ms absolute).
   - BM25 index строится синхронно с vector index (verify через indexing
     pipeline test).
4. Subtype breakdown:
   - `sku` (ABC-1234): BM25 должен ловить точно, recall improvement high
     (>=40%).
   - `error_code` (ERR-502): BM25 ловит точно, recall improvement high
     (>=40%).
   - `employee_id` (EMP-123456): BM25 ловит (custom regex? нет, tsvector
     handles as token), recall improvement medium (>=25%).
5. Запуск в CI:
   - `scripts/ab_test_hybrid_rag.py` — nightly job, separate от
     `ab_test_reranker.py` (C-6).
   - Результат сохраняется в `reports/ab_test_hybrid_rag_{date}.json`.
   - PASS: improvement >=30% AND latency overhead <50%.
6. Regression test для BM25 indexing:
   - Отдельный unit-тест: при `index_document(doc)`, `tsvector` обновляется
     синхронно (не позже, не асинхронно).
   - Это гарантирует, что после индексации документ сразу searchable в BM25
     (latency <1 сек).

Definition of Done:
- Dataset расширен: 30 exact_term queries (10 sku + 10 error_code + 10
  employee_id).
- A/B test runner: baseline (vector) vs treatment (hybrid + reranker), PASS
  if recall@5 ↑ ≥30% AND latency overhead <50%.
- Subtype breakdown в JSON-отчёте: per-subtype recall improvement.
- Запуск nightly в CI (Блок E-5), результат в CI-артефактах.
- При FAIL — alert в Slack #architecture.
- BM25 indexing regression test: after `index_document`, `BM25Retriever.
  retrieve` finds the document in <1 сек.
- Trend visible в Grafana (Блок F-2): exact_term recall trend за 6 месяцев.

Антипаттерны:
- НЕ сравнивай hybrid без reranker vs vector — это некорректно (ADR-020
  требует ADR-017 как prerequisite, без reranker hybrid noisy). Treatment =
  hybrid + reranker, baseline = vector (без reranker).
- НЕ агрегируй all categories в single recall@5 — ADR-020 критерий
  specifically для exact_term, не для semantic. Semantic recall может
  упасть (vector на semantic лучше), это OK.
- НЕ пропускай subtype breakdown — если employee_id improvement <25%, это
  red flag (BM25 не ловит EMP-формат, возможно нужен custom tsvector
  config).
- НЕ делай latency overhead relative <30% — это слишком tight, hybrid
  удваивает retriever calls. <50% (relative) или <100ms absolute (как в
  C-6) — разумно.
- НЕ запускай A/B test на unit-тестах — нужен staging с реальными
  PG tsvector + bge-reranker.

Связанные ADR:
- Тестирует: ADR-020 (exact-term recall improvement).
- Зависит от: Блок D-1..D-5 (full implementation), Блок C-1..C-6 (reranker
  — prerequisite для hybrid), Блок A-3 (tsvector).
- Переиспользует: C-6 (RAGEvaluator framework).
- Используется в: Блок E-4 (CI integration), Блок F-2 (Grafana trend).
- Не затрагивает: ADR-001, ADR-010.
```

---

## 5. Блок E. Тесты и CI для Phase 2

**Источник**: `ROADMAP.md` v1.1.0 §6.6 (критерии выхода), §15.2 (метрика идеальности), §18.2 (Grafana dashboard + Slack alerting). Покрывает три ADR-критерия: (1) ADR-010 — latency checkpoint <2 мс, восстановление при restart; (2) ADR-017 — recall@5 ↑ ≥15%, latency retrieval ↑ <100 мс; (3) ADR-020 — recall ↑ для точных терминов ≥30%, latency retrieval ↑ <50%. Расширяет Phase 1 CI pipeline из `MVP-PROMPTS.md` Блок F-4 (не дублирует).

### E-1. Latency checkpoint test (<2 мс в 99% на staging)

```
Ты — QA/Automation-разработчик LLM Client. Создай integration-тест для
ADR-010 (Блок B), проверяющий критерий готовности "latency checkpoint <2 мс
в 99% случаев на staging".

Контекст:
- ROADMAP.md §6.6 п.1 (ADR-010 критерий): "latency checkpoint <2 мс в 99%
  случаев на staging".
- Блок B-6 уже создал `test_checkpoint_latency` — этот промпт описывает
  расширение: НЕ дублируй B-6, а интегрируй в CI pipeline (E-5) и добавь
  trend tracking в Grafana (F-2).
- MVP-PROMPTS.md Блок F-1 — аналог для ADR-013 (cancel latency <100ms),
  паттерн переиспользуется: 1000 сэмплов, p50/p95/p99, nightly job.

Задача:
1. Убедись, что `test_checkpoint_latency` из B-6 настроен как nightly job в
   CI (не в PR-pipeline, долго — 10 минут).
2. Добавь trend tracking:
   - Каждый запуск пишет JSON-отчёт в `reports/checkpoint_latency_{date}.json`.
   - Скрипт `scripts/track_checkpoint_latency.py` агрегирует отчёты в
     single timeseries CSV `reports/checkpoint_latency_trend.csv`.
   - Grafana (Блок F-2) читает CSV (или через Prometheus pushgateway —
     `B-6 → pushgateway → Grafana`).
3. Alerting (через Grafana → Slack webhook):
   - Alert: `p99 checkpoint latency >2ms` за последние 7 дней (trend up).
   - Alert: `p50 checkpoint latency >1ms` (раньше времени signal of
     degradation, до p99 breach).
   - Channel: #architecture.
4. Regression gates:
   - PR-pipeline (Блок E-5) запускает quick-версию теста (100 сэмплов, не
     1000) — PASS: p99 <5 мс (looser criterion, чем staging <2 мс).
   - Nightly (staging) — full test, 1000 сэмплов, p99 <2 мс.

Definition of Done:
- `test_checkpoint_latency` запускается nightly на staging.
- JSON-отчёт сохраняется в CI-артефактах.
- Trend tracking: CSV обновляется после каждого nightly run.
- Grafana dashboard (Блок F-2) показывает trend за 6 месяцев.
- Slack alert при p99 >2ms (7-day trend) ИЛИ p50 >1ms.
- PR-pipeline quick-test (100 сэмплов) PASS: p99 <5 мс.

Антипаттерны:
- НЕ запускай full test (1000 сэмплов) в PR-pipeline — это 10 минут,
  блокирует разработчиков. Quick-test 100 сэмплов = 1 минута.
- НЕ алертить на single bad run — trend (7-day window), не single point.
- НЕ игнорируй p50 — это early warning signal, p99 breach = уже regression.

Связанные ADR:
- Тестирует: ADR-010 (Блок B).
- Зависит от: Блок B-6 (test exists), Блок E-5 (CI integration), Блок F-2
  (Grafana).
- Расширяет: Блок F-1 MVP-PROMPTS (cancel latency test pattern).
```

### E-2. Restart recovery test (snapshot + replay protocol)

```
Ты — QA/разработчик LLM Client. Создай integration-тест для recovery
protocol (Блок B-5): 4 сценария (planned restart, Redis crash, PG crash,
simultaneous crash) выполняются в CI nightly.

Контекст:
- ROADMAP.md §6.6 п.2 (ADR-010 критерий): "восстановление при restart
  корректно (snapshot + replay)".
- Блок B-5 п.5 уже описал 4 test-scenarios; этот промпт описывает их
  integration в CI.
- MVP-PROMPTS.md Блок F-1 (cancel latency) — pattern переиспользуется.

Задача:
1. Используй testcontainers-python или docker-compose для управления
   контейнерами Redis, PG, agent-service.
2. Для каждого из 4 сценариев (B-5 п.5):
   - Setup: write 10 checkpoint-ов через `aput`.
   - Trigger: kill service (Redis/PG/app), wait, restart.
   - Verify: `recover()` replays delta, state consistent, loss <=5 сек.
3. CI integration:
   - Nightly job (long-running, ~20 минут).
   - 4 parallel jobs (scenarios independent).
   - PASS: все 4 сценария проходят.
   - FAIL: alert в Slack с указанием fail-ящего сценария.
4. Reporting:
   - JSON-отчёт per scenario: recovered count, replayed delta, conflicts.
   - Aggregated trend в Grafana (Блок F-2): recovery time, data loss.

Definition of Done:
- 4 сценария проходят nightly.
- Recovery time <10 сек для 100 active thread_id-ов (B-5 критерий).
- Loss <=5 сек в сценарии 4 (simultaneous crash) — verified.
- JSON-отчёт per scenario в CI-артефактах.
- Grafana trend за 6 месяцев.
- При FAIL — Slack alert.

Антипаттерны:
- НЕ запускай recovery test в PR-pipeline — нужны реальные контейнеры, long.
- НЕ эмулируй "одновременный отказ" через `docker-compose stop redis
  postgres` последовательно — это не simultaneous. Используй `docker kill
  -SIGKILL` для обоих сразу.
- НЕ пропускай scenario 4 (simultaneous crash) — это маловероятный, но
  critical scenario; "пилотная неделя без потери" (ROADMAP.md §6.3) —
  именно про него.

Связанные ADR:
- Тестирует: ADR-010 (Блок B-5 recovery).
- Зависит от: Блок B-5 (recovery protocol), Блок E-5 (CI integration),
  Блок F-2 (Grafana).
```

### E-3. Recall@5 A/B test (bge-reranker vs baseline)

```
Ты — QA/ML-разработчик LLM Client. Интегрируй A/B test framework (C-6) в
CI pipeline: nightly job сравнивает recall@5 между baseline (no reranker)
и treatment (bge-reranker).

Контекст:
- ROADMAP.md §6.6 п.3 (ADR-017 критерий): "recall@5 ↑ ≥15%; latency retrieval
  ↑ <100 мс".
- Блок C-6 уже создал A/B test framework + dataset; этот промпт описывает
  CI integration.

Задача:
1. Используй `scripts/ab_test_reranker.py` (C-6 п.3) в nightly job.
2. PASS criteria:
   - recall@5 ↑ ≥15% (overall).
   - Semantic category recall@5 ↑ ≥15% (most affected by reranker).
   - Latency overhead <100 мс absolute.
3. Regression gates:
   - PR-pipeline (Блок E-5): quick test on 10 queries (not full 50+), PASS:
     no regression vs main branch.
   - Nightly: full test on 50+ queries, PASS per criteria above.
4. Trend tracking:
   - JSON-отчёт per run → `reports/ab_test_reranker_{date}.json`.
   - Aggregated CSV `reports/reranker_recall_trend.csv` (baseline, treatment,
     improvement, latency_overhead, date).
   - Grafana (Блок F-2): trend за 6 месяцев.
5. Alerting:
   - Alert: improvement <15% (regression in reranker quality).
   - Alert: latency overhead >100 мс (reranker slow).
   - Channel: #architecture.

Definition of Done:
- Nightly job запускает full A/B test (50+ queries).
- PASS: recall@5 ↑ ≥15% AND latency overhead <100 мс.
- PR-pipeline: quick test on 10 queries, no regression.
- Trend visible в Grafana.
- Slack alert при regression.

Антипаттерны:
- НЕ запускай full A/B test в PR-pipeline — долго (нужна реальная bge-model).
- НЕ агрегируй categories в single recall@5 для PASS criterion — semantic
  recall@5 must >=15% specifically; exact_term improvement может быть low
  (BM25 доминирует, не reranker).
- НЕ игнорируй latency overhead — если >100 мс, это breach ADR-017.

Связанные ADR:
- Тестирует: ADR-017 (Блок C-6 framework).
- Зависит от: Блок C-6 (A/B test framework), Блок E-5 (CI), Блок F-2
  (Grafana).
```

### E-4. Exact-term recall A/B test (hybrid vs vector-only)

```
Ты — QA/ML-разработчик LLM Client. Интегрируй A/B test для ADR-020 (D-6) в
CI pipeline: nightly job сравнивает exact-term recall между baseline
(vector-only) и treatment (hybrid + reranker).

Контекст:
- ROADMAP.md §6.6 п.4 (ADR-020 критерий): "recall ↑ для точных терминов
  ≥30%; latency retrieval ↑ <50%".
- Блок D-6 уже создал A/B test runner; этот промпт описывает CI integration.
- Dataset расширен (D-6 п.1): 30 exact_term queries (sku, error_code,
  employee_id).

Задача:
1. Используй `scripts/ab_test_hybrid_rag.py` (D-6 п.2) в nightly job.
2. PASS criteria:
   - Exact-term recall@5 ↑ ≥30%.
   - Subtype breakdown: sku >=40%, error_code >=40%, employee_id >=25%.
   - Latency overhead <50% relative (baseline 50ms → treatment <75ms).
3. Regression gates:
   - PR-pipeline (Блок E-5): quick test on 5 queries per subtype, PASS:
     no regression vs main branch.
   - Nightly: full test on 30 queries, PASS per criteria above.
4. Trend tracking:
   - JSON-отчёт per run → `reports/ab_test_hybrid_rag_{date}.json`.
   - Aggregated CSV `reports/hybrid_recall_trend.csv` (per-subtype:
     baseline, treatment, improvement, latency, date).
   - Grafana (Блок F-2): per-subtype trend.
5. Alerting:
   - Alert: exact_term recall@5 improvement <30%.
   - Alert: subtype improvement <threshold (sku/error_code <40%,
     employee_id <25%).
   - Alert: latency overhead >50% relative.
   - Channel: #architecture.
6. BM25 indexing regression test (D-6 п.6):
   - Unit-тест: при `index_document(doc)`, `BM25Retriever.retrieve(query,
     doc.content)` находит документ в <1 сек.
   - Запускается в PR-pipeline (не nightly, fast).

Definition of Done:
- Nightly job запускает full A/B test (30 exact_term queries, 10 per
  subtype).
- PASS: exact_term recall@5 ↑ ≥30% AND per-subtype criteria AND latency
  overhead <50%.
- PR-pipeline: quick test (15 queries, 5 per subtype), no regression.
- BM25 indexing regression test в PR-pipeline.
- Trend visible в Grafana (per-subtype).
- Slack alert при regression.

Антипаттерны:
- НЕ запускай full A/B test в PR-pipeline — нужно ~10 минут.
- НЕ агрегируй subtypes в single exact_term recall@5 — subtype breakdown
  важен, чтобы поймать "employee_id плохо работает, но sku/error_code
  тащат overall".
- НЕ пропускай BM25 indexing regression test — это cheap unit-test, в
  PR-pipeline, ловит рассинхронизацию tsvector и content.

Связанные ADR:
- Тестирует: ADR-020 (Блок D-6 framework).
- Зависит от: Блок D-6 (A/B test framework), Блок A-3 (tsvector), Блок E-5
  (CI), Блок F-2 (Grafana).
```

### E-5. Phase 2 CI pipeline (расширение Phase 1 CI)

```
Ты — DevOps/CI-разработчик LLM Client. Расширь Phase 1 CI pipeline
(MVP-PROMPTS.md Блок F-4) для Phase 2: добавь jobs для ADR-010/017/020
тестов, обнови nightly pipeline.

Контекст:
- MVP-PROMPTS.md Блок F-4 создал Phase 1 CI:
  - PR-pipeline: lint + unit + integration-dev + integration-staging + pii-
    leak-audit + minio-parity.
  - Nightly: cancel-latency-staging + minio-parity-full + idealidad-metric.
- Phase 2 добавляет 3 new ADR (010, 017, 020) — каждый требует testing.
- ROADMAP.md §6.6 — критерии выхода Phase 2.

Задача:
1. Расширь `.github/workflows/phase1-ci.yml` (или эквивалент) — добавь jobs:
   - `checkpoint-quick`: Блок E-1 quick-test (100 сэмплов), PASS p99 <5 мс.
     <2 мин. В PR-pipeline.
   - `bm25-indexing-regression`: Блок E-4 BM25 indexing unit-test. <30 сек.
     В PR-pipeline.
   - `reranker-quick`: Блок E-3 quick-test (10 queries), no regression vs
     main. <3 мин. В PR-pipeline.
   - `hybrid-rag-quick`: Блок E-4 quick-test (15 queries), no regression.
     <5 мин. В PR-pipeline.
2. Обнови `.github/workflows/phase1-nightly.yml` (или создай `phase2-nightly
   .yml`):
   - `checkpoint-latency-staging`: Блок E-1 full (1000 сэмплов), p99 <2 мс.
     <10 мин.
   - `checkpoint-recovery-staging`: Блок E-2 (4 scenarios). <20 мин.
   - `reranker-ab-test-staging`: Блок E-3 full (50+ queries). <10 мин.
   - `hybrid-rag-ab-test-staging`: Блок E-4 full (30 queries). <10 мин.
   - `idealidad-metric`: обнови под Phase 2 metrics (Блок F-2).
3. Кэширование (расширь Phase 1):
   - `~/.cache/huggingface` для bge-reranker (Блок A-2) — large cache, days.
   - `models/bge-reranker-base/` volume (если не через cache).
4. Artefacts (расширь Phase 1):
   - `checkpoint_latency_report_{date}.json` (E-1).
   - `checkpoint_recovery_report_{date}.json` (E-2).
   - `ab_test_reranker_{date}.json` (E-3).
   - `ab_test_hybrid_rag_{date}.json` (E-4).
   - Все хранить 30 дней (наследовано из Phase 1).
5. Staging secrets (через GitHub Secrets / GitLab Variables):
   - `COHERE_API_KEY` (опционально, для CohereRerankAdapter testing).
   - `STAGING_REDIS_URL`, `STAGING_POSTGRES_URL` (если separate от CI
     runner).
6. Локальный запуск (расширь `make ci-local`):
   - `make ci-local-quick` — запускает PR-pipeline jobs локально.
   - `make ci-local-staging` — запускает nightly jobs на staging (manual).
   - Тот же docker-compose + pytest, что в CI.

Definition of Done:
- PR-pipeline завершается за <25 минут (parallel jobs, 5 новых quick-
  tests добавили ~15 мин к Phase 1 baseline 15 мин).
- Nightly pipeline завершается за <60 минут (4 new jobs).
- При FAIL — понятное сообщение в PR с ссылкой на artefact.
- Coverage report показывает % покрытия ADR-010 (Блок B), ADR-017 (Блок C),
  ADR-020 (Блок D).
- Slack alerting в #architecture при падении idealidad metric.
- Hugging Face cache переиспользуется между запусками (visible через cache
  hit rate в CI logs).

Антипаттерны:
- НЕ делай sequential jobs — все независимые должны идти параллельно.
- НЕ хардкодй secrets в workflow — через GitHub Secrets.
- НЕ пропускай nightly job "потому что weekend" — метрика идеальности
  важна, A/B tests — regression detection.
- НЕ забудь cleanup docker-compose после тестов (down -v) — иначе runner
  забивается (наследовано из Phase 1).
- НЕ добавляй Phase 2 jobs в `phase1-ci.yml` без namespace — создай отдельный
  `phase2-ci.yml` или используй префикс `phase2-*` для jobs.
- НЕ запускай nightly jobs одновременно — staggered (один за другим, не
  параллельно), чтобы не перегружать staging.

Связанные ADR:
- Покрывает CI для: ADR-010 (Блок B + E-1, E-2), ADR-017 (Блок C + E-3),
  ADR-020 (Блок D + E-4).
- Расширяет: Блок F-4 MVP-PROMPTS (Phase 1 CI).
- Зависит от: Блок A-1..A-3 (infra для Phase 2), Блоки B/C/D (реализации),
  Блоки E-1..E-4 (тесты).
```

---

## 6. Блок F. Документация и метрика идеальности

**Источник**: `ROADMAP.md` v1.1.0 §6.6 п.5 (документация обновлена), §15.2 (метрика идеальности Phase 2 control point), §18.2 (Grafana + Slack alerting). Расширяет Phase 1 Блок G `MVP-PROMPTS.md`.

### F-1. Обновление `ARCHITECT.md` §7 / §8 / §12 после Phase 2

```
Ты — Tech-писатель / архитектор LLM Client. Обнови `ARCHITECT.md` после
завершения Phase 2: добавь новые ADR (010, 017, 020), пометь противоречия
C-2, C-6 как resolved, обнови component diagram.

Контекст:
- ROADMAP.md §6.6 п.5: "ARCHITECT.md § 7 ADR обновлён (ADR-010, ADR-017,
  ADR-020 добавлены); § 8 Trade-offs обновлён (C-2, C-6 помечены как
  resolved)".
- ROADMAP.md §18.5: "После approval каждого ADR — обновление ARCHITECT.md.
  Срок: 1 день после approval."
- MVP-PROMPTS.md Блок G-1 — аналог для Phase 1; паттерн переиспользуется.

Задача:
1. В §7 ADR ARCHITECT.md:
   - Добавь ADR-010 (Async Checkpoint Write-Behind Log) — Status: Approved.
     Context, Decision (composite Redis+PG), Consequences (из TRIZ-ANALYSIS
     §11).
   - Добавь ADR-017 (Reranker Model in RAG) — Status: Approved. Context,
     Decision (bge-reranker-base default + Cohere optional + RerankerRegistry),
     Consequences.
   - Добавь ADR-020 (Hybrid BM25+Vector RAG default) — Status: Approved.
     Context, Decision (RetrieverConfig.retrieval_strategy=hybrid default +
     BM25IndexBuilder + RRF fusion), Consequences.
   - Для каждого нового ADR — Context, Decision, Consequences (как в
     TRIZ-ANALYSIS.md §11).
2. В §8 Trade-offs:
   - C-2 (PG checkpoint vs latency) → [RESOLVED by ADR-010 in Phase 2].
   - C-6 (long RAG context vs cost) → [RESOLVED by ADR-017 + ADR-020 in
     Phase 2 (precision/recall)] + [ADR-011 в Phase 3 — cost component
     pending].
   - Каждое противоречие — оставить для исторического контекста, добавить
     markdown-зачёркивание или [RESOLVED] метку.
3. В §12 Открытые вопросы:
   - Q-5 (Стоимость LLM при >50k токенов контекста) → [PARTIALLY CLOSED:
     ADR-017 + ADR-020 снижают context size; ADR-011 в Phase 3 — full
     closure через semantic cache].
   - Q-1 (Ollama), Q-4 (Streamlit+async) — оставлены для Phase 4 (TRIZ §18.4
     triage).
4. В §13 (если есть компонентная диаграмма) — обновить:
   - Добавить Redis DB 1 (checkpoint-WAL) рядом с Redis DB 0 (pub/sub).
   - Добавить `RedisPostgresCheckpointer` в Orchestration Layer.
   - Добавить `RerankerRegistry` + `BgeRerankerAdapter` в RAG Layer.
   - Добавить `BM25IndexBuilder` + `BM25Retriever` + `HybridRetriever` +
     `RRFFusion` в RAG Layer.
   - Показать PostgreSQL с двумя extensions: pgvector (existing) + tsvector
     (new).
5. В §5.2.2 (Checkpointer):
   - Обновить: "PostgresSaver (ADR-001)" → "RedisPostgresCheckpointer
     (ADR-010, Phase 2; composite sync Redis + async PG; PostgresSaver
     deprecated, только для backward-compat tests)".
6. В §5.2.5 (RAG Layer):
   - Обновить pipeline: "...vector top-20 + BM25 top-20 → RRF fusion top-50
     → reranker top-5" (ADR-020 + ADR-017).
   - Обновить RetrieverConfig fields (D-1).
7. Согласованность с ROADMAP/TRIZ:
   - В §7 ARCHITECT.md для каждого ADR — ссылка на соответствующий § в
     ROADMAP.md (§6.3, §6.4, §6.5) и TRIZ-ANALYSIS.md (§5.2, §6.1, §11).

Definition of Done:
- ARCHITECT.md версия обновлена (1.1.0 → 1.2.0) с changelog.
- Changelog: "1.2.0 (2026-09-XX): Phase 2 завершена — добавлены ADR-010,
  ADR-017, ADR-020; C-2 помечено [RESOLVED]; C-6 помечено [PARTIALLY
  RESOLVED, ADR-011 pending Phase 3]; Q-5 частично закрыт; component
  diagram обновлён с Redis DB 1, RerankerRegistry, HybridRetriever,
  BM25IndexBuilder; §5.2.2 Checkpointer обновлён на
  RedisPostgresCheckpointer; §5.2.5 RAG pipeline обновлён на hybrid +
  reranker".
- §7 содержит ADR-010, ADR-017, ADR-020 (новые).
- §8 содержит 2 помеченных [RESOLVED] / [PARTIALLY RESOLVED] противоречия.
- §12 содержит Q-5 [PARTIALLY CLOSED].
- Компонентная диаграмма обновлена.
- Все ссылки на ROADMAP.md / TRIZ-ANALYSIS.md — корректны (не 404).
- PR с обновлением reviewed архитектурным комитетом, merged.

Антипаттерны:
- НЕ удаляй старые Trade-offs — оставь для исторического контекста с
  [RESOLVED] меткой.
- НЕ скрывай упразднённый PostgresSaver — явно пометь "deprecated in Phase
  2, replaced by RedisPostgresCheckpointer".
- НЕ переписывай ADR-001, ADR-003, ADR-005, ADR-007, ADR-008, ADR-013, ADR-014
  (Phase 1) — только обнови cross-references если нужно.
- НЕ добавляй ADR из Phase 3+ (ADR-011, ADR-015, ADR-016, ADR-018, ADR-019)
  — только Phase 2 ADR.
- НЕ забудь changelog — без него невозможно отследить что изменилось.

Связанные ADR:
- Документирует: ADR-010, ADR-017, ADR-020.
- Ссылается на: ROADMAP.md §6, TRIZ-ANALYSIS.md §5.2, §6.1, §11.
- Расширяет: Блок G-1 MVP-PROMPTS (Phase 1 ARCHITECT.md update).
```

### F-2. Grafana dashboard: Phase 2 control point (Δф/Δсложности = 1.5)

```
Ты — DevOps/Observability-разработчик LLM Client. Расширь Grafana dashboard
из Phase 1 (MVP-PROMPTS.md Блок G-2) для Phase 2: добавь panel с метрикой
идеальности Phase 2 control point (Δф=+3, Δсложности=+2, ratio=1.5).

Контекст:
- ROADMAP.md §15.2: Phase 2 control point — Δф/Δсложности = 1.5 (3 new
  capabilities / 2 new dependencies) ≥ 1.
- Phase 2 new capabilities: (1) async checkpoint, (2) reranker, (3) hybrid
  retrieval.
- Phase 2 new dependencies: (1) bge-reranker (~600MB RAM), (2) PostgreSQL
  tsvector (existing PG, new extension).
- MVP-PROMPTS.md Блок G-2 создал dashboard для Phase 1 (ratio 2.0). Этот
  промпт расширяет dashboard, не дублирует.

Задача:
1. Расширь Grafana dashboard JSON model (из Phase 1, Блок G-2):
   - Panel 5 (new): Phase 2 metrics:
     - `llm_client_phase2_checkpoint_p99_latency_ms` (Блок E-1).
     - `llm_client_phase2_checkpoint_recovery_count` (Блок E-2).
     - `llm_client_phase2_reranker_recall_at_5` (Блок E-3).
     - `llm_client_phase2_hybrid_recall_exact_term` (Блок E-4).
     - `llm_client_phase2_reranker_fallback_count` (Блок C-5).
   - Panel 6 (new): Phase 2 idealidad control point:
     - Vertical line at Phase 2 start date.
     - Phase 2 ratio = 1.5 (annotation).
     - Trend: dependency_count (bge-reranker, tsvector added) vs
       capability_count (3 new).
   - Panel 7 (new): RAG quality trend:
     - Per-category recall@5 (exact_term, semantic, fuzzy).
     - Latency overhead (reranker vs baseline, hybrid vs vector-only).
2. Annotations (vertical lines):
   - Phase 1 end / Phase 2 start (date из changelog ARCHITECT.md).
   - Phase 2 end / Phase 3 start (когда начнётся).
3. Slack alerting (расширь Phase 1 alerts):
   - Alert: `idealidad ratio <1.0` (Phase 2 control point не достигнут).
   - Alert: `reranker fallback_count >100/day` (reranker chain деградирует).
   - Alert: `checkpoint recovery loss >5 сек` (acceptable risk breach).
   - Alert: `hybrid exact_term recall@5 regression >5%` (trend down).
4. Annotations in dashboard:
   - Когда каждый ADR-010/017/020 был Approved (manual annotation).
   - Когда каждый A/B test запущен (auto из CI).

Definition of Done:
- Dashboard доступен по той же ссылке в Confluence / internal wiki.
- Panel 5 (Phase 2 metrics) показывает live data.
- Panel 6 (idealidad control point) показывает Phase 1 (ratio 2.0) и Phase 2
  (ratio 1.5) annotations.
- Panel 7 (RAG quality trend) показывает per-category recall@5 за 6 месяцев.
- Slack alerting: 4 новых alerts (idealidad, reranker fallback, recovery
  loss, hybrid regression).
- Phase 2 control point visible check: ratio = 1.5 (3 caps / 2 deps), ≥1
  PASS.

Антипаттерны:
- НЕ удаляй Phase 1 panels — расширяем, не перезаписываем.
- НЕ добавляй Phase 3 metrics (semantic cache, cost-aware router) — они
  появятся в Phase 3, сейчас данных нет.
- НЕ считай capability_count вручную — через automated script (как в
  Phase 1 Блок G-2).
- НЕ алертить на single bad day — trend (7-day window).

Связанные ADR:
- Не ADR-specific, инфраструктурная задача.
- Расширяет: Блок G-2 MVP-PROMPTS (Phase 1 dashboard).
- Источник требования: ROADMAP.md §15.2, §18.2.
```

---

## 7. Приложение: чек-лист выхода из Phase 2

**Источник**: `ROADMAP.md` v1.1.0 §6.6. Используется после прогона всех блоков A–F для самопроверки перед ревью архитектурным комитетом. Критерии выхода — параллельно с Phase 1 чек-листом `MVP-PROMPTS.md` §8 (Phase 1 + Phase 2 — последовательные фазы, Phase 2 не стартует до завершения Phase 1).

| # | Критерий | Где проверяется | Соответствующий блок промптов |
|---|---|---|---|
| 1 | ADR-010 Approved: latency checkpoint <2 мс в 99% случаев на staging | E-1 nightly | Блок B + E-1 |
| 2 | ADR-010: восстановление при restart корректно (snapshot + replay) | E-2 nightly | B-5, E-2 |
| 3 | ADR-010: потеря состояния при одновременном отказе Redis+PG <=5 сек в пилотной неделе | E-2 scenario 4 + manual 1 week observation | B-3, B-5, E-2 |
| 4 | ADR-010: Redis — mandatory dependency, maxmemory-policy=noeviction | manual (`redis-cli -n 1 CONFIG GET maxmemory-policy`) | A-1, B-1 |
| 5 | ADR-017 Approved: recall@5 ↑ ≥15% vs baseline (no reranker) | E-3 nightly A/B test | Блок C + E-3 |
| 6 | ADR-017: latency retrieval ↑ <100 мс over baseline (no reranker) | E-3 nightly | Блок C, E-3 |
| 7 | ADR-017: bge-reranker загружается in-process за <5 сек при старте | manual (startup log timestamps) | A-2, C-2 |
| 8 | ADR-017: RerankerRegistry с entrypoints работает, ≥3 reranker-а (bge, cohere, identity) | `python -c "from importlib.metadata import entry_points; print(list(entry_points(group='llm_client.rerankers')))"` | C-1, C-2, C-3 |
| 9 | ADR-020 Approved: recall ↑ для точных терминов ≥30% | E-4 nightly A/B test | Блок D + E-4 |
| 10 | ADR-020: latency retrieval ↑ <50% (relative to baseline vector-only) | E-4 nightly | Блок D, E-4 |
| 11 | ADR-020: BM25 index строится синхронно с vector index при индексации | E-4 BM25 indexing regression test | D-2, E-4 |
| 12 | ADR-020: hybrid retrieval default (RetrieverConfig.retrieval_strategy=HYBRID) | `python -c "from llm_client.rag.config import RetrieverConfig; print(RetrieverConfig().retrieval_strategy)"` → `RetrievalStrategy.HYBRID` | D-1 |
| 13 | Метрика идеальности: Δф=+3 capabilities (async checkpoint, reranker, hybrid retrieval), Δсложности=+2 dependencies (bge-reranker, tsvector) → Δф/Δсложности = 1.5 ≥ 1 | F-2 Grafana dashboard | F-2 |
| 14 | Документация обновлена: `ARCHITECT.md` §7 ADR-010/017/020, §8 C-2/C-6 [RESOLVED]/[PARTIALLY RESOLVED], §12 Q-5 [PARTIALLY CLOSED] | PR merged | F-1 |
| 15 | Все ADR Phase 2: Status Approved в `ARCHITECT.md` v1.2.0 | manual check | F-1 |
| 16 | Phase 1 не регрессировал: ADR-013 cancel latency <100ms, ADR-014 PII leaks = 0, расш. ADR-008 MinIO parity | Phase 1 nightly jobs (MVP-PROMPTS.md Блок F-1..F-3) — все PASS | Блоки F-1..F-3 MVP-PROMPTS (не регрессируют) |

**При невыполнении любого из п.1–4, 5–7, 9–11**: фаза продлевается на 1 sprint (`ROADMAP.md` §6.6).
**При невыполнении п.8** (RerankerRegistry): ADR-017 не может быть Approved (pluggable architecture нарушена), блокирует п.5–7.
**При невыполнении п.12** (retrieval_strategy=HYBRID default): ADR-020 не Approved, блокирует п.9–11.
**При невыполнении п.13** (метрика идеальности <1): ADR пересматривается (вероятный over-engineering, `ROADMAP.md` §13.1 — Phase 2 превышает tight 1.5, но должен ≥1).
**При невыполнении п.14–15**: документационный долг, блокирует старт Phase 3.
**При невыполнении п.16** (Phase 1 regression): критично — Phase 2 не может быть Approved если Phase 1 сломан; rollback Phase 2 changes, fix Phase 1 first.

---

## 8. Карта промптов для быстрого навигации

| ID | Промпт | Зависимости | Срок (чел-дн) |
|---|---|---|---|
| A-1 | Redis WAL configuration (расширение Phase 1) | Блок A-1 MVP (Redis) | 0.25 |
| A-2 | `bge-reranker-base` in-process ML model setup | — | 0.5 |
| A-3 | PostgreSQL tsvector column + GIN index на documents | — | 0.5 |
| B-1 | `RedisCheckpointer` (sync, TTL=24h) | A-1 | 0.5 |
| B-2 | `PostgresCheckpointer` (async batched) | — | 0.5 |
| B-3 | `RedisPostgresCheckpointer` (composite) | B-1, B-2 | 0.75 |
| B-4 | Background flusher (5s / N checkpoints) | B-2 | 0.5 |
| B-5 | Recovery protocol (snapshot + replay) | B-3, B-4 | 0.75 |
| B-6 | Latency + durability test | B-3..B-5 | 0.5 |
| C-1 | `Reranker` interface + `RerankerRegistry` (entrypoints) | — | 0.25 |
| C-2 | `BgeRerankerAdapter` (in-process cross-encoder) | A-2, C-1 | 0.75 |
| C-3 | `CohereRerankAdapter` (external API, опциональный) | C-1 | 0.5 |
| C-4 | Pipeline integration (reranker после fusion) | C-1, C-2, D-5 | 0.75 |
| C-5 | Fallback chain (Cohere → bge → identity) | C-2, C-3 | 0.25 |
| C-6 | A/B test framework (recall@5 metric) | C-4 | 0.5 |
| D-1 | `RetrieverConfig.retrieval_strategy` enum (default hybrid) | — | 0.25 |
| D-2 | `BM25IndexBuilder` (parallel with vector index) | A-3 | 0.75 |
| D-3 | PostgreSQL tsvector в documents (BM25Retriever) | A-3, D-2 | 0.5 |
| D-4 | `HybridRetriever` (vector top-20 + BM25 top-20) | D-1, D-3 | 0.75 |
| D-5 | RRF fusion (top-50) → reranker (top-5) | C-4, D-4 | 0.5 |
| D-6 | A/B test для exact-term recall (sku/error/employee_id) | D-5 | 0.5 |
| E-1 | Latency checkpoint test (<2 мс в 99%) | Блок B, A-1..A-3 | 0.25 |
| E-2 | Restart recovery test (4 scenarios) | B-5 | 0.5 |
| E-3 | Recall@5 A/B test (bge vs baseline) | Блок C | 0.25 |
| E-4 | Exact-term recall A/B test (hybrid vs vector-only) | Блок D | 0.25 |
| E-5 | Phase 2 CI pipeline (расширение Phase 1 CI) | Блоки A-D, E-1..E-4 | 0.75 |
| F-1 | `ARCHITECT.md` update (ADR-010/017/020, C-2/C-6 resolved) | Блоки B, C, D completed | 0.25 |
| F-2 | Grafana dashboard Phase 2 control point (ratio 1.5) | — | 0.25 |
| **Итого** | **27 промптов** | | **~14 чел-дн ADR-работы + 2.5 чел-дн тесты/CI/доки = 16.5 чел-дн** |

**Параллелизация (2 разработчика)** (`ROADMAP.md` §11.2):

- **Дев 1 (Backend/Orchestration)**: A-1 → B-1 → B-2 → B-3 → B-4 → B-5 → B-6 → E-1 → E-2 → F-1 (orchestration часть)
  - Срок: 5 чел-дн ADR-010 + 1.5 чел-дн tests/docs = **6.5 чел-дн**
- **Дев 2 (Backend/RAG)**: A-2 → C-1 → C-2 → C-3 → A-3 → D-1 → D-2 → D-3 → D-4 → D-5 → C-4 → C-5 → C-6 → D-6 → E-3 → E-4 → F-1 (RAG часть) → F-2
  - Срок: 4 чел-дн ADR-017 + 5 чел-дн ADR-020 + 1.5 чел-дн tests/docs = **10.5 чел-дн**
- **Параллельные (стартуют сразу, не блокируют critical path)**: A-3 (1 разработчик), E-5 (DevOps).

**Critical path**: A-1 → B-1..B-6 (6 промптов, 3.5 чел-дн) → E-1, E-2 (1 чел-дн) → F-1 (0.25 чел-дн) = **4.75 чел-дн** для Dev 1.

**Суммарная оценка Phase 2**: 14 чел-дн ADR-работы (`ROADMAP.md` §6.2: 5 + 4 + 5 = 14) + 2.5 чел-дн тесты/CI/доки (Блоки E, F) = **16.5 чел-дн** total. С параллелизацией 2 разработчиков — **9–10 рабочих дней** (Dev 1 critical path 4.75 чел-дн + Dev 2 critical path 10.5 чел-дн, max = 10.5 чел-дн / 2 = 5.25 рабочих дня = 1 sprint).

**Зависимости между блоками** (см. диаграмму в §0):
- Блок A — стартует первым, все 3 подзадачи (A-1, A-2, A-3) параллельны.
- Блок B — зависит от A-1 (Redis WAL).
- Блок C — зависит от A-2 (bge-reranker).
- Блок D — зависит от A-3 (tsvector) и C-4 (reranker для fusion top-5).
- Блок E — зависит от Блоков B, C, D.
- Блок F — зависит от Блоков B, C, D (после их завершения).

**Переход к Phase 3 (Beta)**: Phase 2 → Phase 3 критерий (`ROADMAP.md` §3.2): все пункты чек-листа §7 выполнены (особенно п.13 — метрика идеальности ≥1, п.14 — документация обновлена). Phase 3 добавляет ADR-011 (semantic cache — закрывает C-6 cost-составляющую), ADR-015 (cost-aware router), ADR-016 (tool capability adapter), ADR-004 ускорение (MCP server mode preview). См. `BETA-PROMPTS.md` (драфт, создать в Phase 2 конце).

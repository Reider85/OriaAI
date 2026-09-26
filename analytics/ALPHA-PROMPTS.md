# ALPHA-PROMPTS.md — Промпты для этапа Alpha (Phase 2)

| Атрибут | Значение |
|---|---|
| Версия документа | 1.1.0 |
| Дата | 2026-09-26 |
| Источники | `ROADMAP.md` v1.2.0 §6 (Phase 2 — Alpha), §5.2.5/§5.8 (AG-составляющая Phase 1 — предусловие), §12, §15.2, §18.1; `TRIZ-ANALYSIS.md` v1.0.0 §5.2 (C-2), §6.1 (C-6), §8.1 (стандарт 1.1.5), §10 (матрица противоречий), §11 (драфты ADR-010/017/020); `ARCHITECT.md` v1.2.0 §4 (agent-service container), §5.1 (Phase 1 Update — FastAPI+SSE), §5.2.2 (Orchestration), §5.2.3 (LLM Provider), §5.2.4 (Tool Layer), §5.2.5 (RAG Layer), §6 (`agent_checkpoints`/`documents` таблицы), §7 ADR-001/003/005/006/007/008/013/014; `BACKLOG.md` v1.1.0 §3.4 (AG-0..AG-7), §3.2 (UI-0..UI-7 сводная таблица), §5.2 (критерии выхода AG Phase 1); `AG-PROMPTS.md` v1.0.0 §1..§5 (AG-0..AG-4 — предусловие для H-1/H-2); `UI-PROMPTS.md` v1.1.0 §1..§11 (UI-0..UI-3 — предусловие для G-1..G-4) |
| Этап | Phase 2 — Alpha (14 чел-дн ADR-работы + 5 чел-дн AG-расширения (AG-5/AG-6) + 1.5 чел-дн UI-расширения (G-1..G-4) + 2.5 чел-дн тесты/CI/доки = 23 чел-дн) |
| ADR в области | ADR-010 (Async Checkpoint Write-Behind Log), ADR-017 (Reranker Model in RAG), ADR-020 (Hybrid BM25+Vector RAG default) |
| AG-расширения в области | AG-5 (`web_search` tool via Tavily, формализация `BACKLOG.md` v1.1.0 §3.4 — применяется ADR-005 Tool Layer), AG-6 (`rag_query` tool + base RAG pipeline + `rag_retriever` нода, формализация `BACKLOG.md` v1.1.0 §3.4 — применяется ADR-003 VectorStoreFactory, расширяется ADR-017/020 в этом же Phase 2) |
| UI-расширения в области | G-1 (tool-call preview component), G-2 (RAG citations panel), G-3 (web search results panel), G-4 (settings panel extension: tools on/off, retrieval_strategy, reranker choice) — расширяют UI-0..UI-3 из `UI-PROMPTS.md` v1.1.0 для отображения результатов AG-5/AG-6 и настроек ADR-017/020 |
| Резолвит противоречия | C-2 (PG checkpoint vs latency) — полностью; C-6 (long RAG context vs cost) — полностью (вместе ADR-017 + ADR-020; ADR-011 в Phase 3 закроет cost-составляющую) |
| Целевой LLM | Универсальные (Cursor / Copilot / Claude Code / ChatGPT) |
| Гранулярность | Микро-промпты (1 промпт = 1 файл / 1 класс / 1 подзадача) |
| Предусловие | Phase 1 завершена полностью (`ROADMAP.md` v1.2.0 §5.6, п.1–11): UI-0..UI-3 Approved (`UI-PROMPTS.md` v1.1.0), AG-0..AG-4 Approved (`AG-PROMPTS.md` v1.0.0) — `python -m llm_client.agent` поднимает FastAPI на :8000, `build_agent_graph(llm, token, tools=[file_export])` возвращает compiled graph с `planner` + `final_answer` + `tool_executor` нодами, SSE event protocol эмитит token/metadata/cancelled/error/done/artifact_ready, `file_export` tool сохраняет артефакты в S3 (UI-1 download buttons активны). Redis (Блок A-1 `MVP-PROMPTS`), PostgreSQL, `S3CompatibleStorage` (расш. ADR-008), ADR-013 (cancel), ADR-014 (DualStreamLogger), `UIClient` abstraction (UI-2) — все Approved. ARCHITECT.md v1.2.0 (§5.1 уточнена: in-process опция не используется, AG-0 фиксирует FastAPI + SSE как единственную MVP-реализацию). |
| Связанные документы | `MVP-PROMPTS.md` v1.0.0 (контракты Phase 1, не переопределяются), `UI-PROMPTS.md` v1.1.0 (UI-0..UI-3 — предусловие для Блока G), `AG-PROMPTS.md` v1.0.0 (AG-0..AG-4 — предусловие для Блока H), `BACKLOG.md` v1.1.0 (AG-5/AG-6 формализованы как Phase 2 работы, §3.4 + §5.3 критерии), `ROADMAP.md` v1.2.0 (Phase 2 = 19 чел-дн ADR+AG + 2.5 чел-дн tests/CI/docs = 21.5 чел-дн без UI-расширений), `ARCHITECT.md` v1.2.0, `TRIZ-ANALYSIS.md` v1.0.0 |

---

## 0. Как пользоваться документом

Каждый промпт — самостоятельный блок, огороженный ` ``` `-код-блоком, готовый к копи-пасту в любой код-ассистент. Промпты сгруппированы в **восемь блоков A–H**, идущих в порядке зависимостей:

```
A. Инфра ──┬──→ B. ADR-010 (RedisPostgresCheckpointer) ──┐
           │                                              │
           ├──→ C. ADR-017 (Reranker) ─────────────────────┤
           │                                              ├──→ E. Тесты/CI ──→ F. Документация
           └──→ D. ADR-020 (Hybrid BM25+Vector RAG) ───────┤
                                                          │
            ┌───────────────────────────────────────────────┘
            │
            │  D-5 зависит от C-4 (reranker применяется после fusion)
            │
            ├──→ G. UI-расширения Phase 2 (G-1 tool-call preview, G-2 RAG citations,
            │    G-3 web search results, G-4 settings panel) — зависит от H-1/H-2
            │    (отображают результаты AG-5/AG-6 + настраивают ADR-017/020)
            │
            └──→ H. AG-расширения Phase 2 (H-1=AG-5 web_search via Tavily,
                 H-2=AG-6 rag_query + base RAG pipeline + rag_retriever нода,
                 H-3 graph integration (bind_tools + tool_executor extension),
                 H-4 SSE event protocol extension (event: tool_call / tool_result /
                 retrieved_docs)) — зависит от AG-1 (Phase 1 graph), AG-3 (SSE)
                 и расширяется Блоками C (reranker) и D (hybrid retrieval)
```

**Конвенции** (наследуются из `MVP-PROMPTS.md` §0, `AG-PROMPTS.md` §0, `UI-PROMPTS.md` §0):

- Имена классов, методов, эндпоинтов — на английском (как в `ARCHITECT.md` v1.2.0).
- Имена ADR и противоречий — в формате `ADR-010`, `C-2` (как в `TRIZ-ANALYSIS.md` §10).
- Имена AG-работ — в формате `AG-5`, `AG-6` (как в `BACKLOG.md` v1.1.0 §3.4 и `ROADMAP.md` v1.2.0 §6.2).
- Имена UI-работ — в формате `UI-1` (как в `BACKLOG.md` v1.1.0 §3.2 и `UI-PROMPTS.md` v1.1.0).
- Раздел `Definition of Done` — конкретные измеримые критерии готовности.
- Раздел `Антипаттерны` — что LLM НЕ должен делать; если предложит — отбраковывать.
- Раздел `Связанные ADR` — какие ADR затрагивает (не ломает / упраздняет / требует).
- Все env vars / class names / interface signatures — **продолжают** контракты Phase 1 (включая `AG-PROMPTS.md` v1.0.0); не переопределяют, не дублируют. Существующие `BaseCheckpointSaver` (LangGraph), `VectorStoreFactory`/`VectorStoreRegistry` (ADR-003 / драфт ADR-009), `RetrieverConfig` (`ARCHITECT.md` §5.2.5), `PostgresSaver` (ADR-001), `agent_checkpoints` / `documents` таблицы (`ARCHITECT.md` §6), `LLMProviderFactory` (AG-2), `build_agent_graph(llm, token, tools)` (AG-1), SSE event protocol (AG-3), `file_export` tool (AG-4), `UIClient` interface + `StreamlitClient` (UI-2), `@st.fragment` chat/sidebar (UI-3) — **не переопределяются**; Phase 2 их расширяет.

Полный прогон блоков A→H занимает 14 чел-дн ADR-работы (`ROADMAP.md` v1.2.0 §6.2.1–6.2.3) + 5 чел-дн AG-расширения (§6.2.4 AG-5 + §6.2.5 AG-6, `BACKLOG.md` v1.1.0 §3.4) + 1.5 чел-дн UI-расширения (Блок G, new в v1.1.0 — не входит в оценку `ROADMAP.md` v1.2.0, добавлен в ALPHA-PROMPTS.md v1.1.0 как необходимое расширение UI-0..UI-3 для отображения результатов AG-5/AG-6) + 2.5 чел-дн (тесты/CI/доки) = **23 чел-дн total** (vs 16.5 чел-дн в v1.0.0; delta = +6.5 чел-дн: +5 AG-5/AG-6 + 1.5 UI). Параллелизация (см. §10) — 11–13 чел-дн при команде из 3 разработчиков (2 backend + 1 frontend). Критерии выхода из Phase 2 — в Приложении §9.

> **Замечание о UI-расширениях Блока G**: `ROADMAP.md` v1.2.0 не выделяет отдельную оценку на UI-работы Phase 2 — UI-0..UI-3 из Phase 1 формируют базовый чат, а следующие UI-работы (UI-4 `SessionStore`/`RedisSessionStore`, UI-5 `ChainlitClient`, UI-6 `FastAPIClient`, UI-7 Embed mode) относятся к Phase 5/6 (см. `BACKLOG.md` v1.1.0 §3.2). Однако с добавлением AG-5/AG-6 (внешние инструменты `web_search`/`rag_query`, эмитящие `event: tool_call` / `event: tool_result` / `event: retrieved_docs`) UI-1 из Phase 1 (sidebar + download buttons + status badge + PII badge) недостаточен — пользователь не видит, какие инструменты вызвал агент и какие результаты получил. Блок G (4 промпта, 1.5 чел-дн) закрывает этот пробел: расширяет `UIClient` interface и `StreamlitClient` реализацию из UI-2/UI-0 минимальными компонентами для отображения tool-call previews, RAG citations, web search results и настроек retrieval. Это не вводит новых ADR и не нарушает ADR-002 (Streamlit) — расширяет существующий интерфейс. Метрика идеальности Phase 2 учитывается отдельно (см. §9 п.13–14).

**Фазировка противоречий** (из `TRIZ-ANALYSIS.md` §10): Phase 2 резолвит C-2 (полностью через ADR-010) и C-6 (полностью через ADR-017 + ADR-020 — качественная составляющая retrieval; cost-составляющая C-6 остаётся для ADR-011 в Phase 3). AG-5/AG-6 (Блок H) — применение уже Approved ADR-005 (Tool Layer) и ADR-003 (VectorStoreFactory) на конкретных инструментах, не вводят новых противоречий. Связанные законы развития ТРИЗ (§4 `TRIZ-ANALYSIS.md`): закон 4.3 (согласование ритмики частей системы) — ADR-010 развязывает ритмику node-execution и persistence; стандарт 1.1.5 (введение второго поля в веполь) — ADR-020 вводит BM25 как второе поле retrieval; стандарт 2.2.2 (переход к более динамичной веполи) — ADR-017 вводит cross-encoder как более сильное поле переранжировки. Принцип 25 (самообслуживание) — AG-5 использует внешний API Tavily, но результат (snippets) кэшируется в `messages` state, не требует повторных вызовов; принцип 3 (местное качество) — AG-6 использует специализированный `rag_retriever` ноду, не general-purpose `tool_executor`, для RAG-pipeline (хотя инструмент exposed to LLM через `bind_tools` как обычный `@tool`); принцип 17 (другое измерение) — UI-расширения Блока G выносят отображение tool-результатов в отдельный фрагмент UI (не в основном chat area), не ломая существующий `chat_component`.

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

## 5. Блок G. UI-расширения Phase 2

**Источник**: `UI-PROMPTS.md` v1.1.0 §1..§11 (UI-0..UI-3 — предусловие), `BACKLOG.md` v1.1.0 §3.2 (UI-0..UI-7 сводная таблица — UI-4..UI-7 относятся к Phase 5/6, в Phase 2 их нет), `ARCHITECT.md` v1.2.0 §5.2.1 (Presentation Layer) и §5.2.4 (Tool Layer — какие tools у AG-5/AG-6), `AG-PROMPTS.md` v1.0.0 §4 (AG-3 SSE event protocol — источник событий `event: artifact_ready` для UI-1 download buttons, в Phase 2 добавляются `event: tool_call`/`event: tool_result`/`event: retrieved_docs`).

**Назначение**: Phase 1 закрывает минимальный chat MVP — UI-0 (scaffold), UI-1 (sidebar + download buttons + status badge + PII badge), UI-2 (`UIClient` abstraction + `StreamlitClient`), UI-3 (`@st.fragment` для chat/sidebar). Phase 2 добавляет AG-5 (`web_search`) и AG-6 (`rag_query`) — инструменты, которые агент вызывает в середине граф-цикла, и которые эмитят новые SSE-события (`event: tool_call`, `event: tool_result`, `event: retrieved_docs` — см. Блок H-4). UI-1 из Phase 1 не имеет компонентов для отображения этих событий — пользователь видит только финальный токен-стрим, не видя, что агент обратился к веб-поиску или RAG. Без Блока G AG-5/AG-6 формально работают, но UX деградирует — пользователь не понимает, откуда агент взял ответ (не видно ни цитат, ни веб-ссылок, ни инструментов). Это не нарушает ADR-002 (Streamlit) и не вводит новые ADR — Блок G расширяет `UIClient` interface и `StreamlitClient` реализацию минимальными новыми методами/компонентами, продолжая контракты UI-0..UI-3.

**Связь с архитектурой**: `ARCHITECT.md` v1.2.0 §5.2.1 таблица «Presentation Layer» упоминает 5 компонентов: `chat_component`, `session_history`, `download_button`, `settings_panel`, `auth_gate`. В Phase 1 реализованы `chat_component` (UI-0/UI-3), `session_history` (UI-1 sidebar), `download_button` (UI-1 через `render_artifact_buttons` в `src/llm_client/ui/render.py`). Phase 2 добавляет `settings_panel` (G-4) и расширяет `chat_component` новыми подкомпонентами: `tool_call_preview` (G-1), `rag_citations` (G-2), `web_search_results` (G-3). `auth_gate` — Phase 5 (расширение ADR-018).

**Принципы ТРИЗ**: 17 (переход в другое измерение — tool-результаты рендерятся в отдельном фрагменте UI, не в основном chat area), 3 (местное качество — каждый компонент специализирован под свой тип tool-результата: RAG citations != web search results), 1 (сегментация — `UIClient` interface расщепляется на основной chat и tool-results sub-views), 16 (частичное/избыточное действие — interface расширяется, но `StreamlitClient` остаётся единственной имплементацией; `ChainlitClient` добавится в Phase 5, расширяя тот же interface).

**Оценка и параллелизация**: 4 промпта, 1.5 чел-дн total. Критический путь: G-1 (0.25) → G-2 (0.5) и G-3 (0.25) параллельно → G-4 (0.5). Один Frontend-разработчик (Дев 3 в §10). Не входит в оценку `ROADMAP.md` v1.2.0 (Phase 2 = 19 чел-дн ADR+AG без UI) — добавлен в ALPHA-PROMPTS.md v1.1.0 как необходимое расширение. Метрика идеальности Phase 2: G-1..G-4 добавляют +1 capability (UX tool-transparency) при +0 новых зависимостей — улучшает ratio, не нарушает порог.

### G-1. Tool-call preview component (расширение `UIClient` + `StreamlitClient`)

```
Ты — Frontend-разработчик LLM Client. Расширь `UIClient` interface и
`StreamlitClient` реализацию из UI-2/UI-PROMPTS.md §3 для отображения
tool-call previews: когда агент вызывает web_search (Блок H-1) или
rag_query (Блок H-2), UI должен показать collapsible-панель с именем
инструмента и его args ДО того, как агент получит результат.

Контекст:
- UI-2 (UI-PROMPTS.md §3, уже реализован в Phase 1) фиксирует `UIClient`
  interface с 4 методами: render_message, render_artifact, stream_token,
  handle_user_input. Этого достаточно для file_export (AG-4) — результат
  рендерится через render_artifact (download button). Но web_search и
  rag_query — не артефакты, а tool_calls с args и results. Нужен новый
  метод.
- AG-3 SSE event protocol (AG-PROMPTS.md §4, реализован в Phase 1)
  эмитит события: token, metadata, artifact_ready, cancelled, error,
  done. Блок H-4 добавляет: tool_call, tool_result, retrieved_docs.
  UI должен уметь их парсить и рендерить.
- ARCHITECT.md v1.2.0 §5.2.1 (строка 351) упоминает `chat_component`
  с ответственностью "Рендеринг сообщений, streaming tokens, tool-call
  previews" — но в Phase 1 tool-call previews не реализованы (только
  токены и артефакты). G-1 их добавляет.
- ТРИЗ-принцип 17 (переход в другое измерение): tool-call preview
  рендерится в отдельном `@st.fragment`-блоке внутри chat_message, не
  вмешиваясь в токен-стрим. Это сохраняет latency streaming (UI-3 benefit)
  и даёт пользователю контекст "что делает агент" без пере-рендера
  всего chat.
- ТРИЗ-принцип 3 (местное качество): каждый preview — отдельный
  компонент под свой tool (web_search — показывает query + max_results;
  rag_query — показывает query + retrieval_strategy; file_export —
  показывает content preview (truncated) + format). Не общий
  tool-call-panel, а специализированные под tool-type.

Задача:
1. Расширь `UIClient` interface в `src/llm_client/ui/client.py`:
   ```python
   from abc import ABC, abstractmethod
   from typing import Any, Literal

   class UIClient(ABC):
       # Существующие 4 метода (UI-2) — без изменений:
       @abstractmethod
       def render_message(self, role, content, metadata=None): ...
       @abstractmethod
       def render_artifact(self, artifact: dict): ...
       @abstractmethod
       def stream_token(self, token: str): ...
       @abstractmethod
       def handle_user_input(self) -> str | None: ...

       # Новый метод (G-1):
       @abstractmethod
       def render_tool_call(self, tool_name: str, args: dict[str, Any],
                             status: Literal["running", "done", "error"]
                             = "running",
                             result_preview: dict[str, Any] | None = None
                             ) -> None:
           '''Рендерит collapsible-панель tool-call preview внутри
           текущего assistant chat_message.

           Args:
               tool_name: "web_search" | "rag_query" | "file_export" |
                          "mcp_call" (Phase 4). Не локализовать —
                          отображать как есть (developer-facing).
               args: dict с аргументами tool_call (query, max_results,
                     format, filename и т.д.). НЕ логировать content
                     аргумент file_export — truncated до 200 символов
                     с "..." (privacy: потенциально PII).
               status: "running" (спиннер), "done" (зелёная галочка),
                       "error" (красный бейдж).
               result_preview: dict с кратким preview результата —
                               {snippet_count: int} для web_search,
                               {chunk_count: int, top_score: float} для
                               rag_query, {artifact_id, format, filename}
                               для file_export. None при status="running".
           '''
   ```

2. Имплементируй в `src/llm_client/ui/streamlit_client.py`:
   ```python
   class StreamlitClient(UIClient):
       # ... существующие методы без изменений ...

       def render_tool_call(self, tool_name, args, status="running",
                            result_preview=None):
           import streamlit as st
           # Фильтрация PII в args для file_export content:
           display_args = dict(args)
           if tool_name == "file_export" and "content" in display_args:
               content = str(display_args["content"])
               display_args["content"] = (content[:200] + "...") \
                   if len(content) > 200 else content

           # Collapsible-панель внутри текущего chat_message:
           with st.expander(f"🔧 {tool_name} — {status}", expanded=False):
               st.json(display_args)
               if result_preview is not None:
                   st.caption("Result preview")
                   st.json(result_preview)
               if status == "running":
                   st.spinner("Running...")
               elif status == "done":
                   st.success("Done")
               elif status == "error":
                   st.error("Failed")
   ```

3. В `src/llm_client/ui/render.py` добавь helper для парсинга SSE events
   `tool_call` и `tool_result` (Блок H-4):
   ```python
   def handle_tool_event(event_type: str, data: dict,
                          client: UIClient,
                          pending_tool_calls: dict[str, dict]) -> None:
       '''Обновляет state pending tool_calls и триггерит ре-рендер
       preview при поступлении tool_call/tool_result.

       Args:
           event_type: "tool_call" | "tool_result" | "retrieved_docs".
           data: SSE event data (Блок H-4 contract).
           client: UIClient instance (StreamlitClient).
           pending_tool_calls: dict[tool_call_id, {tool_name, args,
               status, result_preview}] в st.session_state.
       '''
       if event_type == "tool_call":
           pending_tool_calls[data["tool_call_id"]] = {
               "tool_name": data["tool_name"],
               "args": data["args"],
               "status": "running",
               "result_preview": None,
           }
           client.render_tool_call(
               tool_name=data["tool_name"],
               args=data["args"],
               status="running",
           )
       elif event_type == "tool_result":
           tc_id = data["tool_call_id"]
           if tc_id in pending_tool_calls:
               pending_tool_calls[tc_id]["status"] = "done"
               pending_tool_calls[tc_id]["result_preview"] = (
                   data.get("preview") or {}
               )
               tc = pending_tool_calls[tc_id]
               client.render_tool_call(
                   tool_name=tc["tool_name"],
                   args=tc["args"],
                   status="done",
                   result_preview=tc["result_preview"],
               )
       elif event_type == "retrieved_docs":
           # Для rag_query — расширенный preview с цитатами (Блок G-2):
           tc_id = data["tool_call_id"]
           if tc_id in pending_tool_calls:
               pending_tool_calls[tc_id]["result_preview"] = {
                   "chunk_count": data.get("chunk_count", 0),
                   "top_score": data.get("top_score", 0.0),
                   "source_uris": data.get("source_uris", []),
               }
               tc = pending_tool_calls[tc_id]
               client.render_tool_call(
                   tool_name=tc["tool_name"],
                   args=tc["args"],
                   status="done",
                   result_preview=tc["result_preview"],
               )
               # G-2 дополнительно рендерит citations panel:
               render_rag_citations(data.get("chunks", []))
   ```

4. Обнови парсер SSE в `src/llm_client/ui/chat.py` `iter_sse_events` —
   добавь case для event_type "tool_call" / "tool_result" /
   "retrieved_docs" (Блок H-4 contract). Сейчас парсер понимает только
   token/metadata/artifact_ready/cancelled/error/done (AG-3 из Phase 1).

5. Оберни render_tool_call в `@st.fragment` (UI-3 pattern) для изоляции
   ре-рендера от основного chat area:
   ```python
   @st.fragment
   def _render_tool_call_fragment(tool_name, args, status, result_preview):
       # ... реализация из п.2 ...
   ```
   Это гарантирует: стриминг токенов основного ответа не пере-рендерит
   tool-call previews; обратное — тоже.

6. Тесты в `tests/unit/test_ui_render.py` (расширь существующий файл):
   - `test_render_tool_call_running` — StreamlitClient mock, проверяет
     expander с label "🔧 web_search — running" и args внутри.
   - `test_render_tool_call_done` — status="done", result_preview
     отображается, "Done" success message.
   - `test_render_tool_call_error` — status="error", error badge.
   - `test_file_export_content_truncation` — args["content"] > 200
     символов → отображается truncated.
   - `test_handle_tool_event_tool_call` — pending_tool_calls обновляется.
   - `test_handle_tool_event_tool_result` — status меняется на "done",
     result_preview добавляется.
   - `test_handle_tool_event_retrieved_docs` — chunk_count, top_score
     отображаются; render_rag_citations вызывается.
   - Integration: полный flow SSE → handle_tool_event → render_tool_call
     для всех 3 events (tool_call, tool_result, retrieved_docs).

Definition of Done:
- `UIClient` interface в `src/llm_client/ui/client.py` содержит
  `render_tool_call` abstractmethod.
- `StreamlitClient` в `src/llm_client/ui/streamlit_client.py`
  имплементирует `render_tool_call` с collapsible expander.
- `src/llm_client/ui/render.py` содержит `handle_tool_event` helper.
- `src/llm_client/ui/chat.py` SSE parser понимает event types
  "tool_call" / "tool_result" / "retrieved_docs" (Блок H-4 contract).
- `tests/unit/test_ui_render.py` — 7+ новых тестов зелёные.
- Существующие тесты `tests/unit/test_ui_render.py`,
  `tests/unit/test_ui_streamlit_client.py` (Phase 1) — не регрессируют.
- Manual test: prompt "search web for python asyncio" → виден
  expander "🔧 web_search — running" → через ~2 сек "🔧 web_search —
  done" с preview {snippet_count: 5}.

Антипаттерны:
- НЕ добавляй в `UIClient` методы под каждый tool-type отдельно
  (render_web_search_call, render_rag_query_call, render_file_export_call)
  — это god-object. Один `render_tool_call(tool_name, args, status,
  result_preview)` с switch внутри StreamlitClient-имплементации.
- НЕ логируй content аргумент file_export в UI без truncation —
  потенциально PII. Max 200 символов, всегда с "..." suffix.
- НЕ показывай полный result (сниппеты, чанки) в tool_call preview —
  это делает G-2 (RAG citations) и G-3 (web search results). Preview —
  только краткая summary (count, top_score, source_uris).
- НЕ пере-рендерь весь chat_message при tool_call event — только
  @st.fragment с tool_call preview. Иначе ломается UI-3 streaming
  latency.
- НЕ хардкодь tool_name="web_search" — поддержи любой (mcp_call в
  Phase 4, будущие tools). Switch внутри StreamlitClient для
  tool-specific rendering, но interface общий.
- НЕ локализуй tool_name в UI — "web_search" отображается как есть
  (developer-facing, как в ADR-005). Локализуются только status-labels
  ("running" → "Выполняется..." — опционально, в Phase 2-en оставляем
  английский для consistency с ADR-005).
- НЕ добавляй кнопку "Cancel tool" — cancel всего агента уже есть
  (UI-1 status badge + MVP-PROMPTS C-5 JS watcher). Granular tool
  cancel — Phase 4 (mcp_invoker с human_review нодой).

Связанные ADR:
- Расширяет: UI-2 (UIClient interface +1 method), AG-3 (SSE event
  protocol +3 events — tool_call/tool_result/retrieved_docs, см. Блок
  H-4).
- Применяет: ADR-002 (Streamlit 1.40+), ADR-007 (SSE), UI-3 (@st.fragment
  для изоляции re-runs).
- Не затрагивает: ADR-013 (cancel endpoint), ADR-014 (PII metadata —
  truncation applied to file_export content).
- Разблокирует: G-2 (rag citations — handle_tool_event для
  retrieved_docs), G-3 (web search results — handle_tool_event для
  tool_result от web_search).
```

### G-2. RAG citations panel (компонент для отображения retrieved chunks)

```
Ты — Frontend-разработчик LLM Client. Создай компонент для отображения
RAG citations: когда агент вызывает rag_query (Блок H-2) и эмитит
event: retrieved_docs (Блок H-4), UI должен показать список чанков с
источниками (source_uri, title, page, content_preview, score). Это
помогает пользователю понять, откуда агент взял информацию в финальном
ответе, и проверить факты.

Контекст:
- AG-6 (Блок H-2) — rag_query tool + rag_retriever нода в graph. Tool
  возвращает list[dict] с чанками. Блок H-4 эмитит SSE event
  "retrieved_docs" с fields: tool_call_id, chunk_count, top_score,
  source_uris (list), chunks (list[{source_uri, title, page,
  content_preview, score}]).
- UI-1 (Phase 1) — sidebar + download buttons + status + PII badge.
  Не покрывает RAG citations.
- ARCHITECT.md v1.2.0 §5.2.5 (RAG Layer) — pipeline возвращает top-5
  чанков после reranker (ADR-017). UI должен показать все 5 (не только
  top-1), чтобы пользователь мог сравнить.
- ТРИЗ-принцип 1 (сегментация): citations — отдельная панель, не часть
  основного chat_message. Открывается по клику на "Показать источники"
  или автоматически — на ваше усмотрение (default: collapsible).
- ТРИЗ-принцип 3 (местное качество): каждый chunk — отдельная карточка с
  source_uri (кликабельная ссылка), title, page (если есть), truncated
  content (200 символов), score (как progress bar, не как число — для
  UX). Не общий list, а визуально структурированные cards.

Задача:
1. Создай функцию `render_rag_citations(chunks: list[dict]) -> None`
   в `src/llm_client/ui/render.py` (расширяет существующий файл из
   Phase 1):
   ```python
   def render_rag_citations(chunks: list[dict]) -> None:
       '''Рендерит RAG citations panel — список чанков с источниками,
       заголовками, truncated content, score. Collapsible по умолчанию.

       Args:
           chunks: list of dict с fields {source_uri, title, page,
                   content_preview, score}. Score в [0, 1] — cosine
                   similarity или reranker score (ADR-017).
       '''
       import streamlit as st

       if not chunks:
           return

       # Header — clickable, collapsed по умолчанию:
       with st.expander(
           f"📚 RAG citations ({len(chunks)} chunks)",
           expanded=False,
       ):
           for i, chunk in enumerate(chunks, 1):
               _render_citation_card(i, chunk)

   def _render_citation_card(index: int, chunk: dict) -> None:
       import streamlit as st

       # Title с source_uri как кликабельная ссылка:
       title = chunk.get("title") or chunk.get("source_uri") or f"Chunk {index}"
       source_uri = chunk.get("source_uri", "")
       page = chunk.get("page")
       score = float(chunk.get("score", 0.0))

       st.markdown(f"**{index}. [{title}]({source_uri})**")

       # Meta-line: source + page:
       meta_parts = [f"📎 {source_uri}"]
       if page is not None:
           meta_parts.append(f"📄 p.{page}")
       st.caption(" · ".join(meta_parts))

       # Score как progress bar (не как число):
       st.progress(score, text=f"Relevance: {score:.2f}")

       # Content preview (truncated, 200 char):
       content = (chunk.get("content_preview") or "")[:200]
       if len(chunk.get("content_preview", "")) > 200:
           content += "..."
       st.markdown(content)

       st.divider()
   ```

2. Интегрируй в handle_tool_event (G-1) — при event_type="retrieved_docs"
   вызывает render_rag_citations(data["chunks"]).
   Уже сделано в G-1 п.3 — оставь как есть, эта функция — реализация
   хелпера.

3. Оберни в @st.fragment (UI-3 pattern):
   ```python
   import streamlit as st

   @st.fragment
   def _render_rag_citations_fragment(chunks: list[dict]) -> None:
       render_rag_citations(chunks)
   ```
   Вызывай _render_rag_citations_fragment из handle_tool_event. Это
   гарантирует: пере-рендер citations panel не вызывает пере-рендер
   основного chat area (стриминг токенов продолжается без lag).

4. Тесты в `tests/unit/test_ui_render.py` (расширь):
   - `test_render_rag_citations_empty` — chunks=[] → ничего не рендерится.
   - `test_render_rag_citations_one_chunk` — 1 chunk, card с title,
     source_uri, page, progress bar, content_preview.
   - `test_render_rag_citations_many_chunks` — 5 chunks (типовой reranker
     top-5), все отображаются, divider между ними.
   - `test_render_rag_citations_long_content` — content_preview > 200
     символов → truncated + "...".
   - `test_render_rag_citations_missing_fields` — chunk без title (использует
     source_uri), без page (скрывает), без score (progress bar = 0.0).
   - Integration: handle_tool_event("retrieved_docs", data, client,
     pending) → render_rag_citations вызывается с data["chunks"].

Definition of Done:
- `render_rag_citations(chunks)` function в `src/llm_client/ui/render.py`.
- `_render_citation_card(index, chunk)` helper.
- @st.fragment обёртка для изоляции re-runs.
- 6+ новых тестов зелёные.
- Manual test: prompt "найди в документации по Python asyncio" →
  rag_query tool_call → event: retrieved_docs → citations panel с
  5 чанками, source_uri кликабельны, score progress bars отображаются.
- Существующие тесты test_ui_render.py — не регрессируют.

Антипаттерны:
- НЕ показывай полный content чанка — может быть PII или IP. Max 200
  символов, всегда с "..." suffix если длиннее.
- НЕ показывай raw score как float — только как progress bar с
  label "Relevance: 0.85". UX-friendly, не требует от пользователя
  знания cosine similarity thresholds.
- НЕ группируй все chunks в один блок text — индивидуальные cards с
  divider. Пользователь может сравнить источники.
- НЕ хардкодь "5 chunks" — len(chunks) переменный (reranker может
  вернуть 3, 5, 8 — зависит от RetrieverConfig).
- НЕ добавляй кнопку "Open in new tab" — source_uri уже кликабельная
  ссылка (markdown `[title](source_uri)`).
- НЕ эмитить новые SSE events из UI — UI только слушает. Citations
  panel — pure render, не интерактивная (кроме раскрытия/сворачивания).
- НЕ показывай chunk_id, content_hash или другие технические fields —
  только user-facing: title, source_uri, page, content_preview, score.
- НЕ путай citations с artifact_ready (download button из UI-1) — это
  разные сущности: artifact = файл для скачивания; citation = источник
  информации в ответе.

Связанные ADR:
- Расширяет: UI-1 (sidebar + download + status + PII — добавляется 5-й
  элемент: citations panel), UI-3 (@st.fragment для citations).
- Применяет: ADR-017 (reranker score — отображается как progress bar),
  ADR-020 (hybrid retrieval — chunks могут прийти из vector или BM25
  path, UI их не различает, только score), расш. ADR-008 (source_uri
  для документов в S3 — кликабельная ссылка).
- Зависит от: G-1 (handle_tool_event для retrieved_docs), H-2 (AG-6
  rag_query tool — источник chunks), H-4 (SSE event: retrieved_docs —
  источник события).
- Не затрагивает: ADR-013 (cancel), ADR-014 (PII — в chunks не
  попадает, meta-filtering на уровне rag_retriever ноды).
```

### G-3. Web search results panel (компонент для отображения Tavily results)

```
Ты — Frontend-разработчик LLM Client. Создай компонент для отображения
web search results: когда агент вызывает web_search (Блок H-1) и
эмитит event: tool_result (Блок H-4), UI должен показать список
результатов с title, url, snippet. Это помогает пользователю понять,
какие веб-источники использовал агент в финальном ответе.

Контекст:
- AG-5 (Блок H-1) — web_search tool via Tavily API. Tool возвращает
  list[dict] с results: [{title, url, snippet, score?}]. Блок H-4
  эмитит event: tool_result с fields: tool_call_id, tool_name="web_search",
  preview: {snippet_count: N}, full_results: [{title, url, snippet}].
- UI-1 (Phase 1) — не покрывает web search results. UI-2 — interface
  для web_search не предусмотрен. Нужен отдельный компонент (G-3),
  аналогичный G-2 (RAG citations), но для веб-результатов.
- ARCHITECT.md v1.2.0 §5.2.4 (Tool Layer) — web_search как @tool,
  возвращает list[dict]. UI должен отобразить list в user-friendly
  виде.
- ТРИЗ-принцип 3 (местное качество): web search results отличаются от
  RAG citations: нет page, нет content_preview (только snippet ~100
  символов), может быть score (Tavily возвращает relevance score).
  Не переиспользовать _render_citation_card из G-2 — другая структура
  данных.
- ТРИЗ-принцип 17 (другое измерение): web search results рендерятся в
  отдельной панели, не смешиваются с RAG citations. Если один запрос
  инициировал и rag_query и web_search — пользователь видит обе панели
  независимо.

Задача:
1. Создай функцию `render_web_search_results(results: list[dict]) -> None`
   в `src/llm_client/ui/render.py` (расширяет существующий файл):
   ```python
   def render_web_search_results(results: list[dict]) -> None:
       '''Рендерит web search results panel — список результатов с title
       (кликабельная ссылка на url), snippet, опционально score.

       Args:
           results: list of dict с fields {title, url, snippet, score?}.
                    Score в [0, 1] — Tavily relevance score (опционально).
       '''
       import streamlit as st

       if not results:
           return

       with st.expander(
           f"🌐 Web search results ({len(results)})",
           expanded=False,
       ):
           for i, result in enumerate(results, 1):
               _render_web_result_card(i, result)

   def _render_web_result_card(index: int, result: dict) -> None:
       import streamlit as st

       title = result.get("title") or result.get("url") or f"Result {index}"
       url = result.get("url", "")
       snippet = result.get("snippet", "")
       score = result.get("score")

       st.markdown(f"**{index}. [{title}]({url})**")
       st.caption(f"🔗 {url}")

       if snippet:
           st.markdown(snippet)

       if score is not None:
           # Score как meter (не progress bar — semantic отличие от
           # RAG citations):
           try:
               st.metric("Relevance", f"{float(score):.2f}")
           except (TypeError, ValueError):
               pass

       st.divider()
   ```

2. Интегрируй в handle_tool_event (G-1) — при event_type="tool_result"
   и tool_name="web_search" вызывает render_web_search_results. Это
   extension к G-1: render_tool_call обновляет preview (snippet_count),
   а render_web_search_results показывает full results.

   Обнови handle_tool_event в `src/llm_client/ui/render.py`:
   ```python
   def handle_tool_event(event_type, data, client, pending_tool_calls):
       # ... существующая логика для tool_call/tool_result/retrieved_docs
       # из G-1 ...
       elif event_type == "tool_result":
           tc_id = data["tool_call_id"]
           tool_name = data.get("tool_name", "")
           if tc_id in pending_tool_calls:
               pending_tool_calls[tc_id]["status"] = "done"
               pending_tool_calls[tc_id]["result_preview"] = (
                   data.get("preview") or {}
               )
               tc = pending_tool_calls[tc_id]
               client.render_tool_call(
                   tool_name=tc["tool_name"],
                   args=tc["args"],
                   status="done",
                   result_preview=tc["result_preview"],
               )
               # G-3 extension: full web search results:
               if tool_name == "web_search" and "full_results" in data:
                   render_web_search_results(data["full_results"])
               # G-2 extension: full RAG chunks (если tool_result несёт
               # chunks, не separate event retrieved_docs):
               elif tool_name == "rag_query" and "full_chunks" in data:
                   render_rag_citations(data["full_chunks"])
   ```

3. Оберни в @st.fragment (UI-3 pattern):
   ```python
   @st.fragment
   def _render_web_search_results_fragment(results: list[dict]) -> None:
       render_web_search_results(results)
   ```

4. Тесты в `tests/unit/test_ui_render.py` (расширь):
   - `test_render_web_search_results_empty` — results=[] → no render.
   - `test_render_web_search_results_one` — 1 result, title+url link,
     snippet, score metric.
   - `test_render_web_search_results_many` — 5 results (default Tavily),
     all rendered with divider.
   - `test_render_web_search_results_missing_snippet` — result без
     snippet (скрывает).
   - `test_render_web_search_results_missing_score` — result без score
     (metric не рендерится).
   - `test_handle_tool_event_web_search_full_results` — tool_result
     с tool_name="web_search" + full_results → render_web_search_results
     вызывается.
   - Integration: SSE event tool_result для web_search → UI panel
     с кликабельными ссылками.

Definition of Done:
- `render_web_search_results(results)` function в
  `src/llm_client/ui/render.py`.
- `_render_web_result_card(index, result)` helper.
- @st.fragment обёртка.
- handle_tool_event обновлён — вызывает render_web_search_results для
  tool_name="web_search" tool_result events.
- 7+ новых тестов зелёные.
- Manual test: prompt "search web for python asyncio best practices" →
  web_search tool_call → event: tool_result → web search results panel
  с 5 результатами, urls кликабельны, snippets отображаются.
- Существующие тесты test_ui_render.py — не регрессируют.

Антипаттерны:
- НЕ переиспользуй _render_citation_card из G-2 для web results —
  другая структура данных (no page, no content_preview, only snippet).
  Принцип 3: местное качество.
- НЕ показывай raw Tavily JSON — только user-facing fields (title, url,
  snippet, score). Технические fields (e.g. api_response_id) скрыть.
- НЕ хардкодь "5 results" — len(results) переменный (max_results
  параметр web_search, default 5, max 20 по WebSearchArgs).
- НЕ добавляй кнопку "Search again" — это не responsibility UI; если
  пользователь хочет новый поиск, он пишет новый prompt. UI только
  отображает результаты tool_call.
- НЕ открывай url в iframe (security: X-Frame-Options) — только как
  markdown link, открывается в новой вкладке браузера.
- НЕ кэшируй результаты в session_state — они уже в messages state на
  backend (AG-1 graph state). Дублирование нарушает single-source-of-
  truth.
- НЕ показывай score для results без score field (Tavily иногда не
  возвращает score для low-relevance results) — st.metric только при
  score is not None.
- НЕ путай web search results panel (G-3) с RAG citations panel (G-2) —
  они оба появляются в одном chat_message, но в разных expanders:
  "🌐 Web search results" vs "📚 RAG citations". Не смешивать.

Связанные ADR:
- Расширяет: UI-1 (+ 6-й элемент: web search results panel), UI-3
  (@st.fragment).
- Применяет: ADR-005 (Tool Layer — web_search @tool returns list[dict]),
  ADR-007 (SSE — event: tool_result).
- Зависит от: G-1 (handle_tool_event), H-1 (AG-5 web_search — источник
  results), H-4 (SSE event: tool_result — источник события).
- Не затрагивает: ADR-013, ADR-014 (PII: web snippets не проходят PII
  detect — в них может быть PII, но не из user input, а из web; в Phase
  2 не фильтруется; Phase 4 рассмотрит — см. OPEN question Q-6 в
  TRIZ-ANALYSIS.md).
```

### G-4. Settings panel extension (tools on/off + retrieval strategy + reranker choice)

```
Ты — Frontend-разработчик LLM Client. Расширь settings_panel из
ARCHITECT.md v1.2.0 §5.2.1 для Phase 2: добавь контроли для включения/
выключения инструментов (web_search, rag_query), выбора retrieval
strategy (vector/bm25/hybrid — ADR-020), выбора reranker (bge/cohere/
none — ADR-017). Эти настройки передаются в agent-service через
POST /sessions/{id}/chat body и используются graph-builder (AG-1) для
конфигурации инструментов и rag_retriever ноды (H-2).

Контекст:
- ARCHITECT.md v1.2.0 §5.2.1 строка 354 упоминает `settings_panel` с
  ответственностью "Выбор провайдера/модели, температура, max_tokens,
  tools on/off". В Phase 1 settings_panel не реализован (UI-0..UI-3
  покрывают только chat scaffold + sidebar + UIClient + fragments).
  Phase 2 добавляет settings_panel + расширяет под ADR-017/020.
- AG-1 (AG-PROMPTS.md §2) — `build_agent_graph(llm, token, tools)`.
  В Phase 1 tools=[file_export]. В Phase 2 tools=[file_export,
  web_search, rag_query] (Блок H-3). Но пользователь должен мочь
  выключить web_search или rag_query (privacy: "не хочу чтобы агент
  лазил в веб", "не хочу RAG по моим документам").
- ADR-020 (Блок D-1) — `RetrieverConfig.retrieval_strategy` enum с
  default HYBRID. Пользователь должен мочь переключить на VECTOR-only
  или BM25-only (debug, performance testing, exact-term override).
- ADR-017 (Блок C-1) — `RerankerRegistry` с bge-reranker (default) и
  Cohere (optional). Пользователь должен мочь выбрать reranker или
  выключить (none — для A/B baseline теста, E-3).
- ТРИЗ-принцип 17 (переход в другое измерение): settings — отдельная
  panel в sidebar, не в основном chat area. Раскрывается по клику на
  "⚙️ Settings" (collapsible, по умолчанию свёрнут — не отвлекает).
- ТРИЗ-принцип 3 (местное качество): каждая настройка — отдельный
  виджет: selectbox для retrieval_strategy, radio для reranker,
  checkbox для каждого tool. Не один большой form, а структурированные
  sub-sections.

Задача:
1. Создай функцию `render_settings_panel(session_state: dict) -> dict`
   в `src/llm_client/ui/render.py` (расширяет):
   ```python
   def render_settings_panel(session_state: dict) -> dict:
       '''Рендерит settings panel в sidebar (collapsible). Возвращает
       обновлённый dict с настройками для передачи в agent-service.

       Args:
           session_state: текущий st.session_state dict (читает
               предыдущие значения).

       Returns:
           dict с fields:
               - tools_enabled: list[str] — subset of ["web_search",
                   "rag_query", "file_export"] (default: all 3).
               - retrieval_strategy: "vector" | "bm25" | "hybrid"
                   (default: "hybrid", ADR-020).
               - reranker: "bge" | "cohere" | "none" (default: "bge",
                   ADR-017).
               - max_results: int (web_search max_results, default 5,
                   range 1-20).
               - top_k: int (rag_query top_k, default 5, range 1-20).
       '''
       import streamlit as st

       with st.sidebar.expander("⚙️ Settings", expanded=False):
           # Sub-section: Tools:
           st.markdown("**Tools**")
           tools_enabled = []
           if st.checkbox("Web search (Tavily)", value=True,
                           key="settings_tool_web_search"):
               tools_enabled.append("web_search")
           if st.checkbox("RAG query (documents)", value=True,
                           key="settings_tool_rag_query"):
               tools_enabled.append("rag_query")
           if st.checkbox("File export", value=True,
                           key="settings_tool_file_export"):
               tools_enabled.append("file_export")

           # Sub-section: Retrieval (only relevant if rag_query enabled):
           if "rag_query" in tools_enabled:
               st.markdown("**Retrieval**")
               retrieval_strategy = st.selectbox(
                   "Strategy",
                   options=["hybrid", "vector", "bm25"],
                   index=0,  # ADR-020 default
                   key="settings_retrieval_strategy",
                   help="hybrid = BM25 + vector (ADR-020 default); "
                        "vector = semantic only; bm25 = exact-term only",
               )
               top_k = st.slider(
                   "top_k (chunks to return)",
                   min_value=1, max_value=20, value=5, step=1,
                   key="settings_top_k",
                   help="After reranker (ADR-017); 5 is recommended",
               )

               st.markdown("**Reranker**")
               reranker = st.radio(
                   "Model",
                   options=["bge", "cohere", "none"],
                   index=0,  # ADR-017 default
                   key="settings_reranker",
                   help="bge = local in-process (ADR-017 default); "
                        "cohere = external API (optional); "
                        "none = disable reranking (A/B baseline)",
               )
           else:
               # Defaults if rag_query disabled:
               retrieval_strategy = "hybrid"
               top_k = 5
               reranker = "bge"

           # Sub-section: Web search (only if web_search enabled):
           if "web_search" in tools_enabled:
               st.markdown("**Web search**")
               max_results = st.slider(
                   "max_results",
                   min_value=1, max_value=20, value=5, step=1,
                   key="settings_max_results",
                   help="Tavily API max results per query",
               )
           else:
               max_results = 5

       # Persist in session_state для следующего re-run:
       settings = {
           "tools_enabled": tools_enabled,
           "retrieval_strategy": retrieval_strategy,
           "reranker": reranker,
           "max_results": max_results,
           "top_k": top_k,
       }
       session_state["settings"] = settings
       return settings
   ```

2. Интегрируй в `src/llm_client/ui/app.py` (точка входа Streamlit):
   ```python
   import streamlit as st
   from llm_client.ui.render import render_settings_panel
   from llm_client.ui.chat import post_chat  # существующий из Phase 1

   def main():
       st.title("LLM Client")
       settings = render_settings_panel(st.session_state)

       # При отправке сообщения — передать settings в chat body:
       prompt = st.chat_input("Ask...")
       if prompt:
           response = post_chat(
               session_id=st.session_state["session_id"],
               message=prompt,
               settings=settings,  # NEW: пробрасываем в agent-service
           )
           # ... streaming logic из Phase 1 ...
   ```

3. Обнови `src/llm_client/ui/chat.py` `post_chat` (или эквивалент) —
   добавь `settings` параметр в тело POST запроса к agent-service:
   ```python
   def post_chat(session_id: str, message: str,
                  settings: dict | None = None) -> dict:
       '''POST /sessions/{session_id}/chat — старт graph с настройками.'''
       body = {"message": message}
       if settings:
           body["settings"] = settings
       response = httpx.post(
           f"{AGENT_SERVICE_URL}/sessions/{session_id}/chat",
           json=body,
           timeout=30.0,
       )
       return response.json()
   ```

4. Обнови agent-service contract (Блок H-3) — POST /chat body принимает
   опциональный `settings` field. См. H-3 п.2 для реализации на стороне
   agent-service.

5. Тесты в `tests/unit/test_ui_render.py` (расширь):
   - `test_render_settings_panel_defaults` — все tools enabled,
     retrieval_strategy="hybrid", reranker="bge", max_results=5,
     top_k=5.
   - `test_render_settings_panel_disable_web_search` — checkbox
     unchecked → tools_enabled не содержит "web_search",
     max_results=default 5.
   - `test_render_settings_panel_disable_rag_query` — rag_query
     unchecked → retrieval sub-section скрыт, defaults применены.
   - `test_render_settings_panel_choose_vector` — selectbox="vector".
   - `test_render_settings_panel_choose_cohere` — radio="cohere".
   - `test_render_settings_panel_choose_none_reranker` — radio="none"
     (A/B baseline mode).
   - Integration: app.py main() → settings в session_state → post_chat
     body содержит settings field.

Definition of Done:
- `render_settings_panel(session_state)` function в
  `src/llm_client/ui/render.py`.
- `src/llm_client/ui/app.py` main() вызывает render_settings_panel и
  передаёт settings в post_chat.
- `src/llm_client/ui/chat.py` post_chat принимает settings, кладёт в
  POST body.
- agent-service POST /chat body schema расширена опциональным settings
  field (Блок H-3 реализует парсинг).
- 6+ новых тестов зелёные.
- Manual test: открыть sidebar → "⚙️ Settings" → выключить web_search
  → отправить prompt "search web for X" → agent отвечает без
  web_search tool_call (видно в tool-call preview G-1).
- Manual test: выбрать reranker="none" → отправить prompt → в Grafana
  видно что reranker fallback chain дошел до identity (Блок C-5).
- Существующие тесты test_ui_render.py — не регрессируют.

Антипаттерны:
- НЕ показывай settings в основном chat area — только в sidebar
  expander. Принцип 17: settings — отдельное измерение UI.
- НЕ хардкодь tools list в UI — агент может добавить mcp_call (Phase 4).
  Settings panel должен поддержать любой tool_name (но показывать
  только для известных Phase 2: web_search, rag_query, file_export).
  Расширение на mcp_call — Phase 4 (G-4 v2.0).
- НЕ делай radio для retrieval_strategy — это selectbox (3 опции, не 2).
  Radio уместен для reranker (3 опции тоже, но categorical vs ordinal).
- НЕ валидируй settings в UI — валидация в agent-service (Блок H-3).
  UI только собирает; валидация и fallback на defaults — backend
  responsibility (security: никогда не доверяй client).
- НЕ добавляй кнопку "Apply" — настройки применяются на следующий
  prompt автоматически (session_state). Если нужен явный Apply — Phase
  5 (UI-4 SessionStore sync).
- НЕ сохраняй settings в БД — только в session_state Streamlit (Phase
  5 UI-4 добавит RedisSessionStore, в Phase 2 in-memory достаточно).
- НЕ показывай продвинутые настройки (temperature, max_tokens, model) —
  это не Phase 2 responsibility (нет явных ADR-requirements). Phase 4
  (Local LLM) рассмотрит advanced settings.
- НЕ混淆 reranker="none" с retrieval_strategy="vector" — это разные
  настройки. reranker="none" отключает переранжировку (A/B baseline);
  retrieval_strategy="vector" отключает BM25 path. Оба могут быть
  independently выбраны.

Связанные ADR:
- Расширяет: UI-1 (sidebar + 7-й элемент: settings_panel),
  ARCHITECT.md §5.2.1 (settings_panel responsibility — реализован).
- Применяет: ADR-017 (RerankerRegistry — radio bge/cohere/none),
  ADR-020 (RetrieverConfig.retrieval_strategy — selectbox
  hybrid/vector/bm25), ADR-005 (Tool Layer — tools_enabled checkboxes).
- Зависит от: H-3 (graph integration — settings парсится на стороне
  agent-service), C-1 (RerankerRegistry), D-1 (RetrieverConfig).
- Не затрагивает: ADR-013 (cancel), ADR-014 (PII), ADR-002 (Streamlit
  — расширяет, не заменяет).
```

---

## 6. Блок H. AG-расширения Phase 2 (AG-5 web_search + AG-6 rag_query)

**Источник**: `BACKLOG.md` v1.1.0 §3.4 (AG-5, AG-6 — формализация для Phase 2), `ROADMAP.md` v1.2.0 §6.2.4 (AG-5, 1 чел-дн) + §6.2.5 (AG-6, 4 чел-дн), `ARCHITECT.md` v1.2.0 §5.2.4 (Tool Layer — `@tool` декоратор + `WebSearchArgs`/`FileExportArgs`), §5.2.2 (Orchestration — `rag_retriever` нода упоминается в graph nodes), §5.2.5 (RAG Layer — pipeline vector → BM25 → fusion → reranker), `AG-PROMPTS.md` v1.0.0 §2 (AG-1 `build_agent_graph(llm, token, tools)` — точка интеграции), §4 (AG-3 SSE event protocol — точка расширения), §5 (AG-4 `file_export` — pattern для нового `@tool`).

**Назначение**: Phase 1 закрыла AG-0..AG-4 — agent-service scaffold (FastAPI + SSE), LangGraph graph (planner + final_answer + tool_executor для file_export), LLMProviderFactory (OpenAI only), SSE event protocol (token/metadata/artifact_ready/cancelled/error/done), file_export tool. Однако `BACKLOG.md` v1.1.0 §3.4 формализует ещё две AG-работы для Phase 2: AG-5 (`web_search` tool via Tavily — реализует ADR-005 Tool Layer на конкретном веб-поиске) и AG-6 (`rag_query` tool + base RAG pipeline — реализует ADR-003 VectorStoreFactory на конкретном retrieval и добавляет `rag_retriever` ноду в graph). Без AG-5/AG-6 LLM-агент умеет только генерировать текст и экспортировать файлы, но не может искать информацию в вебе (G-1 business goal "сокращение времени аналитика на поиск") или в корпоративном корпусе (G-1 RAG). Phase 2 закрывает обе возможности — и заодно даёт реальный pipeline, на котором работают ADR-017 (reranker) и ADR-020 (hybrid retrieval): без `rag_query` tool/rag_retriever ноды Блоки C и D — абстрактные компоненты без точки вызова. AG-6 — тот самый "вызов", на котором ADR-017 и ADR-020 применяются в production pipeline.

**Связь с архитектурой**: `ARCHITECT.md` v1.2.0 §5.2.4 явно показывает `WebSearchArgs`/`web_search` (строка 435) и `FileExportArgs`/`file_export` (строка 445) как примеры Tool Layer. В Phase 1 реализован только `file_export` (AG-4). AG-5 реализует `web_search` —.architecture уже зафиксирована, нужно только написать `@tool`-функцию. AG-6 добавляет `rag_query` tool — architecture явно не показывает (упоминается в §5.2.4 как часть `tools_enabled: ["web_search", "rag_query", ...]` в AgentState, и в §5.2.2 как `rag_retriever` нода). Блок H-2 фиксирует RagQueryArgs/rag_query contract.

**Принципы ТРИЗ**: 25 (самообслуживание — web_search использует внешний API Tavily, но результат кэшируется в `messages` state, не требует повторных вызовов; AG-6 использует `BGEEmbeddings` в Phase 4 для локального режима), 3 (местное качество — `rag_retriever` специализированная нода, не general-purpose `tool_executor`; хотя для LLM tool exposed через `bind_tools` как обычный `@tool`), 19 (переход в другое измерение — `rag_retriever` вынесен в отдельную ноду graph, не выполняется внутри `tool_executor`; даёт точку перехвата для retrieval-specific logic — reranker, hybrid fusion, PII filtering), 16 (частичное/избыточное действие — `web_search` и `rag_query` exposed to LLM через `bind_tools` как обычные `@tool`, но `rag_query` имеет второй путь — `rag_retriever` нода, когда planner явно решает "RAG first" strategy; LLM может вызвать rag_query через tool_call, или planner может направить в rag_retriever напрямую).

**Оценка и параллелизация**: 4 промпта, 5 чел-дн total (AG-5: 1 чел-дн, AG-6: 4 чел-дн — включает base RAG pipeline + rag_retriever ноду + интеграцию с C/D блоками). Критический путь: H-1 (1) и H-2 (4) параллельны → H-3 (0.5, после H-1+H-2) → H-4 (0.5, после H-3). Два Backend-разработчика (Дев 1 и Дев 2 в §10): Дев 1 → H-1 + H-3 (graph integration), Дев 2 → H-2 + H-4 (SSE event protocol).

### H-1. (AG-5) `web_search` tool via Tavily API

```
Ты — Backend/Agent-разработчик LLM Client. Создай `web_search` tool —
@tool-декорированную async-функцию, вызывающую Tavily API для веб-поиска.
Это AG-5 из `BACKLOG.md` v1.1.0 §3.4, реализует ADR-005 (Tool Layer)
на конкретном инструменте веб-поиска.

Контекст:
- ARCHITECT.md v1.2.0 §5.2.4 строки 435–443 уже зафиксировали contract:
  ```python
  class WebSearchArgs(BaseModel):
      query: str = Field(..., description="Поисковый запрос")
      max_results: int = Field(5, ge=1, le=20)

  @tool(args_schema=WebSearchArgs)
  def web_search(query: str, max_results: int = 5) -> list[dict]:
      '''Ищет в вебе через Tavily API. Возвращает список {title, url,
      snippet}.'''
      # реализация через tavily-python
      ...
  ```
  Этот contract НЕ переопределяется — реализуется как есть.
- AG-4 `file_export` (AG-PROMPTS.md §5) — pattern для нового `@tool`.
  Структура: FileExportArgs schema + @tool декоратор + storage = ... +
  return dict. web_search следует той же структуре: WebSearchArgs
  schema + @tool декоратор + tavily client call + return list[dict].
- AG-1 graph (AG-PROMPTS.md §2) — `build_agent_graph(llm, token,
  tools)`. В Phase 1 tools=[file_export]. В Phase 2 (Блок H-3)
  tools=[file_export, web_search, rag_query]. LLM получает tools через
  `llm.bind_tools(tools)` (ADR-006 native tool calling).
- AG-3 SSE (AG-PROMPTS.md §4) — эмитит events. В Phase 1: token,
  metadata, artifact_ready, cancelled, error, done. Блок H-4
  расширяет: tool_call, tool_result, retrieved_docs. web_search
  tool_call эмитит tool_call event; return value эмитит tool_result
  event.
- Tavily API: https://api.tavily.com — LLM-oriented search API.
  Requires TAVILY_API_KEY env var. Free tier: 1000 calls/month.
  Returns: {results: [{title, url, content, score}], answer?
  (LLM-generated summary)}.
- ТРИЗ-принцип 25 (самообслуживание): web_search — внешний API, но
  результат кэшируется в messages state (ToolMessage content). При
  follow-up вопросе LLM видит предыдущие результаты в context, не
  вызывает tool снова (если не нужен refresh).
- ТРИЗ-принцип 35 (изменение физических свойств): web_search — external
  dependency, но hot path синхронный (HTTP call ~2 сек). В Phase 3
  (ADR-011 semantic cache) рассмотрим кэширование query → results,
  сейчас — простой прямой вызов.

Задача:
1. Создай src/llm_client/agent/tools/__init__.py (если ещё не создан
   в AG-4 — в существующей кодовой базе пакет tools может отсутствовать;
   проверь src/llm_client/agent/tools/ перед стартом. Если нет — создай).
2. Создай src/llm_client/agent/tools/web_search.py:
   ```python
   """web_search tool via Tavily API (AG-5, Phase 2).

   Implements ADR-005 (Tool Layer) on a concrete web-search tool.
   Architecture contract: ARCHITECT.md v1.2.0 §5.2.4 строки 435-443.
   """
   import logging
   from typing import Any

   import httpx
   from langchain_core.tools import tool
   from pydantic import BaseModel, Field

   from ...config import get_settings

   logger = logging.getLogger(__name__)


   class WebSearchArgs(BaseModel):
       query: str = Field(..., description="Поисковый запрос")
       max_results: int = Field(
           default=5, ge=1, le=20,
           description="Max number of results to return (1-20)",
       )


   @tool(args_schema=WebSearchArgs)
   async def web_search(query: str, max_results: int = 5) -> list[dict]:
       '''Ищет в вебе через Tavily API. Возвращает список
       {title, url, snippet, score?}.

       Используется агентом для актуальной информации (новости,
       документация, факты). Результат кэшируется в ToolMessage —
       follow-up вопрос может переиспользовать результаты без
       повторного вызова.
       '''
       settings = get_settings()
       api_key = settings.tavily_api_key
       if not api_key:
           logger.error("TAVILY_API_KEY not set — web_search unavailable")
           raise RuntimeError(
               "web_search tool requires TAVILY_API_KEY in environment"
           )

       async with httpx.AsyncClient(timeout=10.0) as client:
           response = await client.post(
               "https://api.tavily.com/search",
               headers={"Authorization": f"Bearer {api_key}"},
               json={
                   "query": query,
                   "max_results": max_results,
                   "include_answer": False,  # мы хотим только results
                   "search_depth": "basic",  # advanced — Phase 3+
               },
           )
           response.raise_for_status()
           data = response.json()

       # Normalize Tavily response to our contract:
       results = []
       for r in data.get("results", [])[:max_results]:
           results.append({
               "title": r.get("title", ""),
               "url": r.get("url", ""),
               "snippet": r.get("content", "")[:500],  # truncate
               "score": r.get("score"),
           })

       logger.info(
           "web_search query=%r max_results=%d returned=%d",
           query, max_results, len(results),
       )
       return results
   ```

3. Добавь настройки в `src/llm_client/config.py` Settings:
   - `tavily_api_key: str | None = None` (env: TAVILY_API_KEY).
   - `tavily_search_depth: Literal["basic", "advanced"] = "basic"`.
   - `tavily_timeout_seconds: float = 10.0`.
   - В `Settings._validate_environment`: если tools_enabled содержит
     "web_search" и TAVILY_API_KEY пустой — startup fail fast
     (аналогично OPENAI_API_KEY валидации из AG-2).
   - В .env.example добавь:
     - `TAVILY_API_KEY=tvly-xxxxxxxxxxxxxxxxxxxxxxxx` (placeholder).
     - `TAVILY_SEARCH_DEPTH=basic` (default).
     - `TAVILY_TIMEOUT_SECONDS=10.0` (default).

4. Тесты в `src/llm_client/agent/tools/test_web_search.py`:
   - `test_web_search_returns_results` — mock httpx.AsyncClient,
     Tavily response с 3 results, web_search returns 3 dicts с
     {title, url, snippet, score}.
   - `test_web_search_truncates_snippet` — Tavily возвращает content
     1000 символов → snippet truncated до 500.
   - `test_web_search_max_results_cap` — max_results=3, Tavily
     возвращает 10 results → web_search returns только 3.
   - `test_web_search_no_api_key_raises` — settings.tavily_api_key=None
     → RuntimeError.
   - `test_web_search_http_error_propagates` — Tavily 500 → httpx
     raises, web_search raises (graph error handler в H-3 поймает).
   - `test_web_search_timeout` — Tavily > 10 сек → httpx.TimeoutException.
   - Integration: build_agent_graph(llm=mock, tools=[web_search]),
     mock LLM возвращает tool_call("web_search", {query: "python
     asyncio"}) → tool_executor вызывает web_search → ToolMessage с
     list[dict] content → graph возвращается в planner для
     интерпретации.

Definition of Done:
- `src/llm_client/agent/tools/web_search.py` существует с
  WebSearchArgs + @tool web_search.
- Settings расширен tavily_api_key, tavily_search_depth,
  tavily_timeout_seconds.
- .env.example обновлён.
- 7+ новых тестов зелёные.
- Integration тест: graph с web_search tool, mock LLM возвращает
  tool_call → web_search выполняется → ToolMessage в state → graph
  продолжается.
- Manual test: запуск agent-service локально с TAVILY_API_KEY, POST
  /chat с prompt "search web for python asyncio best practices" →
  agent вызывает web_search → SSE event: tool_call (Блок H-4) →
  event: tool_result → event: token × N (финальный ответ с
  веб-источниками) → event: done.
- Существующие тесты tests/unit/test_ui_*.py — не регрессируют.

Антипаттерны:
- НЕ хардкодь TAVILY_API_KEY в коде — только через Settings + .env.
- НЕ используй sync `requests` library — только async `httpx`. AG-1
  graph — async; sync HTTP call блокирует event loop.
- НЕ хардкодь Tavily URL в коде — вынеси в Settings.tavily_api_url
  (default "https://api.tavily.com/search"; для self-hosted Tavily
  alternative в Phase 4).
- НЕ возвращай Tavily "answer" field (LLM-generated summary) — мы
  хотим {title, url, snippet, score} для UI (G-3), не LLM summary
  (дубликат с нашим LLM в graph).
- НЕ хардкодь snippet truncation 500 — вынеси в Settings
  (tavily_snippet_max_chars=500). В UI (G-3) ещё раз truncate до 200.
- НЕ делай web_search sync @tool — обязательно async. Sync @tool
  в LangGraph tool_executor блокирует event loop.
- НЕ добавляй retry в web_search — retry_decorator на уровне LLM
  Provider (AG-2) для LLM вызовов; web_search — single call, при
  failure graph error handler (H-3) ловит и эмитит event: error. Retry
  logic — Phase 3 (cost-aware router ADR-015 consider caching).
- НЕ кэшируй results в Redis (Phase 3 ADR-011 — semantic cache для
  LLM responses, не для tool results). Phase 2 — простой прямой вызов.
- НЕ вызывай web_search напрямую из planner ноды — только через
  LLM tool_call (bind_tools) → tool_executor нода (H-3 integration).
  Planner не должен знать о конкретных tools.
- НЕ показывай raw Tavily JSON в ToolMessage content — нормализуй
  в {title, url, snippet, score} list. UI (G-3) парсит этот формат.

Связанные ADR:
- Реализует: ADR-005 (Tool Layer — web_search как @tool с
  args_schema=WebSearchArgs).
- Применяет: ADR-006 (native tool calling через bind_tools в AG-1
  graph), расш. ADR-008 (S3 storage — не используется, но web_search
  results могут быть saved как artifact через file_export в future
  tool-chaining — Phase 3+).
- Зависит от: AG-1 (graph), AG-3 (SSE — Блок H-4 расширяет под
  tool_call/tool_result events), AG-4 (pattern для @tool — file_export
  из Phase 1).
- Расширяется в: Phase 3 (ADR-011 semantic cache — кэш query → results;
  ADR-015 cost-aware router — решение web_search vs LLM-knowledge).
- Не затрагивает: ADR-010 (checkpoint — graph state автоматически
  сериализует ToolMessage), ADR-013 (cancel — token.is_cancelled
  проверяется между нодами, web_search inside tool_executor не
  отменяемо, но после tool_executor graph выходит на cancel).
```

### H-2. (AG-6) `rag_query` tool + `rag_retriever` нода + base RAG pipeline

```
Ты — Backend/Agent-разработчик LLM Client. Создай `rag_query` tool и
`rag_retriever` ноду в graph для RAG-поиска по корпоративному корпусу.
Это AG-6 из `BACKLOG.md` v1.1.0 §3.4, реализует ADR-003
(VectorStoreFactory) на конкретном retrieval pipeline. Базовый
vector retrieval; ADR-017 (reranker, Блок C) и ADR-020 (hybrid BM25+
vector, Блок D) расширяют этот pipeline в том же Phase 2.

Контекст:
- ARCHITECT.md v1.2.0 §5.2.5 (RAG Layer) описывает pipeline:
  Load → Chunk → Embed → Store (через VectorStoreFactory) → Retrieve
  (vector_store.as_retriever). В Phase 1 нет retrieval — retrieval
  появляется в Phase 2 с AG-6.
- ARCHITECT.md v1.2.0 §5.2.2 (Orchestration) перечисляет ноды графа:
  planner, tool_executor, rag_retriever, mcp_invoker, final_answer.
  В Phase 1 (AG-1) реализованы planner + final_answer + tool_executor
  (для file_export). В Phase 2 AG-6 добавляет rag_retriever.
- ARCHITECT.md v1.2.0 §5.2.4 (Tool Layer) — упоминает rag_query в
  AgentState.tools_enabled: ["web_search", "rag_query", ...].
  Блок H-2 фиксирует RagQueryArgs/rag_query contract.
- ADR-003 (VectorStoreFactory) — Approved в Phase 1 (MVP-PROMPTS).
  Создаёт Chroma/Qdrant/PGVector. В Phase 2 default — Chroma (in-
  process, no external service) для dev; PGVector для staging (uses
  existing PostgreSQL + pgvector extension).
- ADR-017 (Блок C) — RerankerRegistry с bge-reranker (default). AG-6
  rag_retriever нода ВЫЗЫВАЕТ reranker после vector retrieval (Блок
  C-4 pipeline integration).
- ADR-020 (Блок D) — RetrieverConfig.retrieval_strategy=hybrid default.
  AG-6 rag_retriever нода ВЫЗЫВАЕТ HybridRetriever (Блок D-4) вместо
  vector-only retriever, если strategy=hybrid.
- ТРИЗ-принцип 19 (переход в другое измерение): rag_retriever —
  отдельная нода graph, не внутри tool_executor. Это даёт точку
  перехвата для retrieval-specific logic (reranker, hybrid fusion,
  PII filtering) без перегрузки tool_executor.
- ТРИЗ-принцип 16 (частичное/избыточное действие): rag_query exposed
  to LLM через bind_tools как обычный @tool (LLM может вызвать
  напрямую), но rag_retriever нода — второй путь, когда planner
  явно решает "RAG first". Оба пути вызывают один и тот же
  RagPipeline.retrieve() — single source of truth.

Задача:
1. Создай src/llm_client/agent/tools/rag_query.py:
   ```python
   """rag_query tool + rag_retriever node (AG-6, Phase 2).

   Implements ADR-003 (VectorStoreFactory) on a concrete retrieval
   pipeline. Extended by ADR-017 (reranker, Block C) and ADR-020
   (hybrid retrieval, Block D) in the same Phase 2.
   """
   import logging
   from typing import Any
   from uuid import uuid4

   from langchain_core.tools import tool
   from pydantic import BaseModel, Field

   from ...config import get_settings
   from ...rag.config import RetrieverConfig  # Блок D-1
   from ...rag.pipeline import RagPipeline  # создан ниже

   logger = logging.getLogger(__name__)


   class RagQueryArgs(BaseModel):
       query: str = Field(..., description="Поисковый запрос по корпусу документов")
       top_k: int = Field(
           default=5, ge=1, le=20,
           description="Number of chunks to return after reranker (1-20)",
       )
       # retrieval_strategy и reranker — из Settings / session settings (G-4),
       # не из args — они session-level, не per-query.


   @tool(args_schema=RagQueryArgs)
   async def rag_query(query: str, top_k: int = 5) -> dict:
       '''Ищет по корпоративному корпусу документов. Возвращает dict
       {chunks: [{source_uri, title, page, content_preview, score}],
       chunk_count, top_score, source_uris}.

       Pipeline: vector retrieval (top-20) → [BM25 retrieval (top-20) →
       RRF fusion (top-50)] (if strategy=hybrid, ADR-020) → reranker
       top-5 (ADR-017). PII filtering applied (ADR-014 metadata).
       '''
       pipeline = RagPipeline.from_settings(get_settings())
       result = await pipeline.retrieve(query, top_k=top_k)
       return result
   ```

2. Создай src/llm_client/rag/__init__.py (новый пакет):
   - `src/llm_client/rag/config.py` — Re-exports RetrieverConfig из
     Блока D-1 (RetrievalStrategy enum + RetrieverConfig dataclass).
   - `src/llm_client/rag/pipeline.py` — RagPipeline class (см. ниже).
   - `src/llm_client/rag/reranker.py` — Re-exports RerankerRegistry
     из Блока C-1.
   - `src/llm_client/rag/retrievers.py` — Re-exports VectorRetriever
     (base), HybridRetriever (Блок D-4), BM25Retriever (Блок D-3).

3. Создай src/llm_client/rag/pipeline.py:
   ```python
   """RagPipeline — single source of truth for RAG retrieval.

   Used by both rag_query @tool (LLM-driven) and rag_retriever node
   (planner-driven). Extended by ADR-017 (reranker) and ADR-020
   (hybrid retrieval) in the same Phase 2.
   """
   import logging
   from typing import Any

   from langchain_core.retrievers import BaseRetriever

   from ..config import get_settings
   from .config import RetrieverConfig, RetrievalStrategy
   from .reranker import RerankerRegistry

   logger = logging.getLogger(__name__)


   class RagPipeline:
       '''Composes retriever + reranker based on RetrieverConfig.

       Lifecycle:
       - Created at agent-service startup (singleton, in-process).
       - retrieve(query, top_k) — called by rag_query tool and by
         rag_retriever node.
       - Vector store created via VectorStoreFactory (ADR-003).
       - Retriever: VectorRetriever (base), HybridRetriever (ADR-020),
         or BM25Retriever (ADR-020) — based on retrieval_strategy.
       - Reranker: BgeRerankerAdapter (ADR-017 default),
         CohereRerankAdapter (optional), or identity (disabled).
       '''

       def __init__(self, retriever: BaseRetriever,
                    reranker_registry: RerankerRegistry,
                    config: RetrieverConfig):
         self._retriever = retriever
         self._reranker_registry = reranker_registry
         self._config = config

       @classmethod
       def from_settings(cls, settings) -> "RagPipeline":
           '''Factory method — called at agent-service startup.'''
           # Vector store через VectorStoreFactory (ADR-003):
           from .retrievers import VectorRetriever, HybridRetriever, BM25Retriever
           from .reranker import RerankerRegistry

           config = RetrieverConfig.from_settings(settings)
           reranker_registry = RerankerRegistry.from_settings(settings)

           if config.retrieval_strategy == RetrievalStrategy.HYBRID:
               retriever = HybridRetriever(config=config)
           elif config.retrieval_strategy == RetrievalStrategy.BM25:
               retriever = BM25Retriever(config=config)
           else:
               retriever = VectorRetriever(config=config)

           return cls(retriever=retriever,
                      reranker_registry=reranker_registry,
                      config=config)

       async def retrieve(self, query: str, top_k: int = 5) -> dict:
           '''Returns dict {chunks, chunk_count, top_score, source_uris}.

           Pipeline:
           1. retriever.get_relevant_documents(query) — vector top-20
              (+ BM25 top-20 if hybrid, fused via RRF).
           2. reranker.rerank(query, docs) → top-top_k chunks.
           3. PII filter on content_preview (Блок D-5 / ADR-014).
           4. Normalize to {source_uri, title, page, content_preview,
              score} list.
           '''
           # Step 1: Retrieval (vector, hybrid, or BM25):
           docs = await self._retriever.aget_relevant_documents(query)
           logger.info("Retrieved %d docs (strategy=%s)",
                       len(docs), self._config.retrieval_strategy)

           # Step 2: Reranker (ADR-017):
           reranker = self._reranker_registry.get_active()
           if reranker is not None:
               docs = await reranker.arerank(query, docs, top_k=top_k)
           else:
               docs = docs[:top_k]

           # Step 3: PII filter on content_preview:
           # (Блок D-5 PII metadata applied at indexing time; here we
           # only truncate preview for UI safety.)
           chunks = []
           source_uris = []
           for doc in docs:
               source_uri = doc.metadata.get("source_uri", "")
               title = doc.metadata.get("title", source_uri)
               page = doc.metadata.get("page")
               content_preview = doc.page_content[:200]
               if len(doc.page_content) > 200:
                   content_preview += "..."
               score = float(doc.metadata.get("score", 0.0))
               chunks.append({
                   "source_uri": source_uri,
                   "title": title,
                   "page": page,
                   "content_preview": content_preview,
                   "score": score,
               })
               if source_uri:
                   source_uris.append(source_uri)

           top_score = chunks[0]["score"] if chunks else 0.0
           return {
               "chunks": chunks,
               "chunk_count": len(chunks),
               "top_score": top_score,
               "source_uris": source_uris,
           }
   ```

4. Создай rag_retriever node в `src/llm_client/agent/graph.py` (расширь
   AG-1):
   ```python
   # В src/llm_client/agent/graph.py:

   async def _rag_retriever_node(state: dict[str, Any],
                                  pipeline: RagPipeline) -> dict[str, Any]:
       """Retrieves documents from RAG corpus based on last user message.

       Called when planner decides 'rag_first' strategy. Updates
       state['retrieved_docs'] for final_answer node to use as context.
       """
       messages = state.get("messages") or []
       last_user_msg = None
       for m in reversed(messages):
           if getattr(m, "type", "") == "human" or \
              getattr(m, "role", "") == "user":
               last_user_msg = m
               break
       if last_user_msg is None:
           return {"retrieved_docs": []}

       query = last_user_msg.content if hasattr(last_user_msg, "content") \
               else str(last_user_msg)
       top_k = state.get("rag_top_k", 5)

       result = await pipeline.retrieve(query, top_k=top_k)
       return {"retrieved_docs": result["chunks"]}
   ```

5. Расширь `build_agent_graph` в `src/llm_client/agent/graph.py` для
   Phase 2 (Блок H-3 детализирует graph integration):
   - Добавь rag_retriever ноду.
   - Добавь conditional edge route_after_planner: если
     route_decision=="rag_first" → rag_retriever; если "tools_needed"
     → tool_executor; иначе → final_answer.
   - rag_retriever → final_answer (после retrieval — агент формирует
     ответ с retrieved_docs как context).

6. Тесты в `src/llm_client/agent/tools/test_rag_query.py`:
   - `test_rag_query_returns_chunks` — mock RagPipeline.retrieve
     возвращает 3 chunks → rag_query returns dict с chunks,
     chunk_count=3, top_score, source_uris.
   - `test_rag_query_top_k_param` — top_k=3 → pipeline.retrieve
     called with top_k=3.
   - `test_rag_query_default_top_k` — no top_k arg → default 5.
   - `test_rag_query_empty_results` — pipeline returns no chunks →
     rag_query returns {chunks: [], chunk_count: 0, top_score: 0.0}.
   - `test_rag_query_content_truncation` — doc.page_content 1000
     chars → content_preview 200 + "...".
   - `test_rag_retriever_node_extracts_query` — last human message
     extracted as query.
   - `test_rag_retriever_node_no_user_msg` — empty messages →
     retrieved_docs=[].
   - Integration: graph с rag_retriever, mock planner возвращает
     route_decision="rag_first" → rag_retriever → final_answer →
     state["retrieved_docs"] contains chunks.

Definition of Done:
- `src/llm_client/agent/tools/rag_query.py` с RagQueryArgs + @tool
  rag_query.
- `src/llm_client/rag/` пакет создан с config.py, pipeline.py,
  reranker.py (re-export), retrievers.py (re-export).
- `RagPipeline` class имплементирован с from_settings + retrieve
  methods.
- `rag_retriever` нода добавлена в `src/llm_client/agent/graph.py`.
- `build_agent_graph` расширена для Phase 2 (Блок H-3 детализирует).
- 8+ новых тестов зелёные.
- Manual test: загрузить 3 документа через RAG indexing (отдельный
  script), POST /chat с prompt "что говорится в документации про
  asyncio?" → agent решает rag_first → rag_retriever нода вызывается
  → event: retrieved_docs (Блок H-4) → event: token × N (ответ с
  цитатами) → event: done.
- Существующие тесты test_graph.py — не регрессируют (Phase 1 graph
  без rag_retriever всё ещё работает через tools=[] path).

Антипаттерны:
- НЕ возвращай полный doc.page_content — truncate до 200 символов.
  Полный content — в ToolMessage для LLM context (LLM видит полный);
  UI (G-2) видит только preview.
- НЕ хардкодь top_k=5 в rag_query — default 5, но параметр
  Pydantic-field. Settings могут override default (G-4 slider).
- НЕ создавай VectorStore instance в rag_query tool — только через
  RagPipeline singleton (создаётся при startup). Если создавать в
  каждом tool_call — +5 сек latency на загрузку модели embeddings.
- НЕ делай retrieve sync — только async (AG-1 graph async; LangChain
  retrievers поддерживают aget_relevant_documents).
- НЕ включай PII filtering в rag_retriever ноде — PII detect applied
  при indexing (Блок D-5 metadata); на retrieval только truncated
  preview. Phase 4 рассмотрит runtime PII filtering (Q-6 TRIZ).
- НЕ добавляй chat_history в rag_query query — только последний
  user message. Multi-turn RAG — Phase 3 (ADR-011 semantic cache с
  conversational context). В Phase 2 каждый rag_query — independent.
- НЕ хардкодь "Chroma" vector store в RagPipeline — через
  VectorStoreFactory (ADR-003) из Settings.vector_store_kind.
- НЕ создавай отдельный RagPipeline instance для rag_retriever и
  rag_query — один singleton. Если разные — разные reranker_registry
  instances, разные models loaded = 1.2GB RAM x2.
- НЕ забудь reranker identity fallback (Блок C-5) — если reranker=
  "none" (settings G-4), pipeline.retrieve всё ещё работает, просто
  без reranking step.
- НЕ эмить SSE events из RagPipeline — только из rag_query/rag_retriever
  через tool_executor (Блок H-4). RagPipeline — pure retrieval logic.

Связанные ADR:
- Реализует: ADR-003 (VectorStoreFactory — RagPipeline использует),
  ADR-005 (Tool Layer — rag_query как @tool), ADR-006 (native tool
  calling через bind_tools), ADR-001 (LangGraph — rag_retriever нода).
- Расширяется: ADR-017 (reranker — RagPipeline.retrieve step 2),
  ADR-020 (hybrid retrieval — RagPipeline.retrieve step 1, если
  strategy=hybrid).
- Зависит от: AG-1 (graph), AG-3 (SSE — Блок H-4 events
  retrieved_docs), Блок D-1 (RetrieverConfig), Блок C-1
  (RerankerRegistry), Блок D-4 (HybridRetriever), Блок D-3
  (BM25Retriever), Блок D-5 (PII metadata applied at indexing).
- Не затрагивает: ADR-010 (checkpoint — graph state автоматически
  сериализует retrieved_docs), ADR-013 (cancel), ADR-014 (PII —
  applied at indexing time, не в retrieval).
```

### H-3. Graph integration: `bind_tools([file_export, web_search, rag_query])` + rag_retriever нода

```
Ты — Backend/Agent-разработчик LLM Client. Интегрируй web_search (H-1)
и rag_query (H-2) tools в AG-1 graph из Phase 1. Расширь
tool_executor для multi-tool dispatch, добавь rag_retriever ноду и
conditional edge route_after_planner для трёх стратегий:
direct_llm / tools_needed / rag_first.

Контекст:
- AG-1 graph (AG-PROMPTS.md §2) — Phase 1 build_agent_graph(llm,
  token, tools) с planner + final_answer + tool_executor (для
  file_export). В Phase 2 tools расширяется до [file_export,
  web_search, rag_query] + добавляется rag_retriever нода.
- AG-4 file_export (AG-PROMPTS.md §5) — pattern для multi-tool
  registry: просто list в build_agent_graph. Pluggable registry —
  Phase 4 (ADR-009 pattern).
- ARCHITECT.md v1.2.0 §5.2.2 — graph nodes: planner, tool_executor,
  rag_retriever, mcp_invoker, final_answer. В Phase 2 реализуем
  planner + tool_executor + rag_retriever + final_answer (mcp_invoker
  — Phase 4 AG-7).
- ARCHITECT.md v1.2.0 §5.2.2 — conditional edges: route_after_planner
  (tools_needed → tool_executor; иначе → final_answer), route_after_tool
  (если новый tool message → обратно в planner; если final_answer_ready
  → END). Phase 2 расширяет route_after_planner третьей опцией:
  rag_first → rag_retriever.
- ТРИЗ-принцип 19 (переход в другое измерение): rag_retriever —
  отдельная нода, не внутри tool_executor. Это даёт точку перехвата
  для retrieval-specific logic без перегрузки tool_executor.
- ТРИЗ-принцип 17 (другое измерение): route_after_planner имеет 3
  выхода (direct_llm / tools_needed / rag_first), не 2 как в Phase 1.
  Это не усложняет graph — добавляется один conditional branch.

Задача:
1. Обнови `build_agent_graph` в `src/llm_client/agent/graph.py` для
   Phase 2 (расширь существующую Phase 1 реализацию):
   ```python
   from typing import Any, Literal
   from langchain_core.language_models import BaseChatModel
   from langchain_core.tools import BaseTool
   from langgraph.graph import END, StateGraph

   from ..rag.pipeline import RagPipeline
   from ..transport.cancel import CancellationToken
   from .cycle_detection import IterationMonitor
   from .tools.file_export import file_export  # AG-4, Phase 1
   from .tools.rag_query import rag_query       # H-2, Phase 2
   from .tools.web_search import web_search      # H-1, Phase 2


   # RouteDecision enum:
   RouteDecision = Literal["direct_llm", "tools_needed", "rag_first"]


   def build_agent_graph(
       llm: BaseChatModel,
       token: CancellationToken | None = None,
       tools: list[BaseTool] | None = None,
       rag_pipeline: RagPipeline | None = None,
       *,
       monitor: IterationMonitor | None = None,
       settings: dict | None = None,
   ) -> Any:
       '''Construct Phase 2 agent graph.

       Phase 2 extensions over Phase 1 (AG-1):
       - tools default = [file_export, web_search, rag_query] (если
         не передан явно).
       - rag_pipeline — singleton RagPipeline (H-2). None в тестах
         без RAG.
       - rag_retriever нода добавлена (если rag_pipeline не None).
       - route_after_planner расширен: 3 выхода (direct_llm /
         tools_needed / rag_first).
       - settings — из G-4 UI panel: tools_enabled, retrieval_strategy,
         reranker, top_k, max_results.

       Returns:
           Compiled LangGraph graph ready for graph.astream(state).
       '''
       if tools is None:
           # Default Phase 2 tools:
           tools = [file_export, web_search, rag_query]

       graph = StateGraph(dict)

       # ── Nodes ────────────────────────────────────────────────────

       async def planner(state: dict[str, Any]) -> dict[str, Any]:
           # Bind tools to LLM (ADR-006 native tool calling):
           bound_llm = llm.bind_tools(tools) if tools else llm
           response = await bound_llm.ainvoke(state["messages"])
           return {
               "messages": [response],
               "iteration": state.get("iteration", 0) + 1,
           }

       async def tool_executor(state: dict[str, Any]) -> dict[str, Any]:
           '''Dispatches tool_calls from last AIMessage to appropriate tool.

           In Phase 2: file_export (AG-4), web_search (H-1), rag_query (H-2).
           '''
           from langchain_core.messages import ToolMessage

           last_msg = state["messages"][-1]
           tool_calls = getattr(last_msg, "tool_calls", []) or []
           results = []
           for tc in tool_calls:
               tool_name = tc["name"]
               tool_args = tc["args"]
               tool_call_id = tc["id"]

               # Find tool by name:
               matching = [t for t in tools if t.name == tool_name]
               if not matching:
                   results.append(ToolMessage(
                       content=f"Tool {tool_name} not found",
                       tool_call_id=tool_call_id,
                   ))
                   continue
               tool = matching[0]

               try:
                   # Both sync and async tools supported:
                   if hasattr(tool, "arun"):
                       result = await tool.arun(tool_args)
                   else:
                       result = await tool.ainvoke(tool_args)
                   results.append(ToolMessage(
                       content=str(result),
                       tool_call_id=tool_call_id,
                   ))
               except Exception as e:
                   logger.exception("Tool %s failed", tool_name)
                   results.append(ToolMessage(
                       content=f"Error: {e}",
                       tool_call_id=tool_call_id,
                   ))

           return {"messages": results}

       async def rag_retriever(state: dict[str, Any]) -> dict[str, Any]:
           '''Retrieves RAG chunks, updates state for final_answer.'''
           if rag_pipeline is None:
               return {"retrieved_docs": []}

           # Extract last user message:
           messages = state.get("messages") or []
           last_user_msg = None
           for m in reversed(messages):
               if getattr(m, "type", "") == "human":
                   last_user_msg = m
                   break
           if last_user_msg is None:
               return {"retrieved_docs": []}

           query = last_user_msg.content if \
                   hasattr(last_user_msg, "content") else str(last_user_msg)
           top_k = (settings or {}).get("top_k", 5)

           result = await rag_pipeline.retrieve(query, top_k=top_k)
           return {"retrieved_docs": result["chunks"]}

       def final_answer(state: dict[str, Any]) -> dict[str, Any]:
           # Если retrieved_docs не пустой — добавить их в context
           # для LLM в final_answer generation:
           # (в Phase 2 simplified — final_answer — это просто
           # extraction последнего AIMessage content; в Phase 3+ будет
           # отдельная LLM generation с retrieved_docs в system prompt)
           messages = state.get("messages") or []
           if messages:
               last = messages[-1]
               content = last.content if hasattr(last, "content") else str(last)
           else:
               content = ""
           return {"final_answer": content, "messages": []}

       graph.add_node("planner", planner)
       graph.add_node("tool_executor", tool_executor)
       if rag_pipeline is not None:
           graph.add_node("rag_retriever", rag_retriever)
       graph.add_node("final_answer", final_answer)

       # ── Conditional edges ─────────────────────────────────────────

       def route_after_planner(state: dict[str, Any]) -> str:
           # Cancel check (C-4):
           if token is not None and token.is_cancelled:
               return END

           # Cycle detection:
           if monitor is not None and monitor.check(state):
               return END

           # Iteration limit:
           if state.get("iteration", 0) >= state.get("max_iterations", 10):
               return END

           last_msg = state["messages"][-1]

           # 1. Если LLM вернул tool_calls —> tool_executor:
           if getattr(last_msg, "tool_calls", None):
               return "tool_executor"

           # 2. Если route_decision=="rag_first" в state (set by
           # planner LLM через structured output — Phase 3+; в Phase 2
           # simplified heuristic: если в last user message есть слова
           # "найди", "search", "find", "документ" и rag_pipeline not
           # None —> rag_retriever):
           user_msg = None
           for m in reversed(state.get("messages") or []):
               if getattr(m, "type", "") == "human":
                   user_msg = m
                   break
           if user_msg and rag_pipeline is not None:
               content_lower = (getattr(user_msg, "content", "") or "").lower()
               rag_triggers = ("найди", "search", "find", "документ",
                               "look up", "поиск")
               if any(t in content_lower for t in rag_triggers):
                   return "rag_retriever"

           # 3. Default — direct LLM, final_answer:
           return "final_answer"

       graph.set_entry_point("planner")
       graph.add_conditional_edges(
           "planner",
           route_after_planner,
           {
               "tool_executor": "tool_executor",
               "rag_retriever": "rag_retriever" if rag_pipeline else "final_answer",
               "final_answer": "final_answer",
               END: END,
           },
       )
       # tool_executor → back to planner (для интерпретации tool result):
       graph.add_edge("tool_executor", "planner")
       # rag_retriever → final_answer (после retrieval — формируем ответ):
       if rag_pipeline is not None:
           graph.add_edge("rag_retriever", "final_answer")
       graph.add_edge("final_answer", END)

       return graph.compile()
   ```

2. Обнови POST /sessions/{session_id}/chat endpoint в
   `src/llm_client/agent/service.py` (AG-0) для приёма settings (G-4):
   ```python
   @app.post("/sessions/{session_id}/chat")
   async def start_chat(session_id: str, body: ChatRequest):
       '''Body: {message: str, user_id?: str, settings?: dict}.
       settings — from G-4 UI panel (tools_enabled, retrieval_strategy,
       reranker, top_k, max_results).'''
       settings = body.settings or {}
       # Filter tools_enabled:
       tools = []
       for name in settings.get("tools_enabled",
                                  ["file_export", "web_search", "rag_query"]):
           if name == "file_export":
               tools.append(file_export)
           elif name == "web_search":
               tools.append(web_search)
           elif name == "rag_query":
               tools.append(rag_query)
       # Build pipeline with settings (retrieval_strategy, reranker):
       rag_pipeline = RagPipeline.from_settings_with_overrides(
           get_settings(), settings
       )
       # Build graph:
       graph = build_agent_graph(
           llm=llm_provider,
           token=token,
           tools=tools or None,
           rag_pipeline=rag_pipeline,
           settings=settings,
       )
       # Start graph async:
       asyncio.create_task(graph.astart({"messages": [...], ...}))
       return {"status": "ok", "session_id": session_id}
   ```

3. Тесты в `src/llm_client/agent/test_graph.py` (расширь
   существующий):
   - `test_build_agent_graph_phase2_default_tools` — tools=None →
     default [file_export, web_search, rag_query].
   - `test_build_agent_graph_phase2_custom_tools` — tools=[web_search]
     only.
   - `test_route_after_planner_tool_calls` — last AIMessage с
     tool_calls → route "tool_executor".
   - `test_route_after_planner_rag_first` — user message "найди
     документацию" → route "rag_retriever".
   - `test_route_after_planner_direct_llm` — user message "привет"
     → route "final_answer".
   - `test_tool_executor_dispatches_web_search` — mock LLM возвращает
     tool_call("web_search", {query: "test"}) → tool_executor
     вызывает web_search (mock) → ToolMessage с list[dict].
   - `test_tool_executor_dispatches_rag_query` — аналогично для
     rag_query.
   - `test_tool_executor_unknown_tool` — tool_call("unknown_tool") →
     ToolMessage "Tool unknown_tool not found".
   - `test_tool_executor_tool_error` — mock tool raises → ToolMessage
     "Error: ...".
   - `test_rag_retriever_node_no_pipeline` — rag_pipeline=None →
     retrieved_docs=[].
   - `test_rag_retriever_node_with_pipeline` — rag_pipeline mock
     returns 3 chunks → state["retrieved_docs"] содержит 3 chunks.
   - `test_settings_filter_tools_enabled` — settings={tools_enabled:
     ["file_export"]} → graph build with only file_export (no web_search,
     no rag_query).

Definition of Done:
- `build_agent_graph` в `src/llm_client/agent/graph.py` расширена:
  tools default = [file_export, web_search, rag_query], rag_pipeline
  параметр, rag_retriever нода, route_after_planner 3 выхода.
- POST /sessions/{id}/chat в `src/llm_client/agent/service.py` принимает
  settings field, фильтрует tools, строит rag_pipeline с overrides.
- 12+ новых тестов зелёные.
- Manual test: POST /chat с settings={tools_enabled:["file_export",
  "web_search"], retrieval_strategy:"hybrid", reranker:"bge"} → agent
  build graph с этими настройками, web_search available, rag_query
  not (filtered out).
- Существующие test_graph.py — не регрессируют (Phase 1 path без
  rag_pipeline и с tools=[file_export] всё ещё работает через
  явную передачу tools параметра).

Антипаттерны:
- НЕ хардкодь tools list внутри build_agent_graph — только default
  (если tools=None). Параметр tools имеет приоритет.
- НЕ создавай rag_pipeline внутри build_agent_graph — передавай через
  параметр. Если создавать внутри — singleton нарушается, embeddings
  model loaded per graph build = +5 sec latency.
- НЕ хардкодь "найди", "search" triggers — вынеси в Settings
  rag_triggers list (default ["найди", "search", "find", "документ",
  "look up", "поиск"]). В Phase 3+ это заменится на LLM structured
  output route_decision field.
- НЕ возвращай graph с rag_retriever нодой если rag_pipeline=None —
  graph.add_edge("rag_retriever", ...) только если rag_pipeline not
  None. Иначе conditional edge route "rag_retriever" приведёт к
  KeyError.
- НЕ передавай settings в graph nodes напрямую — settings = параметр
  build_agent_graph, используется в closure для rag_retriever (top_k).
  Не "протаскивать" через state — state чисто для graph dataflow.
- НЕ делай tool_executor синхронным — только async. Sync tool_executor
  блокирует event loop graph.astream.
- НЕ хардкодь tool_call_id format — берётся из last_msg.tool_calls[i]["id"].
  LangChain format, не переопределять.
- НЕ забудь CycleMonitor integration — после добавления rag_retriever
  cycle detection всё ещё работает (monitor.check(state) после
  planner).
- НЕ добавляй human_review ноду — это Phase 4 (mcp_invoker с
  human_review для тяжёлых действий). Phase 2 — нет human-in-the-loop.
- НЕ забудь route_after_planner END case — если iteration >=
  max_iterations → END. Это защита от зацикливания (planner ↔
  tool_executor ↔ planner loop).

Связанные ADR:
- Расширяет: AG-1 (build_agent_graph — Phase 1 → Phase 2), AG-0
  (POST /chat — settings field добавлен).
- Применяет: ADR-001 (LangGraph — rag_retriever нода), ADR-003
  (VectorStoreFactory — через RagPipeline), ADR-005 (Tool Layer —
  bind_tools(tools)), ADR-006 (native tool calling), ADR-017 (reranker
  через RagPipeline), ADR-020 (hybrid через RagPipeline).
- Зависит от: H-1 (web_search), H-2 (rag_query + RagPipeline), AG-4
  (file_export — pattern, не переопределяется).
- Не затрагивает: ADR-010 (checkpoint — graph state автоматически),
  ADR-013 (cancel — token проверяется в route_after_planner, как в
  Phase 1), ADR-014 (PII — на indexing time, не в graph).
```

### H-4. SSE event protocol extension: `event: tool_call` / `event: tool_result` / `event: retrieved_docs`

```
Ты — Backend/Agent-разработчик LLM Client. Расширь SSE event protocol
из AG-3 (AG-PROMPTS.md §4, реализован в Phase 1) для Phase 2: добавь
3 новых события для tool-call lifecycle. UI (Блок G-1) слушает эти
события и рендерит tool-call previews / RAG citations / web search
results.

Контекст:
- AG-3 SSE (AG-PROMPTS.md §4, реализован в Phase 1) эмитит 6 событий:
  token, metadata, artifact_ready, cancelled, error, done. В Phase 2
  добавляются tool_call, tool_result, retrieved_docs — для отображения
  tool lifecycle в UI (Блок G).
- SSE format — RFC 8895-style (см. src/llm_client/ui/chat.py
  iter_sse_events): каждое событие — `event: <name>\n` + `data:
  <json>\n` + `\n` (separator). Heartbeat `: keepalive\n\n` каждые
  15 сек.
- AG-1 graph (H-3) — graph.astream(...) отдаёт chunks: AIMessage
  chunks (tokens), ToolMessage (tool results), dict updates
  (retrieved_docs). Stream generator (AG-3) парсит chunks и эмитит
  соответствующие SSE events.
- ТРИЗ-принцип 17 (переход в другое измерение): tool lifecycle events
  — отдельные SSE events, не смешиваются с token streaming. Это
  даёт UI точку перехвата для render_tool_call (G-1) без парсинга
  всего стрима.
- ТРИЗ-принцип 1 (сегментация): tool_call и tool_result — separate
  events, не один "tool_event" с all-fields. Это даёт UI возможность
  progressive rendering (preview running → preview done).

Задача:
1. Обнови stream_generator в `src/llm_client/agent/service.py`
   (AG-0) для Phase 2 (расширь существующий из Phase 1):
   ```python
   import json
   from typing import AsyncIterator
   from langchain_core.messages import AIMessage, ToolMessage

   async def stream_generator(graph, session_id: str) -> AsyncIterator[str]:
       '''Yields SSE events from graph.astream(...).

       Phase 1 events: token, metadata, artifact_ready, cancelled,
                       error, done.
       Phase 2 events (new): tool_call, tool_result, retrieved_docs.
       '''
       try:
           async for chunk in graph.astream(
               {"messages": ...},  # state from session
               stream_mode="values",
           ):
               # chunk может быть: AIMessage (with content + tool_calls),
               # ToolMessage, dict (state update с retrieved_docs).

               if isinstance(chunk, AIMessage):
                   # 1. Token streaming (если есть content):
                   if chunk.content:
                       for token in (chunk.content if isinstance(chunk.content, str)
                                     else [chunk.content]):
                           yield f"event: token\ndata: {json.dumps({'token': token})}\n\n"

                   # 2. Tool calls (если AIMessage содержит tool_calls):
                   for tc in (chunk.tool_calls or []):
                       tool_call_event = {
                           "tool_call_id": tc["id"],
                           "tool_name": tc["name"],
                           "args": tc["args"],
                       }
                       yield f"event: tool_call\ndata: {json.dumps(tool_call_event)}\n\n"

               elif isinstance(chunk, ToolMessage):
                   # 3. Tool result (когда tool_executor возвращает
                   # ToolMessage):
                   tool_result_event = {
                       "tool_call_id": chunk.tool_call_id,
                       "tool_name": _infer_tool_name_from_tool_call_id(
                           chunk.tool_call_id, graph
                       ),
                       "preview": _build_tool_result_preview(chunk.content),
                       "full_results": _parse_tool_full_results(chunk.content),
                   }
                   yield f"event: tool_result\ndata: {json.dumps(tool_result_event)}\n\n"

               elif isinstance(chunk, dict) and "retrieved_docs" in chunk:
                   # 4. Retrieved docs (когда rag_retriever нода
                   # возвращает state update с retrieved_docs):
                   chunks_data = chunk.get("retrieved_docs", [])
                   retrieved_event = {
                       "tool_call_id": _get_last_rag_query_call_id(graph),
                       "chunk_count": len(chunks_data),
                       "top_score": chunks_data[0]["score"] if chunks_data else 0.0,
                       "source_uris": [c.get("source_uri") for c in chunks_data
                                        if c.get("source_uri")],
                       "chunks": chunks_data,
                   }
                   yield f"event: retrieved_docs\ndata: {json.dumps(retrieved_event)}\n\n"

               # Heartbeat (каждые 15 сек — упрощённо, в реальном коде
               # через asyncio.timeout):
               # yield ": keepalive\n\n"

           # Final event:
           yield "event: done\ndata: {}\n\n"

       except asyncio.CancelledError:
           yield f"event: cancelled\ndata: {json.dumps({'reason': 'user_cancelled'})}\n\n"
       except Exception as e:
           yield f"event: error\ndata: {json.dumps({'message': str(e), 'type': type(e).__name__})}\n\n"
   ```

2. Создай helper functions в `src/llm_client/agent/service.py`:
   ```python
   def _build_tool_result_preview(tool_message_content: str) -> dict:
       '''Builds short preview dict for tool_call preview (G-1).

       For web_search: {snippet_count: N}.
       For rag_query: {chunk_count: N, top_score: float}.
       For file_export: {artifact_id, format, filename} (legacy —
                         artifact_ready event в Phase 1, здесь для
                         полноты).
       '''
       try:
           result = json.loads(tool_message_content)
       except (json.JSONDecodeError, TypeError):
           return {}

       if isinstance(result, list):
           # web_search returns list[dict]:
           return {"snippet_count": len(result)}
       if isinstance(result, dict):
           if "chunks" in result:
               # rag_query:
               return {
                   "chunk_count": result.get("chunk_count", len(result["chunks"])),
                   "top_score": result.get("top_score", 0.0),
               }
           if "artifact_id" in result:
               # file_export:
               return {
                   "artifact_id": result["artifact_id"],
                   "format": result.get("format"),
                   "filename": result.get("filename"),
               }
       return {}


   def _parse_tool_full_results(tool_message_content: str) -> list[dict] | None:
       '''Parses tool_message_content for full results (G-3 web search).

       For web_search: returns list[{title, url, snippet, score}].
       For rag_query: returns None (chunks через retrieved_docs event,
                       не tool_result).
       For file_export: returns None (artifact через artifact_ready
                         event из Phase 1).
       '''
       try:
           result = json.loads(tool_message_content)
       except (json.JSONDecodeError, TypeError):
           return None

       if isinstance(result, list):
           # web_search results:
           return result
       return None


   def _infer_tool_name_from_tool_call_id(tool_call_id: str, graph) -> str:
       '''Looks up tool_name by tool_call_id from graph state messages.'''
       # Simplified — в реальном коде через graph.get_state(...) или
       # tracking pending tool_calls в stream_generator closure:
       for msg in (graph.state.get("messages") or []):
           if hasattr(msg, "tool_calls"):
               for tc in (msg.tool_calls or []):
                   if tc["id"] == tool_call_id:
                       return tc["name"]
       return "unknown"
   ```

3. Обнови SSE parser в `src/llm_client/ui/chat.py` `iter_sse_events`
   (Phase 1) для понимания новых event types:
   ```python
   async def iter_sse_events(response: httpx.Response) -> AsyncIterator[dict]:
       '''Parses SSE events from agent-service stream endpoint.

       Phase 1: token, metadata, artifact_ready, cancelled, error, done.
       Phase 2 (new): tool_call, tool_result, retrieved_docs.
       '''
       event_type = None
       data_buffer = []

       async for line in response.aiter_lines():
           if line.startswith("event: "):
               event_type = line[len("event: "):].strip()
           elif line.startswith("data: "):
               data_buffer.append(line[len("data: "):])
           elif line == "" and event_type is not None:
               # End of event — yield:
               data = json.loads("".join(data_buffer)) if data_buffer else {}
               yield {"event": event_type, "data": data}
               event_type = None
               data_buffer = []
           # Ignore heartbeat lines (": keepalive") and others.
   ```

4. Тесты в `tests/unit/test_sse.py` (расширь существующий):
   - `test_stream_generator_emits_tool_call` — graph mock yields
     AIMessage с tool_calls=[{id: "1", name: "web_search", args:
     {query: "test"}}] → stream emits event: tool_call с
     {tool_call_id, tool_name, args}.
   - `test_stream_generator_emits_tool_result_web_search` — ToolMessage
     с content='[{title,url,snippet}]' → stream emits event: tool_result
     с {tool_call_id, tool_name="web_search", preview={snippet_count:
     1}, full_results=[...]}.
   - `test_stream_generator_emits_tool_result_rag_query` — ToolMessage
     с content='{"chunks": [...], "chunk_count": 5, "top_score": 0.9}'
     → stream emits event: tool_result с preview={chunk_count: 5,
     top_score: 0.9}, full_results=None.
   - `test_stream_generator_emits_retrieved_docs` — graph yields
     {"retrieved_docs": [chunk1, chunk2]} → stream emits event:
     retrieved_docs с {tool_call_id, chunk_count: 2, top_score,
     source_uris, chunks}.
   - `test_stream_generator_token_interleaved_with_tool_events` —
     graph yields AIMessage("Hello"), AIMessage с tool_call,
     ToolMessage, AIMessage("final answer") → stream emits event:
     token × 2, event: tool_call × 1, event: tool_result × 1, event:
     token × 1, event: done.
   - `test_iter_sse_events_parses_tool_call` — raw SSE "event:
     tool_call\ndata: {...}\n\n" → parsed as {event: "tool_call",
     data: {...}}.
   - `test_iter_sse_events_parses_retrieved_docs` — аналогично для
     retrieved_docs.
   - `test_iter_sse_events_ignores_heartbeat` — ": keepalive\n\n"
     → не эмитит event.
   - Integration: full flow graph.astream → stream_generator → SSE
     response → iter_sse_events → handle_tool_event (G-1) → UI render.

Definition of Done:
- `stream_generator` в `src/llm_client/agent/service.py` расширена:
  emits tool_call, tool_result, retrieved_docs events в дополнение
  к Phase 1 events (token, metadata, artifact_ready, cancelled, error,
  done).
- Helper functions `_build_tool_result_preview` и
  `_parse_tool_full_results` имплементированы.
- `iter_sse_events` в `src/llm_client/ui/chat.py` понимает новые event
  types.
- 9+ новых тестов зелёные.
- Manual test: POST /chat → GET /stream → видно последовательность:
  event: tool_call (web_search) → event: tool_result → event: token ×
  N → event: done. UI (G-1, G-3) рендерит tool-call preview и web
  search results panel.
- Существующие test_sse.py — не регрессируют.

Антипаттерны:
- НЕ эмить PII в tool_call event args — для file_export content
  truncate до 200 символов с "..." (на стороне UI в G-1, но также
  можно в stream_generator). В Phase 2 — UI truncation (G-1), в
  Phase 3+ рассмотрим server-side truncation.
- НЕ объединять tool_call и tool_result в один event — UI (G-1)
  progressive rendering: preview running → preview done. Один event
  не дал бы этого UX.
- НЕ эмить full chunks в tool_result event для rag_query — chunks
  идут через отдельное event retrieved_docs. tool_result для rag_query
  — только preview (chunk_count, top_score).
- НЕ эмить artifact_ready (Phase 1 event) для web_search/rag_query —
  только для file_export. web_search и rag_query не генерируют
  artifacts (файлы), только results.
- НЕ хардкодь "web_search" и "rag_query" в _build_tool_result_preview —
  распознавание по структуре data (list → web_search, dict с chunks →
  rag_query, dict с artifact_id → file_export).
- НЕ забывай heartbeat `: keepalive\n\n` — без него proxy закрывает
  connection через 60 сек. В stream_generator через asyncio.timeout
  или async iterator with periodic yield.
- НЕ эмить event: done после event: cancelled или event: error —
  terminal события последние (наследовано из AG-3 Phase 1).
- НЕ эмить event: tool_call если tool_calls=[] — пустой tool_calls
  не должен генерировать events.
- НЕ хардкодь tool_call_id format — берётся из LangChain AIMessage.
  tool_calls[i]["id"].
- НЕ теряй token events при interleaving с tool events — stream
  generator должен yield всех событий по порядку (tokens для
  content AIMessage, tool_calls для tool_calls field).

Связанные ADR:
- Расширяет: AG-3 (SSE event protocol +3 events — tool_call,
  tool_result, retrieved_docs).
- Применяет: ADR-007 (SSE — RFC 8895-style, heartbeat).
- Зависит от: H-3 (graph integration — graph.astream yields
  AIMessage/ToolMessage/dict), G-1 (UI handle_tool_event —
  consumer).
- Не затрагивает: ADR-013 (cancel — event: cancelled остаётся),
  ADR-014 (PII — в args truncation на UI side, G-1), ADR-010
  (checkpoint — graph state автоматически сериализует ToolMessage,
  не влияет на SSE event emission).
```

---

## 7. Блок E. Тесты и CI для Phase 2

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
(MVP-PROMPTS.md Блок F-4 + AG-PROMPTS.md §6 (future, создать в Phase 1
конце) + UI-PROMPTS.md §11 (future, создать в Phase 1 конце)) для
Phase 2: добавь jobs для ADR-010/017/020 тестов + AG-5/AG-6 tool
тестов + UI-расширений (Блок G) тестов, обнови nightly pipeline.

Контекст:
- MVP-PROMPTS.md Блок F-4 создал Phase 1 CI baseline:
  - PR-pipeline: lint + unit + integration-dev + integration-staging + pii-
    leak-audit + minio-parity.
  - Nightly: cancel-latency-staging + minio-parity-full + idealidad-metric.
- AG-PROMPTS.md Приложение (Phase 1 конец) добавит AG-0..AG-4 тесты
  (test_graph.py, test_provider.py, test_sse.py, test_file_export.py).
- UI-PROMPTS.md §11 (Phase 1 конец) добавит UI-0..UI-3 тесты
  (test_ui_render.py, test_ui_streamlit_client.py, test_ui_chat.py,
  test_ui_session.py, test_ui_sidebar.py, latency_benchmark.py).
- Phase 2 добавляет 3 new ADR (010, 017, 020) — каждый требует testing.
- Phase 2 добавляет 2 new AG-расширения (AG-5 web_search, AG-6 rag_query)
  — каждый требует unit + integration тестов.
- Phase 2 добавляет 4 new UI-расширения (G-1..G-4) — каждый требует
  unit тестов (test_ui_render.py extension).
- ROADMAP.md v1.2.0 §6.6 — критерии выхода Phase 2.

Задача:
1. Расширь `.github/workflows/phase1-ci.yml` (или эквивалент) — добавь
   PR-pipeline jobs:
   - `checkpoint-quick`: Блок E-1 quick-test (100 сэмплов), PASS p99 <5 мс.
     <2 мин.
   - `bm25-indexing-regression`: Блок E-4 BM25 indexing unit-test. <30 сек.
   - `reranker-quick`: Блок E-3 quick-test (10 queries), no regression vs
     main. <3 мин.
   - `hybrid-rag-quick`: Блок E-4 quick-test (15 queries), no regression.
     <5 мин.
   - `web-search-quick` (new для AG-5): test_web_search.py с mock Tavily
     API (httpx mocking), no real API calls в PR-pipeline. <1 мин.
   - `rag-query-quick` (new для AG-6): test_rag_query.py + test_graph.py
     extension (rag_retriever node) с mock RagPipeline. <2 мин.
   - `ui-render-phase2-quick` (new для Блока G): test_ui_render.py
     extension — render_tool_call, render_rag_citations,
     render_web_search_results, render_settings_panel, handle_tool_event.
     <1 мин.
2. Обнови `.github/workflows/phase1-nightly.yml` (или создай `phase2-nightly
   .yml`):
   - `checkpoint-latency-staging`: Блок E-1 full (1000 сэмплов), p99 <2 мс.
     <10 мин.
   - `checkpoint-recovery-staging`: Блок E-2 (4 scenarios). <20 мин.
   - `reranker-ab-test-staging`: Блок E-3 full (50+ queries). <10 мин.
   - `hybrid-rag-ab-test-staging`: Блок E-4 full (30 queries). <10 мин.
   - `web-search-integration-staging` (new для AG-5): real Tavily API call
     (через STAGING_TAVILY_API_KEY secret), 5 queries, validates 200 OK
     + result schema. <3 мин.
   - `rag-query-integration-staging` (new для AG-6): real vector store
     (PGVector on staging), 10 queries, validates chunks returned +
     reranker applied (top_score in [0, 1]). <5 мин.
   - `sse-tool-events-staging` (new для Блока H-4 + G-1): full flow POST
     /chat + GET /stream с web_search prompt → validates event: tool_call
     + event: tool_result + event: retrieved_docs (если rag_query) +
     event: done. <2 мин.
   - `idealidad-metric`: обнови под Phase 2 metrics (Блок F-2).
3. Кэширование (расширь Phase 1):
   - `~/.cache/huggingface` для bge-reranker (Блок A-2) — large cache, days.
   - `models/bge-reranker-base/` volume (если не через cache).
4. Artefacts (расширь Phase 1):
   - `checkpoint_latency_report_{date}.json` (E-1).
   - `checkpoint_recovery_report_{date}.json` (E-2).
   - `ab_test_reranker_{date}.json` (E-3).
   - `ab_test_hybrid_rag_{date}.json` (E-4).
   - `web_search_integration_report_{date}.json` (new для AG-5).
   - `rag_query_integration_report_{date}.json` (new для AG-6).
   - `sse_tool_events_report_{date}.json` (new для Блока H-4).
   - Все хранить 30 дней (наследовано из Phase 1).
5. Staging secrets (через GitHub Secrets / GitLab Variables):
   - `COHERE_API_KEY` (опционально, для CohereRerankAdapter testing).
   - `STAGING_REDIS_URL`, `STAGING_POSTGRES_URL` (если separate от CI
     runner).
   - `STAGING_TAVILY_API_KEY` (new для AG-5 integration tests).
   - `STAGING_OPENAI_API_KEY` (наследовано из Phase 1 AG-2).
6. Локальный запуск (расширь `make ci-local`):
   - `make ci-local-quick` — запускает PR-pipeline jobs локально.
   - `make ci-local-staging` — запускает nightly jobs на staging (manual).
   - Тот же docker-compose + pytest, что в CI.

Definition of Done:
- PR-pipeline завершается за <30 минут (parallel jobs, 8 новых quick-
  tests добавили ~18 мин к Phase 1 baseline 15 мин = 33 мин, с
  parallelism 12 мин).
- Nightly pipeline завершается за <80 минут (7 new jobs).
- При FAIL — понятное сообщение в PR с ссылкой на artefact.
- Coverage report показывает % покрытия ADR-010 (Блок B), ADR-017 (Блок C),
  ADR-020 (Блок D), AG-5 (Блок H-1), AG-6 (Блок H-2), G-1..G-4 (Блок G).
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
- НЕ делай real Tavily API calls в PR-pipeline — только mock. Real calls
  — nightly only (cost + rate limit 1000/month free tier).
- НЕ делай real OpenAI API calls в CI — только mock LLM (FakeListChatModel
  из LangChain, как в test_graph.py AG-1). Real LLM calls — manual
  integration test only.
- НЕ пропускай UI тесты (Блок G) — они unit, <1 мин, ловят
  regression в handle_tool_event / render_tool_call контрактах.

Связанные ADR:
- Покрывает CI для: ADR-010 (Блок B + E-1, E-2), ADR-017 (Блок C + E-3),
  ADR-020 (Блок D + E-4), AG-5 (Блок H-1), AG-6 (Блок H-2), G-1..G-4
  (Блок G).
- Расширяет: Блок F-4 MVP-PROMPTS (Phase 1 CI) + AG-PROMPTS §6 (future)
  + UI-PROMPTS §11 (future).
- Зависит от: Блок A-1..A-3 (infra для Phase 2), Блоки B/C/D (реализации),
  Блоки E-1..E-4 (тесты), Блок G (UI-расширения), Блок H (AG-расширения).
```

---

## 8. Блок F. Документация и метрика идеальности

**Источник**: `ROADMAP.md` v1.2.0 §6.6 п.5 (документация обновлена), §15.2 (метрика идеальности Phase 2 control point), §18.2 (Grafana + Slack alerting). Расширяет Phase 1 Блок G `MVP-PROMPTS.md` и Phase 1 AG-PROMPTS §6 (future).

### F-1. Обновление `ARCHITECT.md` §7 / §8 / §12 после Phase 2

```
Ты — Tech-писатель / архитектор LLM Client. Обнови `ARCHITECT.md` после
завершения Phase 2: добавь новые ADR (010, 017, 020), пометь противоречия
C-2, C-6 как resolved, обнови component diagram, добавь AG-5/AG-6
описание в §5.2.4 Tool Layer, обнови §5.2.2 Orchestration с rag_retriever
нодой, обнови §5.2.5 RAG Layer с RagPipeline.

Контекст:
- ROADMAP.md v1.2.0 §6.6 п.5: "ARCHITECT.md § 7 ADR обновлён (ADR-010,
  ADR-017, ADR-020 добавлены); § 8 Trade-offs обновлён (C-2, C-6 помечены
  как resolved)".
- ROADMAP.md §18.5: "После approval каждого ADR — обновление ARCHITECT.md.
  Срок: 1 день после approval."
- MVP-PROMPTS.md Блок G-1 — аналог для Phase 1; паттерн переиспользуется.
- AG-PROMPTS.md §6 (future, создать в Phase 1 конце) — аналог для AG-0..AG-4;
  ALPHA-PROMPTS.md v1.1.0 Блок F-1 расширяет его для AG-5/AG-6.
- BACKLOG.md v1.1.0 §3.4 — AG-5/AG-6 формализованы как Phase 2 работы.
- ARCHITECT.md v1.2.0 §5.2.4 (Tool Layer) — уже упоминает web_search и
  file_export как примеры @tool; F-1 добавляет rag_query к ним.
- ARCHITECT.md v1.2.0 §5.2.2 (Orchestration) — упоминает rag_retriever
  ноду; F-1 фиксирует её Phase 2 реализацию (H-2/H-3).
- ARCHITECT.md v1.2.0 §5.2.5 (RAG Layer) — упоминает pipeline (vector →
  BM25 → fusion → reranker); F-1 фиксирует RagPipeline class (H-2).

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
   - Добавить `RagPipeline` (class H-2) в RAG Layer — композирует retriever
     + reranker на основе RetrieverConfig.
   - Добавить `rag_retriever` ноду в Orchestration Layer (между planner и
     final_answer).
   - Добавить `web_search` tool + `rag_query` tool в Tool Layer (§5.2.4)
     рядом с `file_export` (Phase 1).
   - Показать PostgreSQL с двумя extensions: pgvector (existing) + tsvector
     (new).
5. В §5.2.2 (Orchestration):
   - Обновить: "PostgresSaver (ADR-001)" → "RedisPostgresCheckpointer
     (ADR-010, Phase 2; composite sync Redis + async PG; PostgresSaver
     deprecated, только для backward-compat tests)".
   - Добавить описание rag_retriever ноды (H-2/H-3): "rag_retriever —
     Phase 2 (AG-6). Извлекает RAG chunks через RagPipeline, обновляет
     state['retrieved_docs'] для final_answer. Вызывается когда planner
     выбирает route_decision='rag_first' (в Phase 2 — heuristic по
     ключевым словам; в Phase 3+ — LLM structured output)."
   - Обновить conditional edges: route_after_planner теперь 3 выхода
     (direct_llm / tools_needed / rag_first) — Phase 1 был 1 выход.
6. В §5.2.4 (Tool Layer):
   - Добавить rag_query к примерам @tool: `RagQueryArgs` + `rag_query`
     (H-2 contract).
   - Обновить: "В Phase 1 реализован только file_export (AG-4). Phase 2
     добавляет web_search (AG-5, через Tavily API) и rag_query (AG-6,
     через RagPipeline). Phase 4 добавит mcp_call (AG-7, через
     MCPTransport)."
7. В §5.2.5 (RAG Layer):
   - Обновить pipeline: "...vector top-20 + BM25 top-20 → RRF fusion top-50
     → reranker top-5" (ADR-020 + ADR-017).
   - Обновить RetrieverConfig fields (D-1).
   - Добавить RagPipeline class (H-2): "RagPipeline — композирует retriever
     (VectorRetriever / HybridRetriever / BM25Retriever) + reranker
     (BgeRerankerAdapter / CohereRerankAdapter / identity) на основе
     RetrieverConfig. Создаётся как singleton при agent-service startup.
     Используется rag_query @tool и rag_retriever нодой — single source of
     truth."
8. В §5.1 (Presentation Layer):
   - Обновить: "chat_component: Рендеринг сообщений, streaming tokens,
     tool-call previews (G-1, Phase 2)" — реализовано.
   - Обновить: "settings_panel: Выбор провайдера/модели, температура,
     max_tokens, tools on/off, retrieval_strategy (ADR-020), reranker
     (ADR-017)" — реализовано (G-4, Phase 2).
   - Добавить: "RAG citations panel (G-2, Phase 2) и web search results
     panel (G-3, Phase 2) — расширения chat_component для отображения
     результатов AG-5/AG-6."
9. В §7 (ADRs) добавить AG-расширения Approved в Phase 2:
   - AG-5 (web_search tool via Tavily) — Status: Approved. Применяет
     ADR-005 (Tool Layer) + ADR-006 (native tool calling через bind_tools).
   - AG-6 (rag_query tool + base RAG pipeline + rag_retriever нода) —
     Status: Approved. Применяет ADR-003 (VectorStoreFactory) + ADR-001
     (LangGraph rag_retriever нода). Расширяется ADR-017 (reranker) и
     ADR-020 (hybrid retrieval).
10. Согласованность с ROADMAP/TRIZ:
    - В §7 ARCHITECT.md для каждого ADR — ссылка на соответствующий § в
      ROADMAP.md (§6.3, §6.4, §6.5) и TRIZ-ANALYSIS.md (§5.2, §6.1, §11).
    - Для AG-5/AG-6 — ссылка на ROADMAP.md §6.2.4/§6.2.5 и BACKLOG.md
      v1.1.0 §3.4.

Definition of Done:
- ARCHITECT.md версия обновлена (1.2.0 → 1.3.0) с changelog.
- Changelog: "1.3.0 (2026-09-XX): Phase 2 завершена — добавлены ADR-010,
  ADR-017, ADR-020; C-2 помечено [RESOLVED]; C-6 помечено [PARTIALLY
  RESOLVED, ADR-011 pending Phase 3]; Q-5 частично закрыт; component
  diagram обновлён с Redis DB 1, RerankerRegistry, HybridRetriever,
  BM25IndexBuilder, RagPipeline, rag_retriever нодой, web_search и
  rag_query tools; §5.2.2 Checkpointer обновлён на RedisPostgresCheckpointer
  + rag_retriever нода; §5.2.4 Tool Layer обновлён с AG-5 web_search и
  AG-6 rag_query; §5.2.5 RAG pipeline обновлён на hybrid + reranker +
  RagPipeline class; §5.1 Presentation Layer обновлён с tool-call
  previews, settings_panel, RAG citations, web search results panels;
  AG-5 и AG-6 помечены Approved в §7."
- §7 содержит ADR-010, ADR-017, ADR-020 (новые) + AG-5, AG-6 (новые).
- §8 содержит 2 помеченных [RESOLVED] / [PARTIALLY RESOLVED] противоречия.
- §12 содержит Q-5 [PARTIALLY CLOSED].
- §13 компонентная диаграмма обновлена.
- §5.1, §5.2.2, §5.2.4, §5.2.5 — обновлены в соответствии с Блоками G, H.
- Все ссылки на ROADMAP.md / TRIZ-ANALYSIS.md / BACKLOG.md / AG-PROMPTS.md /
  UI-PROMPTS.md — корректны (не 404).
- PR с обновлением reviewed архитектурным комитетом, merged.

Антипаттерны:
- НЕ удаляй старые Trade-offs — оставь для исторического контекста с
  [RESOLVED] меткой.
- НЕ скрывай упразднённый PostgresSaver — явно пометь "deprecated in Phase
  2, replaced by RedisPostgresCheckpointer".
- НЕ переписывай ADR-001, ADR-003, ADR-005, ADR-006, ADR-007, ADR-008,
  ADR-013, ADR-014 (Phase 1) — только обнови cross-references если нужно.
- НЕ добавляй ADR из Phase 3+ (ADR-011, ADR-015, ADR-016, ADR-018, ADR-019)
  — только Phase 2 ADR + AG-5/AG-6.
- НЕ забудь changelog — без него невозможно отследить что изменилось.
- НЕ забудь обновить §5.2.4 Tool Layer с rag_query — это новое ADR-005
  применение (AG-6), должно быть в архитектурной документации.
- НЕ забудь обновить §5.1 с tool-call previews и settings_panel — эти
  UI-компоненты упоминались в v1.2.0 как "ответственность", но не были
  реализованы; v1.3.0 помечает их как реализованные (Блок G).

Связанные ADR:
- Документирует: ADR-010, ADR-017, ADR-020, AG-5 (H-1), AG-6 (H-2).
- Ссылается на: ROADMAP.md v1.2.0 §6, TRIZ-ANALYSIS.md §5.2, §6.1, §11,
  BACKLOG.md v1.1.0 §3.4.
- Расширяет: Блок G-1 MVP-PROMPTS (Phase 1 ARCHITECT.md update) +
  AG-PROMPTS §6 (future, AG-0..AG-4 update) + UI-PROMPTS §11 (future,
  UI-0..UI-3 update).
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

## 9. Приложение: чек-лист выхода из Phase 2

**Источник**: `ROADMAP.md` v1.2.0 §6.6. Используется после прогона всех блоков A–H для самопроверки перед ревью архитектурным комитетом. Критерии выхода — параллельно с Phase 1 чек-листом `MVP-PROMPTS.md` §8 + `AG-PROMPTS.md` Приложение (Phase 1 + Phase 2 — последовательные фазы, Phase 2 не стартует до завершения Phase 1, включая AG-0..AG-4).

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
| 13 | Метрика идеальности (ADR-часть): Δф=+3 capabilities (async checkpoint, reranker, hybrid retrieval), Δсложности=+2 dependencies (bge-reranker, tsvector) → Δф/Δсложности = 1.5 ≥ 1 | F-2 Grafana dashboard | F-2 |
| 14 | AG-5 Approved: `web_search` tool via Tavily — `curl -X POST .../sessions/test/chat -d '{"message":"search web for python asyncio","settings":{"tools_enabled":["web_search"]}}'` → SSE event: tool_call + event: tool_result (snippet_count ≥1) + event: done | E-5 `web-search-integration-staging` nightly + manual | Блок H-1 |
| 15 | AG-5: TAVILY_API_KEY validation — startup fail fast если tools_enabled содержит "web_search" и TAVILY_API_KEY пустой | `python -c "from llm_client.config import get_settings; s = get_settings(); s.tools_enabled=['web_search']; s._validate_environment()"` → `ValidationError` | H-1 (Settings validation) |
| 16 | AG-6 Approved: `rag_query` tool + `rag_retriever` нода — `curl -X POST .../sessions/test/chat -d '{"message":"найди в документации","settings":{"tools_enabled":["rag_query"],"retrieval_strategy":"hybrid","reranker":"bge"}}'` → SSE event: tool_call + event: retrieved_docs (chunk_count ≥1) + event: done | E-5 `rag-query-integration-staging` nightly + manual | Блок H-2, H-3 |
| 17 | AG-6: `RagPipeline.from_settings(settings)` создаётся как singleton при agent-service startup, переиспользуется `rag_query` tool и `rag_retriever` нодой (single instance, не per-call) | manual (startup log “RagPipeline initialized” once) + test_rag_query.py | H-2 |
| 18 | AG-6: pipeline — vector retrieval (top-20) → [BM25 retrieval (top-20) → RRF fusion (top-50)] (if strategy=hybrid, ADR-020) → reranker top-5 (ADR-017) | E-5 `rag-query-integration-staging` nightly (validate top_score in [0, 1] and chunk_count ≤ top_k) | H-2, Блок C, Блок D |
| 19 | H-3 Graph integration: `build_agent_graph(llm, token, tools=[file_export, web_search, rag_query], rag_pipeline=pipeline)` возвращает compiled graph; `route_after_planner` имеет 3 выхода (direct_llm / tools_needed / rag_first) | test_graph.py `test_route_after_planner_*` (3 теста) | H-3 |
| 20 | H-4 SSE event protocol: после POST /chat + GET /stream UI получает `event: tool_call` × N + `event: tool_result` × N + (опционально) `event: retrieved_docs` + `event: done`. При cancel — `event: cancelled` < 200 мс | E-5 `sse-tool-events-staging` nightly + test_sse.py `test_stream_generator_emits_*` | H-4 |
| 21 | G-1 Tool-call preview: `UIClient` interface содержит `render_tool_call` abstractmethod; `StreamlitClient` имплементирует с collapsible expander; file_export content truncated до 200 символов | test_ui_render.py `test_render_tool_call_*` + `test_file_export_content_truncation` | G-1 |
| 22 | G-2 RAG citations panel: `render_rag_citations(chunks)` отображает chunks с source_uri (кликабельная ссылка), title, page, content_preview (≤200 char), score (progress bar) | test_ui_render.py `test_render_rag_citations_*` (6 тестов) | G-2 |
| 23 | G-3 Web search results panel: `render_web_search_results(results)` отображает results с title (url link), snippet, score (metric) | test_ui_render.py `test_render_web_search_results_*` (7 тестов) | G-3 |
| 24 | G-4 Settings panel: `render_settings_panel` в sidebar expander с tools on/off checkboxes, retrieval_strategy selectbox (default hybrid), reranker radio (default bge), top_k/max_results sliders | test_ui_render.py `test_render_settings_panel_*` (6 тестов) + manual (sidebar UI) | G-4 |
| 25 | UI-расширения метрика идеальности (Блок G): Δф=+1 capability (UX tool-transparency), Δсложности=+0 dependencies → Δф/Δсложности = ∞ (улучшает общий ratio, не нарушает порог) | F-2 Grafana dashboard (Panel 6 дополнить) | G-1..G-4 |
| 26 | AG-расширения метрика идеальности (Блок H): Δф=+2 capabilities (web_search, rag_query), Δсложности=+1 dependency (Tavily API) → Δф/Δсложности = 2.0 ≥ 1 | F-2 Grafana dashboard (Panel 6 дополнить) | H-1..H-4 |
| 27 | Документация обновлена: `ARCHITECT.md` §7 ADR-010/017/020 + AG-5/AG-6, §8 C-2/C-6 [RESOLVED]/[PARTIALLY RESOLVED], §12 Q-5 [PARTIALLY CLOSED], §5.1 tool-call previews + settings_panel, §5.2.2 rag_retriever нода, §5.2.4 rag_query tool, §5.2.5 RagPipeline | PR merged | F-1 |
| 28 | Все ADR Phase 2 + AG-5/AG-6: Status Approved в `ARCHITECT.md` v1.3.0 | manual check | F-1 |
| 29 | Phase 1 не регрессировал: ADR-013 cancel latency <100ms, ADR-014 PII leaks = 0, расш. ADR-008 MinIO parity, UI-0..UI-3 чат работает, AG-0..AG-4 agent-service отвечает на /health | Phase 1 nightly jobs (MVP-PROMPTS.md Блок F-1..F-3 + AG-PROMPTS §6) — все PASS | Блоки F-1..F-3 MVP-PROMPTS + AG-PROMPTS §6 (не регрессируют) |

**При невыполнении любого из п.1–4, 5–7, 9–11**: фаза продлевается на 1 sprint (`ROADMAP.md` v1.2.0 §6.6).
**При невыполнении п.8** (RerankerRegistry): ADR-017 не может быть Approved (pluggable architecture нарушена), блокирует п.5–7.
**При невыполнении п.12** (retrieval_strategy=HYBRID default): ADR-020 не Approved, блокирует п.9–11.
**При невыполнении п.13** (ADR-метрика идеальности <1): ADR пересматривается (вероятный over-engineering, `ROADMAP.md` v1.2.0 §13.1 — Phase 2 превышает tight 1.5, но должен ≥1).
**При невыполнении п.14–15** (AG-5): web_search не работает или fail-fast нарушен — блокирует п.20 (SSE tool events для web_search) и п.21–24 (UI-расширения не имеют источника событий).
**При невыполнении п.16–18** (AG-6): rag_query не работает или pipeline неверный — блокирует п.20 (SSE tool events для rag_query), п.22 (RAG citations не имеют источника chunks), п.18 (ADR-017/ADR-020 pipeline integration).
**При невыполнении п.19** (H-3 Graph integration): graph не собирается или route_after_planner неверный — блокирует все зависящие выше (п.14, 16, 20).
**При невыполнении п.20** (H-4 SSE event protocol): UI-расширения (Блок G) не получают события — п.21–24 не имеют источника данных.
**При невыполнении п.21–24** (Блок G): UI не отображает tool-call previews / RAG citations / web search results / settings — UX деградирует, но AG-5/AG-6 (п.14–18) работают. Метрика идеальности п.25 падает (Δф=+0 вместо +1). Фаза может быть Approved без Блока G, но с пометкой "UI-расширения отложены на Phase 3" — `ROADMAP.md` v1.2.0 §6.6 не блокирует.
**При невыполнении п.25–26** (метрики идеальности AG/UI): Блок G/H рассматривается на over-engineering (аналогично п.13). Блок G (UI-расширения) —+1/0 = ∞, не может нарушить порог. Блок H — +2/+1 = 2.0, не нарушает.
**При невыполнении п.27–28**: документационный долг, блокирует старт Phase 3.
**При невыполнении п.29** (Phase 1 regression): критично — Phase 2 не может быть Approved если Phase 1 сломан; rollback Phase 2 changes, fix Phase 1 first.

---

## 10. Карта промптов для быстрого навигации

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
| **G-1** | **Tool-call preview component** (`UIClient.render_tool_call` + StreamlitClient) | UI-2 (Phase 1) | **0.25** |
| **G-2** | **RAG citations panel** (`render_rag_citations`) | G-1, H-2, H-4 | **0.5** |
| **G-3** | **Web search results panel** (`render_web_search_results`) | G-1, H-1, H-4 | **0.25** |
| **G-4** | **Settings panel extension** (tools on/off, retrieval strategy, reranker) | UI-1 (Phase 1) | **0.5** |
| **H-1** | **AG-5 `web_search` tool via Tavily API** (WebSearchArgs + @tool) | AG-1 (Phase 1), Tavily API | **1.0** |
| **H-2** | **AG-6 `rag_query` tool + `rag_retriever` нода + `RagPipeline`** | AG-1, ADR-003, ADR-017 (C), ADR-020 (D) | **4.0** |
| **H-3** | **Graph integration** (`bind_tools([file_export, web_search, rag_query])` + `rag_retriever` + `route_after_planner` 3 выхода) | H-1, H-2, AG-1 | **0.5** |
| **H-4** | **SSE event protocol extension** (`event: tool_call` / `tool_result` / `retrieved_docs`) | AG-3 (Phase 1), H-3 | **0.5** |
| E-1 | Latency checkpoint test (<2 мс в 99%) | Блок B, A-1..A-3 | 0.25 |
| E-2 | Restart recovery test (4 scenarios) | B-5 | 0.5 |
| E-3 | Recall@5 A/B test (bge vs baseline) | Блок C | 0.25 |
| E-4 | Exact-term recall A/B test (hybrid vs vector-only) | Блок D | 0.25 |
| E-5 | Phase 2 CI pipeline (расширение Phase 1 CI + AG + UI tests) | Блоки A-D, G, H, E-1..E-4 | 0.75 |
| F-1 | `ARCHITECT.md` update (ADR-010/017/020 + AG-5/AG-6 + §5.1/§5.2.2/§5.2.4/§5.2.5 updates, C-2/C-6 resolved) | Блоки B, C, D, G, H completed | 0.25 |
| F-2 | Grafana dashboard Phase 2 control point (ADR ratio 1.5, AG ratio 2.0, UI ratio ∞) | — | 0.25 |
| **Итого** | **36 промптов** (28 v1.0.0 + 4 G + 4 H) | | **~14 чел-дн ADR + 5 чел-дн AG + 1.5 чел-дн UI + 2.5 чел-дн tests/CI/docs = 23 чел-дн** |

**Параллелизация (3 разработчика)** (`ROADMAP.md` v1.2.0 §11.2 + ALPHA-PROMPTS.md v1.1.0 extension):

- **Дев 1 (Backend/Orchestration)**: A-1 → B-1 → B-2 → B-3 → B-4 → B-5 → B-6 → E-1 → E-2 → F-1 (orchestration часть)
  - Срок: 5 чел-дн ADR-010 + 1.5 чел-дн tests/docs = **6.5 чел-дн**
- **Дев 2 (Backend/RAG)**: A-2 → C-1 → C-2 → C-3 → A-3 → D-1 → D-2 → D-3 → D-4 → D-5 → C-4 → C-5 → C-6 → D-6 → E-3 → E-4 → H-1 (AG-5) → H-2 (AG-6) → H-3 (graph integration) → H-4 (SSE) → F-1 (RAG+AG часть) → F-2
  - Срок: 4 чел-дн ADR-017 + 5 чел-дн ADR-020 + 5 чел-дн AG (H-1..H-4) + 1.5 чел-дн tests/docs = **15.5 чел-дн**
- **Дев 3 (Frontend/UI)**: G-1 → G-2 → G-3 → G-4 (UI-расширения, после готовности H-1/H-2/H-4 для manual integration test)
  - Срок: 1.5 чел-дн UI + 0.5 чел-дн integration = **2 чел-дн** (стартует после Dev 2 H-1 + H-4 ready)
- **Параллельные (стартуют сразу, не блокируют critical path)**: A-3 (1 разработчик), E-5 (DevOps).

**Critical path**: A-1 → B-1..B-6 (6 промптов, 3.5 чел-дн) → E-1, E-2 (1 чел-дн) → F-1 (0.25 чел-дн) = **4.75 чел-дн** для Dev 1. Dev 2 critical path = 15.5 чел-дн. Dev 3 = 2 чел-дн после Dev 2 готовности H-1/H-4 (на 9-10 чел-дн Dev 2).

**Суммарная оценка Phase 2**: 14 чел-дн ADR-работы (`ROADMAP.md` v1.2.0 §6.2.1–6.2.3: 5 + 4 + 5 = 14) + 5 чел-дн AG-расширения (§6.2.4 AG-5 + §6.2.5 AG-6, `BACKLOG.md` v1.1.0 §3.4: 1 + 4 = 5) + 1.5 чел-дн UI-расширения (Блок G, new в ALPHA-PROMPTS.md v1.1.0, не входит в оценку `ROADMAP.md` v1.2.0) + 2.5 чел-дн тесты/CI/доки (Блоки E, F) = **23 чел-дн** total (vs 16.5 чел-дн в v1.0.0; delta = +6.5 чел-дн: +5 AG-5/AG-6 + 1.5 UI). С параллелизацией 3 разработчиков — **11–13 рабочих дней** (max(Dev 1 4.75, Dev 2 15.5, Dev 3 2 + lag) = 15.5 чел-дн / 3 разработчика = 5.17 рабочих дней critical path, но с onboarding и review — 11–13 дней = ~2.5 sprint).

**Зависимости между блоками** (см. диаграмму в §0):
- Блок A — стартует первым, все 3 подзадачи (A-1, A-2, A-3) параллельны.
- Блок B — зависит от A-1 (Redis WAL).
- Блок C — зависит от A-2 (bge-reranker).
- Блок D — зависит от A-3 (tsvector) и C-4 (reranker для fusion top-5).
- Блок H (AG-расширения) — зависит от AG-1 (Phase 1 graph), AG-3 (Phase 1 SSE); H-2 (AG-6) дополнительно зависит от Блоков C и D (использует reranker и hybrid retriever из RagPipeline).
- Блок G (UI-расширения) — зависит от Блока H (SSE events tool_call/tool_result/retrieved_docs из H-4 — источник данных для UI render).
- Блок E — зависит от Блоков B, C, D, G, H.
- Блок F — зависит от Блоков B, C, D, G, H (после их завершения).

**Переход к Phase 3 (Beta)**: Phase 2 → Phase 3 критерий (`ROADMAP.md` v1.2.0 §3.2): все пункты чек-листа §9 выполнены (особенно п.13, 25, 26 — метрики идеальности ≥1, п.27–28 — документация обновлена, п.29 — Phase 1 regression-free). Phase 3 добавляет ADR-011 (semantic cache — закрывает C-6 cost-составляющую), ADR-015 (cost-aware router), ADR-016 (tool capability adapter), ADR-004 ускорение (MCP server mode preview). AG-7 (mcp_call tool, Phase 4, `BACKLOG.md` v1.1.0 §3.4) — следующий AG-промпт после AG-5/AG-6. См. `BETA-PROMPTS.md` (драфт, создать в Phase 2 конце).

---

## 11. История изменений

| Версия | Дата | Изменение |
|---|---|---|
| 1.0.0 | 2026-09-23 | Initial draft. 28 промптов в 6 блоках A–F: A (инфра), B (ADR-010 RedisPostgresCheckpointer), C (ADR-017 Reranker), D (ADR-020 Hybrid BM25+Vector), E (тесты/CI), F (документация/метрика идеальности). Суммарно 16.5 чел-дн (14 ADR + 2.5 tests/CI/docs). Источники: `ROADMAP.md` v1.1.0, `TRIZ-ANALYSIS.md` v1.0.0, `ARCHITECT.md` v1.1.0. |
| 1.1.0 | 2026-09-26 | Добавлены 2 новых блока: **G (UI-расширения Phase 2, 4 промпта — G-1 tool-call preview, G-2 RAG citations, G-3 web search results, G-4 settings panel extension)** и **H (AG-расширения Phase 2, 4 промпта — H-1=AG-5 web_search via Tavily, H-2=AG-6 rag_query + base RAG + rag_retriever нода, H-3 graph integration, H-4 SSE event protocol extension)**. Обновлён header: источники (`BACKLOG.md` v1.1.0, `AG-PROMPTS.md` v1.0.0, `UI-PROMPTS.md` v1.1.0, `ROADMAP.md` v1.2.0, `ARCHITECT.md` v1.2.0), предусловие (Phase 1 полностью завершена с UI-0..UI-3 + AG-0..AG-4), этап (23 чел-дн total). Обновлён §0 (диаграмма A→H, параллелизация 3 разработчика). Обновлён E-5 (CI pipeline — добавлены jobs для AG-5/AG-6 + UI тестов). Обновлён F-1 (ARCHITECT.md update — добавлены §5.2.4 Tool Layer rag_query, §5.2.2 Orchestration rag_retriever нода, §5.2.5 RAG Layer RagPipeline, §5.1 Presentation Layer tool-call previews + settings_panel; AG-5/AG-6 Approved). Обновлён §9 чек-лист (29 критериев: +13 для Блоков G/H). Обновлён §10 карта промптов (36 промптов total). Источник патча: `BACKLOG.md` v1.1.0 §3.4 (AG-5/AG-6 для Phase 2), `ROADMAP.md` v1.2.0 §6.2.4/§6.2.5. |

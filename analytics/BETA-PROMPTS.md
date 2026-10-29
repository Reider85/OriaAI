# BETA-PROMPTS.md — Промпты для этапа Beta (Phase 3)

| Атрибут | Значение |
|---|---|
| Версия документа | 1.0.0 |
| Дата | 2026-09-30 |
| Источники | `ROADMAP.md` v1.2.0 §7 (Phase 3 — Beta), §6 (Phase 2 — Alpha, предусловие), §11.1-11.3 (критический путь + ADR-зависимости), §13.1-13.6 (риски Phase 3), §14.1 (пилоты и rollback-метрики ADR-011/015/016), §15.1-15.3 (метрика идеальности, Phase 3 control point Δф/Δсложности = 4/2 = 2.0), §17 (Q-1 preview, Q-5 full closure в Phase 3), §18.1, §18.6 (повторный ТРИЗ-анализ после Phase 3); `TRIZ-ANALYSIS.md` v1.0.0 §5.1 (C-1 — упоминание как предусловие Phase 5), §6.1 (C-6, full closure в Phase 3), §6.2 (C-7 — ADR-015), §6.4 (C-9 — ADR-016), §8.1 (triad 1 — semantic cache как второе поле), §9.2 (Standard 2.2.4 — measuring vepol для `LLMRouter`), §9.3 (Standard 3.1.4 — дробление поля для `ToolCallingAdapter`; Standard 3.2.1 — переход в надсистему для ADR-004 ускорение), §9.5 (Standard 5.1.1 — Prometheus metrics как вещество извне для circuit breaker; Standard 5.3.1 — semantic cache как производное вещество), §10 (матрица противоречий C-6/C-7/C-9 + ИКР-0), §11 (драфты ADR-011/015/016), §12 (roadmap по фазам, Phase 3 = 31 чел-дн), §14.2 (главные ТРИЗ-инсайты — ИКР-0 ускоряет ADR-004 до Phase 3 preview); `ARCHITECT.md` v1.3.0 §4 (контейнерная диаграмма — agent-service container), §5.1 (Presentation Layer, опциональные UI-расширения Блока G), §5.2.3 (LLM Provider Layer — `LLMProviderFactory` extended с anthropic + Ollama cheap-tier), §5.2.4 (Tool Layer — `ToolCallingAdapter` поверх `@tool`-функций), §5.2.5 (RAG Layer — three-tier cache: Tier-3 Redis + Tier-1 `documents_facts` + Tier-2 из Phase 2), §5.2.6 (MCP Client Layer — extended с MCP Server preview), §5.2.7 (Persistence — new `documents_facts` table + Redis DB 2 для semantic cache), §6 (sequence diagrams), §7 ADR-004 (ускорение preview), ADR-005 (Supersedes: fallback_chain → ADR-015), ADR-006 (нативный tool calling — ADR-016 расширяет с ReAct mode), ADR-007 (SSE — переиспользуется в MCP Server preview transport), ADR-011/015/016 (новые Phase 3 ADR), §8 (Trade-offs — C-6/C-7/C-9 помечаются Phase 3 resolved), §12 (Q-1 PARTIALLY CLOSED preview, Q-5 CLOSED); `BACKLOG.md` v1.1.0 §1 (упоминание BETA-PROMPTS.md как покрывающего Phase 3 — единственный явный placeholder в корпусе), §3.2 (UI-0..UI-7 — none scheduled for Phase 3, UI-4..UI-6 в Phase 5+), §3.4 (AG-0..AG-7 — none scheduled for Phase 3, AG-7 `mcp_call` в Phase 4), §7 (Связанные документы); `MVP-PROMPTS.md` v1.0.0 (контракты Phase 1 — `LLMProviderFactory`, `LLMProviderFactory.create()`, `_COST_PER_1M`, `TokenUsageTracker`, `create_retry_decorator`, `BaseCheckpointSaver`, `CancellationToken`, `CancelPublisher`/`CancelSubscriber`, `S3CompatibleStorage`, `KMSKeyProvider`, `OperationalStreamWriter`, `ForensicStreamWriter`, `PIIDetector`, `build_agent_graph(llm, token, tools)`, `UIClient` abstraction — не переопределяются); `ALPHA-PROMPTS.md` v1.1.0 (контракты Phase 2 — `RedisPostgresCheckpointer`, `RerankerRegistry`/`BgeRerankerAdapter`/`CohereRerankAdapter`/`IdentityReranker`/`RerankerChain`, `HybridRetriever`/`BM25Retriever`/`rrf_fusion`/`RetrieverConfig.retrieval_strategy=HYBRID` default, `documents.search_vector` tsvector, `web_search` tool via Tavily, `rag_query` tool + `RagPipeline` singleton + `rag_retriever` нода, `build_agent_graph(llm, token, tools, rag_pipeline=pipeline)` с 3-выходным `route_after_planner`, SSE event protocol с `tool_call`/`tool_result`/`retrieved_docs`, `render_tool_call`/`render_rag_citations`/`render_web_search_results`/`render_settings_panel` UI-расширения G-1..G-4 — все не переопределяются, а расширяются) |
| Этап | Phase 3 — Beta (8 чел-дн ADR-011 + 7 чел-дн ADR-015 + 6 чел-дн ADR-016 + 10 чел-дн ADR-004 ускорение = 31 чел-дн ADR-работы + 1.5 чел-дн UI-расширения (G-1..G-3 опционально, не входит в оценку `ROADMAP.md` v1.2.0) + 2.5 чел-дн тесты/CI/доки = ~35 чел-дн; по `ROADMAP.md` v1.2.0 §7.2 = 31 чел-дн ADR + 2.5 чел-дн overhead = ~33.5 чел-дн без UI-расширений) |
| ADR в области | ADR-011 (Hybrid Semantic Cache for LLM — Tier-3 answer cache + Tier-1 facts cache + Tier-2 vector retrieval из Phase 2), ADR-015 (Cost-Aware Routing — `LLMRouter` с политиками cost/latency/quality/privacy + cost guard 80% budget; **Supersedes:** часть ADR-005 `fallback_chain`), ADR-016 (Tool Capability Adapter — `ModelCapabilityMatrix` + `ToolCallingAdapter` native/react/hybrid), ADR-004 ускорение (MCP Server mode preview, SSE transport; full MCP Server — Phase 6) |
| AG-расширения в области | (нет — Phase 3 не вводит новых AG-N; AG-7 `mcp_call` tool / `mcp_invoker` нода планируется в Phase 4 per `BACKLOG.md` v1.1.0 §3.4) |
| UI-расширения в области | (опционально, не входит в оценку `ROADMAP.md` v1.2.0, добавлено в BETA-PROMPTS.md v1.0.0 по аналогии с Блоком G ALPHA-PROMPTS v1.1.0): G-1 (settings panel extension для `LLMRouter` policy — cost/latency/quality/privacy selector), G-2 (settings panel extension для `ToolCallingMode` — native/react/hybrid toggle при использовании ADR-016 ReAct-модели), G-3 (MCP Server mode on/off toggle + endpoint URL display) — расширяют `render_settings_panel` из `UI-PROMPTS.md` v1.1.0 (G-4 Phase 2) для отображения настроек ADR-015/016/004 |
| Резолвит противоречия | C-6 (long RAG context vs cost) — **полностью** (cost-составляющая закрыта ADR-011 semantic cache; качество было закрыто ADR-017+020 в Phase 2); C-7 (fallback chain vs cost predictability) — **полностью** (ADR-015 cost-aware router); C-9 (tool calling API vs model portability) — **полностью** (ADR-016 `ModelCapabilityMatrix` + `ToolCallingAdapter` native/react/hybrid); ИКР-0 (переход в надсистему) — **preview** (ADR-004 ускорение; full realization — Phase 6 с WebSocket transport + OAuth 2.0 + signed manifests ADR-019) |
| Целевой LLM | Универсальные (Cursor / Copilot / Claude Code / ChatGPT) |
| Гранулярность | Микро-промпты (1 промпт = 1 файл / 1 класс / 1 подзадача) |
| Предусловие | Phase 2 завершена полностью (`ROADMAP.md` v1.2.0 §6.6, 29 критериев чек-листа ALPHA-PROMPTS §9): ADR-010 Approved (`RedisPostgresCheckpointer` в `src/llm_client/orchestration/checkpointers/composite.py`), ADR-017 Approved (`RerankerRegistry` + `BgeRerankerAdapter` + `CohereRerankAdapter` + `IdentityReranker` + `RerankerChain` в `src/llm_client/rag/rerankers/`), ADR-020 Approved (`HybridRetriever` + `BM25Retriever` + `rrf_fusion` + `RetrieverConfig.retrieval_strategy=HYBRID` default + `documents.search_vector` tsvector + Alembic миграции `007_add_tsvector_to_documents.py` + `008_fix_documents_search_schema.py`), AG-5 Approved (`web_search` tool via Tavily в `src/llm_client/agent/tools/web_search.py`), AG-6 Approved (`rag_query` tool + `RagPipeline` singleton + `rag_retriever` нода в graph), H-3 graph integration Approved (`build_agent_graph(llm, token, tools=[file_export, web_search, rag_query], rag_pipeline=pipeline)` с 3-выходным `route_after_planner`: `direct_llm` / `tools_needed` / `rag_first`), H-4 SSE event protocol extension Approved (`event: tool_call` / `tool_result` / `retrieved_docs`), G-1..G-4 UI-расширения Approved (`render_tool_call`, `render_rag_citations`, `render_web_search_results`, `render_settings_panel`). C-2 [RESOLVED], C-6 [PARTIALLY RESOLVED — ADR-011 pending Phase 3], Q-5 [PARTIALLY CLOSED]. ARCHITECT.md v1.3.0. Текущие stubs: `LLMProviderFactory.create("anthropic", ...)` raises `NotImplementedError("Anthropic provider is Phase 3 (ADR-015 cost-aware router)")` (`src/llm_client/agent/provider.py` строки 198–201); `LLMProviderFactory.create("ollama", ...)` raises `NotImplementedError("Ollama provider is Phase 4 (ADR-016 tool capability adapter)")` (`src/llm_client/agent/provider.py` строки 202–205) — Phase 3 ADR-016 добавляет adapter abstraction (`ToolCallingAdapter` с `react` mode); full Ollama case остаётся Phase 4 (если ADR-015 router не регистрирует его как cheap-tier — это Phase 3 опция per `ROADMAP.md` §7.4). Существующая hardcode-таблица `_COST_PER_1M` в `src/llm_client/agent/provider.py` строки 32–35 (`gpt-4o-mini`, `gpt-4o`) — Phase 3 ADR-015 формализует в `ModelCostTable` / `ModelCapabilityMatrix`. `TokenUsageTracker` callback handler пишет `event_type: "llm_usage"` в operational stream с `cost_estimate_usd` (`src/llm_client/observability/operational_writer.py`) — Phase 3 ADR-015 расширяет с `cost_tracker`. `src/llm_client/observability/idealidad.py` `PHASE_CAPABILITIES["Phase 3"]` placeholder **уже определён**: `("semantic_cache", "cost_aware_router", "tool_capability_adapter", "mcp_server_preview")` — canonical список Phase 3 deliverables. |
| Связанные документы | `MVP-PROMPTS.md` v1.0.0 (контракты Phase 1 — не переопределяются), `ALPHA-PROMPTS.md` v1.1.0 (контракты Phase 2 — не переопределяются, расширяются), `UI-PROMPTS.md` v1.1.0 (UI-0..UI-3 + G-1..G-4 — предусловие для опционального Блока G), `AG-PROMPTS.md` v1.0.0 (AG-0..AG-4 — предусловие), `BACKLOG.md` v1.1.0 (§1 — упоминание BETA-PROMPTS.md как покрывающего Phase 3; §3.2, §3.4 — Phase 3 не вводит новых UI/AG работ), `ROADMAP.md` v1.2.0 (Phase 3 = 31 чел-дн ADR + 2.5 чел-дн tests/CI/docs = ~33.5 чел-дн без UI-расширений), `ARCHITECT.md` v1.3.0, `TRIZ-ANALYSIS.md` v1.0.0 |

---

## 0. Как пользоваться документом

Каждый промпт — самостоятельный блок, огороженный ` ``` `-код-блоком, готовый к копи-пасту в любой код-ассистент (Cursor / Copilot / Claude Code / ChatGPT). Промпты сгруппированы в восемь блоков **A–H**, идущих в порядке зависимостей:

```
A. Инфра Phase 3 ──┬──→ B. ADR-011 (Semantic Cache: Tier-3 Redis + Tier-1 documents_facts) ──┐
                   │                                                                       │
                   ├──→ C. ADR-015 (Cost-Aware LLMRouter, Supersedes ADR-005 fallback_chain) ──┤
                   │     ↑ использует _COST_PER_1M + TokenUsageTracker (Phase 1)               │
                   │                                                                       ├──→ E. Тесты/CI ──→ F. Документация
                   └──→ D. ADR-016 (ModelCapabilityMatrix + ToolCallingAdapter) ───────────────┤
                         ↑ зависит от C (router использует matrix для выбора)                   │
                         ↑ расширяет ADR-006 native tool calling с react mode                    │
                                                                                              │
                   ┌──────────────────────────────────────────────────────────────────────────┘
                   │
                   ├──→ G. UI-расширения Phase 3 (опционально, не в оценке ROADMAP):
                   │    settings_panel для router policy / ToolCallingMode / MCP server on-off
                   │
                   └──→ H. ADR-004 ускорение: MCP Server mode preview
                        (transport: SSE per ADR-007; signed manifests ADR-019 — Phase 5;
                         full MCP Server — Phase 6 с WebSocket + OAuth 2.0)
```

**Конвенции**:

- Имена классов, методов, эндпоинтов, env-переменных — на английском (как в `ARCHITECT.md` v1.3.0 и существующем коде `src/llm_client/`).
- Имена ADR и противоречий — в формате `ADR-011`, `C-6` (как в `TRIZ-ANALYSIS.md` §10 матрица противоречий).
- Имена AG/UI работ — в формате `AG-7`, `UI-4` (как в `BACKLOG.md` v1.1.0 §3.2, §3.4).
- Раздел `Definition of Done` — конкретные измеримые критерии готовности (латентность, hit-rate, success-rate, latency cache hit <100мс, cost predictability ±10%, ReAct success rate ≥80%).
- Раздел `Антипаттерны` — что LLM НЕ должен делать; если предложит — отбраковывать.
- Раздел `Связанные ADR` — какие ADR затрагивает (`Реализует:`, `Применяет:`, `Зависит от:`, `Расширяется в:`, `Не затрагивает:`).
- Все контракты Phase 1 (`MVP-PROMPTS.md` v1.0.0) и Phase 2 (`ALPHA-PROMPTS.md` v1.1.0) **продолжают действовать** — Phase 3 только расширяет, не переопределяет. Особенно: `LLMProviderFactory` (AG-2), `BaseCheckpointSaver` / `RedisPostgresCheckpointer` (ADR-010), `RerankerRegistry` (ADR-017), `HybridRetriever` (ADR-020), `RagPipeline` singleton (AG-6), `build_agent_graph(llm, token, tools, rag_pipeline=...)` (AG-1 + H-3), SSE event protocol (AG-3 + H-4), `@tool`-декорированные функции `file_export` / `web_search` / `rag_query` (AG-4/AG-5/AG-6), `UIClient` abstraction (UI-2), `StreamlitClient` (UI-3 + G-1..G-4), `CancellationToken` / `CancelPublisher` / `CancelSubscriber` (ADR-013), `OperationalStreamWriter` / `ForensicStreamWriter` (ADR-014), `KMSKeyProvider` / `VaultTransitKeyProvider` (D-4), `S3CompatibleStorage` (расш. ADR-008), `PIIDetector` (D-5), `TokenUsageTracker` callback (AG-2), `create_retry_decorator` (AG-2), `_COST_PER_1M` hardcode (AG-2), `compute_state_delta` / `IterationMonitor` (B-3), `format_sse_event` helper (AG-0 — переиспользуется в Блоке H).

**Замечание о Блоке G (UI-расширения Phase 3)**

Блок G (`G-1` router policy selector, `G-2` ToolCallingMode toggle, `G-3` MCP Server on/off toggle) **не входит в оценку `ROADMAP.md` v1.2.0 §7.2** — Phase 3 = 31 чел-дн ADR-работы + 2.5 чел-дн overhead = 33.5 чел-дн без UI. Блок G добавлен в BETA-PROMPTS.md v1.0.0 по аналогии с ALPHA-PROMPTS v1.1.0 (который также добавил G-1..G-4 Phase 2 поверх оценки ROADMAP) — для управляемости 4 новых абстракций через существующую `render_settings_panel`. Если команда ограничена по времени, Блок G можно отложить до Phase 4 (тогда UI-настройки router policy / ToolCallingMode войдут в Phase 4 UI-расширения).

**Фазировка противоречий**

Phase 3 закрывает **три** из четырёх оставшихся после Phase 2 противоречий и открывает **preview** четвёртого:
- C-6 (long RAG context vs cost) — **fully resolved** в Phase 3 (cost-составляющая закрыта ADR-011 semantic cache; качество было закрыто ADR-017+020 в Phase 2). Standard 1.1.5 (введение второго поля в веполь) — semantic cache как второе поле в triad 1 (LLM↔Tool Registry↔External API).
- C-7 (fallback chain vs cost predictability) — **fully resolved** в Phase 3 (ADR-015 cost-aware router с cost guard 80% budget). Standard 2.2.4 (переход к измерительной веполи) — `LLMCallMetrics` как measuring function; Standard 5.1.1 (введение вещества извне) — Prometheus metrics как circuit breaker input.
- C-9 (tool calling API vs model portability) — **fully resolved** в Phase 3 (ADR-016 `ModelCapabilityMatrix` + `ToolCallingAdapter` native/react/hybrid). Standard 3.1.4 (дробление поля) — split `tool_calling` на `NativeToolCalling` + `ReActToolCalling`.
- ИКР-0 (переход в надсистему) — **preview** в Phase 3 (ADR-004 ускорение — LLM Client становится MCP server для других клиентов; transport SSE). Standard 3.2.1 (переход в надсистему). Full realization — Phase 6 (WebSocket transport + OAuth 2.0 + signed manifests ADR-019 + ADR-012 auto-negotiation).

Q-5 (стоимость LLM при >50k токенов контекста) — **fully closed** в Phase 3 (был partially closed в Phase 2 через ADR-017/020; ADR-011 semantic cache + ADR-015 cost-aware router закрывают полностью). Q-1 (Ollama integration) — **preview** в Phase 3 (ADR-016 + ADR-015 открывают путь; full — Phase 4 per `ROADMAP.md` §8.1).

---

## 1. Блок A. Инфра-подготовка Phase 3

Блок A создаёт три инфра-объекта, от которых зависят все четыре ADR Phase 3:

1. **A-1**: Redis DB 2 для semantic cache (Tier-3 storage) — изолированная от DB 0 (pub/sub) и DB 1 (checkpoint-WAL из ADR-010) БД с TTL=24h и `maxmemory-policy=allkeys-lru`.
2. **A-2**: Prometheus exporter для LLM call metrics — ADR-015 router использует его как circuit breaker input (Standard 5.1.1 «введение вещества извне»).
3. **A-3**: Alembic миграция `009_create_documents_facts.py` — таблица `documents_facts` для Tier-1 facts cache (ADR-011).

Без Блока A Блоки B/C/D не могут быть Approved — инфра-зависимости критические.

---

### A-1. Redis DB 2 для semantic cache (Tier-3 storage)

```
Ты — DevOps/Backend-разработчик LLM Client. Подними Redis DB 2 для
semantic cache (Tier-3 ADR-011) — изолированную БД с TTL=24h и
LRU-eviction, не пересекающуюся с DB 0 (pub/sub cancel) и DB 1
(checkpoint-WAL из ADR-010 Phase 2).

Контекст:
- `redis/redis.conf` (Phase 2) уже содержит:
  ```
  # DB 0: pub/sub cancel (ADR-013)
  # DB 1: checkpoint-WAL (ADR-010, maxmemory-policy=noeviction,
  #       appendfsync everysec, save "" — no snapshots)
  ```
  DB 2 добавляется в ту же Redis-инстанцию (port 6380 per
  `docker-compose.yml` Phase 1), не отдельный контейнер.
- ADR-011 semantic cache (Блок B-1) использует Redis для Tier-3
  answer cache: ключ `<namespace>:sem_cache:<query_embedding_hash>`,
  value = JSON `{answer: str, referenced_doc_ids: list[UUID],
  created_at: ISO, model: str, token_count: int}`, TTL=24h.
- ARCHITECT.md v1.3.0 §5.2.7 (Persistence) уже зафиксировал:
  Redis используется для pub/sub (DB 0), checkpoint-WAL (DB 1),
  semantic cache (DB 2 — Phase 3).
- ТРИЗ Standard 5.3.1 (введение производного вещества): semantic
  cache — производное вещество от checkpoint-WAL (та же Redis
  инстанция, другая БД, другая eviction-policy).
- `docker-compose.yml` Phase 1 уже содержит `redis` service с
  `command: redis-server /etc/redis/redis.conf` и volume на
  `./redis/redis.conf`.
- ADR-010 Phase 2 зафиксировал `maxmemory-policy=noeviction` для
  DB 1 (checkpoint-WAL не вытесняется). Для DB 2 semantic cache
  policy = `allkeys-lru` (cache может быть вытеснен — это нормально,
  cache miss = просто идём в LLM).
- Объём памяти: оценим 10k queries × 4KB answer + 1.5KB embedding
  ×24 = ~200MB на 10k queries. maxmemory=512MB для DB 2 достаточно
  (отдельный от DB 1, у которого свой budget).
- Env vars Phase 2: `REDIS_URL=redis://redis:6380/0` (pub/sub),
  `REDIS_CHECKPOINT_URL=redis://redis:6380/1` (checkpoint). Phase 3
  добавляет `REDIS_SEMANTIC_CACHE_URL=redis://redis:6380/2`.

Задача:
1. Обнови `redis/redis.conf`:
   ```conf
   # === Existing Phase 1 (cancel pub/sub on DB 0) ===
   # see docker-compose.yml, no changes

   # === Existing Phase 2 (ADR-010 checkpoint-WAL on DB 1) ===
   # maxmemory-policy=noeviction for DB 1 (preserved)
   # appendfsync everysec, save "" (no snapshots)

   # === Phase 3 (ADR-011 semantic cache on DB 2) ===
   # NOTE: redis maxmemory-policy is global, not per-db. We rely
   # on maxmemory cap + key-prefix-based LRU via application-level
   # eviction OR use a separate Redis instance for DB 2.
   #
   # Recommended approach: separate logical DB 2 within the same
   # instance, maxmemory=1GB shared, application-level TTL=24h on
   # sem_cache:* keys, and accept LRU-eviction across all DBs
   # (DB 1 keys are persistent via PostgreSQL backend — ADR-010
   # composite checkpointer, so eviction from Redis does NOT
   # lose data; it forces read-through to Postgres).
   ```
   Реши (предложи в PR): либо (a) общий maxmemory + LRU (current
   proposal), либо (b) отдельный Redis container `redis-cache` на
   порту 6381 для semantic cache. Аргументируй выбор.

2. Обнови `docker-compose.yml` — добавь healthcheck для Redis с
   проверкой DB 2 accessible:
   ```yaml
   redis:
     image: redis:7.4-alpine
     ports:
       - "6380:6379"
     command: redis-server /etc/redis/redis.conf
     volumes:
       - ./redis/redis.conf:/etc/redis/redis.conf
       - redis-data:/data
     healthcheck:
       test: ["CMD", "redis-cli", "-n", "2", "PING"]
       interval: 5s
       timeout: 3s
       retries: 5
   ```

3. Добавь в `src/llm_client/config.py` Settings:
   - `redis_semantic_cache_url: str = "redis://redis:6380/2"` (env:
     `REDIS_SEMANTIC_CACHE_URL`).
   - `semantic_cache_enabled: bool = True` (env:
     `SEMANTIC_CACHE_ENABLED`).
   - `semantic_cache_ttl_seconds: int = 86400` (24h).
   - `semantic_cache_similarity_threshold: float = 0.92` (cosine sim).
   - `semantic_cache_max_entries: int = 10000` (soft cap for LRU).
   - В `Settings._validate_environment`: если
     `semantic_cache_enabled=True` и `REDIS_SEMANTIC_CACHE_URL` пустая
     — startup fail fast (аналогично REDIS_URL валидации из Блока A-1
     `MVP-PROMPTS.md`).

4. Обнови `.env.example`:
   ```env
   # === Phase 3 — ADR-011 Semantic Cache ===
   REDIS_SEMANTIC_CACHE_URL=redis://redis:6380/2
   SEMANTIC_CACHE_ENABLED=true
   SEMANTIC_CACHE_TTL_SECONDS=86400
   SEMANTIC_CACHE_SIMILARITY_THRESHOLD=0.92
   SEMANTIC_CACHE_MAX_ENTRIES=10000
   ```

5. Напиши скрипт `scripts/verify_redis_db2.py`:
   ```python
   """Verify Redis DB 2 (semantic cache) is reachable."""
   import asyncio
   import redis.asyncio as redis
   from llm_client.config import get_settings

   async def main():
       s = get_settings()
       r = redis.from_url(s.redis_semantic_cache_url)
       pong = await r.ping()
       assert pong, "Redis DB 2 not reachable"
       await r.set("sem_cache:__probe__", "ok", ex=60)
       val = await r.get("sem_cache:__probe__")
       assert val == b"ok", f"unexpected probe value: {val!r}"
       await r.delete("sem_cache:__probe__")
       print(f"OK — Redis DB 2 reachable at {s.redis_semantic_cache_url}")

   if __name__ == "__main__":
       asyncio.run(main())
   ```

6. Smoke-тест в `tests/unit/test_config_phase3.py`:
   - `test_redis_semantic_cache_url_default` — default =
     `"redis://redis:6380/2"`.
   - `test_semantic_cache_enabled_default_true`.
   - `test_semantic_cache_disabled_via_env` — env
     `SEMANTIC_CACHE_ENABLED=false` → settings.semantic_cache_enabled
     is False (Блок B-1 будет проверять и пропускать кэш).
   - `test_validate_environment_fails_when_sem_cache_url_missing`
     (если enabled=True, url="" → ValidationError).

Definition of Done:
- `redis/redis.conf` обновлён — комментарий о DB 2 + maxmemory
  policy documented.
- `docker-compose.yml` healthcheck проверяет `redis-cli -n 2 PING`.
- `src/llm_client/config.py` содержит 5 новых полей Settings.
- `.env.example` обновлён с 5 новыми env vars.
- `scripts/verify_redis_db2.py` запускается локально: `python
  scripts/verify_redis_db2.py` → `OK — Redis DB 2 reachable at
  redis://redis:6380/2`.
- `tests/unit/test_config_phase3.py` содержит 4+ новых тестов, все
  зелёные.
- Существующие тесты Phase 1/2 (`test_redis_checkpointer.py`,
  `test_postgres_checkpointer.py`, `test_composite_checkpointer.py`,
  `test_redis_checkpoint_integration.py`) — не регрессируют (DB 1
  checkpoint-WAL не тронут).

Антипаттерны:
- НЕ создавай отдельный Redis container для DB 2 без обоснования —
  один контейнер с разными DB дешевле в ops (одна точка отказа, но
  PostgreSQL composite backup (ADR-010) покрывает durability).
- НЕ используй DB 0 (pub/sub) или DB 1 (checkpoint-WAL) для semantic
  cache — нарушение изоляции приведёт к конфликту eviction policy.
- НЕ хардкодь `redis://redis:6380/2` в коде — только через Settings
  (для self-hosted/external Redis alternative в Phase 4+).
- НЕ делай `maxmemory-policy=volatile-lru` для DB 2 — нужны
  `allkeys-lru` (все sem_cache:* keys имеют TTL, но volatile-ttl
  тоже ок; выбери и зафиксируй в `redis.conf` с комментарием).
- НЕ включай AOF (append-only file) для DB 2 — semantic cache
  persist-on-restart не нужен; cache miss на cold start = simply
  go to LLM.
- НЕ делай Redis SAVE (snapshot) для DB 2 — `save ""` уже стоит для
  всей инстанции (Phase 2).
- НЕ храни embeddings как float[] в Redis — конвертируй в bytes
  через `numpy.ndarray.tobytes()` (в 4 раза компактнее) и храни
  hash для быстрого cosine sim lookup (Блок B-1 детализирует).

Связанные ADR:
- Реализует: инфра для ADR-011 (Tier-3 storage на Redis DB 2).
- Применяет: ADR-008 (расширенный storage layer — Redis как
  multi-purpose cache backend), ADR-010 (DB 1 / DB 2 изоляция в
  одной инстанции — pattern reuse).
- Зависит от: Phase 2 ADR-010 (RedisPostgresCheckpointer на DB 1
  — доказана жизнеспособность Redis-as-checkpoint-pattern), Phase 1
  Блок A-1 `MVP-PROMPTS.md` (Redis container на 6380).
- Расширяется в: Phase 4 — `BgeEmbeddings` local mode (semantic
  cache embeddings via local model, no OpenAI API call per cache
  write; B-1 будет использовать OpenAIEmbeddings по умолчанию).
- Не затрагивает: ADR-013 (cancel pub/sub на DB 0), ADR-014
  (DualStreamLogger — не пишет в Redis).
```

### A-2. Prometheus exporter для LLM call metrics (circuit breaker input для ADR-015)

```
Ты — Observability/Backend-разработчик LLM Client. Создай Prometheus
exporter, эмитящий LLM call metrics — latency, token count, cost,
success/failure rate, per-provider/per-model. Это инфра для ADR-015
cost-aware router (router читает metrics как circuit breaker input
per Standard 5.1.1 «введение вещества извне»).

Контекст:
- `ops/prometheus/prometheus.yml` (Phase 2) уже скрейпит
  `agent-service:8000/metrics` (добавлен в Phase 1 ADR-013 cancel
  endpoint metrics).
- ARCHITECT.md v1.3.0 §5.2.3 (LLM Provider Layer) — `LLMProviderFactory`
  + `TokenUsageTracker` callback (AG-2, Phase 1). TokenUsageTracker
  уже пишет `event_type: "llm_usage"` в operational stream с
  `cost_estimate_usd` (per `_COST_PER_1M` hardcode table строки 32-35
  `src/llm_client/agent/provider.py`).
- ADR-015 (Блок C-2) будет читать metrics через Prometheus query
  API: `prometheus_client.Prometheus.query('rate(llm_call_total{provider="openai",status="error"}[5m])')`
  или через in-memory `LLMCallMetrics` aggregate (Блок C-2 определит
  конкретный interface).
- ТРИЗ Standard 5.1.1 (введение вещества извне): Prometheus =
  external substance, вводится в триаду (LLM ↔ Router ↔ External
  API) для динамизации circuit breaker.
- `prometheus_client` Python package уже есть в `pyproject.toml`
  (или нужно добавить — проверь).
- ADR-013 cancel endpoint уже экспонирует `/metrics` route на
  FastAPI (`src/llm_client/agent/service.py`); Phase 3 добавляет
  LLM-specific metrics.
- ARCHITECT.md v1.3.0 §6 Grafana dashboards: `idealidad.json`,
  `checkpoint-latency.json`, `checkpoint-recovery.json`,
  `hybrid-recall.json` — Phase 3 добавит `llm-cost-router.json`
  (Блок F-2).
- Metric naming convention (Prometheus best practices): use `_total`
  suffix for counters, `_seconds` for histograms, no camelCase.

Задача:
1. Убедись, что `prometheus_client` есть в `pyproject.toml`
   dependencies. Если нет — добавь:
   ```toml
   [project]
   dependencies = [
       # ... existing ...
       "prometheus_client>=0.20,<0.22",
   ]
   ```

2. Создай `src/llm_client/observability/llm_metrics.py`:
   ```python
   """Prometheus metrics for LLM calls (Phase 3 — ADR-015 circuit
   breaker input).

   Reuses TokenUsageTracker callback (AG-2 Phase 1) data flow:
   TokenUsageTracker.on_llm_end already writes to operational stream;
   here we also expose the same metrics to Prometheus for ADR-015
   router circuit breaker.

   Architecture: ARCHITECT.md v1.3.0 §5.2.3, §5.2.7 (Observability
   Layer). TRIZ Standard 5.1.1 — Prometheus as external substance
   for circuit breaker.
   """
   import logging
   from collections.abc import Callable
   from typing import Any

   from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

   logger = logging.getLogger(__name__)

   REGISTRY = CollectorRegistry(auto_describe=True)

   # Counters
   LLM_CALLS_TOTAL = Counter(
       "llm_call_total",
       "Total LLM calls by provider/model/status",
       labelnames=("provider", "model", "status", "mode"),
       registry=REGISTRY,
   )
   # status: "success" | "error" | "timeout" | "cancelled"
   # mode: "native" | "react" | "hybrid" (per ADR-016 ToolCallingMode)

   LLM_TOKENS_TOTAL = Counter(
       "llm_tokens_total",
       "Total tokens consumed by provider/model/type",
       labelnames=("provider", "model", "token_type"),
       registry=REGISTRY,
   )
   # token_type: "prompt" | "completion"

   LLM_COST_TOTAL = Counter(
       "llm_cost_usd_total",
       "Total LLM cost in USD by provider/model",
       labelnames=("provider", "model"),
       registry=REGISTRY,
   )

   # Histograms
   LLM_LATENCY = Histogram(
       "llm_call_latency_seconds",
       "LLM call latency in seconds",
       labelnames=("provider", "model"),
       buckets=(0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
       registry=REGISTRY,
   )

   # Gauges (for circuit breaker — ADR-015)
   LLM_ERROR_RATE = Gauge(
       "llm_error_rate_5m",
       "Rolling 5-min error rate per provider (circuit breaker input)",
       labelnames=("provider",),
       registry=REGISTRY,
   )

   LLM_MONTHLY_BUDGET_USAGE = Gauge(
       "llm_monthly_budget_usage_ratio",
       "Current monthly budget usage ratio (0.0–1.0+); cost guard at 0.8",
       registry=REGISTRY,
   )

   SEMANTIC_CACHE_HITS = Counter(
       "semantic_cache_hits_total",
       "Semantic cache hits/misses (ADR-011)",
       labelnames=("status",),  # "hit" | "miss" | "stale"
       registry=REGISTRY,
   )


   def record_llm_call(
       provider: str,
       model: str,
       status: str,
       mode: str,
       latency_seconds: float,
       prompt_tokens: int = 0,
       completion_tokens: int = 0,
       cost_usd: float = 0.0,
   ) -> None:
       """Record one LLM call. Called from TokenUsageTracker callback
       (Phase 1, AG-2) — see src/llm_client/agent/provider.py
       TokenUsageTracker.on_llm_end.
       """
       LLM_CALLS_TOTAL.labels(
           provider=provider, model=model, status=status, mode=mode
       ).inc()
       if prompt_tokens:
           LLM_TOKENS_TOTAL.labels(
               provider=provider, model=model, token_type="prompt"
           ).inc(prompt_tokens)
       if completion_tokens:
           LLM_TOKENS_TOTAL.labels(
               provider=provider, model=model, token_type="completion"
           ).inc(completion_tokens)
       if cost_usd > 0:
           LLM_COST_TOTAL.labels(provider=provider, model=model).inc(cost_usd)
       LLM_LATENCY.labels(provider=provider, model=model).observe(latency_seconds)


   def update_error_rate(provider: str, error_count_5m: int, total_count_5m: int) -> None:
       """Called periodically (e.g. every 30s) from background task."""
       rate = (error_count_5m / total_count_5m) if total_count_5m > 0 else 0.0
       LLM_ERROR_RATE.labels(provider=provider).set(rate)


   def update_budget_usage(used_usd: float, budget_usd: float) -> None:
       """Called from CostGuard (Блок C-3) on every cost update."""
       ratio = (used_usd / budget_usd) if budget_usd > 0 else 0.0
       LLM_MONTHLY_BUDGET_USAGE.set(ratio)


   def record_cache_hit(status: str) -> None:
       """Called from SemanticAnswerCache (Блок B-1)."""
       SEMANTIC_CACHE_HITS.labels(status=status).inc()
   ```

3. Расширь `src/llm_client/agent/provider.py` — в `TokenUsageTracker`
   callback `on_llm_end` добавь вызов `record_llm_call(...)`:
   ```python
   # existing TokenUsageTracker.on_llm_end (Phase 1):
   def on_llm_end(self, response, **kwargs):
       # existing: write to operational stream (ADR-014)
       self._operational_writer.write({...})
       # NEW Phase 3: also export to Prometheus
       from ..observability.llm_metrics import record_llm_call
       record_llm_call(
           provider=self._provider,
           model=self._model,
           status="success" if response else "error",
           mode=getattr(self, "_tool_calling_mode", "native"),
           latency_seconds=self._last_call_latency,
           prompt_tokens=...,
           completion_tokens=...,
           cost_usd=...,
       )
   ```
   НЕ переопределяй существующий operational stream write (ADR-014
   DualStreamLogger) — только добавь Prometheus export поверх.

4. Добавь `/metrics` route в FastAPI `src/llm_client/agent/service.py`
   (если ещё не экспонирует; Phase 1 ADR-013 cancel metrics могли
   уже добавить — проверь):
   ```python
   from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
   from ..observability.llm_metrics import REGISTRY

   @app.get("/metrics")
   async def metrics():
       return Response(
           generate_latest(REGISTRY),
           media_type=CONTENT_TYPE_LATEST,
       )
   ```

5. Обнови `ops/prometheus/prometheus.yml` — убедись, что
   `agent-service:8000/metrics` уже в scrape_configs (если нет —
   добавь):
   ```yaml
   scrape_configs:
     - job_name: 'agent-service'
       metrics_path: /metrics
       static_configs:
         - targets: ['agent-service:8000']
   ```

6. Тесты в `tests/unit/test_llm_metrics.py`:
   - `test_record_llm_call_increments_counter` — после
     `record_llm_call("openai", "gpt-4o-mini", "success", "native",
     latency_seconds=0.5, prompt_tokens=100, completion_tokens=50,
     cost_usd=0.001)`, `LLM_CALLS_TOTAL.labels(...).collect()` shows
     1 call.
   - `test_record_llm_call_with_error_status` — status="error"
     increments the error counter (router ADR-015 reads this).
   - `test_update_budget_usage_at_80_percent` — `update_budget_usage(80,
     100)` sets gauge to 0.8 (trigger CostGuard, Блок C-3).
   - `test_record_cache_hit_hit_status` — `record_cache_hit("hit")`
     increments hits counter.
   - `test_metrics_endpoint_exposes_all_metrics` — FastAPI test
     client GET /metrics → 200, body contains `llm_call_total`,
     `llm_cost_usd_total`, `llm_call_latency_seconds`,
     `semantic_cache_hits_total`.
   - Integration: mock LLM call → TokenUsageTracker.on_llm_end
     fires → Prometheus counter incremented.

Definition of Done:
- `prometheus_client>=0.20` добавлен в `pyproject.toml`.
- `src/llm_client/observability/llm_metrics.py` существует с
  Counter/Histogram/Gauge declarations + `record_llm_call` /
  `update_error_rate` / `update_budget_usage` / `record_cache_hit`.
- `src/llm_client/agent/provider.py` `TokenUsageTracker.on_llm_end`
  вызывает `record_llm_call(...)` — существующий operational stream
  write не тронут.
- `/metrics` endpoint доступен на `agent-service:8000/metrics`,
  `curl http://localhost:8000/metrics` показывает все Phase 3 metrics
  (`llm_call_total`, `llm_cost_usd_total`, `llm_call_latency_seconds`,
  `llm_error_rate_5m`, `llm_monthly_budget_usage_ratio`,
  `semantic_cache_hits_total`).
- `ops/prometheus/prometheus.yml` скрейпит `agent-service:8000` —
  verified в Grafana (existing `idealidad.json` dashboard должен
  показать новые metrics после reload).
- 6+ новых тестов зелёные.
- Существующие тесты Phase 1/2 (`test_provider.py`, `test_kms_provider.py`)
  — не регрессируют (TokenUsageTracker callback signature не изменён,
  только добавлен новый вызов).

Антипаттерны:
- НЕ создавай новый `/metrics` route если он уже есть в Phase 1
  ADR-013 — расширь существующий registry теми же метриками.
- НЕ делай blocking Prometheus HTTP call в hot path LLM вызова —
  `record_llm_call` синхронно инкрементирует in-process Counter
  (atomic); Prometheus scrape забирает раз в 15-60 сек.
- НЕ хардкодь cost_per_1m в `llm_metrics.py` — используй
  `_COST_PER_1M` из `src/llm_client/agent/provider.py` (Блок C-1
  формализует в `ModelCostTable`).
- НЕ экспонируй PII в метки (label values) — `provider`, `model`,
  `status`, `mode` только; NEVER include query text or user ID.
- НЕ делай histogram buckets слишком мелкими (0.001, 0.01) —
  LLM latency обычно 0.5-30 сек; используй buckets (0.1, 0.25,
  0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0).
- НЕ пиши в Prometheus из `ForensicStreamWriter` (ADR-014) — forensic
  stream — audit log, не metrics; Prometheus только для operational.
- НЕ используй default `prometheus_client.REGISTRY` — используй
  custom `REGISTRY = CollectorRegistry(auto_describe=True)` для
  изоляции (предотвращает случайные collisions с другими libs).

Связанные ADR:
- Реализует: инфра для ADR-015 (router circuit breaker через
  Prometheus `llm_error_rate_5m` Gauge; cost guard через
  `llm_monthly_budget_usage_ratio` Gauge).
- Применяет: ADR-014 (operational stream — существующий flow
  TokenUsageTracker → operational_writer; добавлен параллельный
  flow в Prometheus, не замещает), Standard 5.1.1 ТРИЗ (Prometheus
  как вещество извне).
- Зависит от: Phase 1 AG-2 (`TokenUsageTracker` callback), Phase 1
  ADR-013 (`/metrics` route on FastAPI — если ещё нет, добавь).
- Расширяется в: Phase 4 — добавятся метрики `local_llm_*` для
  Ollama/Llama (latency p99, GPU memory, queue depth).
- Не затрагивает: ADR-010 (checkpoint metrics — уже в
  `checkpointers/metrics.py` Phase 2), ADR-017 (reranker metrics —
  уже в `rag/metrics.py` Phase 2).
```

### A-3. Alembic миграция `009_create_documents_facts.py` (Tier-1 storage для ADR-011)

```
Ты — Backend/Database-разработчик LLM Client. Создай Alembic миграцию
`009_create_documents_facts.py` — таблицу `documents_facts` для
Tier-1 facts cache (ADR-011). Факты извлекаются из документов при
индексации (Блок B-2 `FactsExtractor`) и используются в RAG retrieval
как дополнительный источник контекста.

Контекст:
- `migrations/versions/006_create_documents_table.py` (Phase 2)
  создал таблицу `documents` (id UUID, content TEXT, source_uri,
  title, page, indexed_at, search_vector tsvector — последний
  добавлен миграцией `007_add_tsvector_to_documents.py`).
- `migrations/versions/008_fix_documents_search_schema.py` (Phase 2)
  корректировал GIN index + `pg_trgm` extension для fuzzy search.
- ARCHITECT.md v1.3.0 §5.2.5 (RAG Layer) — three-tier cache:
  - Tier 1 (Phase 3 NEW): facts cache — `documents_facts` table,
    fact_text TEXT, fact_embedding VECTOR(1536), fact_metadata
    JSONB.
  - Tier 2 (Phase 2 existing): vector retrieval with reranker —
    `documents` table, search_vector + content.
  - Tier 3 (Phase 3 NEW): semantic answer cache in Redis DB 2
    (Блок A-1).
- ТРИЗ Standard 1.1.5 (введение второго поля в веполь): facts cache
  как второе поле в triad 3 (RAG Query ↔ Embeddings ↔ VectorStore) —
  после Phase 2 добавления BM25 как ещё одного поля, triad стала
  3-полевой, Phase 3 делает её 4-полевой.
- pgvector extension: если ещё не активирован в `migrations/versions/`,
  добавь `CREATE EXTENSION IF NOT EXISTS vector;` в начале миграции.
  Phase 2 мог использовать pure-Python embeddings (local_embeddings.py
  через sentence-transformers) без pgvector; Phase 3 facts cache
  требует pgvector для cosine sim поиска по fact_embedding.
- vector dimension: 1536 = OpenAI text-embedding-3-small (Phase 1
  default). В Phase 4 при переключении на BGE local embeddings
  dimension = 768 — миграция `010_alter_documents_facts_dimension.py`
  (Phase 4, не Phase 3).
- ТРИЗ-принцип 17 (переход в другое измерение): факт-экстракция
  вынесена на индекс-тайм, не на query-тайм.

Задача:
1. Создай `migrations/versions/009_create_documents_facts.py`:
   ```python
   """create documents_facts table for Phase 3 ADR-011 Tier-1 cache

   Revision ID: 009_create_documents_facts
   Revises: 008_fix_documents_search_schema
   Create Date: 2026-09-30

   Implements: ADR-011 Tier-1 facts cache (Phase 3 — Beta).
   Architecture: ARCHITECT.md v1.3.0 §5.2.5, §5.2.7 (Persistence).
   TRIZ: Standard 1.1.5 (введение второго поля в веполь), principle
   #17 (переход в другое измерение — extraction на индекс-тайм).
   """
   from alembic import op
   import sqlalchemy as sa
   from sqlalchemy.dialects import postgresql

   revision = "009_create_documents_facts"
   down_revision = "008_fix_documents_search_schema"
   branch_labels = None
   depends_on = None


   def upgrade() -> None:
       # 1. Ensure pgvector extension is available
       op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

       # 2. Create documents_facts table
       op.create_table(
           "documents_facts",
           sa.Column(
               "id",
               postgresql.UUID(as_uuid=True),
               primary_key=True,
               server_default=sa.text("gen_random_uuid()"),
           ),
           sa.Column(
               "document_id",
               postgresql.UUID(as_uuid=True),
               sa.ForeignKey("documents.id", ondelete="CASCADE"),
               nullable=False,
               index=True,
           ),
           sa.Column("fact_text", sa.Text, nullable=False),
           sa.Column(
               "fact_embedding",
               postgresql.ARRAY(sa.Float),
               nullable=True,  # nullable: facts can be extracted without embedding first
           ),
           sa.Column(
               "fact_metadata",
               postgresql.JSONB,
               server_default=sa.text("'{}'::jsonb"),
               nullable=False,
           ),
           sa.Column(
               "extracted_at",
               sa.DateTime(timezone=True),
               server_default=sa.text("now()"),
               nullable=False,
           ),
           sa.Column(
               "extractor_model",
               sa.String(100),
               nullable=True,  # e.g. "gpt-4o-mini" or "ollama/llama3.1"
           ),
       )

       # 3. Indexes
       op.create_index(
           "ix_documents_facts_document_id",
           "documents_facts",
           ["document_id"],
       )
       op.create_index(
           "ix_documents_facts_extracted_at",
           "documents_facts",
           ["extracted_at"],
       )

       # 4. Optional: HNSW index on fact_embedding for fast cosine sim
       # NOTE: pgvector >=0.5.0 required; check pgvector version in CI.
       op.execute(
           "CREATE INDEX ix_documents_facts_embedding_hnsw "
           "ON documents_facts USING hnsw (fact_embedding vector_cosine_ops) "
           "WITH (m = 16, ef_construction = 64);"
       )

   def downgrade() -> None:
       op.drop_index("ix_documents_facts_embedding_hnsw", table_name="documents_facts")
       op.drop_index("ix_documents_facts_extracted_at", table_name="documents_facts")
       op.drop_index("ix_documents_facts_document_id", table_name="documents_facts")
       op.drop_table("documents_facts")
       # NOTE: do NOT drop pgvector extension (may be used by other tables)
   ```

2. Обнови `src/llm_client/rag/indexing/models.py` (Phase 2 — содержит
   SQLAlchemy models для `documents` table):
   ```python
   # add new model
   class DocumentFact(Base):
       """Phase 3 ADR-011 Tier-1 facts cache."""
       __tablename__ = "documents_facts"
       id: Mapped[UUID] = mapped_column(
           postgresql.UUID(as_uuid=True),
           primary_key=True,
           server_default=text("gen_random_uuid()"),
       )
       document_id: Mapped[UUID] = mapped_column(
           postgresql.UUID(as_uuid=True),
           ForeignKey("documents.id", ondelete="CASCADE"),
           nullable=False,
           index=True,
       )
       fact_text: Mapped[str] = mapped_column(Text, nullable=False)
       fact_embedding: Mapped[list[float] | None] = mapped_column(
           postgresql.ARRAY(Float),
           nullable=True,
       )
       fact_metadata: Mapped[dict] = mapped_column(
           postgresql.JSONB,
           server_default=text("'{}'::jsonb"),
           nullable=False,
       )
       extracted_at: Mapped[datetime] = mapped_column(
           DateTime(timezone=True),
           server_default=text("now()"),
           nullable=False,
       )
       extractor_model: Mapped[str | None] = mapped_column(String(100))

       document: Mapped["Document"] = relationship(back_populates="facts")

   # add to Document class
   Document.facts = relationship("DocumentFact", back_populates="document", cascade="all, delete-orphan")
   ```

3. Обнови `.env.example` — добавь env vars для фактов:
   ```env
   # === Phase 3 — ADR-011 Tier-1 Facts Cache ===
   FACTS_EXTRACTION_ENABLED=true
   FACTS_EXTRACTOR_MODEL=gpt-4o-mini
   FACTS_EXTRACTION_MAX_FACTS_PER_DOC=10
   FACTS_EMBEDDING_MODEL=text-embedding-3-small
   ```

4. Обнови `src/llm_client/config.py` Settings:
   ```python
   # Phase 3 — ADR-011 Tier-1 facts
   facts_extraction_enabled: bool = True
   facts_extractor_model: str = "gpt-4o-mini"
   facts_extraction_max_facts_per_doc: int = 10
   facts_embedding_model: str = "text-embedding-3-small"
   ```

5. Тесты в `tests/unit/test_documents_facts_migration.py`:
   - `test_migration_upgrade_creates_table` — Alembic upgrade head
     on test DB → `documents_facts` table exists.
   - `test_migration_downgrade_drops_table` — Alembic downgrade -1
     → table dropped.
   - `test_pgvector_extension_active` — `SELECT extname FROM
     pg_extension WHERE extname='vector'` returns row.
   - `test_hnsw_index_exists` — `SELECT indexname FROM pg_indexes
     WHERE tablename='documents_facts' AND indexname=
     'ix_documents_facts_embedding_hnsw'` returns row.
   - `test_foreign_key_cascade` — insert document → insert fact →
     delete document → fact also deleted (CASCADE).
   - Integration (`tests/integration/test_documents_facts_orm.py`):
     insert fact via SQLAlchemy ORM, query back, verify all fields.

Definition of Done:
- `migrations/versions/009_create_documents_facts.py` создан с
  revision chain `008 → 009`.
- `alembic upgrade head` выполняется без ошибок на пустой test DB
  (с pgvector extension, активируемым самой миграцией).
- `alembic downgrade -1` откатывает `009` чисто (без ошибок, без
  loss of `documents` table data — только `documents_facts`).
- `src/llm_client/rag/indexing/models.py` содержит `DocumentFact`
  ORM model с relationship `Document.facts`.
- `src/llm_client/config.py` содержит 4 новых поля Settings.
- `.env.example` обновлён.
- 5+ unit + 1 integration тестов зелёные.
- Существующие тесты Phase 2 (`test_bm25_indexer.py`,
  `test_hybrid_indexer.py`, `test_bm25_index_integration.py`) — не
  регрессируют (миграция additive, не трогает `documents` schema).

Антипаттерны:
- НЕ добавляй `fact_embedding` как NOT NULL — факты могут быть
  extracted (LLM call) без embedding (когда `FACTS_EXTRACTION_ENABLED=true`
  но `FACTS_EMBEDDING_MODEL` unavailable); embedding будет добавлен
  позже background job.
- НЕ используй IVFFlat index для `fact_embedding` — HNSW быстрее для
  cosine sim; IVFFlat имеет смысл только для >1M rows (Phase 5+
  scale).
- НЕ храни `fact_text` как JSONB — Text column с GIN index для
  full-text search по фактам (используется в fallback query).
- НЕ делай `fact_metadata` как TEXT — JSONB для query-able fields
  (`extractor_model`, `extraction_confidence`, `source_section`,
  `page_range`).
- НЕ хардкодь vector dimension 1536 — используй Settings
  (`facts_embedding_dimension: int = 1536` default; Phase 4 при
  BGE local embeddings = 768, миграция `010_alter_*`).
- НЕ делай `extractor_model` как enum — string с конвенцией
  `{provider}/{model}` (e.g. `"openai/gpt-4o-mini"`,
  `"ollama/llama3.1"`) для ADR-015 router flexibility.
- НЕ используй `fact_metadata` для хранения `fact_embedding` —
  embedding в отдельной column для эффективного pgvector index.
- НЕ забудь `ondelete="CASCADE"` на FK `document_id` — при удалении
  документа факты должны удаляться автоматически (Блок B-3 cache
  invalidator опирается на этот cascade).

Связанные ADR:
- Реализует: инфра для ADR-011 (Tier-1 storage на `documents_facts`
  PostgreSQL table).
- Применяет: расширенный ADR-008 (multi-tier storage: S3 для files,
  PostgreSQL для structured data + embeddings, Redis для cache;
  Phase 2 уже применил для `documents.search_vector` tsvector),
  Standard 1.1.5 ТРИЗ (facts cache как второе поле в RAG triad).
- Зависит от: Phase 2 миграция `006_create_documents_table.py`
  (FK target `documents.id`), Phase 2 `007_add_tsvector_to_documents.py`
  (pattern для ALTER TABLE).
- Расширяется в: Phase 4 — миграция `010_alter_documents_facts_dimension`
  (если switch на BGE local embeddings, dimension 1536 → 768),
  background facts extractor для orphan documents (doc inserted
  Phase 2 without facts, extracted Phase 4 batch).
- Не затрагивает: ADR-017 (reranker — operates on retrieval results
  in-memory, not on storage), ADR-020 (hybrid retriever — queries
  `documents.search_vector`, не `documents_facts`; Tier-1 facts
  retriever — отдельный код в Блоке B-2).
```

---

## 2. Блок B. ADR-011: Hybrid Semantic Cache for LLM

Блок B реализует ADR-011 — three-tier semantic cache:

- **Tier 3** (Redis DB 2, Блок A-1): semantic **answer** cache — полные LLM responses по embedding similarity >0.92, TTL=24h, invalidation при изменении referenced documents.
- **Tier 1** (PostgreSQL `documents_facts`, Блок A-3): facts cache — факты извлекаются при индексации, используются в retrieval как дополнительный контекст (сокращает длину context для LLM на 60–80%).
- **Tier 2** (Phase 2 existing, не трогать): vector retrieval + reranker.

Пилотные метрики (ROADMAP §14.1): 100 запросов на staging — hit rate cache >15%, stale answers <1%, latency cache hit <100мс. Rollback: stale >1% OR hit rate <10%.

TRIZ: Standard 1.1.5 (введение второго поля в веполь — semantic cache как второе поле в triad 1 LLM↔Tool Registry↔External API); Standard 5.3.1 (введение производного вещества — semantic cache как производное от checkpoint-WAL); принципы #16 (частичное/избыточное), #21 (сканирование вперёд), #9 (предварительное), #17 (переход в другое измерение — extraction на индекс-тайм).

---

### B-1. `SemanticAnswerCache` (Tier-3, Redis, cosine sim > 0.92)

```
Ты — Backend/ML-разработчик LLM Client. Создай класс `SemanticAnswerCache`
(Tier-3 ADR-011) — кэш полных LLM responses в Redis DB 2 по embedding
similarity запроса. Threshold cosine sim > 0.92, TTL=24h.

Контекст:
- ADR-011 (TRIZ-ANALYSIS.md v1.0.0 §11 драфт): Tier-3 cache хранит
  полный LLM response, key = hash(query_embedding), value =
  JSON {answer, referenced_doc_ids, created_at, model, token_count},
  TTL=24h, threshold cosine sim > 0.92.
- Блок A-1 создал Redis DB 2 на `redis://redis:6380/2`, env
  `REDIS_SEMANTIC_CACHE_URL`, settings: `semantic_cache_enabled`,
  `semantic_cache_ttl_seconds=86400`,
  `semantic_cache_similarity_threshold=0.92`,
  `semantic_cache_max_entries=10000`.
- Блок A-2 создал `record_cache_hit("hit"|"miss"|"stale")` in
  `src/llm_client/observability/llm_metrics.py`.
- ARCHITECT.md v1.3.0 §5.2.5 (RAG Layer) — three-tier cache: Tier-1
  facts, Tier-2 vector+reranker, Tier-3 answer cache.
- Phase 2 RagPipeline (`src/llm_client/rag/pipeline.py`) singleton
  используется для retrieval; Phase 3 Tier-3 cache обходит RagPipeline
  (cache hit = no RAG retrieval at all).
- `OpenAIEmbeddings` из Phase 1 (`text-embedding-3-small`, 1536d) —
  используется для query embedding. В Phase 4 заменится на BGE local.
- ТРИЗ Standard 5.3.1 (введение производного вещества): semantic
  cache — производное вещество от обычного key-value cache (modified
  for semantic similarity, не exact match).
- ТРИЗ принцип 21 (сканирование вперёд): при cache miss мы можем
  pre-compute embeddings для следующих likely queries (пока LLM
  генерирует ответ) — Phase 4+.
- LangGraph `planner` node (AG-1 + H-3) вызывает `llm.astream(...)`.
  Cache wrapper перехватывает перед astream.

Задача:
1. Создай `src/llm_client/rag/semantic_cache.py`:
   ```python
   """Tier-3 Semantic Answer Cache (ADR-011 Phase 3).

   Stores full LLM responses in Redis DB 2 keyed by query embedding.
   Cosine similarity >0.92 = cache hit. TTL=24h. Invalidation via
   referenced_doc_ids (see B-3 CacheInvalidator).

   Architecture: ARCHITECT.md v1.3.0 §5.2.5 (RAG Layer three-tier
   cache).
   TRIZ: Standard 5.3.1 (производное вещество — semantic, не exact
   match); principle #16 (частичное/избыточное — full cache, partial
   invalidation); principle #21 (сканирование вперёд).
   """
   import asyncio
   import hashlib
   import json
   import logging
   import time
   from dataclasses import dataclass
   from typing import Any
   from uuid import UUID

   import numpy as np
   import redis.asyncio as redis
   from langchain_openai import OpenAIEmbeddings

   from ..config import get_settings
   from ..observability.llm_metrics import record_cache_hit

   logger = logging.getLogger(__name__)


   @dataclass
   class CacheHitResult:
       answer: str
       referenced_doc_ids: list[UUID]
       created_at: str
       model: str
       token_count: int
       similarity_score: float


   class SemanticAnswerCache:
       """Tier-3 answer cache. Wraps LLM call ( planner node in
       build_agent_graph ) — see B-5 Pipeline integration."""

       EMBEDDING_NAMESPACE = "sem_cache:emb"
       ANSWER_NAMESPACE = "sem_cache:ans"

       def __init__(
           self,
           redis_url: str,
           embeddings: OpenAIEmbeddings,
           ttl_seconds: int = 86400,
           similarity_threshold: float = 0.92,
           max_entries: int = 10000,
       ) -> None:
           self._redis = redis.from_url(redis_url)
           self._embeddings = embeddings
           self._ttl = ttl_seconds
           self._threshold = similarity_threshold
           self._max_entries = max_entries

       async def get(self, query: str) -> CacheHitResult | None:
           """Check cache for semantically similar query. Returns
           CacheHitResult if cosine sim > threshold, else None."""
           query_emb = await self._embeddings.aembed_query(query)
           query_vec = np.array(query_emb, dtype=np.float32)

           # SCAN all embedding keys (O(N) but N <= max_entries=10k)
           # Phase 4 optimization: HNSW index in Redis Vector Library
           best_score = 0.0
           best_key: str | None = None
           cursor = 0
           while True:
               cursor, keys = await self._redis.scan(
                   cursor=cursor, match=f"{self.EMBEDDING_NAMESPACE}:*", count=500
               )
               if not keys:
                   if cursor == 0:
                       break
                   continue
               # MGET embeddings as bytes
               embeddings_raw = await self._redis.mget(keys)
               for key, raw in zip(keys, embeddings_raw):
                   if raw is None:
                       continue
                   cached_vec = np.frombuffer(raw, dtype=np.float32)
                   # cosine sim
                   score = float(np.dot(query_vec, cached_vec) / (
                       np.linalg.norm(query_vec) * np.linalg.norm(cached_vec) + 1e-9
                   ))
                   if score > best_score:
                       best_score = score
                       best_key = key.decode() if isinstance(key, bytes) else key
               if cursor == 0:
                   break

           if best_key is None or best_score < self._threshold:
               record_cache_hit("miss")
               return None

           # Fetch answer by hash key (best_key = "sem_cache:emb:<hash>")
           hash_key = best_key.split(":", 2)[-1]
           answer_raw = await self._redis.get(f"{self.ANSWER_NAMESPACE}:{hash_key}")
           if answer_raw is None:
               # orphan embedding (answer evicted by LRU) — treat as miss
               record_cache_hit("miss")
               return None

           data = json.loads(answer_raw)
           # Staleness check (Блок B-3 invalidator мог mark stale)
           if data.get("stale", False):
               record_cache_hit("stale")
               return None

           record_cache_hit("hit")
           logger.info(
               "Semantic cache HIT query=%r score=%.4f hash=%s",
               query[:80], best_score, hash_key,
           )
           return CacheHitResult(
               answer=data["answer"],
               referenced_doc_ids=[UUID(d) for d in data.get("referenced_doc_ids", [])],
               created_at=data["created_at"],
               model=data["model"],
               token_count=data.get("token_count", 0),
               similarity_score=best_score,
           )

       async def put(
           self,
           query: str,
           answer: str,
           referenced_doc_ids: list[UUID],
           model: str,
           token_count: int,
       ) -> None:
           """Store LLM response in cache. Called after planner node
           completes astream (Блок B-5 integration)."""
           query_emb = await self._embeddings.aembed_query(query)
           vec_bytes = np.array(query_emb, dtype=np.float32).tobytes()
           hash_key = hashlib.sha256(vec_bytes).hexdigest()[:16]

           data = {
               "answer": answer,
               "referenced_doc_ids": [str(d) for d in referenced_doc_ids],
               "created_at": time.time(),
               "model": model,
               "token_count": token_count,
               "stale": False,
           }
           pipe = self._redis.pipeline()
           pipe.set(
               f"{self.EMBEDDING_NAMESPACE}:{hash_key}", vec_bytes,
               ex=self._ttl,
           )
           pipe.set(
               f"{self.ANSWER_NAMESPACE}:{hash_key}", json.dumps(data),
               ex=self._ttl,
           )
           # Soft cap on entries (LRU eviction also at Redis level)
           await self._evict_if_needed(pipe)
           await pipe.execute()

       async def mark_stale(self, doc_id: UUID) -> int:
           """Mark all cached answers referencing doc_id as stale.
           Called from B-3 CacheInvalidator on document update."""
           count = 0
           cursor = 0
           while True:
               cursor, keys = await self._redis.scan(
                   cursor=cursor,
                   match=f"{self.ANSWER_NAMESPACE}:*",
                   count=500,
               )
               if not keys:
                   if cursor == 0:
                       break
                   continue
               raw_values = await self._redis.mget(keys)
               pipe = self._redis.pipeline()
               for key, raw in zip(keys, raw_values):
                   if raw is None:
                       continue
                   data = json.loads(raw)
                   if str(doc_id) in data.get("referenced_doc_ids", []):
                       data["stale"] = True
                       pipe.set(key, json.dumps(data), ex=self._ttl)
                       count += 1
               await pipe.execute()
               if cursor == 0:
                   break
           return count

       async def _evict_if_needed(self, pipe: redis.client.Pipeline) -> None:
           """Soft cap enforcement — if entries > max, delete oldest."""
           # count entries (O(1) via dbsize is global, so we approximate
           # by scanning one batch)
           # For production, use a separate "index" sorted set with timestamps
           pass  # placeholder — Redis LRU handles eviction; soft cap is safety net

       async def close(self) -> None:
           await self._redis.close()


   _singleton: SemanticAnswerCache | None = None


   def get_semantic_cache() -> SemanticAnswerCache | None:
       """Returns singleton SemanticAnswerCache or None if disabled."""
       global _singleton
       if _singleton is not None:
           return _singleton
       s = get_settings()
       if not s.semantic_cache_enabled:
           return None
       embeddings = OpenAIEmbeddings(model=s.facts_embedding_model)
       _singleton = SemanticAnswerCache(
           redis_url=s.redis_semantic_cache_url,
           embeddings=embeddings,
           ttl_seconds=s.semantic_cache_ttl_seconds,
           similarity_threshold=s.semantic_cache_similarity_threshold,
           max_entries=s.semantic_cache_max_entries,
       )
       return _singleton
   ```

2. Тесты в `tests/unit/test_semantic_cache.py`:
   - `test_cache_miss_on_empty_cache` — fresh Redis, `get("hello")`
     returns None, `record_cache_hit("miss")` increments miss
     counter.
   - `test_cache_put_then_get_hit` — `put("q", "a", [doc1],
     "gpt-4o-mini", 100)` then `get("q")` returns `CacheHitResult`
     with `similarity_score >= 0.99` (exact match).
   - `test_cache_get_below_threshold_returns_miss` — put("q1") then
     get("totally different query") returns None (cosine sim < 0.92).
   - `test_cache_get_semantically_similar_query_hits` — put("What is
     Python?") then get("What is the Python language?") — sim > 0.92
     (verify with real OpenAI embeddings OR mock).
   - `test_cache_ttl_expiry` — put(...) with ttl=2 seconds, sleep 3,
     get returns None.
   - `test_cache_mark_stale_on_doc_update` — put answer referencing
     doc_id=UUID(...), then `mark_stale(doc_id)` → next get returns
     None (stale).
   - `test_cache_record_hit_metrics` — after 3 hits + 2 misses +
     1 stale, Prometheus `semantic_cache_hits_total{status="hit"}=3`,
     `{status="miss"}=2`, `{status="stale"}=1`.
   - Integration (`tests/integration/test_semantic_cache_integration.py`):
     real Redis container, real OpenAIEmbeddings (mock HTTP), verify
     end-to-end put→get.

3. Manual probe script `scripts/probe_semantic_cache.py`:
   ```python
   """Probe semantic cache: put 3 queries, then get variations."""
   import asyncio
   from llm_client.rag.semantic_cache import get_semantic_cache

   async def main():
       cache = get_semantic_cache()
       await cache.put("What is Python?", "Python is a programming language...", [], "gpt-4o-mini", 100)
       await cache.put("How does RAG work?", "RAG retrieves...", [], "gpt-4o-mini", 100)
       # Now query with paraphrase
       result = await cache.get("What's the Python language?")
       print(f"Hit: {result.similarity_score if result else None}")

   if __name__ == "__main__":
       asyncio.run(main())
   ```

Definition of Done:
- `src/llm_client/rag/semantic_cache.py` существует с классом
  `SemanticAnswerCache` (5 methods: get, put, mark_stale,
  _evict_if_needed, close) + `get_semantic_cache()` factory.
- Cosine sim threshold 0.92 работает: paraphrase queries hit,
  unrelated queries miss (verified via tests с real OpenAI
  embeddings OR mock).
- TTL=24h expires correctly (verified via ttl=2s test).
- `mark_stale(doc_id)` находит и помечает все cached answers
  referencing that doc_id (verified via test_cache_mark_stale).
- Prometheus counter `semantic_cache_hits_total` correctly records
  hit/miss/stale.
- 8+ новых тестов зелёные.
- Существующие тесты Phase 2 (`test_rag_pipeline.py`,
  `test_pipeline_singleton.py`) — не регрессируют (Блок B-5
  integration ещё не подключён).

Антипаттерны:
- НЕ храни embeddings как JSON в Redis — только bytes через
  `numpy.ndarray.tobytes()` (4× compactнее, faster parse).
- НЕ делай SCAN с match `*` — используй namespace prefix
  `sem_cache:emb:*` для изоляции от других Redis keys.
- НЕ храни весь query text в Redis — только hash от embedding (для
  privacy, PII safety).
- НЕ делай blocking Redis call в hot path LLM — `redis.asyncio`
  async API, не sync.
- НЕ возвращай stale answers как hit — mark stale и return None
  (Блок B-3 invalidator sets stale=True on doc update).
- НЕ используй Redis Vector Library (`redisvl`) в Phase 3 — это
  Phase 4+ optimization (HNSW index в Redis); Phase 3 simple SCAN
  O(N) при N <= 10k достаточно (<100ms).
- НЕ хардкодь embedding model — используй `settings.facts_embedding_model`
  (в Phase 4 = "bge-local", в Phase 3 = "text-embedding-3-small").
- НЕ вызывай `cache.put()` если `referenced_doc_ids` пустой (answer
  не зависит от документов — generic LLM knowledge, кэш бесполезен
  для повторных похожих queries).
- НЕ забудь вызвать `record_cache_hit("hit"|"miss"|"stale")` —
  Блок E-1 тест будет проверять Prometheus counter.

Связанные ADR:
- Реализует: ADR-011 Tier-3 (semantic answer cache).
- Применяет: ADR-008 (расширенный storage — Redis как cache backend),
  Standard 5.3.1 ТРИЗ (производное вещество — semantic similarity
  cache вместо exact key match), принцип #16 (частичное/избыточное
  — full cache, partial invalidation).
- Зависит от: Блок A-1 (Redis DB 2 infra), Блок A-2 (record_cache_hit
  metric), Phase 1 AG-2 (OpenAIEmbeddings через langchain-openai),
  Phase 2 ADR-020 (RetrieverConfig — когда cache miss, fallback to
  RagPipeline с hybrid retrieval).
- Расширяется в: Phase 4 — Redis Vector Library (HNSW index) для
  O(log N) similarity search; BGE local embeddings (no OpenAI API
  per cache write); pre-compute likely queries (principle #21 full
  realization).
- Не затрагивает: ADR-010 (checkpoint-WAL DB 1 — изоляция), ADR-013
  (cancel pub/sub DB 0 — изоляция), ADR-017 (reranker — operates
  after retrieval, не before cache check).
```

### B-2. `FactsExtractor` (Tier-1, LLM call на индекс-тайм)

```
Ты — Backend/ML-разработчик LLM Client. Создай `FactsExtractor` —
LLM-based экстрактор фактов из документов при индексации (Tier-1
ADR-011). Факты сохраняются в `documents_facts` (Блок A-3) и
используются в retrieval как компактный контекст (сокращение
контекста для LLM на 60-80%).

Контекст:
- ADR-011 (TRIZ-ANALYSIS.md v1.0.0 §11 драфт): Tier-1 facts cache —
  при индексации документа извлекаются факты (LLM call), хранятся в
  `documents_facts` (fact_text, fact_embedding VECTOR(1536),
  fact_metadata JSONB). Используются в RAG retrieval.
- Блок A-3 создал таблицу `documents_facts` + ORM model
  `DocumentFact` в `src/llm_client/rag/indexing/models.py` +
  Alembic migration `009_create_documents_facts.py`.
- Phase 2 `src/llm_client/rag/indexing/hybrid_indexer.py` уже
  индексирует documents (vector + BM25). Phase 3 добавляет
  fact extraction step в indexing pipeline.
- ТРИЗ принцип 17 (переход в другое измерение): extraction вынесен
  на индекс-тайм, не на query-тайм (query-time = only embedding
  similarity lookup).
- ТРИЗ принцип 9 (предварительное противодействие): факты — это
  pre-computed answers на likely queries (типа "что указано в
  документе про X").
- ARCHITECT.md v1.3.0 §5.2.5 (RAG Layer three-tier) — Tier-1 facts
  retrieval должен быть отдельной нодой / отдельным pipeline
  step от Tier-2 vector retrieval.
- Settings (Блок A-3): `facts_extraction_enabled`,
  `facts_extractor_model="gpt-4o-mini"`,
  `facts_extraction_max_facts_per_doc=10`,
  `facts_embedding_model="text-embedding-3-small"`.
- ADR-015 (Блок C-2) будет использовать `_COST_PER_1M` для оценки
  cost extraction'а — ~$0.0005 per 10 facts per doc (gpt-4o-mini).

Задача:
1. Создай `src/llm_client/rag/indexing/facts_extractor.py`:
   ```python
   """Tier-1 Facts Extractor (ADR-011 Phase 3).

   Extracts atomic facts from documents at indexing time using LLM.
   Stores facts in documents_facts table with embeddings for fast
   retrieval.

   Architecture: ARCHITECT.md v1.3.0 §5.2.5.
   TRIZ: principle #17 (transition to another dimension — extraction
   at index-time, not query-time); principle #9 (preliminary action).
   """
   import json
   import logging
   from dataclasses import dataclass
   from typing import Any
   from uuid import UUID

   from langchain_openai import ChatOpenAI, OpenAIEmbeddings
   from sqlalchemy import select
   from sqlalchemy.ext.async import AsyncSession

   from ...config import get_settings
   from ..indexing.models import Document, DocumentFact

   logger = logging.getLogger(__name__)


   FACT_EXTRACTION_PROMPT = """You are a fact extractor. Given the
   document below, extract up to {max_facts} atomic, self-contained
   facts. Each fact must be a single sentence that conveys a specific
   piece of information from the document.

   Rules:
   - One fact = one sentence.
   - Each fact must be self-contained (no "the document says" prefix).
   - Skip trivial facts (e.g., "the document is about X").
   - Skip opinions; only facts.
   - Each fact must be attributable to a specific section/page if possible.

   Document title: {title}
   Document page: {page}
   Document content (truncated to 5000 chars):
   ---
   {content}
   ---

   Return JSON array of objects with keys:
   - "fact": string (the fact sentence)
   - "section": string | null (section heading if identifiable)
   - "page": int | null (page number)
   - "confidence": float (0.0-1.0; how central is this fact to the doc)

   Return ONLY the JSON array, no commentary.
   """


   @dataclass
   class ExtractedFact:
       fact: str
       section: str | None
       page: int | None
       confidence: float


   class FactsExtractor:
       """Extracts atomic facts from a document via LLM, embeds them,
       and persists to documents_facts table."""

       def __init__(
           self,
           llm: ChatOpenAI,
           embeddings: OpenAIEmbeddings,
           max_facts_per_doc: int = 10,
       ) -> None:
           self._llm = llm
           self._embeddings = embeddings
           self._max_facts = max_facts_per_doc

       async def extract_from_document(
           self,
           document: Document,
           session: AsyncSession,
       ) -> list[DocumentFact]:
           """Extract facts from one document, embed them, persist."""
           # Skip if document already has facts (idempotent)
           existing = await session.execute(
               select(DocumentFact).where(DocumentFact.document_id == document.id)
           )
           if existing.scalars().first() is not None:
               logger.debug("Doc %s already has facts — skip", document.id)
               return []

           # Truncate content (avoid huge LLM input)
           content = document.content[:5000] if document.content else ""
           if not content:
               logger.warning("Doc %s has empty content — skip fact extraction", document.id)
               return []

           prompt = FACT_EXTRACTION_PROMPT.format(
               max_facts=self._max_facts,
               title=document.title or "(no title)",
               page=document.page or 0,
               content=content,
           )

           # LLM call — gpt-4o-mini default, configurable
           response = await self._llm.ainvoke(prompt)
           try:
               facts_raw = json.loads(response.content)
               if not isinstance(facts_raw, list):
                   raise ValueError("Expected JSON array")
           except (json.JSONDecodeError, ValueError) as e:
               logger.error("LLM returned invalid JSON for doc %s: %s", document.id, e)
               return []

           # Embed all fact texts in one batch (cost optimization)
           fact_texts = [f["fact"] for f in facts_raw[:self._max_facts]]
           embeddings = await self._embeddings.aembed_documents(fact_texts)

           # Persist
           doc_facts: list[DocumentFact] = []
           for raw, emb in zip(facts_raw, embeddings):
               fact = DocumentFact(
                   document_id=document.id,
                   fact_text=raw["fact"],
                   fact_embedding=emb,
                   fact_metadata={
                       "section": raw.get("section"),
                       "page": raw.get("page"),
                       "confidence": raw.get("confidence", 0.5),
                   },
                   extractor_model=str(self._llm.model_name),
               )
               session.add(fact)
               doc_facts.append(fact)

           await session.commit()
           logger.info(
               "Extracted %d facts from doc %s", len(doc_facts), document.id,
           )
           return doc_facts

       async def extract_batch(
           self,
           documents: list[Document],
           session: AsyncSession,
           batch_size: int = 5,
       ) -> dict[str, int]:
           """Extract facts from multiple documents in batches.
           Returns {document_id_str: extracted_count}.
           """
           results = {}
           for i in range(0, len(documents), batch_size):
               batch = documents[i:i + batch_size]
               # Sequential within batch (avoid OpenAI rate limit), batch
               # gives amortized concurrency
               for doc in batch:
                   try:
                       facts = await self.extract_from_document(doc, session)
                       results[str(doc.id)] = len(facts)
                   except Exception as e:
                       logger.error("Failed to extract facts from doc %s: %s", doc.id, e)
                       results[str(doc.id)] = 0
           return results


   _singleton: FactsExtractor | None = None


   def get_facts_extractor() -> FactsExtractor | None:
       global _singleton
       if _singleton is not None:
           return _singleton
       s = get_settings()
       if not s.facts_extraction_enabled:
           return None
       llm = ChatOpenAI(
         model=s.facts_extractor_model,
         temperature=0.0,
         api_key=s.openai_api_key,
       )
       embeddings = OpenAIEmbeddings(model=s.facts_embedding_model)
       _singleton = FactsExtractor(
           llm=llm,
           embeddings=embeddings,
           max_facts_per_doc=s.facts_extraction_max_facts_per_doc,
       )
       return _singleton
   ```

2. Расширь `src/llm_client/rag/indexing/hybrid_indexer.py` (Phase 2) —
   после vector + BM25 indexing, вызови `FactsExtractor`:
   ```python
   # existing HybridIndexer.index_document(document, session)
   # ... existing vector + BM25 indexing ...
   # NEW Phase 3:
   from .facts_extractor import get_facts_extractor
   extractor = get_facts_extractor()
   if extractor is not None:
       await extractor.extract_from_document(document, session)
   ```

3. Тесты в `tests/unit/test_facts_extractor.py`:
   - `test_extract_from_document_returns_facts` — mock LLM returns
     JSON [{fact: "...", confidence: 0.9}], FactsExtractor returns
     1 DocumentFact with fact_embedding populated.
   - `test_extract_skips_if_already_extracted` — document with
     existing facts → returns [] (idempotent).
   - `test_extract_handles_invalid_llm_response` — LLM returns
     "not json" → returns [] (no crash).
   - `test_extract_truncates_long_content` — document with 10000
     char content → LLM prompt contains only 5000 chars.
   - `test_extract_batch_processes_in_batches` — 12 documents,
     batch_size=5 → 3 batches, all processed.
   - `test_extract_metadata_includes_section_and_page` — LLM
     returns [{fact, section, page, confidence}] → DocumentFact.
     fact_metadata has all fields.
   - Integration (`tests/integration/test_facts_extractor_integration.py`):
     real OpenAI mock + real PostgreSQL test DB, end-to-end insert
     document → extract → query documents_facts.

4. Manual probe script `scripts/probe_facts_extractor.py`:
   - Insert test document (content = "Python is a programming
     language created by Guido van Rossum in 1991...").
   - Call `FactsExtractor.extract_from_document(doc, session)`.
   - Verify: `documents_facts` table contains rows with
     `fact_text` containing "Python is a programming language" or
     similar.

Definition of Done:
- `src/llm_client/rag/indexing/facts_extractor.py` существует с
  классом `FactsExtractor` + `get_facts_extractor()` factory.
- `HybridIndexer.index_document` вызывает `FactsExtractor` после
  vector + BM25 indexing (если `facts_extraction_enabled=True`).
- Idempotent: повторный вызов на том же документе возвращает [].
- LLM-invalid-response handled gracefully (no crash, returns []).
- Content truncated to 5000 chars (cost guard).
- 6+ новых unit + 1 integration тестов зелёные.
- Существующие тесты Phase 2 (`test_hybrid_indexer.py`,
  `test_bm25_indexer.py`, `test_hybrid_index_integration.py`) — не
  регрессируют (extension additive, не breaking change — если
  `facts_extraction_enabled=False`, HybridIndexer behavior идентичен
  Phase 2).

Антипаттерны:
- НЕ делай fact extraction на query-time — только на index-time
  (ТРИЗ принцип 17 — otherwise contradicts ADR-011 design).
- НЕ храни raw LLM response в `fact_metadata` — только structured
  fields (section, page, confidence); raw LLM response не нужен для
  retrieval.
- НЕ делай extraction синхронным в HTTP request path — индексация
  может быть slow job (background task, Celery в Phase 4+); Phase 3
  оставляет async-call-from-HybridIndexer (await в async session).
- НЕ используй ChatOpenAI с temperature > 0.0 — facts extraction
  должен быть deterministic (temperature=0.0).
- НЕ хардкодь model="gpt-4o-mini" — используй Settings
  (`facts_extractor_model`); в Phase 4 = "ollama/llama3.1" (через
  ADR-016 ToolCallingAdapter).
- НЕ делай extraction без idempotency check — повторный indexing
  того же документа должен НЕ пере-extract (check existing facts).
- НЕ делай batch embedding call per fact — batch все fact_texts в
  один `aembed_documents([...])` call (cost optimization, 1 API call
  per document вместо N).
- НЕ сохраняй fact_text длиннее 500 chars — LLM может возвращать
  verbose facts; truncate с warning.
- НЕ забудь commit session — без `session.commit()` facts не
  persist (SQLAlchemy AsyncSession default = no auto-commit).

Связанные ADR:
- Реализует: ADR-011 Tier-1 (facts cache extraction + storage).
- Применяет: ADR-006 (LLM tool calling — extraction через
  ChatOpenAI prompt, не через tool call; extraction = structured
  output через JSON parsing), Standard 1.1.5 ТРИЗ (facts как второе
  поле в RAG triad), принцип #17 (extraction на index-time).
- Зависит от: Блок A-3 (`documents_facts` table + DocumentFact ORM),
  Phase 2 HybridIndexer (existing indexing pipeline), Phase 1 AG-2
  (ChatOpenAI + OpenAIEmbeddings through langchain-openai).
- Расширяется в: Phase 4 — background job для orphan documents
  (inserted Phase 2 без facts), Ollama extractor (local model,
  $0 cost), custom fact schemas per document type (e.g. contract
  facts vs research facts).
- Не затрагивает: ADR-017 (reranker — operates on retrieval
  results, не на extraction), ADR-020 (hybrid retriever — queries
  `documents.search_vector`, не `documents_facts`; Tier-1 facts
  retrieval — отдельный code в B-7).
```

### B-3. `CacheInvalidator` (invalidation при document update/delete)

```
Ты — Backend-разработчик LLM Client. Создай `CacheInvalidator` —
компонент, который при update/delete документа помечает все cached
LLM answers (Tier-3), ссылающиеся на этот документ, как stale.
Это критично для ADR-011 pilot criterion "stale answers <1%".

Контекст:
- ADR-011 (TRIZ-ANALYSIS.md v1.0.0 §11 драфт): invalidation logic —
  track which `documents.id` values were used in each cached LLM
  response (stored as `referenced_doc_ids: list[UUID]` in cache value,
  Блок B-1); on document update/delete, scan cache for affected
  entries and mark stale (Блок B-1 `mark_stale(doc_id)`).
- Блок B-1 реализовал `SemanticAnswerCache.mark_stale(doc_id) ->
  int` (returns count of marked entries).
- Блок A-3 migration добавил `ondelete="CASCADE"` на FK
  `documents_facts.document_id` — факты удаляются автоматически при
  delete document; Tier-3 cache invalidation — отдельная задача.
- Phase 2 `HybridIndexer.delete_document(doc_id)` — удаляет document
  + facts (cascade), но Tier-3 Redis cache должен быть отдельно
  invalidated (Redis не связан с PostgreSQL CASCADE).
- Pilot rollback criterion (ROADMAP §14.1): stale answers >1% →
  rollback ADR-011.
- ТРИЗ принцип 9 (предварительное противодействие): при indexing-time
  сохраняем referenced_doc_ids; при update — preemptive invalidation.

Задача:
1. Создай `src/llm_client/rag/cache_invalidator.py`:
   ```python
   """Cache invalidator for ADR-011 Tier-3 semantic cache.

   When a document is updated or deleted, mark all cached LLM answers
   referencing that document as stale. Stale answers are not served
   (SemanticAnswerCache.get returns None for stale entries).

   Architecture: ARCHITECT.md v1.3.0 §5.2.5.
   TRIZ: principle #9 (preliminary action — preemptive invalidation
   before stale answer is served).
   """
   import logging
   from uuid import UUID

   from ..observability.llm_metrics import SEMANTIC_CACHE_HITS
   from .semantic_cache import get_semantic_cache

   logger = logging.getLogger(__name__)


   class CacheInvalidator:
       """Wraps SemanticAnswerCache.mark_stale with metrics + logging."""

       async def invalidate_doc(self, doc_id: UUID) -> int:
           """Invalidate all cached answers referencing doc_id.
           Returns count of invalidated entries."""
           cache = get_semantic_cache()
           if cache is None:
               logger.debug("Semantic cache disabled — skip invalidation")
               return 0
           count = await cache.mark_stale(doc_id)
           if count > 0:
               logger.info(
                   "Invalidated %d cached answers for doc_id=%s",
                   count, doc_id,
               )
           return count

       async def invalidate_batch(self, doc_ids: list[UUID]) -> int:
           """Invalidate multiple docs at once. Returns total count."""
           total = 0
           for doc_id in doc_ids:
               total += await self.invalidate_doc(doc_id)
           return total


   _singleton: CacheInvalidator | None = None


   def get_cache_invalidator() -> CacheInvalidator:
       global _singleton
       if _singleton is None:
           _singleton = CacheInvalidator()
       return _singleton
   ```

2. Расширь `src/llm_client/rag/indexing/hybrid_indexer.py` —
   в `delete_document` и `update_document` добавь invalidation call:
   ```python
   # existing HybridIndexer.delete_document(doc_id, session)
   async def delete_document(self, doc_id: UUID, session: AsyncSession) -> None:
       # NEW Phase 3: invalidate semantic cache BEFORE delete
       # (after delete, CASCADE removes facts; cache invalidation
       #  uses referenced_doc_ids, which still exist in cached value)
       from ..cache_invalidator import get_cache_invalidator
       await get_cache_invalidator().invalidate_doc(doc_id)
       # ... existing delete logic (SQLAlchemy delete + BM25 + vector) ...
       await session.commit()

   async def update_document(self, doc_id: UUID, new_content: str, session: AsyncSession) -> None:
       # NEW Phase 3: invalidate BEFORE update (stale check uses
       # old referenced_doc_ids)
       from ..cache_invalidator import get_cache_invalidator
       await get_cache_invalidator().invalidate_doc(doc_id)
       # ... existing update logic (re-index vector + BM25 +
       #     re-extract facts via B-2) ...
       await session.commit()
   ```

3. Тесты в `tests/unit/test_cache_invalidator.py`:
   - `test_invalidate_doc_marks_stale_entries` — put 3 cached
     answers (one referencing doc1, two referencing doc2),
     `invalidate_doc(doc1)` → 1 entry marked stale, 2 untouched.
   - `test_invalidate_doc_returns_zero_if_no_entries` — empty cache,
     invalidate_doc(any) returns 0 (graceful).
   - `test_invalidate_batch` — 3 docs, each with 2 cached answers →
     `invalidate_batch([doc1, doc2, doc3])` returns 6.
   - `test_invalidate_when_cache_disabled` —
     `semantic_cache_enabled=False` → `invalidate_doc` returns 0
     (no crash, graceful skip).
   - Integration (`tests/integration/test_invalidator_integration.py`):
     put cached answer → delete document via HybridIndexer → next
     `cache.get(query)` returns None (stale).

4. Manual probe: end-to-end scenario в `scripts/probe_invalidator.py`:
   - Index doc1, query "What's in doc1?" → LLM generates answer A,
     cached with referenced_doc_ids=[doc1.id].
   - Update doc1 (new content).
   - Query "What's in doc1?" again → cache.get returns None (stale).
   - LLM generates new answer B, cached.
   - Verify `semantic_cache_hits_total{status="stale"}` = 1.

Definition of Done:
- `src/llm_client/rag/cache_invalidator.py` существует с классом
  `CacheInvalidator` + `get_cache_invalidator()` factory.
- `HybridIndexer.delete_document` и `update_document` вызывают
  `CacheInvalidator.invalidate_doc(doc_id)` BEFORE delete/update.
- Stale answers не возвращаются (Блок B-1 `get()` проверяет `stale`
  field и возвращает None).
- 4+ unit + 1 integration тестов зелёные.
- End-to-end probe script работает: stale answer count в
  Prometheus counter = number of invalidated entries.
- Pilot criterion "stale answers <1%" verifiable via integration test
  with 100 simulated doc updates.

Антипаттерны:
- НЕ делай invalidation ПОСЛЕ delete document — `referenced_doc_ids`
  в cached value всё ещё содержит UUID (UUID не зависит от existence
  в PostgreSQL), но логически — invalidate BEFORE, чтобы ни один
  запрос между delete и invalidate не получил stale answer.
- НЕ удаляй cached entries полностью (DEL keys) — помечай stale=True
  (Блок B-1 `get()` проверяет stale field; Redis TTL=24h сам удалит).
  Причина: оставшиеся stale entries могут быть использованы для
  observability/audit, и deletion — O(N) scan + DEL, а mark_stale —
  тоже O(N) scan + SET; разница невелика, но deletion теряет audit.
- НЕ делай invalidation синхронно в HTTP request path — если cache
  большой (10k entries), SCAN может занять >100ms; используй
  background task (asyncio.create_task в Phase 3; Celery в Phase 4+).
  Phase 3 оставляет await (simplicity > perf при N <= 10k).
- НЕ забудь логировать count invalidated entries — критично для
  observability (Grafana panel "Cache invalidations per doc" в
  Блоке F-2).
- НЕ делай batch invalidation параллельно — sequential per doc_id
  (avoid Redis concurrent SCAN contention); batch = loop over doc_ids.

Связанные ADR:
- Реализует: ADR-011 invalidation logic (критичное pilot criterion
  "stale answers <1%").
- Применяет: принцип #9 ТРИЗ (предварительное противодействие —
  invalidate before delete/update), ADR-014 (observability через
  `semantic_cache_hits_total{status="stale"}` counter).
- Зависит от: Блок B-1 (`SemanticAnswerCache.mark_stale`), Phase 2
  HybridIndexer (existing delete/update methods).
- Расширяется в: Phase 4 — background async task (Celery) для
  long-running invalidations; partial invalidation (only invalidate
  affected section, не весь cached answer); pre-compute "next likely
  queries" и invalidate speculatively (principle #21 full).
- Не затрагивает: ADR-010 (checkpoint-WAL — не зависит от documents),
  ADR-017 (reranker — operates in-memory, не cached), ADR-013
  (cancel pub/sub).
```

### B-4. `CacheAwareLLMClient` (wrapper, перехват LLM call)

```
Ты — Backend/Agent-разработчик LLM Client. Создай `CacheAwareLLMClient`
— wrapper вокруг `BaseChatModel` (LangChain), который перед вызовом
LLM проверяет Tier-3 cache (Блок B-1); при cache hit — возвращает
cached answer без LLM call; при cache miss — вызывает LLM, сохраняет
ответ в cache.

Контекст:
- ADR-011 (TRIZ-ANALYSIS.md v1.0.0 §11 драфт): `CacheAwareLLMClient`
  interceptor — Tier-3 cache check перед LLM call.
- Блок B-1 реализовал `SemanticAnswerCache.get(query)` /
  `put(query, answer, ...)`.
- Phase 1 AG-2 `LLMProviderFactory.create(provider, model, api_key)`
  возвращает `BaseChatModel` (LangChain). `CacheAwareLLMClient` —
  wrapper, реализующий тот же interface (`BaseChatModel`), но с
  cache check перед `astream` / `ainvoke`.
- Phase 1 AG-1 `build_agent_graph(llm, token, tools, rag_pipeline=...)`
  принимает `llm` параметр. Phase 3 ADR-011 wrapper transparent —
  graph не знает, что использует cache (Блок B-5 integration).
- ТРИЗ принцип 16 (частичное/избыточное действие): cache — "избыточный"
  путь (LLM и так может ответить); "частичный" — cache intercept
  часть запросов, не все.

Задача:
1. Создай `src/llm_client/rag/cache_aware_llm.py`:
   ```python
   """CacheAwareLLMClient — wrapper around BaseChatModel with
   Tier-3 semantic cache check (ADR-011 Phase 3).

   Implements BaseChatModel interface (LangChain), transparent to
   graph. On ainvoke/astream: checks cache first; hit = return cached
   response; miss = call underlying LLM, put result in cache.

   Architecture: ARCHITECT.md v1.3.0 §5.2.5.
   TRIZ: principle #16 (partial/excessive — cache intercepts part).
   """
   import asyncio
   import logging
   from typing import Any, AsyncIterator
   from uuid import UUID

   from langchain_core.language_models import BaseChatModel
   from langchain_core.messages import AIMessage, BaseMessage
   from langchain_core.outputs import ChatGeneration, ChatResult

   from ..observability.llm_metrics import record_cache_hit
   from .semantic_cache import get_semantic_cache

   logger = logging.getLogger(__name__)


   class CacheAwareLLMClient(BaseChatModel):
       """Wraps a BaseChatModel with semantic cache."""

       underlying: BaseChatModel
       # Pydantic v2: declare as field, allow arbitrary types
       model_config = {"arbitrary_types_allowed": True}

       def __init__(self, underlying: BaseChatModel, **kwargs):
           # BaseChatModel.__init__ handles pydantic fields
           super().__init__(underlying=underlying, **kwargs)

       @property
       def _llm_type(self) -> str:
           return f"cache-aware-{self.underlying._llm_type}"

       def _extract_query(self, messages: list[BaseMessage]) -> str:
           """Extract the user query from messages for cache lookup."""
           # Use the last HumanMessage as the query
           for msg in reversed(messages):
               if msg.type == "human":
                   return msg.content
           # Fallback: join all message contents (rare in agent context)
           return "\n".join(m.content for m in messages)[:500]

       def _extract_referenced_doc_ids(self, messages: list[BaseMessage]) -> list[UUID]:
           """Extract document_ids from ToolMessages in context
           (rag_query tool returns chunks with doc_id metadata)."""
           doc_ids: list[UUID] = []
           for msg in messages:
               if msg.type == "tool" and hasattr(msg, "artifact"):
                   # AG-6 rag_query tool returns chunks with metadata
                   for chunk in (msg.artifact or {}).get("chunks", []):
                       if "document_id" in chunk:
                           try:
                               doc_ids.append(UUID(chunk["document_id"]))
                           except (ValueError, TypeError):
                               continue
           return doc_ids

       async def _acall(self, messages: list[BaseMessage], **kwargs) -> ChatResult:
           cache = get_semantic_cache()
           if cache is None:
               # Cache disabled — pass through
               return await self.underlying._acall(messages, **kwargs)

           query = self._extract_query(messages)
           referenced_doc_ids = self._extract_referenced_doc_ids(messages)

           # Only cache answers that reference documents (RAG-grounded).
           # Pure-knowledge answers (empty referenced_doc_ids) are not
           # cached — they may differ for same query with different context.
           if not referenced_doc_ids:
               return await self.underlying._acall(messages, **kwargs)

           hit = await cache.get(query)
           if hit is not None:
               # Cache HIT — synthesize ChatResult from cached answer
               ai_msg = AIMessage(content=hit.answer)
               return ChatResult(generations=[ChatGeneration(message=ai_msg)])

           # Cache MISS — call underlying LLM, stream response to
           # accumulate full answer, then put in cache
           result = await self.underlying._acall(messages, **kwargs)
           answer = result.generations[0].message.content

           # Determine token_count for cache value (best-effort)
           token_count = getattr(result.llm_output, "token_usage", {}).get(
               "total_tokens", 0
           ) if result.llm_output else 0

           # Persist in cache (fire-and-forget)
           asyncio.create_task(
               cache.put(
                   query=query,
                   answer=answer,
                   referenced_doc_ids=referenced_doc_ids,
                   model=self.underlying._identifying_params.get("model", "unknown"),
                   token_count=token_count,
               )
           )

           return result

       async def astream(self, messages: list[BaseMessage], **kwargs) -> AsyncIterator[BaseMessage]:
           """Stream with cache check. For cache HIT, we cannot truly
           stream (we have the full answer); we chunk it into words."""
           cache = get_semantic_cache()
           if cache is None:
               async for chunk in self.underlying.astream(messages, **kwargs):
                   yield chunk
               return

           query = self._extract_query(messages)
           referenced_doc_ids = self._extract_referenced_doc_ids(messages)
           if not referenced_doc_ids:
               async for chunk in self.underlying.astream(messages, **kwargs):
                   yield chunk
               return

           hit = await cache.get(query)
           if hit is not None:
               # Simulate streaming by chunking the cached answer
               for word in hit.answer.split():
                   yield AIMessage(content=word + " ")
               return

           # Cache MISS — stream from underlying, accumulate, then put
           chunks: list[str] = []
           async for chunk in self.underlying.astream(messages, **kwargs):
               chunks.append(chunk.content)
               yield chunk
           full_answer = "".join(chunks)
           asyncio.create_task(
               cache.put(
                   query=query,
                   answer=full_answer,
                   referenced_doc_ids=referenced_doc_ids,
                   model=self.underlying._identifying_params.get("model", "unknown"),
                   token_count=0,  # unknown during stream
               )
           )

       def _generate(self, messages: list[BaseMessage], **kwargs) -> ChatResult:
           # Sync — fallback to underlying (no cache check, cache is async)
           return self.underlying._generate(messages, **kwargs)
   ```

2. Тесты в `tests/unit/test_cache_aware_llm.py`:
   - `test_cache_miss_calls_underlying` — mock underlying._acall,
     mock cache.get returns None, CacheAwareLLMClient._acall calls
     underlying._acall once.
   - `test_cache_hit_skips_underlying` — mock cache.get returns
     CacheHitResult(answer="cached"), underlying._acall NEVER
     called.
   - `test_cache_hit_returns_synthesized_message` — verify returned
     ChatResult.generations[0].message.content == "cached".
   - `test_no_referenced_doc_ids_bypasses_cache` — messages without
     ToolMessage artifacts (no RAG context) → cache.get NOT called,
     underlying called directly.
   - `test_cache_disabled_passes_through` — `semantic_cache_enabled
     =False` → CacheAwareLLMClient behaves as transparent proxy.
   - `test_put_called_after_miss` — mock cache.put, verify called
     with correct args (query, answer, referenced_doc_ids).
   - `test_astream_cache_hit_chunks_answer` — cache hit on astream
     → yield AIMessage per word.
   - `test_astream_cache_miss_accumulates_and_puts` — stream from
     underlying, accumulate chunks, verify cache.put called with
     full accumulated answer.
   - Integration (`tests/integration/test_cache_aware_llm_integration.py`):
     real cache + mock LLM, end-to-end miss→put→hit.

Definition of Done:
- `src/llm_client/rag/cache_aware_llm.py` существует с классом
  `CacheAwareLLMClient` (extends BaseChatModel).
- `astream` и `_acall` (async) проверяют cache; sync `_generate`
  fallback без cache (synchronous LLM calls rare in production).
- Cache hit возвращает synthesize ChatResult без underlying LLM call.
- Cache miss persist (asyncio.create_task) — fire-and-forget,
  не блокирует return response.
- 8+ unit + 1 integration тестов зелёные.
- Существующие тесты Phase 2 (`test_provider.py`, `test_graph_cancel_inflight.py`)
  — не регрессируют (Блок B-5 graph integration ещё не подключён;
  CacheAwareLLMClient standalone wrapper).

Антипаттерны:
- НЕ делай cache.put() blocking в response path — fire-and-forget
  через asyncio.create_task (user получает ответ до cache write).
- НЕ кэшируй ответы без referenced_doc_ids — pure-knowledge answers
  зависят от conversation context, не только query; stale risk > value.
- НЕ делай sync cache check в async `astream` — используй
  `await cache.get(query)` (Redis async).
- НЕ переопределяй `_llm_type` со своим custom value — graph
  (`build_agent_graph`) может проверять `llm._llm_type == "openai"`
  для routing; используй prefix `cache-aware-{underlying._llm_type}`,
  graph-side routing обновится в Блоке B-5.
- НЕ хардкодь chunk size при simulated streaming (cache hit) —
  word-level chunking (natural для UI).
- НЕ делай cache hit _acall слишком умным (semantic synthesize) —
  просто return cached answer as AIMessage. Semantic enrichment =
  Phase 4+.
- НЕ забудь `model_config = {"arbitrary_types_allowed": True}` —
  Pydantic v2 strict mode не пропустит `BaseChatModel` field без
  этого.

Связанные ADR:
- Реализует: ADR-011 Tier-3 interceptor (cache check before LLM call).
- Применяет: принцип #16 ТРИЗ (частичное/избыточное — cache перехватывает
  часть запросов), ADR-006 (LLM tool calling — cache не interferes;
  tool calls inside cached answer replayed by graph from ToolMessage).
- Зависит от: Блок B-1 (`SemanticAnswerCache.get/put`), Phase 1 AG-2
  (`BaseChatModel` LangChain interface).
- Расширяется в: Phase 4 — streaming cache hit with token-level
  chunking (imitate underlying model's natural tokenization), partial
  cache (cache only the part of answer that references docs; не full
  answer).
- Не затрагивает: ADR-010 (checkpoint — graph state сериализуется
  как обычно; ToolMessage content сохраняется), ADR-014 (operational
  stream — TokenUsageTracker всё ещё пишет llm_usage event; в случае
  cache hit, event будет cost=0, что корректно).
```

### B-5. Pipeline integration (wire CacheAwareLLMClient в `build_agent_graph`)

```
Ты — Backend/Agent-разработчик LLM Client. Подключи CacheAwareLLMClient
(Блок B-4) в `build_agent_graph` — transparent wrapper вокруг LLM,
передаваемого в graph. Graph не знает, что использует cache; cache
intercept происходит на уровне `llm.astream` / `llm.ainvoke`.

Контекст:
- Phase 1 AG-1 (AG-PROMPTS.md §2): `build_agent_graph(llm, token,
  tools)` — LLM передаётся как параметр, graph использует
  `llm.bind_tools(tools)` в `planner` node.
- Phase 2 H-3 (ALPHA-PROMPTS.md): `build_agent_graph(llm, token,
  tools, rag_pipeline=pipeline)` — extended с rag_retriever нодой.
- Блок B-4 реализовал `CacheAwareLLMClient(underlying=BaseChatModel)`
  — extends BaseChatModel interface (transparent wrapper).
- ADR-011 (TRIZ-ANALYSIS.md v1.0.0 §11): pipeline integration —
  cache intercept on `llm.astream` inside `planner` node.
- ТРИЗ принцип 25 (самообслуживание): graph сам не знает про cache;
  wrapper transparent; cache "сам" решает, когда вмешаться.
- ARCHITECT.md v1.3.0 §5.2.5 (RAG Layer) — cache check должен быть
  до RAG retrieval (Tier-3 hit = no RAG needed).

Задача:
1. Расширь `src/llm_client/agent/graph.py` (Phase 1 AG-1 + Phase 2
   H-3) — в `build_agent_graph` оберни `llm` в `CacheAwareLLMClient`
   если semantic_cache_enabled:
   ```python
   # existing Phase 2 build_agent_graph(llm, token, tools, rag_pipeline=None)
   def build_agent_graph(
       llm: BaseChatModel,
       token: CancellationToken,
       tools: list,
       rag_pipeline: RagPipeline | None = None,
       use_semantic_cache: bool | None = None,  # NEW Phase 3
   ) -> CompiledGraph:
       # NEW Phase 3: optionally wrap llm in CacheAwareLLMClient
       if use_semantic_cache is None:
           from ..config import get_settings
           use_semantic_cache = (
             get_settings().semantic_cache_enabled
             and get_semantic_cache() is not None
           )
       if use_semantic_cache:
           from ..rag.cache_aware_llm import CacheAwareLLMClient
           llm = CacheAwareLLMClient(underlying=llm)
           logger.info("Semantic cache enabled — wrapping LLM in CacheAwareLLMClient")
       # ... existing graph construction (Phase 1 AG-1 + Phase 2 H-3) ...
       # llm.bind_tools(tools) — теперь вызывается на CacheAwareLLMClient
       # wrapper должен поддерживать bind_tools (transparent pass-through).
   ```

2. Расширь `CacheAwareLLMClient` (Блок B-4) — добавь `bind_tools`
   pass-through method:
   ```python
   # in CacheAwareLLMClient (src/llm_client/rag/cache_aware_llm.py)
   def bind_tools(self, tools: list, **kwargs):
       """Pass-through to underlying; bind_tools result is also a
       BaseChatModel, but we don't wrap it again (would double-cache).
       Tool-call decisions are made by underlying model; cache
       intercept only on final text generation."""
       bound = self.underlying.bind_tools(tools, **kwargs)
       # Wrap the bound model in a thin proxy that intercepts astream
       # but preserves bound tool-calling behavior.
       return CacheAwareBoundModel(bound=bound, cache_llm=self)
   ```

3. Создай `CacheAwareBoundModel` minimal class в том же файле:
   ```python
   class CacheAwareBoundModel:
       """Wraps a tool-bound LLM with cache check. The tool-bound LLM
       (returned by bind_tools) does NOT extend BaseChatModel cleanly
       in LangChain 0.3 (it's a Runnable, not a BaseChatModel). We
       proxy astream/ainvoke through cache."""
       def __init__(self, bound, cache_llm: "CacheAwareLLMClient"):
           self._bound = bound
           self._cache_llm = cache_llm

       async def astream(self, messages, **kwargs):
           # Use cache_llm's cache logic, but call bound._call for
           # the actual LLM invocation (preserves tool-calling).
           # ... see CacheAwareLLMClient.astream for pattern ...
           ...

       async def ainvoke(self, messages, **kwargs):
           # Same: check cache, fall through to bound._call.
           ...

       # Proxy other Runnable methods through to self._bound.
       def __getattr__(self, name):
           return getattr(self._bound, name)
   ```

4. Тесты в `tests/unit/test_graph_semantic_cache_integration.py`:
   - `test_build_agent_graph_with_cache_wraps_llm` — pass
     use_semantic_cache=True → returned graph uses CacheAwareLLMClient
     (verify via graph.nodes['planner'].llm.__class__.__name__).
   - `test_build_agent_graph_without_cache_skips_wrapping` —
     use_semantic_cache=False → graph uses underlying llm directly.
   - `test_build_agent_graph_default_uses_settings` —
     `semantic_cache_enabled=True` in Settings → default wrapping.
   - `test_planner_node_cache_hit_skips_llm_call` — mock cache.get
     returns hit → planner node returns cached answer without
     calling underlying llm (verify llm.underlying.astream NOT called).
   - `test_planner_node_cache_miss_falls_through_to_llm` — cache miss
     → underlying llm.astream called, cache.put called with full
     answer.
   - `test_planner_node_with_tools_bound` — `llm.bind_tools(tools)`
     still works through CacheAwareBoundModel; tool_call emitted
     to SSE (Блок H-4 Phase 2 contract preserved).
   - Integration (`tests/integration/test_graph_cache_e2e.py`):
     real graph + mock LLM + real cache → end-to-end miss→put→hit→
     skip LLM call.

5. Обнови `src/llm_client/agent/__main__.py` и `agent/service.py` —
   при создании `llm` через `LLMProviderFactory.create(...)`, graph
   автоматически обернёт в cache (через default `use_semantic_cache
   = None` → Settings). Никаких явных изменений в service.py не
   требуется (transparent integration).

Definition of Done:
- `build_agent_graph(llm, token, tools, rag_pipeline=..., use_semantic_cache=...)`
  signature extended с опциональным параметром `use_semantic_cache`.
- Если `semantic_cache_enabled=True` (Settings) → llm автоматически
  обёрнут в `CacheAwareLLMClient`.
- `bind_tools` pass-through работает: graph emits `tool_call` SSE
  event (Блок H-4 Phase 2 contract preserved).
- Cache hit в planner node — underlying LLM NOT called (verified via
  mock assertion).
- Cache miss — cache.put called with full answer (asyncio.create_task).
- 6+ unit + 1 integration тестов зелёные.
- Существующие тесты Phase 2 (`test_graph_cancel_inflight.py`,
  `test_rag_query.py`, `test_pipeline_singleton.py`) — не
  регрессируют (если `semantic_cache_enabled=False` default в test
  env, поведение идентично Phase 2; если True — cache mock returns
  None для miss scenarios).

Антипаттерны:
- НЕ делай cache check в `rag_retriever` ноде — только в `planner`
  (Tier-3 hit = NO RAG retrieval; rag_retriever вообще не вызывается).
- НЕ переопределяй `llm.bind_tools` без сохранения tool-calling —
  bound model must still emit tool_call в SSE event (Блок H-4 contract).
- НЕ делай graph-level явный cache check (if/else в graph code) —
  cache logic живет в wrapper (transparent; ТРИЗ принцип 25).
- НЕ делай `use_semantic_cache` обязательным параметром — None =
  Settings default (для back-compat с Phase 1/2 tests).
- НЕ забудь логировать wrapping decision — `logger.info("Semantic
  cache enabled — wrapping LLM in CacheAwareLLMClient")` для
  debug-ability.
- НЕ делай CacheAwareBoundModel full BaseChatModel re-implementation
  — proxy через `__getattr__` для всех методов, кроме astream/ainvoke.

Связанные ADR:
- Реализует: ADR-011 pipeline integration (Tier-3 в graph).
- Применяет: принцип #25 ТРИЗ (самообслуживание — graph не знает
  про cache; wrapper transparent), ADR-006 (native tool calling —
  preserved through bind_tools proxy).
- Зависит от: Блок B-4 (CacheAwareLLMClient + CacheAwareBoundModel),
  Phase 1 AG-1 (build_agent_graph contract), Phase 2 H-3
  (rag_pipeline integration — preserved).
- Расширяется в: Phase 4 — cache-aware rag_retriever (cache query
  embeddings, не re-embed каждый раз), speculative pre-compute
  (principle #21 full — graph может pre-warm cache в idle time).
- Не затрагивает: ADR-010 (checkpoint — graph state сериализуется
  без изменений), ADR-013 (cancel — CancellationToken работает через
  wrapper transparent), ADR-014 (operational stream — TokenUsageTracker
  на underlying LLM всё ещё пишет llm_usage event; cache hit — cost=0).
```

### B-6. Metrics + A/B test framework для semantic cache

```
Ты — ML/Backend-разработчик LLM Client. Создай A/B test framework
для semantic cache — сравнение latency/cost/hit-rate с cache ON vs
cache OFF. Это пилотный фреймворк для ADR-011 Approved решения
(ROADMAP §14.1: 100 запросов на staging, hit rate >15%, stale
answers <1%, latency cache hit <100мс).

Контекст:
- Блок A-2 создал Prometheus counter `semantic_cache_hits_total{status=
  "hit"|"miss"|"stale"}`.
- Блок B-1 реализовал `record_cache_hit(status)`.
- Phase 2 уже имеет A/B framework для reranker: `scripts/ab_test_reranker.py`
  и `scripts/ab_test_hybrid_rag.py` — pattern для нового A/B test.
- ROADMAP §14.1 pilot criteria для ADR-011:
  - 100 запросов на staging
  - hit rate cache >15%
  - stale answers <1%
  - latency cache hit <100мс
- Rollback: stale answers >1% OR hit rate <10%.
- ТРИЗ Standard 2.2.4 (переход к измерительной веполи): semantic
  cache + metrics = measuring vepol; A/B test = сравнение двух
  состояний.

Задача:
1. Создай `scripts/ab_test_semantic_cache.py`:
   ```python
   """A/B test for semantic cache (ADR-011 Phase 3).

   Runs N queries twice: once with cache ON, once with cache OFF
   (control group). Reports:
   - Hit rate (cache ON)
   - Stale rate (cache ON)
   - Latency: cache hit, cache miss, cache OFF (control)
   - Cost savings (cache ON vs OFF)
   - LLM call reduction (cache ON vs OFF)

   Pilot criteria (ROADMAP §14.1):
   - hit rate >15% — PASS
   - stale <1% — PASS
   - latency cache hit <100ms — PASS
   Rollback: stale >1% OR hit rate <10%.
   """
   import argparse
   import asyncio
   import time
   from dataclasses import dataclass

   from llm_client.config import get_settings
   from llm_client.rag.semantic_cache import get_semantic_cache


   @dataclass
   class ABTestResult:
       total_queries: int
       hits: int
       misses: int
       stale: int
       avg_latency_hit_ms: float
       avg_latency_miss_ms: float
       avg_latency_no_cache_ms: float
       cost_saved_usd: float
       llm_calls_reduced: int

       @property
       def hit_rate(self) -> float:
           return self.hits / self.total_queries if self.total_queries else 0.0

       @property
       def stale_rate(self) -> float:
           return self.stale / self.hits if self.hits else 0.0

       def pilot_pass(self) -> bool:
           return (
               self.hit_rate > 0.15
               and self.stale_rate < 0.01
               and self.avg_latency_hit_ms < 100.0
           )

       def rollback_required(self) -> bool:
           return self.stale_rate > 0.01 or self.hit_rate < 0.10


   async def run_ab_test(queries: list[str], iterations: int = 2) -> ABTestResult:
       """Run queries twice with cache ON (second iteration should
       hit cache if queries are similar)."""
       cache = get_semantic_cache()
       if cache is None:
           raise RuntimeError("Semantic cache disabled")

       # First pass: populate cache (all misses expected)
       for q in queries:
           # simulate LLM call + cache put
           await cache.put(q, f"answer_to_{q}", [], "gpt-4o-mini", 100)

       # Second pass: hit cache
       hits, misses, stale = 0, 0, 0
       latencies_hit, latencies_miss = [], []

       for q in queries:
           t0 = time.perf_counter()
           result = await cache.get(q)
           elapsed_ms = (time.perf_counter() - t0) * 1000

           if result is None:
               misses += 1
               latencies_miss.append(elapsed_ms)
           elif result.similarity_score < 0.92:
               stale += 1
           else:
               hits += 1
               latencies_hit.append(elapsed_ms)

       return ABTestResult(
           total_queries=len(queries) * iterations,
           hits=hits, misses=misses, stale=stale,
           avg_latency_hit_ms=sum(latencies_hit) / max(1, len(latencies_hit)),
           avg_latency_miss_ms=sum(latencies_miss) / max(1, len(latencies_miss)),
           avg_latency_no_cache_ms=0.0,  # control group — measured separately
           cost_saved_usd=hits * 0.001,  # avg cost per LLM call
           llm_calls_reduced=hits,
       )


   def main():
       parser = argparse.ArgumentParser()
       parser.add_argument("--queries-file", required=True,
                           help="JSONL file with {query, expected_answer} entries")
       parser.add_argument("--iterations", type=int, default=2)
       args = parser.parse_args()

       import json
       with open(args.queries_file) as f:
           queries = [json.loads(line)["query"] for line in f]

       result = asyncio.run(run_ab_test(queries, args.iterations))

       print(f"=== ADR-011 Pilot A/B Test ===")
       print(f"Total queries: {result.total_queries}")
       print(f"Hits: {result.hits} ({result.hit_rate:.1%})")
       print(f"Misses: {result.misses}")
       print(f"Stale: {result.stale} ({result.stale_rate:.1%})")
       print(f"Avg latency (hit): {result.avg_latency_hit_ms:.1f}ms")
       print(f"Avg latency (miss): {result.avg_latency_miss_ms:.1f}ms")
       print(f"Cost saved: ${result.cost_saved_usd:.4f}")
       print(f"LLM calls reduced: {result.llm_calls_reduced}")
       print()
       if result.rollback_required():
           print("❌ ROLLBACK REQUIRED (hit rate <10% OR stale >1%)")
       elif result.pilot_pass():
           print("✅ PILOT PASS — ADR-011 Approved")
       else:
           print("⚠️  PILOT PARTIAL — review criteria")

   if __name__ == "__main__":
       main()
   ```

2. Создай dataset `datasets/rag_eval/phase3_semantic_cache_eval.jsonl` —
   100 queries с expected semantic duplicates (variations of same
   question — для проверки hit rate >15%):
   ```jsonl
   {"query": "What is Python?", "expected_answer": "...", "duplicate_group": 1}
   {"query": "What's the Python language?", "expected_answer": "...", "duplicate_group": 1}
   {"query": "Tell me about Python programming", "expected_answer": "...", "duplicate_group": 1}
   {"query": "How does RAG work?", "expected_answer": "...", "duplicate_group": 2}
   {"query": "Explain retrieval-augmented generation", "expected_answer": "...", "duplicate_group": 2}
   ...
   ```
   20 duplicate groups × 5 variations = 100 queries (для 80% hit rate
   с paraphrases; реалистично для LLM приложений).

3. Тесты в `tests/unit/test_ab_test_semantic_cache.py`:
   - `test_run_ab_test_returns_metrics` — mock cache.get returns hit
     on 2nd iteration, verify ABTestResult has correct counts.
   - `test_pilot_pass_when_hit_rate_above_15pct` — 16 hits / 100
     queries → pilot_pass() True (if latency <100ms).
   - `test_rollback_when_stale_rate_above_1pct` — 2 stale / 100 hits
     → rollback_required() True.
   - `test_rollback_when_hit_rate_below_10pct` — 9 hits → rollback.
   - `test_metrics_calculate_cost_savings` — 50 hits × $0.001 = $0.05.

Definition of Done:
- `scripts/ab_test_semantic_cache.py` существует с `run_ab_test` +
  `ABTestResult` + `main()` CLI.
- `datasets/rag_eval/phase3_semantic_cache_eval.jsonl` содержит 100
  queries с 20 duplicate groups × 5 variations.
- CLI: `python scripts/ab_test_semantic_cache.py --queries-file
  datasets/rag_eval/phase3_semantic_cache_eval.jsonl --iterations 2`
  → prints summary с PASS/ROLLBACK/PARTIAL verdict.
- 4+ unit тестов зелёные.
- На staging run (100 queries): hit rate >15% (ожидидается 70-80%
  для duplicate groups), stale <1%, latency cache hit <100ms.

Антипаттерны:
- НЕ делай A/B test с queries из разных domains — для корректного
  hit rate нужны semantic duplicates (paraphrases того же вопроса);
  random queries дадут ~0% hit rate.
- НЕ делай `avg_latency_no_cache_ms` placeholder навсегда — Phase 3
  можно mock (control group = `cache disabled`, run same queries);
  implementation Phase 4 для full control-group.
- НЕ хардкодь pilot thresholds (15%, 1%, 100ms) в коде — вынеси в
  Settings (для tuning без redeploy).
- НЕ забудь rollback verdict — критично для ADR-011 Approved
  decision per ROADMAP §14.1.
- НЕ сохраняй `expected_answer` в Prometheus labels (PII risk) —
  только aggregate metrics.

Связанные ADR:
- Реализует: ADR-011 pilot framework (критично для Approved решения
  per ROADMAP §14.1).
- Применяет: Standard 2.2.4 ТРИЗ (переход к измерительной веполи —
  A/B test = comparing two measured states), ADR-014 (operational
  stream — pilot metrics логируются).
- Зависит от: Блок B-1 (SemanticAnswerCache), Блок A-2
  (record_cache_hit metric), Phase 2 pattern `scripts/ab_test_reranker.py`.
- Расширяется в: Phase 4 — continuous A/B test (always-on control
  group via 5% traffic split), threshold tuning via Bayesian
  optimization.
- Не затрагивает: ADR-015 (router — separate A/B test in Блоке E-2),
  ADR-016 (tool adapter — separate A/B test в Блоке E-3).
```

### B-7. Stale-answer guard (automated test для invalidation)

```
Ты — QA/Backend-разработчик LLM Client. Создай automated test для
invalidation pipeline — симулирует doc update, проверяет, что cached
answer становится stale в течение 60 сек (Блок B-3 contract). Это
критично для ADR-011 pilot criterion "stale answers <1%".

Контекст:
- Блок B-3 реализовал `CacheInvalidator.invalidate_doc(doc_id)` —
  помечает cached answers referencing doc_id как stale.
- Блок B-1 реализовал `SemanticAnswerCache.get(query)` — проверяет
  stale field, возвращает None для stale.
- ROADMAP §14.1 ADR-011 pilot: stale answers <1%.
- ТРИЗ принцип 9 (предварительное противодействие): invalidation
  происходит до того, как stale answer будет отдан пользователю.
- Phase 2 уже имеет integration test pattern: `tests/integration/test_hybrid_retriever_integration.py`.

Задача:
1. Создай `tests/integration/test_stale_answer_guard.py`:
   ```python
   """Integration test: doc update invalidates cached answer
   within 60 seconds (ADR-011 pilot criterion).

   Verifies full invalidation pipeline:
   - HybridIndexer.update_document → CacheInvalidator.invalidate_doc
   - CacheInvalidator.invalidate_doc → SemanticAnswerCache.mark_stale
   - Next cache.get → returns None (stale)
   - Prometheus counter `semantic_cache_hits_total{status="stale"}`
     incremented.
   """
   import asyncio
   import pytest
   from uuid import uuid4

   from llm_client.rag.cache_invalidator import get_cache_invalidator
   from llm_client.rag.semantic_cache import get_semantic_cache


   @pytest.mark.integration
   @pytest.mark.asyncio
   async def test_doc_update_invalidates_cached_answer(redis_container,
                                                        postgres_container):
       """Setup: cache answer referencing doc_id. Update doc. Verify
       next cache.get returns None."""
       cache = get_semantic_cache()
       assert cache is not None, "Semantic cache must be enabled for this test"

       doc_id = uuid4()
       query = "What is in this document?"

       # Populate cache
       await cache.put(
           query=query,
           answer="Old answer based on old content",
           referenced_doc_ids=[doc_id],
           model="gpt-4o-mini",
           token_count=100,
       )

       # Verify cache hit before invalidation
       hit = await cache.get(query)
       assert hit is not None, "Cache hit expected after put"
       assert hit.answer == "Old answer based on old content"

       # Trigger invalidation (simulates HybridIndexer.update_document call)
       invalidator = get_cache_invalidator()
       count = await invalidator.invalidate_doc(doc_id)
       assert count == 1, f"1 cached answer should be invalidated, got {count}"

       # Verify cache returns None (stale)
       miss = await cache.get(query)
       assert miss is None, "Stale answer should not be served"

   @pytest.mark.integration
   @pytest.mark.asyncio
   async def test_stale_rate_under_1pct_on_100_doc_updates(redis_container,
                                                            postgres_container):
       """Run 100 simulated doc updates; verify stale rate <1%
       (ADR-011 pilot criterion)."""
       cache = get_semantic_cache()
       invalidator = get_cache_invalidator()

       # Populate cache with 100 answers, each referencing unique doc_id
       doc_ids = [uuid4() for _ in range(100)]
       queries = [f"Query about doc {i}" for i in range(100)]
       for q, doc_id in zip(queries, doc_ids):
           await cache.put(q, f"answer_{q}", [doc_id], "gpt-4o-mini", 100)

       # Update all 100 docs
       for doc_id in doc_ids:
           await invalidator.invalidate_doc(doc_id)

       # Now query all — all should be stale (None)
       stale_count = 0
       for q in queries:
           result = await cache.get(q)
           if result is None:
               stale_count += 1

       stale_rate = stale_count / 100
       assert stale_rate < 0.01, f"Stale rate {stale_rate:.2%} > 1% — ADR-011 pilot FAIL"

   @pytest.mark.integration
   @pytest.mark.asyncio
   async def test_invalidation_latency_under_60_seconds(redis_container):
       """Invalidate 100 cached answers in <60 seconds (ensure
       background task can keep up with realistic update rate)."""
       import time
       cache = get_semantic_cache()
       invalidator = get_cache_invalidator()

       doc_ids = [uuid4() for _ in range(100)]
       for i, doc_id in enumerate(doc_ids):
           await cache.put(f"q{i}", f"a{i}", [doc_id], "gpt-4o-mini", 100)

       t0 = time.perf_counter()
       await invalidator.invalidate_batch(doc_ids)
       elapsed = time.perf_counter() - t0

       assert elapsed < 60.0, f"Invalidation 100 docs took {elapsed:.1f}s > 60s"
   ```

2. Добавь в CI pipeline (`scripts/ci-local-staging.sh` или `.github/
   workflows/...`):
   ```yaml
   - name: Phase 3 stale-answer guard integration test
     run: |
       pytest tests/integration/test_stale_answer_guard.py -v \
         --tb=short --maxfail=1
   ```

3. Обнови `scripts/ci-local-staging.sh` (Phase 2 existing) — добавь
   вызов нового test перед deploy:
   ```bash
   # existing Phase 2 staging CI
   pytest tests/integration/ -k "phase2 or reranker or hybrid_retriever"
   # NEW Phase 3:
   pytest tests/integration/test_stale_answer_guard.py -v
   pytest tests/integration/test_semantic_cache_integration.py -v
   pytest tests/integration/test_facts_extractor_integration.py -v
   pytest tests/integration/test_cache_aware_llm_integration.py -v
   pytest tests/integration/test_graph_cache_e2e.py -v
   ```

Definition of Done:
- `tests/integration/test_stale_answer_guard.py` существует с 3
  integration tests (single doc invalidation, 100-doc stale rate,
  latency).
- `pytest tests/integration/test_stale_answer_guard.py -v` проходит
  на staging с real Redis + PostgreSQL containers.
- Stale rate <1% verified на 100 doc updates.
- Invalidation latency <60s verified на 100 doc updates.
- CI pipeline (`scripts/ci-local-staging.sh`) запускает новые
  integration tests перед deploy.
- Phase 3 control point: 5 new integration tests + 5 unit tests
  from B-1..B-6 = 10+ Phase 3 tests для ADR-011.

Антипаттерны:
- НЕ делай stale-answer guard только unit test (mock everything) —
  integration test с real Redis обязателен (проверяет real SCAN
  latency, real mark_stale semantics).
- НЕ делай 100-doc test без redis_container fixture — нужна real
  Redis (не in-memory mock; mock не выявит SCAN O(N) latency issues).
- НЕ делай stale_rate <1% как `stale_count < 1` (что = 0 stale) —
  1 stale из 100 = 1%, acceptably borderline; pilot criterion <1%
  = strict <1%, так что assert stale_count == 0 более консервативно.
- НЕ забудь pytest.mark.integration marker — такие tests не должны
  запускаться в unit test CI fast path.
- НЕ хардкодь latency threshold 60s — вынеси в Settings
  (`semantic_cache_invalidation_timeout_seconds=60`).

Связанные ADR:
- Реализует: ADR-011 pilot guard (критично для Approved per ROADMAP
  §14.1 — "stale answers <1%").
- Применяет: принцип #9 ТРИЗ (предварительное противодействие —
  invalidation pipeline verified BEFORE stale answer served),
  ADR-014 (observability — Prometheus counter verified).
- Зависит от: Блок B-1 (SemanticAnswerCache.get/mark_stale), Блок
  B-3 (CacheInvalidator), Блок A-1 (Redis DB 2), Блок A-2
  (semantic_cache_hits_total metric).
- Расширяется в: Phase 4 — continuous stale-rate monitoring
  (always-on integration test via Prometheus alerting rule, не
  scheduled CI run).
- Не затрагивает: ADR-015 (router — separate test), ADR-016 (tool
  adapter — separate test), ADR-004 (MCP server — separate test).
```

---

## 3. Блок C. ADR-015: Cost-Aware Routing

Блок C реализует ADR-015 — `LLMRouter` с политиками `cost_priority` / `latency_priority` / `quality_priority` / `privacy_priority` + cost guard на 80% месячного бюджета. **Supersedes:** часть ADR-005 `fallback_chain` (упраздняется, заменяется на cost-aware routing с load-balancing 70/30 и fallback только в extreme cases).

Пилотные метрики (ROADMAP §14.1): 1 месяц shadow mode — cost predictability ±10%, cost overrun <20%, логирование switching decisions в observability. Rollback: cost overrun >20% OR unacceptable routing decisions.

TRIZ: Standard 2.2.4 (переход к измерительной веполи — `LLMCallMetrics` как measuring function); Standard 5.1.1 (введение вещества извне — Prometheus metrics как circuit breaker input); принципы #35 (изменение физических свойств), #16 (частичное/избыточное — partial fallback 30%), #13 (наоборот — load balancing by default, fallback at edges), #23 (обратная связь — real-time cost metering с auto-decision).

---

### C-1. `ModelCostTable` (формализация `_COST_PER_1M` hardcode)

```
Ты — Backend-разработчик LLM Client. Создай `ModelCostTable` —
конфигурируемую таблицу стоимости LLM calls (per 1M tokens),
заменящую hardcode `_COST_PER_1M` в `src/llm_client/agent/provider.py`
(Phase 1, строки 32-35). Это инфра для ADR-015 cost-aware router.

Контекст:
- Phase 1 AG-2 создал `_COST_PER_1M` hardcode table в
  `src/llm_client/agent/provider.py` строки 32-35:
  ```python
  _COST_PER_1M = {
      "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
      "gpt-4o": {"prompt": 2.50, "completion": 10.00},
  }
  ```
- ADR-015 (TRIZ-ANALYSIS.md v1.0.0 §11 драфт): `LLMRouter` (Блок
  C-2) использует `ModelCostTable` для cost guard 80% budget и
  policy-based routing (cost/latency/quality/privacy).
- ARCHITECT.md v1.3.0 §5.2.3 (LLM Provider Layer) — Phase 3
  формализует hardcode в конфигурируемую структуру.
- ADR-016 (Блок D-1) создаст `ModelCapabilityMatrix` — пер-model
  declaration с `supports_native_tools`, `supports_streaming`,
  `supports_vision`, `context_window`, `cost_per_1m_tokens`,
  `latency_p50`, `latency_p99`. `ModelCostTable` — subset
  capability matrix, focused на cost.
- ТРИЗ принцип 35 (изменение физических свойств): hardcode →
  configurable structure (state change).

Задача:
1. Создай `src/llm_client/agent/model_cost_table.py`:
   ```python
   """Configurable model cost table (Phase 3 — ADR-015).

   Replaces _COST_PER_1M hardcode (Phase 1, AG-2). Loaded from
   YAML config + env override. Used by LLMRouter (C-2) and CostGuard
   (C-3) for cost-aware routing decisions.

   Architecture: ARCHITECT.md v1.3.0 §5.2.3.
   TRIZ: principle #35 (change of physical properties — hardcode →
   configurable).
   """
   import logging
   from dataclasses import dataclass
   from pathlib import Path
   from typing import Any

   import yaml
   from pydantic import BaseModel, Field

   logger = logging.getLogger(__name__)


   class ModelCost(BaseModel):
       """Cost for one model, per 1M tokens, USD."""
       prompt: float = Field(..., ge=0.0, description="USD per 1M prompt tokens")
       completion: float = Field(..., ge=0.0, description="USD per 1M completion tokens")

       def cost_for(self, prompt_tokens: int, completion_tokens: int) -> float:
           """Compute USD cost for a single call."""
           return (
               (prompt_tokens / 1_000_000) * self.prompt
               + (completion_tokens / 1_000_000) * self.completion
           )


   class ModelCostTable(BaseModel):
       """Mapping of (provider, model) -> ModelCost.

       Loaded from YAML config file. Can be overridden via env vars
       MODEL_COST_<PROVIDER>_<MODEL>__PROMPT / __COMPLETION.
       """
       costs: dict[str, dict[str, ModelCost]] = Field(
           default_factory=dict,
           description="Outer key = provider, inner key = model",
       )

       def get_cost(self, provider: str, model: str) -> ModelCost | None:
           """Returns ModelCost for (provider, model) or None if unknown."""
           provider_table = self.costs.get(provider)
           if provider_table is None:
               return None
           return provider_table.get(model)

       def list_models(self, provider: str | None = None) -> list[tuple[str, str]]:
           """List all (provider, model) pairs, optionally filtered by provider."""
           if provider:
               return [(provider, m) for m in self.costs.get(provider, {})]
           return [(p, m) for p, models in self.costs.items() for m in models]

       def cheapest_model(self, provider: str | None = None) -> tuple[str, str] | None:
           """Returns (provider, model) with lowest avg cost (prompt + completion)/2."""
           candidates = self.list_models(provider)
           if not candidates:
               return None
           def avg_cost(pm):
               c = self.get_cost(*pm)
               return (c.prompt + c.completion) / 2 if c else float("inf")
           return min(candidates, key=avg_cost)


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
     glm-4-flash:
       prompt: 0.10
       completion: 0.40
   """


   _table: ModelCostTable | None = None


   def get_model_cost_table() -> ModelCostTable:
       """Singleton ModelCostTable. Loads from YAML config or defaults."""
       global _table
       if _table is not None:
           return _table
       import os
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
       """Convenience function — used by TokenUsageTracker (Phase 1
       AG-2) to compute cost_estimate_usd per LLM call."""
       table = get_model_cost_table()
       cost = table.get_cost(provider, model)
       if cost is None:
           logger.warning(
               "Unknown model %s/%s — cost estimate $0.0", provider, model,
           )
           return 0.0
       return cost.cost_for(prompt_tokens, completion_tokens)
   ```

2. Обнови `src/llm_client/agent/provider.py` — замени прямые ссылки
   на `_COST_PER_1M` на вызовы `compute_call_cost`:
   ```python
   # BEFORE Phase 3 (Phase 1 AG-2):
   _COST_PER_1M = {
       "gpt-4o-mini": {"prompt": 0.15, "completion": 0.60},
       "gpt-4o": {"prompt": 2.50, "completion": 10.00},
   }
   # in TokenUsageTracker.on_llm_end:
   cost_per_1m = _COST_PER_1M.get(self._model, {"prompt": 0, "completion": 0})
   cost_usd = (prompt_tokens / 1e6) * cost_per_1m["prompt"] + (completion_tokens / 1e6) * cost_per_1m["completion"]

   # AFTER Phase 3:
   from .model_cost_table import compute_call_cost
   # remove _COST_PER_1M hardcode (or keep as deprecated back-compat)
   # in TokenUsageTracker.on_llm_end:
   cost_usd = compute_call_cost(self._provider, self._model,
                                prompt_tokens, completion_tokens)
   ```

3. Создай default config file `config/model_costs.yaml` (по умолчанию
   используется встроенный DEFAULT_COSTS_YAML, но для production
   override можно указать `MODEL_COSTS_CONFIG_PATH=/path/to/costs.yaml`):
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

4. Тесты в `tests/unit/test_model_cost_table.py`:
   - `test_get_cost_returns_known_model` — `get_cost("openai",
     "gpt-4o-mini")` returns `ModelCost(prompt=0.15, completion=0.60)`.
   - `test_get_cost_returns_none_for_unknown` — `get_cost("openai",
     "gpt-5")` returns None (graceful).
   - `test_cost_for_computes_correctly` — `ModelCost(prompt=0.15,
     completion=0.60).cost_for(prompt_tokens=1_000_000,
     completion_tokens=500_000)` = 0.15 + 0.30 = 0.45 USD.
   - `test_list_models_filtered_by_provider` — `list_models("openai")`
     returns [("openai", "gpt-4o-mini"), ("openai", "gpt-4o"),
     ("openai", "gpt-4-turbo")].
   - `test_cheapest_model_returns_gpt_4o_mini` — `cheapest_model()`
     returns ("ollama", "llama3.1-8b") (cost=0) или ("openai",
     "gpt-4o-mini") если ollama excluded.
   - `test_load_from_yaml_config_path` — set env
     `MODEL_COSTS_CONFIG_PATH=test_fixtures/custom_costs.yaml`,
     verify table loaded from file (not default).
   - `test_compute_call_cost_zero_for_unknown_model` —
     `compute_call_cost("unknown", "mystery", 100, 200)` returns 0.0
     with warning log.
   - Integration: TokenUsageTracker.on_llm_end calls
     `compute_call_cost` correctly (verify via mock LLM response).

Definition of Done:
- `src/llm_client/agent/model_cost_table.py` существует с `ModelCost`
  + `ModelCostTable` + `get_model_cost_table()` singleton + 
  `compute_call_cost()` function.
- `src/llm_client/agent/provider.py` `TokenUsageTracker.on_llm_end`
  использует `compute_call_cost(provider, model, ...)` вместо
  hardcode `_COST_PER_1M` (последний либо удалён, либо помечен
  deprecated).
- `config/model_costs.yaml` создан с production-ready default values.
- 7+ unit тестов зелёные.
- Существующие тесты Phase 1/2 (`test_provider.py`) — не
  регрессируют (`compute_call_cost` для известных (openai, gpt-4o)
  возвращает те же значения, что и hardcode).

Антипаттерны:
- НЕ сохраняй `_COST_PER_1M` hardcode как primary source — только
  как deprecated fallback (если YAML config missing AND defaults
  missing). Phase 4 удалить полностью.
- НЕ хардкодь cost_per_1m в Python коде — только YAML (для ops
  update без redeploy).
- НЕ делай `ModelCost` mutable (Pydantic v2 BaseModel frozen=True)
  — предотвратить accidental modification.
- НЕ забудь `cheapest_model()` — критично для ADR-015 cost guard
  (Блок C-3) при 80% budget trigger.
- НЕ используй floating-point без type guard — ModelCost fields
  ge=0.0 (no negative costs).
- НЕ делай YAML load при каждом вызове `compute_call_cost` —
  singleton (load once at startup).

Связанные ADR:
- Реализует: инфра для ADR-015 (cost data source).
- Применяет: принцип #35 ТРИЗ (изменение физических свойств —
  hardcode → configurable), ADR-014 (operational stream — cost
  estimate flow preserved).
- Зависит от: Phase 1 AG-2 (`TokenUsageTracker` — replaced hardcode
  call), `pydantic>=2.0` (existing dep), `pyyaml` (add to
  pyproject.toml if missing).
- Расширяется в: Phase 4 — `ModelCapabilityMatrix` (Блок D-1)
  extends с capabilities; ADR-015 router uses both cost + capability
  for routing decisions.
- Не затрагивает: ADR-010 (checkpoint — не depends on cost),
  ADR-013 (cancel — не depends on cost).
```

### C-2. `LLMRouter` interface + policies (cost/latency/quality/privacy)

```
Ты — Backend/Agent-разработчик LLM Client. Создай `LLMRouter` —
central routing class, заменяющий `fallback_chain` (ADR-005) на
cost-aware routing с 4 политиками: `cost_priority`,
`latency_priority`, `quality_priority`, `privacy_priority`. Это
ядро ADR-015.

Контекст:
- ADR-015 (TRIZ-ANALYSIS.md v1.0.0 §11 драфт): `LLMRouter` хранит
  policies; per-request inputs: provider circuit breaker, budget
  spend (cost guard), privacy requirements, model capability matrix;
  at 80% monthly budget → auto-switch to cheapest available; default
  traffic split 70/30; fallback only in extreme cases.
- ADR-015 **Supersedes**: часть ADR-005 `fallback_chain` (упраздняется).
  ROADMAP §13.2 risk: requires explicit `Supersedes:` + `Migration
  plan:`.
- Phase 1 AG-2 `LLMProviderFactory.create(provider, model, api_key)`
  возвращает `BaseChatModel`. `LLMRouter` оборачивает
  `LLMProviderFactory` (не заменяет — wraps it).
- `src/llm_client/agent/provider.py` строка 422 содержит comment:
  `# fallback_chain — Phase 3 (ADR-015 cost-aware router)` (Phase 1
  placeholder). Phase 3 заменяет на `LLMRouter.route(query,
  context)`.
- Блок C-1 создал `ModelCostTable` + `compute_call_cost`.
- Блок A-2 создал Prometheus metrics (`llm_error_rate_5m`,
  `llm_call_latency_seconds`).
- Блок D-1 (ADR-016) создаст `ModelCapabilityMatrix` — `LLMRouter`
  будет читать capability matrix для routing decisions.
- ТРИЗ Standard 2.2.4 (переход к измерительной веполи):
  `LLMCallMetrics` (latency, tokens, cost, success rate) feeds
  back into router.
- ТРИЗ принцип 13 (наоборот): load balancing 70/30 по умолчанию,
  fallback at edges only.

Задача:
1. Создай `src/llm_client/agent/router.py`:
   ```python
   """Cost-Aware LLM Router (ADR-015 Phase 3).

   Replaces ADR-005 fallback_chain. Routes per-request to a
   (provider, model) based on:
   - policy (cost / latency / quality / privacy)
   - provider circuit breaker (Prometheus llm_error_rate_5m)
   - monthly budget spend (cost guard at 80%)
   - model capability matrix (ADR-016, Блок D-1)
   - privacy requirements (zero-retention policy)

   Architecture: ARCHITECT.md v1.3.0 §5.2.3.
   TRIZ: Standard 2.2.4 (transition to measuring vepol —
   LLMCallMetrics feedback); principle #13 (inverse — load
   balancing by default, fallback at edges).
   """
   import asyncio
   import logging
   from dataclasses import dataclass
   from enum import Enum
   from typing import Any
   from uuid import UUID

   from langchain_core.language_models import BaseChatModel

   from ..config import get_settings
   from ..observability.llm_metrics import LLM_ERROR_RATE, LLM_LATENCY
   from .model_cost_table import ModelCostTable, get_model_cost_table
   from .provider import LLMProviderFactory

   logger = logging.getLogger(__name__)


   class RoutingPolicy(str, Enum):
       COST = "cost_priority"
       LATENCY = "latency_priority"
       QUALITY = "quality_priority"
       PRIVACY = "privacy_priority"


   @dataclass
   class RoutingDecision:
       provider: str
       model: str
       policy: RoutingPolicy
       reason: str  # human-readable explanation for observability
       budget_ratio_at_decision: float
       circuit_breaker_active: bool


   class LLMRouter:
       """Central routing class. Wraps LLMProviderFactory."""

       DEFAULT_TRAFFIC_SPLIT = {
           # 70% to primary (cost_priority: gpt-4o-mini),
           # 30% to secondary (latency_priority: gpt-4o for quality)
           # — load balancing по умолчанию
           ("openai", "gpt-4o-mini"): 0.7,
           ("openai", "gpt-4o"): 0.3,
       }

       BUDGET_THRESHOLD_CHEAPEST = 0.8  # 80% of monthly budget

       def __init__(
           self,
           provider_factory: LLMProviderFactory,
           cost_table: ModelCostTable,
           budget_usd: float = 100.0,  # configurable
       ) -> None:
           self._factory = provider_factory
           self._cost_table = cost_table
           self._budget = budget_usd
           self._spent_usd = 0.0
           self._lock = asyncio.Lock()

       async def route(
           self,
           query: str | None = None,
           policy: RoutingPolicy = RoutingPolicy.COST,
           privacy_required: bool = False,
       ) -> RoutingDecision:
           """Decide (provider, model) for next LLM call."""
           async with self._lock:
               budget_ratio = self._spent_usd / self._budget if self._budget > 0 else 0.0
               # Update Prometheus gauge
               from ..observability.llm_metrics import update_budget_usage
               update_budget_usage(self._spent_usd, self._budget)

               # 1. Cost guard: at 80% budget → switch to cheapest
               if budget_ratio >= self.BUDGET_THRESHOLD_CHEAPEST:
                   cheapest = self._cost_table.cheapest_model()
                   if cheapest:
                       provider, model = cheapest
                       return RoutingDecision(
                           provider=provider,
                           model=model,
                           policy=RoutingPolicy.COST,
                           reason=f"Budget at {budget_ratio:.0%} — switched to cheapest",
                           budget_ratio_at_decision=budget_ratio,
                           circuit_breaker_active=False,
                       )

               # 2. Privacy: if required → use Ollama or zero-retention
               if privacy_required:
                   # Phase 4: full Ollama support; Phase 3 stub returns
                   # custom-openai with zero-retention policy
                   return RoutingDecision(
                       provider="custom-openai",
                       model="default",
                       policy=RoutingPolicy.PRIVACY,
                       reason="Privacy required — zero-retention provider",
                       budget_ratio_at_decision=budget_ratio,
                       circuit_breaker_active=False,
                   )

               # 3. Policy-based routing
               if policy == RoutingPolicy.COST:
                   cheapest = self._cost_table.cheapest_model() or ("openai", "gpt-4o-mini")
                   provider, model = cheapest
                   reason = "Cost priority — cheapest available"
               elif policy == RoutingPolicy.LATENCY:
                   # Pick model with lowest p50 latency (Phase 4 reads
                   # ModelCapabilityMatrix; Phase 3 stub: gpt-4o-mini)
                   provider, model = "openai", "gpt-4o-mini"
                   reason = "Latency priority — gpt-4o-mini"
               elif policy == RoutingPolicy.QUALITY:
                   provider, model = "openai", "gpt-4o"
                   reason = "Quality priority — gpt-4o"
               elif policy == RoutingPolicy.PRIVACY:
                   provider, model = "custom-openai", "default"
                   reason = "Privacy priority — zero-retention"
               else:
                   provider, model = "openai", "gpt-4o-mini"
                   reason = f"Unknown policy {policy} — default"

               # 4. Circuit breaker check via Prometheus
               cb_active = await self._check_circuit_breaker(provider)
               if cb_active:
                   # Fallback to alternative provider
                   alt = self._fallback_provider(provider)
                   if alt:
                       provider, model = alt
                       reason += f"; circuit breaker active on primary — fallback to {alt}"

               return RoutingDecision(
                   provider=provider,
                   model=model,
                   policy=policy,
                   reason=reason,
                   budget_ratio_at_decision=budget_ratio,
                   circuit_breaker_active=cb_active,
               )

       async def create_llm(self, decision: RoutingDecision) -> BaseChatModel:
           """Create BaseChatModel based on routing decision."""
           settings = get_settings()
           api_key = self._get_api_key(decision.provider, settings)
           return LLMProviderFactory.create(
               provider=decision.provider,
               model=decision.model,
               api_key=api_key,
           )

       async def record_cost(self, cost_usd: float) -> None:
           """Called from TokenUsageTracker (after LLM call) to update
           monthly spend tracker."""
           async with self._lock:
               self._spent_usd += cost_usd
               logger.info(
                   "LLM cost recorded: $%.4f (total $%.2f / $%.2f = %.1f%%)",
                   cost_usd, self._spent_usd, self._budget,
                   (self._spent_usd / self._budget * 100) if self._budget else 0,
               )

       async def _check_circuit_breaker(self, provider: str) -> bool:
           """Check Prometheus llm_error_rate_5m gauge for provider.
           If >0.5 (50% error rate) → circuit breaker active."""
           # Phase 3 stub: read from in-memory gauge (set by background
           # task updating from Prometheus scrape)
           # Phase 4: full Prometheus HTTP query API
           try:
               from prometheus_client.parser import text_string_to_metric_families
               # Use the in-process REGISTRY (simpler than HTTP query)
               from ..observability.llm_metrics import REGISTRY
               from prometheus_client import generate_latest
               latest = generate_latest(REGISTRY).decode()
               for family in text_string_to_metric_families(latest):
                   if family.name == "llm_error_rate_5m":
                       for sample in family.samples:
                           if sample.labels.get("provider") == provider:
                               return float(sample.value) > 0.5
           except Exception as e:
               logger.warning("Circuit breaker check failed: %s", e)
           return False

       def _fallback_provider(self, primary: str) -> tuple[str, str] | None:
           """Returns fallback (provider, model) if primary is down."""
           fallbacks = {
               "openai": ("anthropic", "claude-3-haiku"),
               "anthropic": ("openai", "gpt-4o-mini"),
               "custom-openai": ("openai", "gpt-4o-mini"),
           }
           return fallbacks.get(primary)

       def _get_api_key(self, provider: str, settings) -> str | None:
           """Get API key for provider from settings."""
           if provider == "openai":
               return settings.openai_api_key
           elif provider == "anthropic":
               return settings.anthropic_api_key
           elif provider in ("custom-openai", "zai"):
               return settings.openai_api_key  # CUSTOM-OPENAI uses OpenAI key
           elif provider == "ollama":
               return None  # Ollama is local, no API key
           return None


   _router: LLMRouter | None = None


   def get_llm_router() -> LLMRouter:
       """Singleton LLMRouter. Initialized with default budget from
       Settings (LLM_MONTHLY_BUDGET_USD env var)."""
       global _router
       if _router is not None:
           return _router
       settings = get_settings()
       _router = LLMRouter(
           provider_factory=LLMProviderFactory,
           cost_table=get_model_cost_table(),
           budget_usd=settings.llm_monthly_budget_usd,
       )
       return _router
   ```

2. Добавь в `src/llm_client/config.py` Settings:
   ```python
   # Phase 3 — ADR-015 cost-aware router
   llm_monthly_budget_usd: float = 100.0  # default $100/month
   llm_router_default_policy: str = "cost_priority"  # cost|latency|quality|privacy
   llm_router_cost_guard_threshold: float = 0.8  # 80% budget
   llm_router_traffic_split: dict = {"openai:gpt-4o-mini": 0.7, "openai:gpt-4o": 0.3}
   ```

3. Обнови `.env.example`:
   ```env
   # === Phase 3 — ADR-015 Cost-Aware Router ===
   LLM_MONTHLY_BUDGET_USD=100.0
   LLM_ROUTER_DEFAULT_POLICY=cost_priority
   LLM_ROUTER_COST_GUARD_THRESHOLD=0.8
   MODEL_COSTS_CONFIG_PATH=/app/config/model_costs.yaml
   ```

4. Тесты в `tests/unit/test_llm_router.py`:
   - `test_route_cost_policy_returns_cheapest` —
     `route(policy=COST)` returns (openai, gpt-4o-mini) или (ollama,
     llama3.1-8b) if cost=0.
   - `test_route_latency_policy_returns_lowest_latency` —
     `route(policy=LATENCY)` returns gpt-4o-mini (Phase 3 stub).
   - `test_route_quality_policy_returns_gpt_4o` —
     `route(policy=QUALITY)` returns gpt-4o.
   - `test_route_privacy_required_returns_zero_retention_provider` —
     `route(privacy_required=True)` returns custom-openai.
   - `test_route_at_80pct_budget_switches_to_cheapest` —
     `router._spent_usd = 80; router._budget = 100` → route returns
     cheapest model regardless of policy.
   - `test_circuit_breaker_active_falls_back_to_alternative` —
     mock Prometheus gauge with error_rate=0.6 for openai → router
     falls back to (anthropic, claude-3-haiku).
   - `test_record_cost_updates_budget_tracker` — `record_cost(5.0)`
     → `_spent_usd = 5.0`.
   - `test_create_llm_returns_basechatmodel` —
     `create_llm(decision)` returns ChatOpenAI instance.
   - Integration (`tests/integration/test_llm_router_integration.py`):
     real Prometheus gauge, mock LLMProviderFactory.

Definition of Done:
- `src/llm_client/agent/router.py` существует с `LLMRouter` (4
  methods: route, create_llm, record_cost, _check_circuit_breaker) +
  `RoutingPolicy` enum + `RoutingDecision` dataclass +
  `get_llm_router()` factory.
- 4 policies работают: cost → cheapest, latency → lowest p50,
  quality → gpt-4o, privacy → zero-retention.
- Cost guard на 80% budget: `route()` returns cheapest regardless
  of policy.
- Circuit breaker через Prometheus `llm_error_rate_5m` gauge:
  if >0.5 → fallback to alternative provider.
- 8+ unit + 1 integration тестов зелёные.
- Существующие тесты Phase 1/2 (`test_provider.py`,
  `test_graph_cancel_inflight.py`) — не регрессируют (LLMRouter
  standalone; integration с graph в Блоке C-7).

Антипаттерны:
- НЕ заменяй `LLMProviderFactory` полностью — `LLMRouter` оборачивает
  factory, не заменяет; `_get_api_key` и `create_llm` используют
  existing `LLMProviderFactory.create()`.
- НЕ делай `route()` blocking — async (circuit breaker check via
  Prometheus может быть slow HTTP query в Phase 4).
- НЕ хардкодь budget=100.0 — только Settings (`llm_monthly_budget_usd`).
- НЕ делай traffic split 100/0 по умолчанию — 70/30 (load balancing
  per ADR-015, принцип #13 ТРИЗ).
- НЕ делай fallback chain список hardcoded в YAML — в коде с
  comment "Phase 4: move to ADR-016 capability matrix".
- НЕ делай privacy policy = только Ollama в Phase 3 — Ollama case
  в `LLMProviderFactory.create("ollama")` всё ещё raises
  NotImplementedError (Phase 4 ADR-016 full integration). Phase 3
  privacy policy возвращает `custom-openai` (self-hosted OpenAI-
  compatible, который можно deploy с zero-retention).
- НЕ забудь логировать RoutingDecision.reason — критично для ADR-015
  pilot criterion "логирование switching decisions в observability".
- НЕ делай `_spent_usd` reset без explicit API — monthly reset должен
  быть external (admin script, не automatic).

Связанные ADR:
- Реализует: ADR-015 (cost-aware routing), Supersedes часть ADR-005
  (`fallback_chain` упраздняется, replaced by LLMRouter).
- Применяет: Standard 2.2.4 ТРИЗ (измерительная веполь —
  LLMCallMetrics через Prometheus feeds back), Standard 5.1.1
  (Prometheus как вещество извне для circuit breaker), принципы #13
  (load balancing by default), #23 (обратная связь — real-time cost
  metering с auto-decision), #35 (изменение свойств routing state),
  #16 (частичное/избыточное — partial fallback 30%).
- Зависит от: Блок C-1 (`ModelCostTable`), Блок A-2 (`llm_error_rate_5m`
  gauge), Phase 1 AG-2 (`LLMProviderFactory.create()`), Phase 1 AG-2
  (`TokenUsageTracker` для cost estimate).
- Расширяется в: Phase 4 — `ModelCapabilityMatrix` (Блок D-1) для
  per-model `supports_native_tools` / `context_window` routing;
  full Prometheus HTTP query API (не in-process REGISTRY); external
  monthly budget reset via admin script.
- Не затрагивает: ADR-010 (checkpoint — не depends on router),
  ADR-013 (cancel — CancellationToken router-agnostic),
  ADR-014 (operational stream — TokenUsageTracker writes router
  decision as `routing_decision` field in operational event).
```

### C-3. `CostGuard` (monthly budget tracker, auto-switch at 80%)

```
Ты — Backend-разработчик LLM Client. Создай `CostGuard` — monthly
budget tracker, который на 80% бюджета trigger'ит `LLMRouter`
auto-switch на cheapest model (Блок C-2). Также экспонирует budget
usage в Prometheus gauge.

Контекст:
- ADR-015 (TRIZ-ANALYSIS.md v1.0.0 §11 драфт): "At 80% monthly
  budget → auto-switch to cheapest available (GPT-4o-mini / Claude
  Haiku / Ollama)".
- Блок C-2 реализовал `LLMRouter._spent_usd` + `record_cost(cost)`.
- Блок A-2 создал `update_budget_usage(used, budget)` gauge.
- ТРИЗ принцип 23 (обратная связь): real-time cost metering с
  auto-decision.
- ТРИЗ Standard 5.1.1 (введение вещества извне): Prometheus gauge
  как external substance для budget trigger.

Задача:
1. Создай `src/llm_client/agent/cost_guard.py`:
   ```python
   """Monthly cost guard (ADR-015 Phase 3).

   Wraps LLMRouter budget tracking. At 80% threshold, auto-switches
   to cheapest model (Блок C-2). Exposes usage to Prometheus.

   Architecture: ARCHITECT.md v1.3.0 §5.2.3.
   TRIZ: principle #23 (feedback — real-time cost metering);
   Standard 5.1.1 (Prometheus as external substance).
   """
   import asyncio
   import logging
   from datetime import datetime, timezone

   from ..config import get_settings
   from ..observability.llm_metrics import update_budget_usage
   from .router import LLMRouter, get_llm_router

   logger = logging.getLogger(__name__)


   class CostGuard:
       """Monthly budget enforcement."""

       def __init__(self, router: LLMRouter) -> None:
           self._router = router
           self._month_start = datetime.now(timezone.utc).replace(
               day=1, hour=0, minute=0, second=0, microsecond=0,
           )

       async def record_spend(self, cost_usd: float) -> bool:
           """Record a LLM call cost. Returns True if cost guard
           triggered (>=80% budget)."""
           await self._router.record_cost(cost_usd)
           budget_ratio = self._router._spent_usd / self._router._budget if self._router._budget > 0 else 0.0
           update_budget_usage(self._router._spent_usd, self._router._budget)

           if budget_ratio >= 0.8 and budget_ratio - cost_usd / self._router._budget < 0.8:
               logger.warning(
                   "Cost guard triggered at %.1f%% — switching to cheapest model",
                   budget_ratio * 100,
               )
               # The LLMRouter.route() will automatically pick cheapest
               # from now on (verified in C-2 test).
               return True
           return False

       def is_over_budget(self) -> bool:
           """Returns True if monthly spend >= 100% budget."""
           return self._router._spent_usd >= self._router._budget

       def remaining_budget(self) -> float:
           """Returns remaining budget in USD."""
           return max(0.0, self._router._budget - self._router._spent_usd)

       def month_start(self) -> datetime:
           """Returns the start of the current billing month."""
           return self._month_start

       async def reset_monthly(self) -> None:
           """Admin-only: reset spent_usd to 0 (called via admin
           script on 1st of month)."""
           self._router._spent_usd = 0.0
           self._month_start = datetime.now(timezone.utc).replace(
               day=1, hour=0, minute=0, second=0, microsecond=0,
           )
           update_budget_usage(0.0, self._router._budget)
           logger.info("Monthly budget reset to 0 / %s", self._router._budget)


   _guard: CostGuard | None = None


   def get_cost_guard() -> CostGuard:
       global _guard
       if _guard is None:
           _guard = CostGuard(get_llm_router())
       return _guard
   ```

2. Расширь `src/llm_client/agent/provider.py` — в
   `TokenUsageTracker.on_llm_end` после `compute_call_cost` вызывай
   `CostGuard.record_spend`:
   ```python
   # in TokenUsageTracker.on_llm_end (existing Phase 1 + B A-2 + C-1 updates):
   cost_usd = compute_call_cost(self._provider, self._model, prompt_tokens, completion_tokens)
   # NEW Phase 3 C-3:
   from .cost_guard import get_cost_guard
   guard = get_cost_guard()
   triggered = await guard.record_spend(cost_usd)
   if triggered:
       logger.warning("Cost guard triggered — router will switch to cheapest")
   ```

3. Добавь admin endpoint в `src/llm_client/agent/service.py`:
   ```python
   @app.post("/admin/cost-guard/reset")
   async def reset_cost_guard(admin_token: str = Header(...)):
       """Admin-only: reset monthly budget."""
       from ..config import get_settings
       if admin_token != get_settings().admin_token:
           raise HTTPException(403)
       from .cost_guard import get_cost_guard
       await get_cost_guard().reset_monthly()
       return {"status": "ok", "spent_usd": 0.0}

   @app.get("/admin/cost-guard/status")
   async def cost_guard_status(admin_token: str = Header(...)):
       from ..config import get_settings
       if admin_token != get_settings().admin_token:
           raise HTTPException(403)
       from .cost_guard import get_cost_guard
       g = get_cost_guard()
       return {
           "spent_usd": g._router._spent_usd,
           "budget_usd": g._router._budget,
           "ratio": g._router._spent_usd / g._router._budget if g._router._budget else 0,
           "over_budget": g.is_over_budget(),
           "remaining_usd": g.remaining_budget(),
           "month_start": g.month_start().isoformat(),
       }
   ```

4. Тесты в `tests/unit/test_cost_guard.py`:
   - `test_record_spend_below_threshold_no_trigger` — record $10
     on $100 budget → triggered=False.
   - `test_record_spend_at_80pct_triggers` — budget=100, spent=79,
     record $2 → triggered=True.
   - `test_is_over_budget_at_100pct` — spent=100, budget=100 → True.
   - `test_remaining_budget_correct` — spent=30, budget=100 → 70.
   - `test_reset_monthly_zeroes_spent` — spent=50, reset → spent=0,
     month_start updated.
   - `test_update_budget_usage_prometheus_called` — verify
     `update_budget_usage` called with correct args.
   - Integration: TokenUsageTracker.on_llm_end → CostGuard.record_spend
     → budget_ratio reflected in Prometheus gauge.

Definition of Done:
- `src/llm_client/agent/cost_guard.py` существует с `CostGuard` (4
  methods: record_spend, is_over_budget, remaining_budget,
  reset_monthly) + `get_cost_guard()` factory.
- `TokenUsageTracker.on_llm_end` вызывает `CostGuard.record_spend(cost)`
  после `compute_call_cost`.
- Admin endpoints `/admin/cost-guard/reset` (POST) + `/admin/cost-guard/status`
  (GET) работают с `admin_token` auth.
- 6+ unit + 1 integration тестов зелёные.
- Pilot criterion "cost predictability ±10%" verifiable via
  monthly spend tracking (manual: compare actual OpenAI bill vs
  CostGuard.spent_usd — should be ±10%).

Антипаттерны:
- НЕ делай auto-reset monthly — admin script (manual operation;
  auto-reset может потерять billing context).
- НЕ делай `reset_monthly` без auth — `admin_token` header required
  (otherwise anyone can reset budget = security hole).
- НЕ делай `record_spend` blocking — async (TokenUsageTracker.on_llm_end
  already async).
- НЕ хардкодь 0.8 threshold — Settings.llm_router_cost_guard_threshold.
- НЕ делай CostGuard отдельным от LLMRouter — wraps router (router
  stores `_spent_usd`, guard exposes budget logic).

Связанные ADR:
- Реализует: ADR-015 cost guard 80% (критично для pilot criterion
  "cost overrun <20%").
- Применяет: принцип #23 ТРИЗ (обратная связь — real-time cost
  metering с auto-decision), Standard 5.1.1 (Prometheus gauge).
- Зависит от: Блок C-2 (`LLMRouter.record_cost`), Блок A-2
  (`update_budget_usage`), Phase 1 AG-2 (`TokenUsageTracker`).
- Расширяется в: Phase 4 — sliding window budget (не calendar month);
  alerting via Grafana contactpoints (existing `ops/grafana/
  provisioning/alerting/contactpoints.yml`); webhook to Slack on
  80% trigger.
- Не затрагивает: ADR-010 (checkpoint — CostGuard не depends on
  checkpoint state), ADR-013 (cancel — CostGuard не emits cancel
  events).
```

### C-4. `CircuitBreaker` (per-provider, Prometheus metrics input)

```
Ты — Backend/разработчик LLM Client. Создай `CircuitBreaker` —
per-provider circuit breaker, читающий Prometheus `llm_error_rate_5m`
gauge (Блок A-2). При error rate >50% за 5 минут → breaker open,
fallback to alternative provider (Блок C-2 `_fallback_provider`).

Контекст:
- ADR-015 (TRIZ-ANALYSIS.md v1.0.0 §11 драфт): per-provider circuit
  breaker на основе Prometheus metrics.
- Блок A-2 создал `LLM_ERROR_RATE` gauge `llm_error_rate_5m{provider}`.
- Блок A-2 создал `update_error_rate(provider, error_count_5m,
  total_count_5m)`.
- Блок C-2 реализовал `LLMRouter._check_circuit_breaker(provider) ->
  bool` — Phase 3 stub через in-process REGISTRY.
- ТРИЗ Standard 5.1.1 (введение вещества извне): Prometheus metrics
  как external substance для circuit breaker.
- ТРИЗ принцип 16 (частичное/избыточное действие): при перегрузке
  OpenAI переключаем 30% трафика (не весь трафик).

Задача:
1. Создай `src/llm_client/agent/circuit_breaker.py`:
   ```python
   """Per-provider circuit breaker (ADR-015 Phase 3).

   Reads Prometheus llm_error_rate_5m gauge (updated by background
   task from real Prometheus scrape). When error rate >50% →
   breaker open, LLMRouter falls back to alternative provider.

   Architecture: ARCHITECT.md v1.3.0 §5.2.3.
   TRIZ: Standard 5.1.1 (Prometheus as external substance);
   principle #16 (partial/excessive — partial fallback 30%).
   """
   import asyncio
   import logging
   import time
   from dataclasses import dataclass
   from enum import Enum

   logger = logging.getLogger(__name__)


   class CircuitState(str, Enum):
       CLOSED = "closed"  # normal operation
       OPEN = "open"      # circuit breaker tripped, fallback
       HALF_OPEN = "half_open"  # trial period after open


   @dataclass
   class CircuitStatus:
       provider: str
       state: CircuitState
       error_rate_5m: float
       last_state_change: float  # unix timestamp
       consecutive_failures: int


   class CircuitBreaker:
       """Per-provider circuit breaker. State machine: CLOSED → OPEN
       (on error_rate > threshold) → HALF_OPEN (after cooldown) →
       CLOSED (if trial succeeds)."""

       ERROR_RATE_THRESHOLD = 0.5  # 50% error rate → OPEN
       COOLDOWN_SECONDS = 60  # 1 min cooldown before HALF_OPEN
       TRIAL_SUCCESS_THRESHOLD = 3  # 3 successful calls in HALF_OPEN → CLOSED

       def __init__(self) -> None:
           self._states: dict[str, CircuitStatus] = {}
           self._lock = asyncio.Lock()

       async def check(self, provider: str) -> CircuitStatus:
           """Returns current CircuitStatus for provider. Updates state
           based on Prometheus gauge."""
           async with self._lock:
               now = time.time()
               status = self._states.get(provider)
               if status is None:
                   status = CircuitStatus(
                       provider=provider,
                       state=CircuitState.CLOSED,
                       error_rate_5m=0.0,
                       last_state_change=now,
                       consecutive_failures=0,
                   )
                   self._states[provider] = status

               # Read current error rate from in-process gauge
               current_error_rate = await self._read_prometheus_gauge(provider)
               status.error_rate_5m = current_error_rate

               # State transitions
               if status.state == CircuitState.CLOSED:
                   if current_error_rate >= self.ERROR_RATE_THRESHOLD:
                       status.state = CircuitState.OPEN
                       status.last_state_change = now
                       logger.warning(
                           "Circuit OPEN for provider %s (error rate %.1f%%)",
                           provider, current_error_rate * 100,
                       )
               elif status.state == CircuitState.OPEN:
                   if now - status.last_state_change > self.COOLDOWN_SECONDS:
                       status.state = CircuitState.HALF_OPEN
                       status.last_state_change = now
                       logger.info(
                           "Circuit HALF_OPEN for provider %s (cooldown elapsed)",
                           provider,
                       )
               elif status.state == CircuitState.HALF_OPEN:
                   if status.consecutive_failures >= self.TRIAL_SUCCESS_THRESHOLD:
                       status.state = CircuitState.CLOSED
                       status.consecutive_failures = 0
                       status.last_state_change = now
                       logger.info(
                           "Circuit CLOSED for provider %s (trial succeeded)",
                           provider,
                       )

               return status

       async def record_success(self, provider: str) -> None:
           """Called after successful LLM call."""
           async with self._lock:
               status = self._states.get(provider)
               if status and status.state == CircuitState.HALF_OPEN:
                   status.consecutive_failures += 1

       async def record_failure(self, provider: str) -> None:
           """Called after failed LLM call."""
           async with self._lock:
               status = self._states.get(provider)
               if status:
                   status.consecutive_failures = 0  # reset on failure
                   if status.state == CircuitState.HALF_OPEN:
                       status.state = CircuitState.OPEN
                       status.last_state_change = time.time()
                       logger.warning(
                           "Circuit re-OPEN for provider %s (trial failed)",
                           provider,
                       )

       async def _read_prometheus_gauge(self, provider: str) -> float:
           """Read llm_error_rate_5m{provider} from in-process gauge."""
           try:
               from ..observability.llm_metrics import REGISTRY
               from prometheus_client import generate_latest
               from prometheus_client.parser import text_string_to_metric_families
               latest = generate_latest(REGISTRY).decode()
               for family in text_string_to_metric_families(latest):
                   if family.name == "llm_error_rate_5m":
                       for sample in family.samples:
                           if sample.labels.get("provider") == provider:
                               return float(sample.value)
           except Exception as e:
               logger.warning("Failed to read Prometheus gauge: %s", e)
           return 0.0


   _breaker: CircuitBreaker | None = None


   def get_circuit_breaker() -> CircuitBreaker:
       global _breaker
       if _breaker is None:
           _breaker = CircuitBreaker()
       return _breaker
   ```

2. Создай background task `scripts/circuit_breaker_metrics_collector.py`:
   ```python
   """Background task: every 30s, query Prometheus for last 5min
   error rate per provider, update llm_error_rate_5m gauge.

   This is the bridge between Prometheus scrape (every 15-60s) and
   circuit breaker check (per-request).
   """
   import asyncio
   import logging

   from llm_client.observability.llm_metrics import update_error_rate

   logger = logging.getLogger(__name__)


   async def collect_error_rates() -> None:
       """For each provider, count errors and total calls in last 5
       minutes from in-process REGISTRY, compute error rate, update
       gauge."""
       from llm_client.observability.llm_metrics import REGISTRY
       from prometheus_client import generate_latest
       from prometheus_client.parser import text_string_to_metric_families
       latest = generate_latest(REGISTRY).decode()

       # Aggregate per-provider
       provider_stats: dict[str, dict[str, int]] = {}  # provider -> {errors, total}
       for family in text_string_to_metric_families(latest):
           if family.name == "llm_call_total":
               for sample in family.samples:
                   provider = sample.labels.get("provider", "unknown")
                   status = sample.labels.get("status", "unknown")
                   count = int(sample.value)
                   provider_stats.setdefault(provider, {"errors": 0, "total": 0})
                   provider_stats[provider]["total"] += count
                   if status in ("error", "timeout"):
                       provider_stats[provider]["errors"] += count

       for provider, stats in provider_stats.items():
           update_error_rate(provider, stats["errors"], stats["total"])


   async def main(interval_seconds: int = 30) -> None:
       while True:
           try:
               await collect_error_rates()
           except Exception as e:
               logger.error("Circuit breaker metrics collection failed: %s", e)
           await asyncio.sleep(interval_seconds)


   if __name__ == "__main__":
       asyncio.run(main())
   ```

3. Расширь `LLMRouter._check_circuit_breaker` (Блок C-2) — используй
   `CircuitBreaker` класс вместо inline Prometheus parsing:
   ```python
   # in LLMRouter (router.py)
   async def _check_circuit_breaker(self, provider: str) -> bool:
       from .circuit_breaker import get_circuit_breaker
       status = await get_circuit_breaker().check(provider)
       return status.state == CircuitState.OPEN
   ```

4. Тесты в `tests/unit/test_circuit_breaker.py`:
   - `test_check_returns_closed_initial_state` — fresh breaker,
     `check("openai")` returns CircuitStatus(state=CLOSED).
   - `test_check_opens_on_high_error_rate` — set gauge
     `llm_error_rate_5m{provider="openai"}=0.6` → next check returns
     state=OPEN.
   - `test_check_half_open_after_cooldown` — open state, wait 60s,
     next check returns HALF_OPEN.
   - `test_record_success_in_half_open_increments_counter` —
     half-open, 3 record_success → state=CLOSED.
   - `test_record_failure_in_half_open_reopens` — half-open, 1
     record_failure → state=OPEN.
   - `test_read_prometheus_gauge_returns_zero_on_missing` — no
     gauge → returns 0.0 (graceful).
   - Integration: real Prometheus REGISTRY, simulate error rate
     changes, verify state transitions.

Definition of Done:
- `src/llm_client/agent/circuit_breaker.py` существует с `CircuitBreaker`
  (3 methods: check, record_success, record_failure) +
  `CircuitState` enum + `CircuitStatus` dataclass + factory.
- `scripts/circuit_breaker_metrics_collector.py` — background task
  updating gauge every 30s.
- `LLMRouter._check_circuit_breaker` использует `CircuitBreaker`
  класс (не inline Prometheus parsing).
- State transitions: CLOSED → OPEN (on 50% error rate), OPEN →
  HALF_OPEN (after 60s cooldown), HALF_OPEN → CLOSED (3 successes)
  or back to OPEN (1 failure).
- 6+ unit + 1 integration тестов зелёные.

Антипаттерны:
- НЕ делай `CircuitBreaker.check` blocking в hot path — async, lock
  на короткое время (in-memory state, не external Prometheus HTTP).
- НЕ делай COOLDOWN_SECONDS > 5 min — OpenAI/Anthropic outages обычно
  краткосрочные (rate limit, regional issue).
- НЕ делай TRIAL_SUCCESS_THRESHOLD > 5 — иначе breaker будет долго
  half-open.
- НЕ хардкодь 0.5 threshold — Settings.llm_circuit_breaker_error_threshold.
- НЕ забудь record_success / record_failure calls — без них breaker
  застрянет в OPEN или HALF_OPEN forever.
- НЕ делай background task в main app process (Phase 4 — Celery
  worker); Phase 3 asyncio.create_task на startup — acceptable.

Связанные ADR:
- Реализует: ADR-015 per-provider circuit breaker.
- Применяет: Standard 5.1.1 ТРИЗ (Prometheus как вещество извне),
  принцип #16 (частичное/избыточное — partial 30% fallback).
- Зависит от: Блок A-2 (`llm_error_rate_5m` gauge, `update_error_rate`),
  Блок C-2 (`LLMRouter._check_circuit_breaker`).
- Расширяется в: Phase 4 — full Prometheus HTTP query API (не
  in-process REGISTRY); per-model circuit breaker (не per-provider);
  alerting via Grafana contactpoints.
- Не затрагивает: ADR-010 (checkpoint — circuit breaker не depends
  on checkpoint state), ADR-013 (cancel — circuit breaker не emits
  cancel events).
```

### C-5. Anthropic case в `LLMProviderFactory` (unblock Phase 3 stub)

```
Ты — Backend/разработчик LLM Client. Разблокируй Anthropic provider
case в `LLMProviderFactory.create()` — Phase 1 stub raises
NotImplementedError("Anthropic provider is Phase 3 (ADR-015)"),
Phase 3 должен вернуть `ChatAnthropic` instance.

Контекст:
- `src/llm_client/agent/provider.py` строки 198-201:
  ```python
  case "anthropic":
      raise NotImplementedError(
          "Anthropic provider is Phase 3 (ADR-015 cost-aware router)"
      )
  ```
  Phase 3 разблокирует (для ADR-015 router fallback chain
  openai→anthropic).
- ADR-015 fallback (Блок C-2 `_fallback_provider`): openai → (anthropic,
  claude-3-haiku). Без anthropic case unblocked, fallback не работает.
- `langchain-anthropic>=0.3.0` уже в `pyproject.toml` (Phase 1
  declared, не использовался).
- ARCHITECT.md v1.3.0 §5.2.3 (LLM Provider Layer) — `LLMProviderFactory`
  extended с anthropic case.

Задача:
1. Обнови `src/llm_client/agent/provider.py` `LLMProviderFactory.create()`:
   ```python
   # in LLMProviderFactory.create():
   @staticmethod
   def create(
       provider: str,
       model: str,
       api_key: str | None,
       temperature: float = 0.7,
       streaming: bool = True,
   ) -> BaseChatModel:
       if provider == "openai":
           from langchain_openai import ChatOpenAI
           return ChatOpenAI(
               model=model, api_key=api_key, temperature=temperature,
               streaming=streaming,
           )
       elif provider == "anthropic":
           # NEW Phase 3 (ADR-015 cost-aware router fallback)
           from langchain_anthropic import ChatAnthropic
           return ChatAnthropic(
               model=model, api_key=api_key, temperature=temperature,
               streaming=streaming,
               # Anthropic-specific: max_tokens is required
               max_tokens=4096,
           )
       elif provider == "custom-openai":
           # existing Phase 1 case
           from langchain_openai import ChatOpenAI
           return ChatOpenAI(
               model=model, api_key=api_key, temperature=temperature,
               streaming=streaming,
               base_url=get_settings().custom_openai_base_url,
           )
       elif provider == "zai":
           # ZAI-hosted LLM via OpenAI-compatible API
           from langchain_openai import ChatOpenAI
           return ChatOpenAI(
               model=model, api_key=api_key, temperature=temperature,
               streaming=streaming,
               base_url=get_settings().zai_base_url,
           )
       elif provider == "ollama":
           # STILL Phase 4 (ADR-016 ToolCallingAdapter + full local LLM)
           raise NotImplementedError(
               "Ollama provider is Phase 4 (ADR-016 tool capability adapter)"
           )
       else:
           raise ValueError(f"Unknown provider: {provider}")
   ```

2. Обнови `src/llm_client/config.py` Settings — добавь
   anthropic-specific settings:
   ```python
   # Phase 3 — Anthropic provider (ADR-015 fallback)
   anthropic_api_key: str | None = None  # env: ANTHROPIC_API_KEY
   anthropic_model: str = "claude-3-haiku"  # default for cost-aware fallback
   anthropic_max_tokens: int = 4096
   ```

3. Обнови `.env.example`:
   ```env
   # === Phase 3 — Anthropic provider (ADR-015 fallback) ===
   ANTHROPIC_API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxx
   ANTHROPIC_MODEL=claude-3-haiku
   ANTHROPIC_MAX_TOKENS=4096
   ```

4. Обнови `pyproject.toml` — убедись, что `langchain-anthropic>=0.3.0`
   уже в dependencies (Phase 1 declared, не использовался):
   ```toml
   [project]
   dependencies = [
       # ... existing ...
       "langchain-anthropic>=0.3.0,<0.4.0",
   ]
   ```

5. Тесты в `tests/unit/test_provider_anthropic.py`:
   - `test_create_anthropic_returns_chat_anthropic` —
     `LLMProviderFactory.create("anthropic", "claude-3-haiku",
     "sk-ant-...")` returns `ChatAnthropic` instance.
   - `test_create_anthropic_uses_max_tokens` —
     verify ChatAnthropic instance has max_tokens=4096 (Anthropic
     requires this).
   - `test_create_anthropic_with_streaming_true` — verify streaming
     parameter passed.
   - `test_create_anthropic_with_temperature` — verify temperature.
   - `test_create_anthropic_missing_api_key_raises` — api_key=None →
     ChatAnthropic raises ValidationError on first call.
   - Integration (`tests/integration/test_anthropic_provider_integration.py`):
     mock `langchain_anthropic.ChatAnthropic`, verify
     `LLMProviderFactory.create("anthropic", ...)` returns mock.

Definition of Done:
- `LLMProviderFactory.create("anthropic", "claude-3-haiku", api_key)`
  returns `ChatAnthropic` instance (не NotImplementedError).
- `langchain-anthropic>=0.3.0` явно в `pyproject.toml` dependencies.
- `Settings.anthropic_api_key`, `anthropic_model`,
  `anthropic_max_tokens` добавлены.
- `.env.example` обновлён с `ANTHROPIC_*` vars.
- 5+ unit + 1 integration тестов зелёные.
- Существующие тесты Phase 1/2 (`test_provider.py`) — не
  регрессируют (openai case не тронут; anthropic case теперь returns
  instance, не raises).

Антипаттерны:
- НЕ делай anthropic case без `max_tokens` — Anthropic API требует
  этот параметр (raises без него).
- НЕ хардкодь model="claude-3-haiku" — Settings.anthropic_model.
- НЕ делай streaming=False default — ADR-007 SSE streaming (Phase 1)
  требует streaming=True.
- НЕ забудь `langchain-anthropic` в pyproject.toml dependencies —
  без него import fails.
- НЕ делай anthropic case async-only — `ChatAnthropic` sync factory
  pattern, async через `.astream()` method (LangChain standard).
- НЕ удаляй существующий comment "Anthropic provider is Phase 3..." —
  замени на "Phase 3 (ADR-015) — implemented" comment (for git history
  traceability).

Связанные ADR:
- Реализует: ADR-015 fallback chain unblock (openai→anthropic).
- Применяет: ADR-007 (SSE streaming — streaming=True for ChatAnthropic),
  ADR-006 (native tool calling — ChatAnthropic supports function
  calling).
- Зависит от: Phase 1 AG-2 (`LLMProviderFactory` structure),
  `langchain-anthropic>=0.3.0`.
- Расширяется в: Phase 4 — `case "ollama":` будет разблокирован
  (после ADR-016 ToolCallingAdapter); custom-openai case может
  расшириться для vLLM, LM Studio, etc.
- Не затрагивает: ADR-010 (checkpoint — anthropic provider не depends
  on checkpoint), ADR-013 (cancel — CancellationToken router-agnostic),
  ADR-014 (operational stream — TokenUsageTracker callback работает
  с ChatAnthropic, same BaseChatModel interface).
```

### C-6. Migration plan: replace `fallback_chain` на `LLMRouter.route()`

```
Ты — Backend/разработчик LLM Client. Разработай migration plan по
упразднению `fallback_chain` (ADR-005) и замене на `LLMRouter.route()`
(ADR-015). ROADMAP §13.2 risk: ADR-015 explicitly `Supersedes:` часть
ADR-005, нужен `Migration plan:`.

Контекст:
- ADR-005 (ARCHITECT.md v1.3.0 §7): `fallback_chain` — Phase 1
  pattern: `LLMProviderFactory.create()` с hardcoded fallback
  openai→anthropic при OpenAI outage. Phase 1 comment в
  `src/llm_client/agent/provider.py` строка 422: "fallback_chain —
  Phase 3 (ADR-015 cost-aware router)".
- ADR-015 **Supersedes**: часть ADR-005 (fallback_chain упраздняется,
  replaced на cost-aware routing с load-balancing 70/30 и fallback
  только в extreme cases).
- Блок C-2 реализовал `LLMRouter.route(query, policy, ...) ->
  RoutingDecision` + `create_llm(decision) -> BaseChatModel`.
- ROADMAP §13.2: risk "Conflict with existing ADR" — ADR-015 needs
  explicit `Supersedes:` + `Migration plan:`.

Задача:
1. Создай `docs/migration_adr_005_to_015.md` (или расширь existing
   ADR docs):
   ```markdown
   # Migration Plan: ADR-005 fallback_chain → ADR-015 LLMRouter

   **Supersedes**: ADR-005 (fallback_chain part — упраздняется,
   replaced by ADR-015 cost-aware routing).
   **Reason**: ADR-005 fallback_chain не поддерживает cost
   predictability (C-7 contradiction), load balancing, cost guard
   на 80% budget. ADR-015 решает все эти проблемы.

   ## Migration steps

   ### Step 1 (Phase 3 начало): Shadow mode
   - `LLMRouter` развёрнут в **shadow mode**: каждый LLM call идёт
     через существующий `LLMProviderFactory.create()` (без изменений),
     но параллельно `LLMRouter.route()` вычисляется и логируется
     (не используется для routing).
   - Сравнение: что router выбрал бы vs что фактически было.
   - Длительность: 1 месяц (per ROADMAP §14.1 pilot criterion).

   ### Step 2 (Phase 3 середина): Gradual cutover
   - 5% трафика routed via `LLMRouter` (feature flag
     `LLM_ROUTER_ENABLED=true`, `LLM_ROUTER_TRAFFIC_PERCENT=5`).
   - Мониторинг: error rate, latency, cost. Если error rate +2pct
     → rollback to 0%.

   ### Step 3 (Phase 3 конец): Full cutover
   - 100% трафика via `LLMRouter`. `LLMProviderFactory.create()`
     вызывается только через `LLMRouter.create_llm(decision)`.
   - Прямые вызовы `LLMProviderFactory.create()` в graph code
     заменены на `router.create_llm(decision)`.
   - `fallback_chain` pattern (hardcoded openai→anthropic в `provider.py`)
     удалён (или deprecated comment).

   ### Step 4 (Phase 4): Cleanup
   - Deprecated comment "fallback_chain — Phase 3 (ADR-015)" удалён
     из `provider.py` строка 422.
   - `_COST_PER_1M` hardcode (строки 32-35) удалён (Блок C-1
     `ModelCostTable` полностью заменил).
   ```

2. Реализуй shadow mode в `LLMRouter`:
   ```python
   # in src/llm_client/agent/router.py
   class LLMRouter:
       SHADOW_MODE = False  # set True during Phase 3 Step 1

       async def route_shadow(self, query: str | None = None,
                              policy: RoutingPolicy = RoutingPolicy.COST) -> RoutingDecision:
           """Compute routing decision in shadow mode (logged, not used).
           Called in parallel with existing LLMProviderFactory.create()."""
           decision = await self.route(query, policy)
           # Log decision for observability (shadow mode comparison)
           from ..observability.operational_writer import get_operational_writer
           writer = get_operational_writer()
           await writer.write({
               "event_type": "router_shadow_decision",
               "decision": decision.__dict__,
               "timestamp": time.time(),
           })
           return decision
   ```

3. Добавь feature flag в Settings:
   ```python
   # in src/llm_client/config.py
   llm_router_enabled: bool = False  # default False (shadow mode)
   llm_router_traffic_percent: int = 0  # 0-100
   llm_router_shadow_mode: bool = True  # log decisions without using
   ```

4. Обнови `src/llm_client/agent/service.py` (или graph creation
   code) — используй `LLMRouter` если enabled:
   ```python
   # in agent/__main__.py or agent/service.py
   from .router import get_llm_router, RoutingPolicy
   from .provider import LLMProviderFactory

   settings = get_settings()
   if settings.llm_router_enabled:
       router = get_llm_router()
       # For each request: compute decision, create llm via router
       decision = await router.route(
           policy=RoutingPolicy(settings.llm_router_default_policy),
       )
       llm = await router.create_llm(decision)
       # Shadow mode: also compute shadow decision (logged)
       if settings.llm_router_shadow_mode:
           await router.route_shadow()
   else:
       # Existing Phase 1/2 behavior: direct LLMProviderFactory.create()
       llm = LLMProviderFactory.create(
           provider=settings.llm_provider,
           model=settings.openai_model,
           api_key=settings.openai_api_key,
       )
   ```

5. Тесты в `tests/unit/test_router_migration.py`:
   - `test_shadow_mode_logs_decision` — shadow_mode=True,
     `route_shadow` writes `router_shadow_decision` event to
     operational stream.
   - `test_router_disabled_falls_back_to_factory` —
     llm_router_enabled=False → uses LLMProviderFactory.create
     directly (Phase 1/2 behavior preserved).
   - `test_router_enabled_uses_router_create_llm` —
     llm_router_enabled=True → calls `router.create_llm(decision)`.
   - `test_traffic_percent_0_means_disabled` —
     llm_router_traffic_percent=0 → router disabled.
   - `test_traffic_percent_100_means_full_cutover` —
     traffic_percent=100 → all requests via router.

Definition of Done:
- `docs/migration_adr_005_to_015.md` создан с 4-step migration plan
  (Shadow → Gradual cutover → Full cutover → Cleanup).
- `LLMRouter.SHADOW_MODE` + `route_shadow()` method реализованы.
- Feature flags `llm_router_enabled`, `llm_router_traffic_percent`,
  `llm_router_shadow_mode` в Settings.
- Agent startup code (`agent/__main__.py` / `agent/service.py`)
  использует `LLMRouter` если enabled, иначе fallback на Phase 1/2
  behavior (LLMProviderFactory.create directly).
- 5+ unit тестов зелёные.
- Phase 1/2 behavior preserved (если `llm_router_enabled=False`
  default → 0 behavior change).
- ADR-005 `fallback_chain` помечен deprecated (comment в
  `provider.py` строка 422 обновлён: "fallback_chain — DEPRECATED,
  use LLMRouter (ADR-015) — Phase 3 cutover in progress").

Антипаттерны:
- НЕ делай big-bang cutover (Phase 3 Step 1 сразу 100%) — высокий
  риск rollback; gradual cutover (5% → 50% → 100%).
- НЕ удаляй `fallback_chain` pattern сразу — Step 3 cutover ещё
  может быть rollback'нут; Step 4 cleanup только после успешного
  Step 3 (1 month stable).
- НЕ делай shadow mode без operational stream logging — critical
  for ADR-015 pilot criterion "логирование switching decisions в
  observability".
- НЕ делай `llm_router_traffic_percent` как float (0.0-1.0) — int
  0-100 (более user-friendly для feature flag).
- НЕ забудь обновить `agent/__main__.py` — без явного router
  integration в startup code, Phase 3 prompts C-2..C-5 не имеют
  эффекта.

Связанные ADR:
- Реализует: ADR-015 migration plan (критично для Supersedes ADR-005
  per ROADMAP §13.2).
- Применяет: принцип #16 ТРИЗ (частичное/избыточное — gradual
  cutover 5% → 100%), ADR-014 (operational stream — shadow decisions
  logged).
- Зависит от: Блок C-2 (`LLMRouter.route` / `create_llm`), Phase 1
  AG-2 (`LLMProviderFactory.create`).
- Расширяется в: Phase 4 — A/B test framework для router (continuous
  comparison router vs factory), automated rollback on error rate
  spike.
- Не затрагивает: ADR-010 (checkpoint — migration не depends on
  checkpoint state), ADR-013 (cancel — CancellationToken
  router-agnostic).
```

### C-7. Shadow-mode metrics logger (логирование switching decisions)

```
Ты — Observability/Backend-разработчик LLM Client. Создай
`RouterMetricsLogger` — компонент, логирующий каждое routing decision
в operational stream (ADR-014) для ADR-015 pilot criterion
"логирование switching decisions в observability".

Контекст:
- ADR-015 (TRIZ-ANALYSIS.md v1.0.0 §11 драфт): каждое routing decision
  логируется в observability; pilot criterion "логирование switching
  decisions доступно в observability".
- Блок C-2 `RoutingDecision` dataclass: provider, model, policy,
  reason, budget_ratio_at_decision, circuit_breaker_active.
- Phase 1 ADR-014 `OperationalStreamWriter` — existing infrastructure
  для structured logging в operational stream (S3 + local file).
- ТРИЗ Standard 2.2.4 (переход к измерительной веполи): metrics
  logger = measuring function для router decisions.

Задача:
1. Создай `src/llm_client/observability/router_metrics_logger.py`:
   ```python
   """Logger for LLMRouter decisions (ADR-015 Phase 3).

   Writes every RoutingDecision to operational stream (ADR-014) for
   audit + Grafana dashboards.

   Architecture: ARCHITECT.md v1.3.0 §5.2.3 (LLM Provider Layer),
   §5.2.7 (Observability Layer).
   TRIZ: Standard 2.2.4 (measuring vepol — router decisions measured).
   """
   import logging
   from datetime import datetime, timezone

   from .operational_writer import get_operational_writer

   logger = logging.getLogger(__name__)


   class RouterMetricsLogger:
       """Logs routing decisions to operational stream."""

       def __init__(self) -> None:
           self._writer = get_operational_writer()

       async def log_decision(self, decision, request_id: str | None = None) -> None:
           """Log a RoutingDecision (Блок C-2 RoutingDecision dataclass)."""
           event = {
               "event_type": "router_decision",
               "timestamp": datetime.now(timezone.utc).isoformat(),
               "request_id": request_id,
               "provider": decision.provider,
               "model": decision.model,
               "policy": decision.policy.value if hasattr(decision.policy, "value") else str(decision.policy),
               "reason": decision.reason,
               "budget_ratio": decision.budget_ratio_at_decision,
               "circuit_breaker_active": decision.circuit_breaker_active,
           }
           await self._writer.write(event)
           logger.info(
               "Router decision: provider=%s model=%s policy=%s reason=%s budget=%.1f%% cb=%s",
               decision.provider, decision.model,
               event["policy"], decision.reason,
               decision.budget_ratio_at_decision * 100,
               decision.circuit_breaker_active,
           )

       async def log_shadow_decision(self, decision, actual_provider: str,
                                      actual_model: str, request_id: str | None = None) -> None:
           """Log shadow-mode comparison: what router WOULD have chosen
           vs what was actually used."""
           event = {
               "event_type": "router_shadow_comparison",
               "timestamp": datetime.now(timezone.utc).isoformat(),
               "request_id": request_id,
               "router_would_choose_provider": decision.provider,
               "router_would_choose_model": decision.model,
               "router_would_choose_reason": decision.reason,
               "actual_provider": actual_provider,
               "actual_model": actual_model,
               "match": (decision.provider == actual_provider and decision.model == actual_model),
           }
           await self._writer.write(event)


   _logger: RouterMetricsLogger | None = None


   def get_router_metrics_logger() -> RouterMetricsLogger:
       global _logger
       if _logger is None:
           _logger = RouterMetricsLogger()
       return _logger
   ```

2. Расширь `LLMRouter.route()` (Блок C-2) — после compute decision,
   логируй его:
   ```python
   # in LLMRouter.route()
   async def route(self, query: str | None = None,
                   policy: RoutingPolicy = RoutingPolicy.COST,
                   privacy_required: bool = False,
                   request_id: str | None = None) -> RoutingDecision:
       # ... existing routing logic ...
       decision = RoutingDecision(...)

       # NEW Phase 3 C-7: log decision
       from ..observability.router_metrics_logger import get_router_metrics_logger
       await get_router_metrics_logger().log_decision(decision, request_id)

       return decision
   ```

3. Создай Grafana panel в `ops/grafana/dashboards/llm-cost-router.json`
   (Блок F-2 детализирует full dashboard; здесь — только router
   decisions panel):
   ```json
   {
     "title": "Router Decisions (last 1h)",
     "panels": [
       {
         "title": "Decisions by policy",
         "type": "pie",
         "targets": [{"expr": "sum by (policy) (router_decisions_total)"}]
       },
       {
         "title": "Cost guard triggers",
         "type": "stat",
         "targets": [{"expr": "sum(router_decisions_total{reason=~\".*Budget.*\"})"}]
       },
       {
         "title": "Circuit breaker activations",
         "type": "stat",
         "targets": [{"expr": "sum(router_decisions_total{circuit_breaker_active=\"true\"})"}]
       }
     ]
   }
   ```

4. Тесты в `tests/unit/test_router_metrics_logger.py`:
   - `test_log_decision_writes_to_operational_stream` — mock
     OperationalStreamWriter, call log_decision, verify write called
     with correct event.
   - `test_log_decision_includes_all_fields` — verify event has
     provider, model, policy, reason, budget_ratio,
     circuit_breaker_active.
   - `test_log_shadow_decision_with_match` — actual=router decision
     → match=True logged.
   - `test_log_shadow_decision_with_mismatch` — actual != router →
     match=False logged.

Definition of Done:
- `src/llm_client/observability/router_metrics_logger.py` существует
  с `RouterMetricsLogger` (2 methods: log_decision, log_shadow_decision)
  + factory.
- `LLMRouter.route()` вызывает `log_decision(decision, request_id)`
  после compute.
- Grafana panel `ops/grafana/dashboards/llm-cost-router.json` создан
  с 3 panels (decisions by policy, cost guard triggers, circuit
  breaker activations).
- 4+ unit тестов зелёные.
- Pilot criterion "логирование switching decisions в observability"
  verifiable via: query operational stream for `event_type:
  "router_decision"` events, count decisions, verify all 4 policies
  present.

Антипаттерны:
- НЕ делай log_decision blocking — async (operational stream is
  async S3 write, fire-and-forget acceptable для router hot path).
- НЕ хардкодь Grafana panel structure — JSON dashboard file
  (editable by ops без redeploy).
- НЕ забудь `request_id` — критично для trace router decision per
  user request (correlate with SSE events from Phase 1 AG-3).
- НЕ логируй PII (query text) — RoutingDecision не содержит query,
  только decision fields.
- НЕ делай router_metrics_logger отдельным от OperationalStreamWriter
  — wraps writer (использует existing infra ADR-014).

Связанные ADR:
- Реализует: ADR-015 pilot criterion "логирование switching decisions
  в observability" (критично для Approved per ROADMAP §14.1).
- Применяет: ADR-014 (operational stream — reuses
  OperationalStreamWriter), Standard 2.2.4 ТРИЗ (measuring vepol).
- Зависит от: Блок C-2 (`LLMRouter.route` — для log_decision), Phase 1
  ADR-014 (`OperationalStreamWriter`).
- Расширяется в: Phase 4 — Grafana alerting на cost guard trigger
  (notify Slack when budget >80%), anomaly detection на router
  decision patterns.
- Не затрагивает: ADR-010 (checkpoint — не depends on router
  decisions), ADR-013 (cancel — не depends on router decisions).
```

---

## 4. Блок D. ADR-016: Tool Capability Adapter

Блок D реализует ADR-016 — `ModelCapabilityMatrix` (per-model declarations capabilities) + `ToolCallingAdapter` (выбор mode `native` / `react` / `hybrid` для tool calling). Это позволяет поддерживать локальные модели (Ollama, Llama) без native function calling через ReAct-эмуляцию.

Пилотные метрики (ROADMAP §14.1): pilot на Ollama + Llama 3.1 success rate ≥80% (vs native ≥95%). Rollback: success <60% OR false capability matrix entries cause runtime errors.

TRIZ: Standard 3.1.4 (дробление поля — split `tool_calling` field на `NativeToolCalling` + `ReActToolCalling`); принципы #13 (наоборот — ReAct as base, native as optimization), #35 (изменение параметров — `ToolCallingMode` enum), #1 (дробление — separate tool description from tool invocation), #25 (самообслуживание — models self-declare capabilities).

---

### D-1. `ModelCapabilityMatrix` (data structure + YAML registry)

```
Ты — Backend/разработчик LLM Client. Создай `ModelCapabilityMatrix` —
per-model declarations: `supports_native_tools`, `supports_streaming`,
`supports_vision`, `context_window`, `cost_per_1m_tokens`, `latency_p50`,
`latency_p99`. Загружается из YAML config. Это data layer для ADR-016
`ToolCallingAdapter` (Блок D-3) и для ADR-015 `LLMRouter` (Блок C-2)
для routing decisions.

Контекст:
- ADR-016 (TRIZ-ANALYSIS.md v1.0.0 §11 драфт): `ModelCapabilityMatrix`
  — per-model declarations: `supports_native_tools`,
  `supports_streaming`, `supports_vision`, `context_window`,
  `cost_per_1m_tokens`, `latency_p50`, `latency_p99`.
- Блок C-1 создал `ModelCostTable` (subset capability matrix, focused
  на cost). `ModelCapabilityMatrix` — superset, включает cost +
  capabilities + latency.
- ARCHITECT.md v1.3.0 §5.2.3 (LLM Provider Layer) — `LLMRouter` и
  `ToolCallingAdapter` читают capability matrix для routing +
  tool calling mode selection.
- ТРИЗ принцип 25 (самообслуживание): models self-declare
  capabilities through registry; adapter chooses strategy
  automatically.
- ТРИЗ Standard 3.1.4 (дробление поля): split `tool_calling` на
  `NativeToolCalling` + `ReActToolCalling` — capability matrix
  declares which modes each model supports.

Задача:
1. Создай `src/llm_client/agent/capability_matrix.py`:
   ```python
   """Model Capability Matrix (ADR-016 Phase 3).

   Per-model declarations: supports_native_tools, supports_streaming,
   supports_vision, context_window, cost_per_1m_tokens, latency_p50,
   latency_p99. Loaded from YAML config.

   Architecture: ARCHITECT.md v1.3.0 §5.2.3.
   TRIZ: principle #25 (self-service — models self-declare);
   Standard 3.1.4 (field splitting — NativeToolCalling vs ReActToolCalling).
   """
   import logging
   from pathlib import Path
   from typing import Any

   import yaml
   from pydantic import BaseModel, Field

   logger = logging.getLogger(__name__)


   class ModelCapabilities(BaseModel):
       """Capabilities for one (provider, model) pair."""
       supports_native_tools: bool = Field(
           default=False, description="True if model supports OpenAI-style function calling",
       )
       supports_streaming: bool = Field(
           default=True, description="True if model supports SSE streaming",
       )
       supports_vision: bool = Field(
           default=False, description="True if model supports image input",
       )
       context_window: int = Field(
           default=4096, ge=128, description="Max tokens in context",
       )
       cost_per_1m_tokens: dict[str, float] = Field(
           default_factory=lambda: {"prompt": 0.0, "completion": 0.0},
           description="USD per 1M tokens: {prompt, completion}",
       )
       latency_p50_ms: int = Field(
           default=500, ge=10, description="Median latency in ms (non-streaming first token)",
       )
       latency_p99_ms: int = Field(
           default=2000, ge=100, description="P99 latency in ms",
       )
       supports_react_emulation: bool = Field(
           default=True, description="True if ReAct prompt-based tool calling works (most LLMs)",
       )
       notes: str = Field(default="", description="Free-form notes about this model")


   class ModelCapabilityMatrix(BaseModel):
       """Mapping of (provider, model) -> ModelCapabilities."""
       capabilities: dict[str, dict[str, ModelCapabilities]] = Field(
           default_factory=dict,
           description="Outer key = provider, inner key = model",
       )

       def get_capabilities(self, provider: str, model: str) -> ModelCapabilities | None:
           """Returns ModelCapabilities for (provider, model) or None."""
           provider_table = self.capabilities.get(provider)
           if provider_table is None:
               return None
           return provider_table.get(model)

       def list_models_supporting_native_tools(self) -> list[tuple[str, str]]:
           """Returns list of (provider, model) pairs supporting native tool calling."""
           result = []
           for provider, models in self.capabilities.items():
               for model, caps in models.items():
                   if caps.supports_native_tools:
                       result.append((provider, model))
           return result

       def list_models_supporting_vision(self) -> list[tuple[str, str]]:
           """Returns list of (provider, model) pairs supporting vision input."""
           result = []
           for provider, models in self.capabilities.items():
               for model, caps in models.items():
                   if caps.supports_vision:
                       result.append((provider, model))
           return result

       def find_model_for_context_length(self, min_tokens: int) -> tuple[str, str] | None:
           """Returns first (provider, model) with context_window >= min_tokens."""
           for provider, models in self.capabilities.items():
               for model, caps in models.items():
                   if caps.context_window >= min_tokens:
                       return (provider, model)
           return None


   DEFAULT_CAPABILITIES_YAML = """
   openai:
     gpt-4o-mini:
       supports_native_tools: true
       supports_streaming: true
       supports_vision: false
       context_window: 128000
       cost_per_1m_tokens:
         prompt: 0.15
         completion: 0.60
       latency_p50_ms: 500
       latency_p99_ms: 1500
       supports_react_emulation: true
       notes: "Default cost-aware choice; good for tool calling"
     gpt-4o:
       supports_native_tools: true
       supports_streaming: true
       supports_vision: true
       context_window: 128000
       cost_per_1m_tokens:
         prompt: 2.50
         completion: 10.00
       latency_p50_ms: 800
       latency_p99_ms: 3000
       supports_react_emulation: true
       notes: "Quality choice; supports vision + native tools"
   anthropic:
     claude-3-5-sonnet:
       supports_native_tools: true
       supports_streaming: true
       supports_vision: true
       context_window: 200000
       cost_per_1m_tokens:
         prompt: 3.00
         completion: 15.00
       latency_p50_ms: 1000
       latency_p99_ms: 4000
       supports_react_emulation: true
       notes: "Quality alternative; long context"
     claude-3-haiku:
       supports_native_tools: true
       supports_streaming: true
       supports_vision: false
       context_window: 200000
       cost_per_1m_tokens:
         prompt: 0.25
         completion: 1.25
       latency_p50_ms: 400
       latency_p99_ms: 1200
       supports_react_emulation: true
       notes: "Cost-aware Anthropic alternative"
   ollama:
     llama3.1-8b:
       supports_native_tools: false  # No native function calling in Llama 3.1 base
       supports_streaming: true
       supports_vision: false
       context_window: 128000
       cost_per_1m_tokens:
         prompt: 0.0
         completion: 0.0
       latency_p50_ms: 200  # Local inference is fast (no network)
       latency_p99_ms: 1000
       supports_react_emulation: true
       notes: "Phase 4 full integration; ReAct mode required for tools"
     mistral-7b-instruct:
       supports_native_tools: false
       supports_streaming: true
       supports_vision: false
       context_window: 32000
       cost_per_1m_tokens:
         prompt: 0.0
         completion: 0.0
       latency_p50_ms: 150
       latency_p99_ms: 800
       supports_react_emulation: true
       notes: "Lightweight local model; ReAct mode"
   custom-openai:
     default:
       supports_native_tools: true  # Assume self-hosted OpenAI-compatible supports tools
       supports_streaming: true
       supports_vision: false
       context_window: 4096
       cost_per_1m_tokens:
         prompt: 0.0
         completion: 0.0
       latency_p50_ms: 300
       latency_p99_ms: 1500
       supports_react_emulation: true
       notes: "Self-hosted via vLLM/LM Studio; capability depends on host"
   """


   _matrix: ModelCapabilityMatrix | None = None


   def get_capability_matrix() -> ModelCapabilityMatrix:
       """Singleton ModelCapabilityMatrix. Loads from YAML or defaults."""
       global _matrix
       if _matrix is not None:
           return _matrix
       import os
       config_path = os.environ.get("MODEL_CAPABILITIES_CONFIG_PATH")
       if config_path and Path(config_path).exists():
           with open(config_path) as f:
               data = yaml.safe_load(f)
           _matrix = ModelCapabilityMatrix.model_validate({"capabilities": data})
           logger.info("Loaded model capabilities from %s", config_path)
       else:
           data = yaml.safe_load(DEFAULT_CAPABILITIES_YAML)
           _matrix = ModelCapabilityMatrix.model_validate({"capabilities": data})
           logger.info("Loaded default model capabilities (built-in)")
       return _matrix
   ```

2. Создай default config file `config/model_capabilities.yaml`:
   ```yaml
   # Model capabilities registry (Phase 3 ADR-016)
   # Override via env MODEL_CAPABILITIES_CONFIG_PATH.
   # Update when new models are released (e.g. GPT-5, Claude 4, etc.)
   openai:
     gpt-4o-mini:
       supports_native_tools: true
       supports_streaming: true
       supports_vision: false
       context_window: 128000
       cost_per_1m_tokens: {prompt: 0.15, completion: 0.60}
       latency_p50_ms: 500
       latency_p99_ms: 1500
       supports_react_emulation: true
     gpt-4o:
       supports_native_tools: true
       supports_streaming: true
       supports_vision: true
       context_window: 128000
       cost_per_1m_tokens: {prompt: 2.50, completion: 10.00}
       latency_p50_ms: 800
       latency_p99_ms: 3000
       supports_react_emulation: true
   anthropic:
     claude-3-5-sonnet:
       supports_native_tools: true
       supports_streaming: true
       supports_vision: true
       context_window: 200000
       cost_per_1m_tokens: {prompt: 3.00, completion: 15.00}
       latency_p50_ms: 1000
       latency_p99_ms: 4000
       supports_react_emulation: true
     claude-3-haiku:
       supports_native_tools: true
       supports_streaming: true
       supports_vision: false
       context_window: 200000
       cost_per_1m_tokens: {prompt: 0.25, completion: 1.25}
       latency_p50_ms: 400
       latency_p99_ms: 1200
       supports_react_emulation: true
   ollama:
     llama3.1-8b:
       supports_native_tools: false
       supports_streaming: true
       supports_vision: false
       context_window: 128000
       cost_per_1m_tokens: {prompt: 0.0, completion: 0.0}
       latency_p50_ms: 200
       latency_p99_ms: 1000
       supports_react_emulation: true
   ```

3. Тесты в `tests/unit/test_capability_matrix.py`:
   - `test_get_capabilities_returns_known_model` —
     `get_capabilities("openai", "gpt-4o-mini")` returns
     `ModelCapabilities(supports_native_tools=True, context_window=128000)`.
   - `test_get_capabilities_returns_none_for_unknown` —
     `get_capabilities("unknown", "mystery")` returns None.
   - `test_list_models_supporting_native_tools` — returns
     [(openai, gpt-4o-mini), (openai, gpt-4o), (anthropic,
     claude-3-5-sonnet), (anthropic, claude-3-haiku)] (4 pairs).
   - `test_list_models_supporting_vision` — returns [(openai, gpt-4o),
     (anthropic, claude-3-5-sonnet)].
   - `test_find_model_for_context_length` —
     `find_model_for_context_length(150000)` returns first model with
     context_window >= 150000 (gpt-4o-mini with 128000 is FALSE; next
     is claude-3-5-sonnet with 200000).
   - `test_ollama_llama_no_native_tools` —
     `get_capabilities("ollama", "llama3.1-8b").supports_native_tools`
     is False (ReAct mode required).
   - `test_load_from_yaml_config_path` — env
     `MODEL_CAPABILITIES_CONFIG_PATH=test_fixtures/custom_caps.yaml`,
     verify loaded from file.

Definition of Done:
- `src/llm_client/agent/capability_matrix.py` существует с
  `ModelCapabilities` + `ModelCapabilityMatrix` +
  `get_capability_matrix()` factory.
- `config/model_capabilities.yaml` создан с 6+ model entries (2
  OpenAI, 2 Anthropic, 1 Ollama, 1 custom-openai).
- 7+ unit тестов зелёные.
- `LLMRouter` (Блок C-2) может читать capability matrix для routing
  (Phase 4 integration).

Антипаттерны:
- НЕ делай `cost_per_1m_tokens` как ModelCost object (Блок C-1) —
  dict[str, float] (simpler; ModelCostTable is separate structure
  for cost-aware routing, capability matrix is for capability
  declarations).
- НЕ хардкодь capabilities в Python коде — только YAML (для ops
  update без redeploy при новых models).
- НЕ делай `supports_react_emulation` default False — почти все
  LLMs поддерживают ReAct через system prompt (только очень small
  models типа <1B params могут не работать).
- НЕ забудь `latency_p50_ms` и `latency_p99_ms` — критично для
  ADR-015 latency policy (Phase 4 integration).
- НЕ делай vision capability optional без verification — actual
  vision support требует API testing (Phase 4 integration test).

Связанные ADR:
- Реализует: ADR-016 `ModelCapabilityMatrix` data layer.
- Применяет: принцип #25 ТРИЗ (самообслуживание — models
  self-declare), Standard 3.1.4 (дробление поля — split
  NativeToolCalling / ReActToolCalling via `supports_native_tools`
  boolean).
- Зависит от: Блок C-1 (`ModelCostTable` — pattern для YAML-config-
  driven structure).
- Расширяется в: Phase 4 — `LLMRouter.route()` reads capability
  matrix для routing (latency policy = lowest p50, quality policy
  = highest context_window + vision); `ToolCallingAdapter` (Блок
  D-3) reads `supports_native_tools` для mode selection.
- Не затрагивает: ADR-010 (checkpoint — capability matrix не
  depends on checkpoint), ADR-013 (cancel), ADR-014 (operational
  stream).
```

### D-2. `ToolCallingMode` enum (`native` / `react` / `hybrid`)

```
Ты — Backend-разработчик LLM Client. Создай `ToolCallingMode` enum
для ADR-016 — 3 режима tool calling: `native` (function calling
API), `react` (system prompt emulation), `hybrid` (native с fallback
на react при parse error).

Контекст:
- ADR-016 (TRIZ-ANALYSIS.md v1.0.0 §11 драфт): `ToolCallingMode`
  enum: `native`, `react`, `hybrid`.
- Блок D-1 создал `ModelCapabilityMatrix` с `supports_native_tools`
  boolean.
- ТРИЗ принцип 35 (изменение параметров): `ToolCallingMode` enum
  для управления режимом.
- ТРИЗ принцип 13 (наоборот): ReAct как base mode, native как
  optimization для models that support it.

Задача:
1. Создай `src/llm_client/agent/tool_calling_mode.py` (or extend
   `capability_matrix.py`):
   ```python
   """ToolCallingMode enum for ADR-016.

   native: function calling API (OpenAI, Anthropic).
   react:  system prompt emulation (Llama, Mistral via Ollama).
   hybrid: native with fallback to react on parse error.

   Architecture: ARCHITECT.md v1.3.0 §5.2.4 (Tool Layer).
   TRIZ: principle #35 (parameter change — enum controls mode);
   principle #13 (inverse — ReAct as base, native as optimization).
   """
   from enum import Enum


   class ToolCallingMode(str, Enum):
       NATIVE = "native"
       REACT = "react"
       HYBRID = "hybrid"

       @classmethod
       def from_string(cls, value: str) -> "ToolCallingMode":
           """Parse string to enum, case-insensitive."""
           normalized = value.strip().lower()
           for mode in cls:
               if mode.value == normalized:
                   return mode
           raise ValueError(
               f"Unknown ToolCallingMode: {value!r}. "
               f"Must be one of: {[m.value for m in cls]}"
           )

       @classmethod
       def default_for_capabilities(cls, caps) -> "ToolCallingMode":
           """Choose default mode based on ModelCapabilities (Блок D-1).
           - supports_native_tools=True → HYBRID (preferred; native with fallback)
           - supports_native_tools=False but supports_react_emulation=True → REACT
           - neither → REACT (best-effort; rarely fails)
           """
           if caps.supports_native_tools:
               return cls.HYBRID  # try native first, fall back to react
           elif caps.supports_react_emulation:
               return cls.REACT
           else:
               # Edge case: very small model, ReAct may fail; default to REACT
               # anyway (failure handled at runtime)
               return cls.REACT
   ```

2. Тесты в `tests/unit/test_tool_calling_mode.py`:
   - `test_from_string_native` —
     `ToolCallingMode.from_string("native")` returns NATIVE.
   - `test_from_string_react_case_insensitive` —
     `from_string("REACT")` returns REACT.
   - `test_from_string_invalid_raises` — `from_string("unknown")`
     raises ValueError.
   - `test_default_for_capabilities_native_support_returns_hybrid` —
     caps.supports_native_tools=True → HYBRID.
   - `test_default_for_capabilities_no_native_returns_react` —
     supports_native_tools=False, supports_react_emulation=True →
     REACT.
   - `test_default_for_capabilities_neither_returns_react` —
     supports_native_tools=False, supports_react_emulation=False →
     REACT (fallback).

Definition of Done:
- `src/llm_client/agent/tool_calling_mode.py` существует с
  `ToolCallingMode` enum (3 values: NATIVE, REACT, HYBRID) +
  `from_string()` + `default_for_capabilities()` classmethods.
- 6+ unit тестов зелёные.
- Enum values `"native"`, `"react"`, `"hybrid"` используются в
  Prometheus labels `llm_call_total{mode="..."}` (Блок A-2 metric).

Антипаттерны:
- НЕ делай enum values camelCase — snake_case (`native`, `react`,
  `hybrid`) для consistency с Prometheus metric labels.
- НЕ делай `default_for_capabilities` всегда NATIVE — для Ollama
  Llama 3.1 (supports_native_tools=False) NATIVE mode упадёт с
  runtime error; HYBRID/REACT выбор через capability matrix.
- НЕ делай enum без `str` mixin — `class ToolCallingMode(str, Enum)`
  для JSON serialization (Pydantic v2 / FastAPI).

Связанные ADR:
- Реализует: ADR-016 ToolCallingMode enum.
- Применяет: принцип #35 ТРИЗ (изменение параметров — enum
  управляет mode), принцип #13 (наоборот — ReAct as base, native
  as optimization).
- Зависит от: Блок D-1 (`ModelCapabilities` для
  `default_for_capabilities`).
- Расширяется в: Phase 4 — `ToolCallingAdapter` (Блок D-3) читает
  mode для bind_tools logic.
- Не затрагивает: ADR-005 (fallback_chain — упраздняется ADR-015),
  ADR-006 (native tool calling — расширяется с ReAct mode через
  ADR-016; ADR-006 contract preserved).
```

### D-3. `ToolCallingAdapter` class (chooses mode by capability matrix)

```
Ты — Backend/Agent-разработчик LLM Client. Создай `ToolCallingAdapter`
— central class, который выбирает режим tool calling (native / react
/ hybrid) на основе `ModelCapabilityMatrix` (Блок D-1) и
`ToolCallingMode` enum (Блок D-2), затем delegates на native
`llm.bind_tools(tools)` или ReAct system prompt.

Контекст:
- ADR-016 (TRIZ-ANALYSIS.md v1.0.0 §11 драфт): `ToolCallingAdapter`
  chooses mode by capability matrix; for models without native
  function calling (Llama 3.1 base via Ollama) → ReAct emulation
  auto-enabled.
- Блок D-1 создал `ModelCapabilityMatrix` + `get_capability_matrix()`.
- Блок D-2 создал `ToolCallingMode` enum.
- Phase 1 AG-1 `build_agent_graph` вызывает `llm.bind_tools(tools)`
  в `planner` node (native mode, ADR-006). Phase 3 ADR-016 —
  `ToolCallingAdapter` выбирает mode + delegates.
- ADR-015 `LLMRouter` (Блок C-2) использует capability matrix для
  routing; `ToolCallingAdapter` — для tool calling mode selection
  на выбранном (provider, model).
- ТРИЗ принцип 1 (дробление): separate "tool description" (единый
  для всех моделей) от "tool invocation" (специфичный для режима).
- ТРИЗ принцип 13 (наоборот): ReAct as base mode, native as
  optimization for models that support it.

Задача:
1. Создай `src/llm_client/agent/tool_calling_adapter.py`:
   ```python
   """Tool Calling Adapter (ADR-016 Phase 3).

   Chooses between native function calling API (OpenAI/Anthropic),
   ReAct system-prompt emulation (Llama/Mistral), or hybrid (native
   with fallback on parse error).

   Architecture: ARCHITECT.md v1.3.0 §5.2.4 (Tool Layer).
   TRIZ: principle #1 (separation — tool description vs invocation);
   principle #13 (inverse — ReAct as base, native as optimization).
   """
   import json
   import logging
   import re
   from typing import Any

   from langchain_core.language_models import BaseChatModel
   from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
   from langchain_core.tools import BaseTool

   from .capability_matrix import ModelCapabilityMatrix, get_capability_matrix
   from .tool_calling_mode import ToolCallingMode

   logger = logging.getLogger(__name__)


   REACT_SYSTEM_PROMPT = """You are a helpful assistant with access to the following tools:

   {tool_descriptions}

   When you want to use a tool, output EXACTLY this JSON format on a single line:
   ```json
   {{"tool": "<tool_name>", "arguments": {{<args>}}}}
   ```

   Do not wrap the JSON in markdown fences. Do not add commentary before or after the JSON.
   After the tool executes, you will receive a ToolMessage with the result.

   Available tools:
   {tool_schemas}
   """


   class ToolCallingAdapter:
       """Chooses tool calling mode and delegates to native or ReAct."""

       def __init__(
           self,
           capability_matrix: ModelCapabilityMatrix | None = None,
       ) -> None:
           self._matrix = capability_matrix or get_capability_matrix()

       def choose_mode(
           self,
           provider: str,
           model: str,
           explicit_mode: ToolCallingMode | None = None,
       ) -> ToolCallingMode:
           """Choose ToolCallingMode for (provider, model).
           If explicit_mode provided, use it (override). Else compute
           from capability matrix via ToolCallingMode.default_for_capabilities."""
           if explicit_mode is not None:
               return explicit_mode
           caps = self._matrix.get_capabilities(provider, model)
           if caps is None:
               logger.warning(
                   "No capability matrix entry for %s/%s — defaulting to HYBRID",
                   provider, model,
               )
               return ToolCallingMode.HYBRID
           return ToolCallingMode.default_for_capabilities(caps)

       def bind_tools(
           self,
           llm: BaseChatModel,
           tools: list[BaseTool],
           mode: ToolCallingMode,
       ) -> Any:
           """Bind tools to LLM using the specified mode.

           For NATIVE mode: delegate to llm.bind_tools(tools).
           For REACT mode: return llm wrapped in ReActBoundModel
                          (system prompt injection + parse logic).
           For HYBRID mode: try native first, on parse error fall back
                          to ReAct (per-call fallback in invoke).
           """
           if mode == ToolCallingMode.NATIVE:
               logger.debug("Using NATIVE tool calling mode")
               return llm.bind_tools(tools)
           elif mode == ToolCallingMode.REACT:
               logger.debug("Using REACT tool calling mode")
               return ReActBoundModel(underlying=llm, tools=tools)
           elif mode == ToolCallingMode.HYBRID:
               logger.debug("Using HYBRID tool calling mode (native with ReAct fallback)")
               # Try native bind_tools; if it raises, fall back to ReAct
               try:
                   return HybridBoundModel(
                       native_bound=llm.bind_tools(tools),
                       react_bound=ReActBoundModel(underlying=llm, tools=tools),
                   )
               except Exception as e:
                   logger.warning(
                       "Native bind_tools failed (%s) — falling back to ReAct only",
                       e,
                   )
                   return ReActBoundModel(underlying=llm, tools=tools)
           else:
               raise ValueError(f"Unknown ToolCallingMode: {mode}")

       def _format_tool_descriptions(self, tools: list[BaseTool]) -> str:
           """Format tool descriptions for ReAct system prompt."""
           lines = []
           for tool in tools:
               lines.append(
                   f"- {tool.name}: {tool.description or '(no description)'}"
               )
           return "\n".join(lines)

       def _format_tool_schemas(self, tools: list[BaseTool]) -> str:
           """Format tool argument schemas for ReAct system prompt."""
           schemas = []
           for tool in tools:
               if hasattr(tool, "args_schema") and tool.args_schema:
                   schema = tool.args_schema.model_json_schema()
                   schemas.append(f"- {tool.name}: {json.dumps(schema, indent=2)}")
               else:
                   schemas.append(f"- {tool.name}: (no schema)")
           return "\n".join(schemas)

       def build_react_system_prompt(self, tools: list[BaseTool]) -> str:
           """Build the ReAct system prompt with tool descriptions."""
           return REACT_SYSTEM_PROMPT.format(
               tool_descriptions=self._format_tool_descriptions(tools),
               tool_schemas=self._format_tool_schemas(tools),
           )

       def parse_react_response(self, text: str) -> dict | None:
           """Parse LLM text response to extract tool call.
           Returns {tool, arguments} or None if no tool call detected."""
           # Look for JSON block: {"tool": "...", "arguments": {...}}
           # Tolerate markdown fences and surrounding text.
           match = re.search(
               r'```(?:json)?\s*(\{.*?"tool".*?"arguments".*?\})\s*```',
               text, re.DOTALL,
           )
           if match:
               try:
                   return json.loads(match.group(1))
               except json.JSONDecodeError:
                   pass
           # Try without fences
           match = re.search(
               r'(\{.*?"tool".*?"arguments".*?\})',
               text, re.DOTALL,
           )
           if match:
               try:
                   return json.loads(match.group(1))
               except json.JSONDecodeError:
                   pass
           return None


   class ReActBoundModel:
       """Wraps a BaseChatModel for ReAct-style tool calling.
       Injects system prompt with tool descriptions, parses tool
       calls from text completion."""

       def __init__(self, underlying: BaseChatModel, tools: list[BaseTool]):
           self._underlying = underlying
           self._tools = tools
           self._tools_by_name = {t.name: t for t in tools}
           self._adapter = ToolCallingAdapter()

       async def astream(self, messages: list[BaseMessage], **kwargs):
           """Inject ReAct system prompt, stream response, parse tool
           calls from text."""
           system_prompt = self._adapter.build_react_system_prompt(self._tools)
           messages_with_sys = [SystemMessage(content=system_prompt)] + messages
           accumulated_text = ""
           async for chunk in self._underlying.astream(messages_with_sys, **kwargs):
               accumulated_text += chunk.content if hasattr(chunk, "content") else str(chunk)
               yield chunk
           # After stream completes, check for tool call in accumulated text
           tool_call = self._adapter.parse_react_response(accumulated_text)
           if tool_call:
               logger.info("ReAct tool call detected: %s", tool_call)
               # Emit as AIMessage with tool_calls metadata (mimic native mode)
               yield AIMessage(
                   content=accumulated_text,
                   additional_kwargs={"tool_calls": [tool_call]},
               )

       async def ainvoke(self, messages: list[BaseMessage], **kwargs):
           """Invoke LLM, parse tool call from response."""
           system_prompt = self._adapter.build_react_system_prompt(self._tools)
           messages_with_sys = [SystemMessage(content=system_prompt)] + messages
           response = await self._underlying.ainvoke(messages_with_sys, **kwargs)
           tool_call = self._adapter.parse_react_response(response.content)
           if tool_call:
               response.additional_kwargs["tool_calls"] = [tool_call]
           return response

       def __getattr__(self, name):
           """Proxy other methods to underlying model."""
           return getattr(self._underlying, name)


   class HybridBoundModel:
       """Tries native tool calling first; on parse error, falls back
       to ReAct. Most useful for models that 'mostly' support native
       tools but occasionally fail (e.g. Claude 3 Opus with complex schemas)."""

       def __init__(self, native_bound, react_bound: ReActBoundModel):
           self._native = native_bound
           self._react = react_bound

       async def astream(self, messages: list[BaseMessage], **kwargs):
           """Try native astream; if no tool_calls in response, fall
           back to ReAct."""
           accumulated = ""
           has_tool_call = False
           async for chunk in self._native.astream(messages, **kwargs):
               accumulated += chunk.content if hasattr(chunk, "content") else str(chunk)
               if chunk.additional_kwargs.get("tool_calls"):
                   has_tool_call = True
               yield chunk
           if not has_tool_call and accumulated:
               # Native didn't produce a tool call; try ReAct
               logger.debug("Native tool call missing — trying ReAct fallback")
               # Note: this re-streams the ReAct response; the first stream
               # is already emitted. For Phase 3 simplicity, we accept this
               # double-streaming; Phase 4 optimization: don't emit native
               # tokens until we know whether it's a tool call.
               async for chunk in self._react.astream(messages, **kwargs):
                   yield chunk

       async def ainvoke(self, messages: list[BaseMessage], **kwargs):
           """Try native ainvoke; if no tool_calls in response, fall
           back to ReAct."""
           response = await self._native.ainvoke(messages, **kwargs)
           if response.additional_kwargs.get("tool_calls"):
               return response
           # Fall back to ReAct
           logger.debug("Native tool call missing — trying ReAct fallback")
           return await self._react.ainvoke(messages, **kwargs)

       def __getattr__(self, name):
           return getattr(self._native, name)


   _adapter: ToolCallingAdapter | None = None


   def get_tool_calling_adapter() -> ToolCallingAdapter:
       global _adapter
       if _adapter is None:
           _adapter = ToolCallingAdapter()
       return _adapter
   ```

2. Тесты в `tests/unit/test_tool_calling_adapter.py`:
   - `test_choose_mode_native_support_returns_hybrid` —
     `choose_mode("openai", "gpt-4o-mini")` returns HYBRID
     (supports_native_tools=True).
   - `test_choose_mode_no_native_returns_react` —
     `choose_mode("ollama", "llama3.1-8b")` returns REACT
     (supports_native_tools=False).
   - `test_choose_mode_explicit_override` —
     `choose_mode("openai", "gpt-4o-mini", explicit_mode=NATIVE)`
     returns NATIVE (override).
   - `test_bind_tools_native_mode_returns_bound_model` — mock
     llm.bind_tools, verify called with tools.
   - `test_bind_tools_react_mode_returns_react_bound_model` —
     verify returns ReActBoundModel instance.
   - `test_bind_tools_hybrid_mode_returns_hybrid_bound_model` —
     verify returns HybridBoundModel instance.
   - `test_parse_react_response_extracts_json_with_fences` —
     text "```json\n{\"tool\": \"web_search\", \"arguments\": {\"query\": \"test\"}}\n```"
     → returns dict.
   - `test_parse_react_response_extracts_json_without_fences` —
     text "I'll use the search tool: {\"tool\": \"web_search\", \"arguments\": {\"query\": \"test\"}}"
     → returns dict.
   - `test_parse_react_response_returns_none_for_no_tool_call` —
     text "Hello world" → returns None.
   - `test_build_react_system_prompt_includes_tool_descriptions` —
     prompt contains "web_search" и "rag_query".
   - Integration (`tests/integration/test_react_e2e.py`):
     mock LLM returns text with JSON tool call, verify
     ReActBoundModel extracts it via additional_kwargs.

Definition of Done:
- `src/llm_client/agent/tool_calling_adapter.py` существует с
  `ToolCallingAdapter` (4 methods: choose_mode, bind_tools,
  build_react_system_prompt, parse_react_response) +
  `ReActBoundModel` + `HybridBoundModel` classes + factory.
- 11+ unit + 1 integration тестов зелёные.
- `ToolCallingAdapter` может работать с любым `BaseChatModel` (Phase
  4 Ollama + Llama support).

Антипаттерны:
- НЕ делай ReActBoundModel extends BaseChatModel — Python's LangChain
  BaseChatModel has many abstract methods; proxy через __getattr__
  проще (как в CacheAwareBoundModel Блок B-4).
- НЕ хардкодь REACT_SYSTEM_PROMPT в коде — вынеси в `prompts/`
  directory (Phase 4 для A/B testability).
- НЕ делай parse_react_response слишком сложным (NLP parsing) —
   regex + JSON.loads достаточно; сложные cases = LLM не выполнил
  prompt, fallback к "no tool call" (LLM отвечает текстом, graph
  продолжает к final_answer).
- НЕ делай HybridBoundModel.astram без double-streaming warning —
   Phase 4 optimization не делать double-stream; Phase 3 принимает
   (simplicity > perf для first pilot).
- НЕ забудь логировать mode choice — критично для ADR-016 pilot
  (ReAct success rate metric).
- НЕ делай mode selection в graph code (if/else в planner node) —
  adapter transparent (Блок D-5 integration).

Связанные ADR:
- Реализует: ADR-016 ToolCallingAdapter (central class).
- Применяет: принцип #1 ТРИЗ (дробление — separate tool description
  от invocation), принцип #13 (наоборот — ReAct as base, native as
  optimization), Standard 3.1.4 (дробление поля).
- Зависит от: Блок D-1 (`ModelCapabilityMatrix`), Блок D-2
  (`ToolCallingMode`), Phase 1 AG-1 (`llm.bind_tools` для native
  mode), Phase 2 H-3 (graph structure preserved).
- Расширяется в: Phase 4 — `case "ollama":` в
  `LLMProviderFactory.create()` разблокируется (Phase 4 full Ollama
  integration via ADR-016 adapter abstraction); custom ReAct
  prompts per model family (Llama vs Mistral have different
  prompt preferences).
- Не затрагивает: ADR-005 (fallback_chain — упраздняется ADR-015),
  ADR-006 (native tool calling — расширяется с ReAct mode; contract
  preserved via additional_kwargs.tool_calls), ADR-010 (checkpoint
  — ToolMessage content сериализуется как обычно).
```

### D-4. `ReactToolCallPromptBuilder` (system prompt для ReAct emulation)

```
Ты — ML/Backend-разработчик LLM Client. Создай
`ReactToolCallPromptBuilder` — dedicated class для построения
ReAct system prompts с tool descriptions. Вынесено из
`ToolCallingAdapter` (Блок D-3) для testability и A/B testability
разных prompt вариантов.

Контекст:
- Блок D-3 `ToolCallingAdapter.build_react_system_prompt` —
  inline implementation. Phase 3 D-4 выделяет в separate class.
- ADR-016 (TRIZ-ANALYSIS.md v1.0.0 §11 драфт): для models без
  native function calling → ReAct emulation auto-enabled.
- ТРИЗ принцип 1 (дробление): separate "tool description"
  construction (per-prompt variant) от "tool invocation" parsing.
- Phase 2 уже имеет `rag_query` tool с detailed description
  (`src/llm_client/agent/tools/rag_query.py`).

Задача:
1. Создай `src/llm_client/agent/react_prompt_builder.py`:
   ```python
   """Builder for ReAct system prompts (ADR-016 Phase 3).

   Constructs prompts with tool descriptions for ReAct-style tool
   calling on models without native function calling (Llama, Mistral
   via Ollama).

   Architecture: ARCHITECT.md v1.3.0 §5.2.4 (Tool Layer).
   TRIZ: principle #1 (separation — tool description vs invocation).
   """
   import json
   import logging
   from typing import Literal

   from langchain_core.tools import BaseTool

   logger = logging.getLogger(__name__)


   PromptVariant = Literal["v1_strict", "v2_tolerant", "v3_cot"]


   PROMPT_VARIANTS = {
       "v1_strict": """You are a helpful assistant with access to the following tools:

   {tool_descriptions}

   When you want to use a tool, output EXACTLY this JSON format on a single line:
   {{"tool": "<tool_name>", "arguments": {{<args>}}}}

   Do not wrap the JSON in markdown fences. Do not add commentary before or after the JSON.
   After the tool executes, you will receive a ToolMessage with the result.

   Available tools:
   {tool_schemas}
   """,

       "v2_tolerant": """You are a helpful assistant with access to the following tools:

   {tool_descriptions}

   When you want to use a tool, you can output the JSON in any of these formats:
   - On a single line: {{"tool": "...", "arguments": {{...}}}}
   - In a markdown JSON block:
   ```json
   {{"tool": "...", "arguments": {{...}}}}
   ```
   - With brief commentary before: "Let me search for that.\n{{"tool": "..."}}"

   Available tools:
   {tool_schemas}
   """,

       "v3_cot": """You are a helpful assistant with access to these tools:

   {tool_descriptions}

   To use a tool, think step by step:
   1. Determine which tool (if any) is needed.
   2. Construct the arguments based on the user's request.
   3. Output the tool call as JSON: {{"tool": "...", "arguments": {{...}}}}

   You may wrap the JSON in markdown fences or output it inline.

   Available tools (with schemas):
   {tool_schemas}
   """,
   }


   class ReactToolCallPromptBuilder:
       """Builds ReAct system prompts with tool descriptions."""

       def __init__(self, variant: PromptVariant = "v1_strict"):
           self._variant = variant

       def build_prompt(self, tools: list[BaseTool]) -> str:
           """Build the ReAct system prompt for the given tools."""
           template = PROMPT_VARIANTS[self._variant]
           return template.format(
               tool_descriptions=self._format_tool_descriptions(tools),
               tool_schemas=self._format_tool_schemas(tools),
           )

       def _format_tool_descriptions(self, tools: list[BaseTool]) -> str:
           lines = []
           for tool in tools:
               desc = tool.description or "(no description)"
               lines.append(f"- {tool.name}: {desc}")
           return "\n".join(lines)

       def _format_tool_schemas(self, tools: list[BaseTool]) -> str:
           schemas = []
           for tool in tools:
               if hasattr(tool, "args_schema") and tool.args_schema:
                   try:
                       schema = tool.args_schema.model_json_schema()
                       schemas.append(f"- {tool.name}: {json.dumps(schema, indent=2)}")
                   except Exception as e:
                       logger.warning("Failed to serialize schema for tool %s: %s",
                                     tool.name, e)
                       schemas.append(f"- {tool.name}: (schema serialization failed)")
               else:
                   schemas.append(f"- {tool.name}: (no schema)")
           return "\n".join(schemas)

       def variant(self) -> PromptVariant:
           return self._variant


   _builder: ReactToolCallPromptBuilder | None = None


   def get_react_prompt_builder(variant: PromptVariant = "v1_strict") -> ReactToolCallPromptBuilder:
       """Singleton factory. Variant can be configured via env
       REACT_PROMPT_VARIANT=v1_strict|v2_tolerant|v3_cot."""
       global _builder
       if _builder is None or _builder.variant() != variant:
           _builder = ReactToolCallPromptBuilder(variant=variant)
       return _builder
   ```

2. Обнови `ToolCallingAdapter` (Блок D-3) — используй
   `ReactToolCallPromptBuilder`:
   ```python
   # in ToolCallingAdapter.build_react_system_prompt
   def build_react_system_prompt(self, tools: list[BaseTool]) -> str:
       from .react_prompt_builder import get_react_prompt_builder
       import os
       variant = os.environ.get("REACT_PROMPT_VARIANT", "v1_strict")
       builder = get_react_prompt_builder(variant)
       return builder.build_prompt(tools)
   ```

3. Тесты в `tests/unit/test_react_prompt_builder.py`:
   - `test_build_prompt_v1_strict_contains_tool_name` — prompt for
     [web_search, rag_query] contains both tool names.
   - `test_build_prompt_v2_tolerant_mentions_markdown_fences` — v2
     prompt contains "```json".
   - `test_build_prompt_v3_cot_mentions_step_by_step` — v3 prompt
     contains "step by step".
   - `test_format_tool_descriptions_includes_description` — desc
     from tool.description is in the prompt.
   - `test_format_tool_schemas_serializes_args_schema` — args_schema
     JSON is in the prompt.
   - `test_format_tool_schemas_handles_missing_schema` — tool without
     args_schema → "(no schema)" in prompt.

Definition of Done:
- `src/llm_client/agent/react_prompt_builder.py` существует с
  `ReactToolCallPromptBuilder` + 3 prompt variants (v1_strict,
  v2_tolerant, v3_cot) + factory.
- `ToolCallingAdapter.build_react_system_prompt` delegates to
  `ReactToolCallPromptBuilder`.
- 6+ unit тестов зелёные.
- Env var `REACT_PROMPT_VARIANT` configurable (default v1_strict).

Антипаттерны:
- НЕ делай prompt variants hardcoded в Python навсегда — Phase 4
  вынеси в `prompts/react_*.txt` (для ops tuning без redeploy).
- НЕ делай v3_cot prompt слишком длинным — Llama 7B context limit;
  prompt overhead must be <500 tokens.
- НЕ забудь handle schema serialization errors gracefully —
  args_schema.model_json_schema() может raises для complex types.

Связанные ADR:
- Реализует: ADR-016 ReAct prompt builder (testability + A/B).
- Применяет: принцип #1 ТРИЗ (дробление — separate prompt
  construction от invocation parsing).
- Зависит от: Блок D-3 (`ToolCallingAdapter` — uses builder).
- Расширяется в: Phase 4 — A/B test framework для prompt variants
  (per model family), per-tool custom descriptions.
- Не затрагивает: ADR-006 (native tool calling — не affected),
  ADR-010 (checkpoint — prompt не serialized).
```

### D-5. Integration в `build_agent_graph` (замена `llm.bind_tools` на `adapter.bind_tools`)

```
Ты — Backend/Agent-разработчик LLM Client. Интегрируй
`ToolCallingAdapter` (Блок D-3) в `build_agent_graph` — замени
прямые `llm.bind_tools(tools)` calls в `planner` node на
`adapter.bind_tools(llm, tools, mode=...)`. Graph transparent —
adapter выбирает mode на основе capability matrix.

Контекст:
- Phase 1 AG-1 + Phase 2 H-3: `build_agent_graph(llm, token, tools,
  rag_pipeline=pipeline)` — `planner` node вызывает
  `llm.bind_tools(tools)`.
- Блок D-3 создал `ToolCallingAdapter.bind_tools(llm, tools, mode)`.
- ADR-016 (TRIZ-ANALYSIS.md v1.0.0 §11 драфт): adapter transparent
  к graph; mode selection automatic.
- ТРИЗ принцип 25 (самообслуживание): graph не знает про adapter;
  adapter "сам" решает, какой mode использовать.

Задача:
1. Расширь `src/llm_client/agent/graph.py` — в `build_agent_graph`
   используй `ToolCallingAdapter`:
   ```python
   # in build_agent_graph (existing Phase 2 + B-5 extension)
   def build_agent_graph(
       llm: BaseChatModel,
       token: CancellationToken,
       tools: list,
       rag_pipeline: RagPipeline | None = None,
       use_semantic_cache: bool | None = None,
       # NEW Phase 3 D-5:
       provider: str | None = None,
       model: str | None = None,
       tool_calling_mode: ToolCallingMode | None = None,
   ) -> CompiledGraph:
       # ... B-5 cache wrapping ...
       # NEW Phase 3 D-5: tool calling adapter
       from .tool_calling_adapter import get_tool_calling_adapter
       adapter = get_tool_calling_adapter()
       # Choose mode: explicit override > capability matrix
       if provider and model:
           mode = adapter.choose_mode(provider, model, tool_calling_mode)
       else:
           mode = tool_calling_mode or ToolCallingMode.HYBRID
       # Replace llm.bind_tools(tools) with adapter.bind_tools(llm, tools, mode)
       llm_with_tools = adapter.bind_tools(llm, tools, mode)
       # ... existing graph construction uses llm_with_tools ...

       logger.info(
           "ToolCallingAdapter mode=%s provider=%s model=%s",
           mode, provider, model,
       )
       # ... rest of graph construction ...
   ```

2. Обнови `src/llm_client/agent/__main__.py` и `agent/service.py` —
   при создании graph передавай `provider` и `model`:
   ```python
   # in agent/__main__.py or service.py
   from .router import get_llm_router, RoutingPolicy
   from .tool_calling_mode import ToolCallingMode

   if settings.llm_router_enabled:
       router = get_llm_router()
       decision = await router.route(policy=RoutingPolicy(settings.llm_router_default_policy))
       llm = await router.create_llm(decision)
       provider, model = decision.provider, decision.model
   else:
       llm = LLMProviderFactory.create(
           provider=settings.llm_provider,
           model=settings.openai_model,
           api_key=settings.openai_api_key,
       )
       provider, model = settings.llm_provider, settings.openai_model

   graph = build_agent_graph(
       llm=llm, token=token, tools=[file_export, web_search, rag_query],
       rag_pipeline=pipeline,
       use_semantic_cache=None,
       provider=provider, model=model,  # NEW Phase 3 D-5
   )
   ```

3. Тесты в `tests/unit/test_graph_tool_calling_adapter.py`:
   - `test_build_agent_graph_with_native_mode` — provider=openai,
     model=gpt-4o-mini → mode=HYBRID (default_for_capabilities),
     llm_with_tools is HybridBoundModel.
   - `test_build_agent_graph_with_react_mode` — provider=ollama,
     model=llama3.1-8b → mode=REACT, llm_with_tools is ReActBoundModel.
   - `test_build_agent_graph_explicit_mode_override` —
     tool_calling_mode=NATIVE passed → mode=NATIVE regardless of
     capability matrix.
   - `test_planner_node_emits_tool_call_event` — graph with
     web_search tool, mock LLM returns native tool_call → SSE event:
     tool_call (Блок H-4 Phase 2 contract preserved).
   - `test_planner_node_react_mode_emits_tool_call_event` — graph
     with react_bound LLM, mock LLM returns text with JSON tool call
     → ReActBoundModel parses, emits SSE event: tool_call.
   - Integration (`tests/integration/test_graph_tool_calling_adapter_e2e.py`):
     real graph + mock LLM, end-to-end tool call through adapter.

Definition of Done:
- `build_agent_graph(llm, token, tools, rag_pipeline=...,
  use_semantic_cache=..., provider=..., model=...,
  tool_calling_mode=...)` signature extended с 3 новыми опциональными
  параметрами.
- `planner` node использует `adapter.bind_tools(llm, tools, mode)`
  вместо `llm.bind_tools(tools)`.
- Mode выбирается автоматически через capability matrix (HYBRID для
  native-supporting models, REACT для non-native).
- SSE event `tool_call` (Блок H-4 Phase 2 contract) preserved (native
  mode direct emission; react mode ReActBoundModel добавляет
  additional_kwargs.tool_calls, graph emits tool_call event from
  there).
- 5+ unit + 1 integration тестов зелёные.
- Существующие тесты Phase 2 (`test_graph_cancel_inflight.py`,
  `test_rag_query.py`) — не регрессируют (default behavior unchanged
  если provider/model=None, tool_calling_mode=None → HYBRID default).

Антипаттерны:
- НЕ делай graph-level явный mode check (if/else в planner code) —
  adapter transparent (ТРИЗ принцип 25).
- НЕ передавай `tool_calling_mode` как обязательный — None = автоматический
  выбор через capability matrix (для back-compat).
- НЕ забудь логировать mode choice — критично для ADR-016 pilot
  (ReAct success rate metric).
- НЕ делай provider/model mandatory — None = HYBRID default (для
  backward compat с existing tests).

Связанные ADR:
- Реализует: ADR-016 graph integration.
- Применяет: принцип #25 ТРИЗ (самообслуживание — graph не знает
  про adapter; adapter transparent), ADR-006 (native tool calling
  preserved; ReAct — extension via additional_kwargs).
- Зависит от: Блок D-3 (`ToolCallingAdapter.bind_tools`), Блок D-1
  (`ModelCapabilityMatrix` для mode selection), Phase 1 AG-1 +
  Phase 2 H-3 (graph structure preserved).
- Расширяется в: Phase 4 — Ollama case в `LLMProviderFactory.create()`
  разблокируется; graph с `provider="ollama", model="llama3.1-8b"`
  → REACT mode auto-selected; full local-LLM pipeline works end-to-end.
- Не затрагивает: ADR-010 (checkpoint — graph state сериализуется
  без изменений), ADR-013 (cancel — CancellationToken работает
  через adapter), ADR-014 (operational stream — TokenUsageTracker
  on underlying llm; mode label в metric).
```

### D-6. Pilot на Ollama + Llama 3.1 (ReAct success rate ≥80%)

```
Ты — ML/Backend-разработчик LLM Client. Подготовь pilot test для
ADR-016 на Ollama + Llama 3.1 — ReAct-эмуляция tool calling.
Pilot criterion: success rate ≥80% (vs native ≥95%).

Контекст:
- ADR-016 (TRIZ-ANALYSIS.md v1.0.0 §11 драфт): pilot на Ollama +
  Llama 3.1 successfully calls tools through ReAct emulation.
- Блок D-3 создал `ToolCallingAdapter` + `ReActBoundModel`.
- Блок D-5 integrated adapter в graph.
- ROADMAP §14.1 pilot: success rate ≥80% vs native ≥95%. Rollback:
  success <60% OR false capability matrix entries cause runtime errors.
- `case "ollama":` в `LLMProviderFactory.create()` всё ещё raises
  NotImplementedError (Phase 4 ADR-016 full integration — pilot
  obходит через manual ChatOllama instance).
- ТРИЗ принцип 13 (наоборот): ReAct as base mode, native as
  optimization; pilot validates ReAct viability.

Задача:
1. Создай `scripts/pilot_ollama_react.py`:
   ```python
   """Pilot test: ADR-016 ReAct emulation on Ollama + Llama 3.1.

   Bypasses LLMProviderFactory.create("ollama") (Phase 4 unblock);
   uses ChatOllama directly from langchain-ollama (or
   langchain-community fallback).

   Pilot criteria (ROADMAP §14.1):
   - ReAct success rate >=80% (vs native >=95%)
   Rollback: success <60% OR false capability matrix entries.

   Usage:
       python scripts/pilot_ollama_react.py --ollama-url http://localhost:11434 --model llama3.1:8b
   """
   import argparse
   import asyncio
   import json
   import logging
   from dataclasses import dataclass

   logger = logging.getLogger(__name__)


   @dataclass
   class PilotResult:
       total_tests: int
       successes: int
       failures: int
       success_rate: float
       failure_reasons: dict[str, int]
       sample_size_warning: bool  # True if <20 tests

       def pilot_pass(self) -> bool:
           return self.success_rate >= 0.80 and not self.sample_size_warning

       def rollback_required(self) -> bool:
           return self.success_rate < 0.60


   async def run_pilot(ollama_url: str, model: str) -> PilotResult:
       """Run pilot: send N tool-calling prompts to Ollama + Llama 3.1
       via ReActBoundModel; verify tool call extracted correctly."""
       try:
           from langchain_ollama import ChatOllama
       except ImportError:
           from langchain_community.chat_models import ChatOllama

       from llm_client.agent.tool_calling_adapter import ToolCallingAdapter, ToolCallingMode
       from llm_client.agent.tools.web_search import web_search
       from llm_client.agent.tools.rag_query import rag_query
       from llm_client.agent.tools.file_export import file_export

       llm = ChatOllama(
           base_url=ollama_url,
           model=model,
           temperature=0.0,
       )
       adapter = ToolCallingAdapter()
       tools = [web_search, rag_query, file_export]

       # Force REACT mode (pilot — don't rely on capability matrix)
       bound = adapter.bind_tools(llm, tools, ToolCallingMode.REACT)

       test_cases = [
           {"query": "Search the web for python asyncio best practices",
            "expected_tool": "web_search"},
           {"query": "Find RAG documents about climate change",
            "expected_tool": "rag_query"},
           {"query": "Save my notes to a file",
            "expected_tool": "file_export"},
           # Add more test cases as needed (10+ for statistical significance)
       ]

       successes = 0
       failures = 0
       failure_reasons: dict[str, int] = {}
       for test in test_cases:
           try:
               from langchain_core.messages import HumanMessage
               response = await bound.ainvoke([HumanMessage(content=test["query"])])
               tool_calls = response.additional_kwargs.get("tool_calls", [])
               if not tool_calls:
                   failures += 1
                   failure_reasons["no_tool_call_detected"] = failure_reasons.get("no_tool_call_detected", 0) + 1
                   continue
               tc = tool_calls[0]
               if tc.get("tool") == test["expected_tool"]:
                   successes += 1
               else:
                   failures += 1
                   reason = f"wrong_tool: expected {test['expected_tool']}, got {tc.get('tool')}"
                   failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
           except Exception as e:
               failures += 1
               reason = f"exception: {type(e).__name__}: {str(e)[:100]}"
               failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

       total = len(test_cases)
       success_rate = successes / total if total > 0 else 0.0
       return PilotResult(
           total_tests=total,
           successes=successes,
           failures=failures,
           success_rate=success_rate,
           failure_reasons=failure_reasons,
           sample_size_warning=total < 20,
       )


   def main():
       parser = argparse.ArgumentParser()
       parser.add_argument("--ollama-url", default="http://localhost:11434")
       parser.add_argument("--model", default="llama3.1:8b")
       args = parser.parse_args()

       result = asyncio.run(run_pilot(args.ollama_url, args.model))
       print(f"=== ADR-016 Pilot: Ollama + {args.model} (ReAct) ===")
       print(f"Total tests: {result.total_tests}")
       print(f"Successes: {result.successes}")
       print(f"Failures: {result.failures}")
       print(f"Success rate: {result.success_rate:.1%}")
       print(f"Failure reasons: {result.failure_reasons}")
       print()
       if result.rollback_required():
           print("❌ ROLLBACK REQUIRED (success rate <60%)")
       elif result.pilot_pass():
           print("✅ PILOT PASS — ADR-016 Approved (success rate >=80%)")
       else:
           print(f"⚠️  PILOT PARTIAL — success rate {result.success_rate:.1%} (need >=80%)")

   if __name__ == "__main__":
       main()
   ```

2. Тесты в `tests/unit/test_pilot_ollama_react.py`:
   - `test_pilot_result_pass_at_80pct` — 8/10 successes, no sample
     warning → pilot_pass() True.
   - `test_pilot_result_rollback_at_50pct` — 5/10 → rollback_required()
     True.
   - `test_pilot_result_partial_at_70pct` — 7/10 → pilot_pass False,
     rollback False (between 60 and 80).
   - `test_pilot_result_sample_size_warning` — 5 tests (<20) →
     sample_size_warning=True, pilot_pass False (insufficient data).

Definition of Done:
- `scripts/pilot_ollama_react.py` создан с `run_pilot` + `PilotResult`
  + `main()` CLI.
- CLI: `python scripts/pilot_ollama_react.py --ollama-url
  http://localhost:11434 --model llama3.1:8b` → prints summary.
- 4+ unit тестов зелёные.
- Manual run on local Ollama + Llama 3.1: success rate measured;
  if >=80% → ADR-016 Approved; if <60% → rollback; if 60-80% →
  partial (tune ReAct prompt in D-4, re-run).

Антипаттерны:
- НЕ делай pilot test с manual Ollama API call — используй
  ChatOllama (langchain-ollama or langchain-community fallback);
  integration with existing `BaseChatModel` interface.
- НЕ хардкодь test cases太少 — minimum 10 (preferably 20+) для
  statistical significance.
- НЕ делай pilot test blocking CI — manual run on local Ollama
  instance (Ollama requires local GPU/CPU; CI не имеет Ollama).
- НЕ делай pilot pass criterion 95% — ReAct emulation всегда ниже
  native; 80% realistic per ADR-016 design.

Связанные ADR:
- Реализует: ADR-016 pilot framework (критично для Approved per
  ROADMAP §14.1).
- Применяет: принцип #13 ТРИЗ (наоборот — ReAct as base, native as
  optimization; pilot validates ReAct viability).
- Зависит от: Блок D-3 (`ToolCallingAdapter` + `ReActBoundModel`),
  Блок D-5 (graph integration, but pilot uses adapter standalone),
  `langchain-ollama` (add to pyproject.toml optional deps).
- Расширяется в: Phase 4 — full Ollama case в
  `LLMProviderFactory.create()` (pilot validates that it will work
  when fully integrated); A/B test framework for ReAct prompt
  variants (D-4 v1_strict vs v2_tolerant vs v3_cot).
- Не затрагивает: ADR-015 (router — separate pilot), ADR-011
  (semantic cache — separate pilot), ADR-004 (MCP server —
  separate pilot).
```

---

## 5. Блок H. ADR-004 ускорение: MCP Server Mode (Preview)

Блок H реализует ADR-004 ускорение (расширение существующего ADR-004 MCP Client-only на Server mode preview) — LLM Client exposes свои capabilities (`rag_query`, `file_export`, `web_search`, `agent_run`) как MCP tools для external clients (IDE, bots, Confluence). Transport: SSE в preview (production-ready в Phase 6 с WebSocket + OAuth 2.0 + signed manifests ADR-019).

Пилотные метрики (ROADMAP §14.1): LLM Client в MCP Server mode отвечает на `list_tools` и `call_tool` от external MCP client.

TRIZ: закон 4.6 (переход в надсистему — LLM Client становится MCP server для других клиентов); Standard 3.2.1 (переход в надсистему); закон 4.9 (динамизация — preview-mode gradual rollout).

---

### H-1. `McpServer` class (FastAPI routes: list_tools, call_tool, SSE streaming)

```
Ты — Backend-разработчик LLM Client. Создай `McpServer` class —
экспонирует LLM Client capabilities как MCP tools через FastAPI
routes (`GET /mcp/tools`, `POST /mcp/tools/{name}`, SSE endpoint
для streaming tool results). Это preview для ADR-004 ускорение
(Phase 6 — full MCP Server с WebSocket + OAuth 2.0).

Контекст:
- ADR-004 (расширение, TRIZ-ANALYSIS.md v1.0.0 §4.6): LLM Client
  экспонирует capabilities как MCP tools.
- ADR-007 (Phase 1): SSE streaming — переиспользуется как transport
  (Phase 6 — optional WebSocket).
- Phase 2 AG-5/AG-6: `web_search`, `rag_query`, `file_export` tools
  уже существуют как `@tool`-decorated functions в
  `src/llm_client/agent/tools/`.
- ARCHITECT.md v1.3.0 §5.2.6 (MCP Client Layer) — extended с MCP
  Server preview.
- `mcp` Python SDK уже в `pyproject.toml` (declared, не
  импортирован — Phase 3 первый use).
- ТРИЗ Standard 3.2.1 (переход в надсистему): LLM Client становится
  MCP server для других клиентов.
- ТРИЗ закон 4.6 (переход в надсистему): LLM Client теперь part of
  надсистема external clients ↔ MCP Server ↔ Tools.
- ТРИЗ закон 4.9 (динамизация): preview-mode gradual rollout (SSE
  transport сейчас, WebSocket optional в Phase 6).

Задача:
1. Создай `src/llm_client/mcp/__init__.py` (новый subpackage) +
   `src/llm_client/mcp/server.py`:
   ```python
   """MCP Server preview (ADR-004 ускорение Phase 3).

   Exposes LLM Client capabilities (rag_query, file_export,
   web_search, agent_run) as MCP tools to external clients via
   FastAPI routes + SSE transport.

   Full MCP Server in Phase 6: WebSocket transport + OAuth 2.0 +
   signed manifests ADR-019.

   Architecture: ARCHITECT.md v1.3.0 §5.2.6.
   TRIZ: Standard 3.2.1 (transition to nad-system); law 4.6
   (transition to nad-system); law 4.9 (dynamization — gradual
   rollout).
   """
   import asyncio
   import json
   import logging
   from typing import Any
   from uuid import UUID

   from fastapi import APIRouter, FastAPI, HTTPException
   from fastapi.responses import StreamingResponse, Response

   logger = logging.getLogger(__name__)


   class McpServer:
       """MCP Server preview. Mounts /mcp/* routes on existing
       FastAPI app (Phase 1 AG-0)."""

       def __init__(self, app: FastAPI) -> None:
           self._app = app
           self._tools_registry: dict[str, dict] = {}  # name -> {tool, schema, handler}
           self._router = APIRouter(prefix="/mcp", tags=["mcp"])
           self._register_routes()

       def register_tool(self, name: str, description: str,
                          args_schema: dict, handler) -> None:
           """Register a tool as MCP-callable. handler is async
           callable taking **args, returning dict."""
           self._tools_registry[name] = {
               "name": name,
               "description": description,
               "args_schema": args_schema,
               "handler": handler,
           }
           logger.info("MCP tool registered: %s", name)

       def _register_routes(self) -> None:
           @self._router.get("/tools")
           async def list_tools() -> dict:
               """MCP list_tools: returns array of tool descriptions."""
               return {
                   "tools": [
                       {
                           "name": t["name"],
                           "description": t["description"],
                           "args_schema": t["args_schema"],
                       }
                       for t in self._tools_registry.values()
                   ]
               }

           @self._router.post("/tools/{name}")
           async def call_tool(name: str, args: dict) -> dict:
               """MCP call_tool: invokes named tool with args.
               Returns {result, error?}."""
               if name not in self._tools_registry:
                   raise HTTPException(404, f"Tool not found: {name}")
               entry = self._tools_registry[name]
               try:
                   result = await entry["handler"](**args)
                   return {"result": result, "error": None}
               except Exception as e:
                   logger.exception("MCP tool %s failed", name)
                   return {"result": None, "error": str(e)}

           @self._router.get("/tools/{name}/stream")
           async def call_tool_streaming(name: str, args_json: str) -> StreamingResponse:
               """SSE streaming endpoint для tool results that stream
               (e.g. agent_run). args passed as JSON query param
               (limited to 4KB; for large args use POST /tools/{name}
               with non-streaming response)."""
               if name not in self._tools_registry:
                   raise HTTPException(404, f"Tool not found: {name}")
               try:
                   args = json.loads(args_json)
               except json.JSONDecodeError as e:
                   raise HTTPException(400, f"Invalid args JSON: {e}")

               entry = self._tools_registry[name]
               async def event_stream():
                   try:
                       # If handler is async generator, stream results
                       if asyncio.isasyncgenfunction(entry["handler"]):
                           async for chunk in entry["handler"](**args):
                               yield f"data: {json.dumps(chunk)}\n\n"
                       else:
                           # Single result, emit as one SSE event
                           result = await entry["handler"](**args)
                           yield f"data: {json.dumps(result)}\n\n"
                   except Exception as e:
                       logger.exception("MCP streaming tool %s failed", name)
                       error_event = {"error": str(e)}
                       yield f"data: {json.dumps(error_event)}\n\n"
               return StreamingResponse(
                   event_stream(),
                   media_type="text/event-stream",
               )

           @self._router.get("/health")
           async def health() -> dict:
               """Health check: returns server status."""
               return {
                   "status": "ok",
                   "tools_count": len(self._tools_registry),
                   "tools": list(self._tools_registry.keys()),
               }

       def mount(self) -> None:
           """Mount /mcp routes on the FastAPI app."""
           self._app.include_router(self._router)
           logger.info(
               "MCP Server preview mounted at /mcp/* with %d tools",
               len(self._tools_registry),
           )
   ```

2. Создай `src/llm_client/mcp/exposed_tools.py` — регистрирует
   LLM Client capabilities как MCP tools:
   ```python
   """Registers LLM Client tools as MCP-callable (H-1)."""
   import logging
   from typing import Any

   from ..agent.tools.rag_query import rag_query, RagQueryArgs
   from ..agent.tools.file_export import file_export, FileExportArgs
   from ..agent.tools.web_search import web_search, WebSearchArgs
   from .server import McpServer

   logger = logging.getLogger(__name__)


   async def rag_query_handler(query: str, top_k: int = 5) -> dict:
       """MCP-callable wrapper for rag_query tool."""
       result = await rag_query.ainvoke({"query": query, "top_k": top_k})
       return result


   async def file_export_handler(filename: str, content: str,
                                  content_type: str = "text/plain") -> dict:
       """MCP-callable wrapper for file_export tool."""
       result = await file_export.ainvoke({
           "filename": filename,
           "content": content,
           "content_type": content_type,
       })
       return result


   async def web_search_handler(query: str, max_results: int = 5) -> list:
       """MCP-callable wrapper for web_search tool."""
       result = await web_search.ainvoke({"query": query, "max_results": max_results})
       return result


   def register_exposed_tools(server: McpServer) -> None:
       """Register all LLM Client tools with the McpServer."""
       server.register_tool(
           name="rag_query",
           description="Query the LLM Client's RAG knowledge base",
           args_schema=RagQueryArgs.model_json_schema(),
           handler=rag_query_handler,
       )
       server.register_tool(
           name="file_export",
           description="Export content as a downloadable file",
           args_schema=FileExportArgs.model_json_schema(),
           handler=file_export_handler,
       )
       server.register_tool(
           name="web_search",
           description="Search the web via Tavily API",
           args_schema=WebSearchArgs.model_json_schema(),
           handler=web_search_handler,
       )
       logger.info("Registered 3 MCP exposed tools: rag_query, file_export, web_search")
   ```

3. Расширь `src/llm_client/agent/service.py` — на startup, mount
   MCP Server:
   ```python
   # in agent/service.py (existing Phase 1 AG-0 FastAPI app)
   from ..mcp.server import McpServer
   from ..mcp.exposed_tools import register_exposed_tools

   @app.on_event("startup")
   async def startup_mcp_server():
       """Mount MCP Server preview (Phase 3 ADR-004 ускорение)."""
       if get_settings().mcp_server_enabled:
           server = McpServer(app)
           register_exposed_tools(server)
           server.mount()
           logger.info("MCP Server preview enabled at /mcp/*")
   ```

4. Добавь Settings для MCP Server:
   ```python
   # in src/llm_client/config.py
   mcp_server_enabled: bool = False  # default OFF (preview, not for production)
   mcp_server_transport: str = "sse"  # sse (Phase 3); websocket (Phase 6)
   ```

5. Тесты в `tests/unit/test_mcp_server.py`:
   - `test_list_tools_returns_registered_tools` — register 3 tools,
     `GET /mcp/tools` returns array with 3 entries.
   - `test_call_tool_invokes_handler` — `POST /mcp/tools/rag_query`
     with `{query: "test"}` → handler called, returns result.
   - `test_call_tool_unknown_returns_404` — `POST /mcp/tools/unknown`
     → 404.
   - `test_call_tool_handler_error_returns_error_dict` — mock
     handler raises → response `{error: "..."}`, not 500.
   - `test_streaming_endpoint_emits_sse_events` — `GET
     /mcp/tools/agent_run/stream?args_json=...` → SSE event stream.
   - `test_health_endpoint_returns_status` — `GET /mcp/health` →
     `{status: ok, tools_count: 4}`.
   - Integration (`tests/integration/test_mcp_server_e2e.py`):
     real FastAPI test client, full end-to-end MCP call.

Definition of Done:
- `src/llm_client/mcp/server.py` существует с `McpServer` (5 routes:
  list_tools, call_tool, call_tool_streaming, health + register_tool).
- `src/llm_client/mcp/exposed_tools.py` регистрирует 4 MCP tools
  (rag_query, file_export, web_search, agent_run).
- `agent/service.py` startup hook монтирует MCP Server если
  `mcp_server_enabled=True`.
- Settings: `mcp_server_enabled`, `mcp_server_transport`.
- 7+ unit + 1 integration тестов зелёные.
- Manual test: `curl http://localhost:8000/mcp/tools` returns list of
  4 tools; `curl -X POST http://localhost:8000/mcp/tools/web_search
  -d '{"query":"python asyncio","max_results":3}'` returns search
  results.

Антипаттерны:
- НЕ делай MCP Server с own FastAPI app — mount routes на existing
  `agent-service` app (Phase 1 AG-0).
- НЕ хардкодь tools в McpServer — `register_tool()` method for
  extensibility.
- НЕ делай streaming endpoint с POST body — SSE transport =
  GET request с query param (limit 4KB; для big args use POST
  non-streaming).
- НЕ забудь `/mcp/health` endpoint — критично для external client
  discovery (external client probes /mcp/health before /mcp/tools).
- НЕ делай auth в Phase 3 preview — full auth (OAuth 2.0) в Phase 6;
  Phase 3 internal trust boundary (deploy behind VPN).

Связанные ADR:
- Реализует: ADR-004 ускорение preview (MCP Server mode).
- Применяет: ADR-007 (SSE transport — reused), закон 4.6 ТРИЗ
  (переход в надсистему), Standard 3.2.1 (переход в надсистему),
  закон 4.9 (динамизация — preview-mode).
- Зависит от: Phase 1 AG-0 (FastAPI app — mount point), Phase 2
  AG-5/AG-6 (existing @tool functions — exposed via MCP), Phase 1
  ADR-013 (FastAPI routes pattern).
- Расширяется в: Phase 6 — WebSocket transport (optional, с SSE
  fallback), OAuth 2.0 auth (через host application), signed
  manifests ADR-019 (tools signed by LLM Client operator).
- Не затрагивает: ADR-010 (checkpoint — MCP Server не depends on
  checkpoint), ADR-013 (cancel — MCP Server не emits cancel events),
  ADR-014 (operational stream — MCP calls логируются отдельно, не
  в operational stream).
```

### H-2. `ExposedToolRegistry` (registers rag_query, file_export, web_search, agent_run)

```
Ты — Backend-разработчик LLM Client. Создай `ExposedToolRegistry` —
central registry для MCP-exposed tools, отделяющий registration logic
от McpServer (H-1) для testability и extensibility.

Контекст:
- Блок H-1 создал `McpServer.register_tool(name, description,
  args_schema, handler)`.
- Блок H-1 `exposed_tools.py` регистрирует 4 tools inline. Phase 3
  H-2 формализует в registry pattern.
- ADR-004 ускорение (TRIZ §4.6): LLM Client exposes own capabilities
  как MCP tools.
- ТРИЗ принцип 1 (дробление): separate tool registration logic от
  tool execution logic (McpServer).

Задача:
1. Создай `src/llm_client/mcp/tool_registry.py`:
   ```python
   """Registry for MCP-exposed tools (ADR-004 ускорение Phase 3).

   Central registry: maps tool name -> {description, args_schema,
   handler}. McpServer (H-1) reads from this registry.

   Architecture: ARCHITECT.md v1.3.0 §5.2.6.
   TRIZ: principle #1 (separation — registration vs execution).
   """
   import logging
   from dataclasses import dataclass
   from typing import Any, Awaitable, Callable

   logger = logging.getLogger(__name__)


   @dataclass
   class ExposedTool:
       name: str
       description: str
       args_schema: dict
       handler: Callable[..., Awaitable[Any]]


   class ExposedToolRegistry:
       """Central registry for MCP-exposed tools."""

       def __init__(self) -> None:
           self._tools: dict[str, ExposedTool] = {}

       def register(self, tool: ExposedTool) -> None:
           """Register an ExposedTool. Logs warning if overwriting."""
           if tool.name in self._tools:
               logger.warning("Overwriting MCP tool: %s", tool.name)
           self._tools[tool.name] = tool
           logger.info("MCP tool registered: %s", tool.name)

       def register_all(self, tools: list[ExposedTool]) -> None:
           """Register multiple tools."""
           for tool in tools:
               self.register(tool)

       def get(self, name: str) -> ExposedTool | None:
           """Get ExposedTool by name, or None if not registered."""
           return self._tools.get(name)

       def list_tools(self) -> list[ExposedTool]:
           """List all registered tools."""
           return list(self._tools.values())

       def list_names(self) -> list[str]:
           """List all registered tool names."""
           return list(self._tools.keys())

       def unregister(self, name: str) -> bool:
           """Unregister a tool. Returns True if was registered."""
           if name in self._tools:
               del self._tools[name]
               logger.info("MCP tool unregistered: %s", name)
               return True
           return False


   _registry: ExposedToolRegistry | None = None


   def get_exposed_tool_registry() -> ExposedToolRegistry:
       global _registry
       if _registry is None:
           _registry = ExposedToolRegistry()
       return _registry


   def register_default_tools() -> None:
       """Register the 4 default MCP-exposed tools (rag_query,
       file_export, web_search, agent_run). Called on startup if
       mcp_server_enabled=True."""
       from ..agent.tools.rag_query import rag_query, RagQueryArgs
       from ..agent.tools.file_export import file_export, FileExportArgs
       from ..agent.tools.web_search import web_search, WebSearchArgs

       registry = get_exposed_tool_registry()

       # rag_query
       async def rag_query_handler(query: str, top_k: int = 5) -> dict:
           return await rag_query.ainvoke({"query": query, "top_k": top_k})

       registry.register(ExposedTool(
           name="rag_query",
           description="Query the LLM Client's RAG knowledge base",
           args_schema=RagQueryArgs.model_json_schema(),
           handler=rag_query_handler,
       ))

       # file_export
       async def file_export_handler(filename: str, content: str,
                                      content_type: str = "text/plain") -> dict:
           return await file_export.ainvoke({
               "filename": filename,
               "content": content,
               "content_type": content_type,
           })

       registry.register(ExposedTool(
           name="file_export",
           description="Export content as a downloadable file",
           args_schema=FileExportArgs.model_json_schema(),
           handler=file_export_handler,
       ))

       # web_search
       async def web_search_handler(query: str, max_results: int = 5) -> list:
           return await web_search.ainvoke({
               "query": query, "max_results": max_results,
           })

       registry.register(ExposedTool(
           name="web_search",
           description="Search the web via Tavily API",
           args_schema=WebSearchArgs.model_json_schema(),
           handler=web_search_handler,
       ))

       # agent_run (async generator — streamed via GET /tools/{name}/stream)
       from .agent_run import AgentRunArgs, agent_run_handler

       registry.register(ExposedTool(
           name="agent_run",
           description="Run a long-running agent task and stream progress events (SSE)",
           args_schema=AgentRunArgs.model_json_schema(),
           handler=agent_run_handler,
       ))

       logger.info("Registered 4 default MCP-exposed tools")
   ```

2. Обнови `McpServer` (Блок H-1) — используй registry:
   ```python
   # in McpServer (server.py)
   def __init__(self, app: FastAPI, registry: ExposedToolRegistry | None = None) -> None:
       self._app = app
       from .tool_registry import get_exposed_tool_registry
       self._registry = registry or get_exposed_tool_registry()
       # ...

   def list_tools(self) -> list[dict]:
       """Returns list of tool descriptions for /mcp/tools."""
       return [
           {"name": t.name, "description": t.description,
            "args_schema": t.args_schema}
           for t in self._registry.list_tools()
       ]
   ```

3. Обнови `agent/service.py` startup:
   ```python
   @app.on_event("startup")
   async def startup_mcp_server():
       if get_settings().mcp_server_enabled:
           from ..mcp.tool_registry import register_default_tools, get_exposed_tool_registry
           from ..mcp.server import McpServer
           register_default_tools()
           server = McpServer(app, get_exposed_tool_registry())
           server.mount()
   ```

4. Тесты в `tests/unit/test_exposed_tool_registry.py`:
   - `test_register_tool_adds_to_registry` — register 1 tool,
     `list_tools` returns 1.
   - `test_register_all_multiple_tools` — register 3 tools at once.
   - `test_get_tool_by_name` — `get("rag_query")` returns ExposedTool.
   - `test_get_unknown_returns_none` — `get("unknown")` returns None.
   - `test_unregister_removes_tool` — register then unregister →
     `list_tools` returns 0.
   - `test_unregister_unknown_returns_false` — unregister non-existent
     → False.
   - `test_register_default_tools_registers_4` — call
     `register_default_tools()`, verify 4 tools (rag_query,
     file_export, web_search, agent_run).
   - Integration (`tests/integration/test_mcp_server_with_registry.py`):
     McpServer + registry, end-to-end /mcp/tools returns 4 tools.

Definition of Done:
- `src/llm_client/mcp/tool_registry.py` существует с `ExposedTool`
  dataclass + `ExposedToolRegistry` (4 methods: register, get,
  list_tools, unregister) + factory.
- `register_default_tools()` регистрирует 4 default MCP tools (включая `agent_run`).
- `McpServer` (H-1) читает из registry (не inline dictionary).
- 7+ unit + 1 integration тестов зелёные.

Антипаттерны:
- НЕ делай registry as singleton только — expose `register_default_tools()`
  function для test setup (mock tools for testing).
- НЕ хардкодь handlers в registry class — async functions outside
  class for clean test mocking.
- НЕ делай registry global mutable without thread-safety — Python
  single-threaded async, but asyncio.Lock if Phase 4 concurrent
  registration is needed.

Связанные ADR:
- Реализует: ADR-004 ускорение registry pattern.
- Применяет: принцип #1 ТРИЗ (дробление — registration vs execution).
- Зависит от: Блок H-1 (`McpServer`), Phase 2 AG-5/AG-6 (existing
  @tool functions).
- Расширяется в: Phase 4 — `agent_run` tool (executes full agent
  graph via MCP); custom tools via plugin system (ADR-009 Phase 4
  plugin registry).
- Не затрагивает: ADR-010, ADR-013, ADR-014 (MCP registry independent).
```

### H-3. Transport: SSE per ADR-007 (reuses `format_sse_event` helper)

```
Ты — Backend-разработчик LLM Client. Реализуй SSE transport для MCP
Server, переиспользуя `format_sse_event` helper из Phase 1 AG-3.
Это соответствует ADR-007 (SSE streaming как единственный Phase 3
transport; WebSocket optional в Phase 6).

Контекст:
- Блок H-1 создал `call_tool_streaming` SSE endpoint
  (`GET /mcp/tools/{name}/stream`).
- Phase 1 AG-3 создал `format_sse_event(event_type, data)` helper
  для SSE events (used in `/sessions/{id}/stream` endpoint).
- ADR-007 (Phase 1): SSE как единственный streaming transport.
- ADR-004 ускорение (Phase 3): MCP Server preview использует SSE
  transport.
- ТРИЗ принцип 25 (самообслуживание): MCP Server переиспользует
  SSE helper, не переопределяет.

Задача:
1. Создай `src/llm_client/mcp/sse_transport.py`:
   ```python
   """SSE transport for MCP Server (ADR-004 ускорение Phase 3).

   Reuses format_sse_event helper from Phase 1 AG-3 (ADR-007).
   """
   import asyncio
   import json
   import logging
   from typing import Any, AsyncIterator

   logger = logging.getLogger(__name__)


   async def format_sse_event(event_type: str, data: Any) -> str:
       """Format one SSE event. Reused from Phase 1 AG-3.

       Args:
           event_type: SSE event field (e.g. "tool_call", "tool_result").
           data: dict to JSON-serialize.
       Returns:
           "event: <type>\ndata: <json>\n\n"
       """
       payload = json.dumps(data) if not isinstance(data, str) else data
       return f"event: {event_type}\ndata: {payload}\n\n"


   async def stream_tool_result(streaming_handler) -> AsyncIterator[str]:
       """Wraps async generator handler into SSE event stream.
       Yields formatted SSE events."""
       try:
           async for chunk in streaming_handler:
               event = await format_sse_event("tool_result", chunk)
               yield event
       except Exception as e:
           logger.exception("SSE tool streaming failed")
           error_event = await format_sse_event("error", {"message": str(e)})
           yield error_event
       # Always emit done event
       done_event = await format_sse_event("done", {})
       yield done_event
   ```

2. Обнови `McpServer.call_tool_streaming` (Блок H-1) — используй
   `stream_tool_result` helper:
   ```python
   # in McpServer (server.py)
   @self._router.get("/tools/{name}/stream")
   async def call_tool_streaming(name: str, args_json: str) -> StreamingResponse:
       # ... existing arg parsing ...
       entry = self._tools_registry[name]
       from .sse_transport import stream_tool_result
       async def streaming_handler():
           if asyncio.isasyncgenfunction(entry["handler"]):
               async for chunk in entry["handler"](**args):
                   yield chunk
           else:
               result = await entry["handler"](**args)
               yield result
       return StreamingResponse(
           stream_tool_result(streaming_handler()),
           media_type="text/event-stream",
       )
   ```

3. Тесты в `tests/unit/test_mcp_sse_transport.py`:
   - `test_format_sse_event_emits_correct_format` — `format_sse_event
     ("tool_result", {"data": 1})` returns "event: tool_result\ndata:
     {\"data\": 1}\n\n".
   - `test_stream_tool_result_emits_done_event` — handler yields 3
     chunks → stream emits 3 tool_result events + 1 done event.
   - `test_stream_tool_result_emits_error_on_exception` — handler
     raises → stream emits error event + done event.
   - `test_stream_tool_result_with_single_result` — non-async-gen
     handler → stream emits 1 tool_result event + done event.

Definition of Done:
- `src/llm_client/mcp/sse_transport.py` существует с
  `format_sse_event` (reused from Phase 1) + `stream_tool_result`
  async generator.
- `McpServer.call_tool_streaming` использует `stream_tool_result`.
- SSE events: `tool_result` (per chunk), `error` (on exception),
  `done` (always emitted at end).
- 4+ unit тестов зелёные.

Антипаттерны:
- НЕ переопределяй `format_sse_event` — переиспользуй Phase 1 AG-3
  helper (или дублируй если Phase 1 helper устарел, но логируй
  deprecation).
- НЕ делай SSE events без `event:` field — bare `data:` events не
  distinguishable для clients.

Связанные ADR:
- Реализует: ADR-004 ускорение SSE transport (через ADR-007).
- Применяет: ADR-007 (SSE — reused helper), принцип #25 ТРИЗ
  (самообслуживание — MCP Server не переопределяет SSE).
- Зависит от: Phase 1 AG-3 (`format_sse_event` pattern), Блок H-1
  (`McpServer.call_tool_streaming`).
- Расширяется в: Phase 6 — WebSocket transport (optional, с SSE
  fallback для clients без WebSocket support).
- Не затрагивает: ADR-010 (checkpoint — SSE transport не depends
  on checkpoint), ADR-013 (cancel).
```

### H-4. Probe / health-check от external MCP client

```
Ты — QA/Backend-разработчик LLM Client. Создай probe script для
проверки MCP Server preview — external MCP client (использующий `mcp`
Python SDK) вызывает `list_tools` и `call_tool`, verifies response.

Контекст:
- Блок H-1 создал MCP Server с routes `/mcp/tools` (list) и
  `/mcp/tools/{name}` (call).
- Блок H-2 создал registry с 3 default tools.
- `mcp` Python SDK уже в `pyproject.toml`.
- ROADMAP §14.1 ADR-004 preview pilot: LLM Client в MCP Server
  mode отвечает на `list_tools` и `call_tool` от external MCP client.
- ТРИЗ закон 4.6 (переход в надсистему): external client — это
  надсистема; probe validates integration.

Задача:
1. Создай `scripts/probe_mcp_server.py`:
   ```python
   """Probe MCP Server preview (ADR-004 ускорение Phase 3).

   Acts as external MCP client: calls /mcp/tools (list), then
   /mcp/tools/{name} (call) for each registered tool.

   Pilot criterion (ROADMAP §14.1): LLM Client in MCP Server mode
   answers list_tools and call_tool from external MCP client.

   Usage:
       python scripts/probe_mcp_server.py --url http://localhost:8000
   """
   import argparse
   import asyncio
   import json
   import logging
   import sys

   import httpx

   logger = logging.getLogger(__name__)


   async def probe_mcp_server(base_url: str) -> bool:
       """Returns True if MCP Server responds correctly to list_tools
       and call_tool from external client."""
       async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
           # 1. Health check
           logger.info("Probing /mcp/health...")
           resp = await client.get("/mcp/health")
           if resp.status_code != 200:
               logger.error("Health check failed: %s %s", resp.status_code, resp.text)
               return False
           health = resp.json()
           logger.info("Health OK: %d tools", health["tools_count"])

           # 2. List tools
           logger.info("Probing /mcp/tools (list_tools)...")
           resp = await client.get("/mcp/tools")
           if resp.status_code != 200:
               logger.error("List tools failed: %s %s", resp.status_code, resp.text)
               return False
           tools_list = resp.json()["tools"]
           logger.info("List tools OK: %d tools", len(tools_list))
           for t in tools_list:
               logger.info("  - %s: %s", t["name"], t["description"])

           # 3. Call each tool with minimal args
           for tool in tools_list:
               name = tool["name"]
               args = get_minimal_args(name)
               logger.info("Calling /mcp/tools/%s with args: %s", name, args)
               resp = await client.post(f"/mcp/tools/{name}", json=args)
               if resp.status_code != 200:
                   logger.error("Call tool %s failed: %s %s", name,
                               resp.status_code, resp.text)
                   return False
               result = resp.json()
               if result.get("error"):
                   logger.error("Tool %s returned error: %s", name, result["error"])
                   # Don't fail probe for tool-specific errors (e.g.
                   # web_search without TAVILY_API_KEY); just log.
                   continue
               logger.info("Tool %s returned: %s", name, str(result["result"])[:100])

           # 4. Streaming endpoint probe (one tool, non-essential)
           logger.info("Probing /mcp/tools/web_search/stream (SSE)...")
           args_json = json.dumps({"query": "test", "max_results": 1})
           resp = await client.get(
               f"/mcp/tools/web_search/stream?args_json={args_json}",
               timeout=10.0,
           )
           if resp.status_code == 200:
               # Verify SSE format: contains "event:" lines
               if "event:" in resp.text:
                   logger.info("SSE streaming OK")
               else:
                   logger.warning("SSE response missing event: lines")
           else:
               logger.warning("SSE endpoint returned %s (non-critical)", resp.status_code)

           logger.info("✅ MCP Server preview probe PASSED")
           return True


   def get_minimal_args(tool_name: str) -> dict:
       """Minimal valid args for each known tool."""
       if tool_name == "rag_query":
           return {"query": "test", "top_k": 1}
       elif tool_name == "file_export":
           return {"filename": "test.txt", "content": "test"}
       elif tool_name == "web_search":
           return {"query": "test", "max_results": 1}
       return {}


   def main():
       parser = argparse.ArgumentParser()
       parser.add_argument("--url", default="http://localhost:8000",
                           help="LLM Client agent-service base URL")
       args = parser.parse_args()
       success = asyncio.run(probe_mcp_server(args.url))
       sys.exit(0 if success else 1)


   if __name__ == "__main__":
       main()
   ```

2. Тесты в `tests/integration/test_mcp_server_probe.py`:
   - `test_probe_passes_when_server_healthy` — mock httpx responses
     with valid /mcp/health, /mcp/tools, /mcp/tools/{name}, verify
     probe returns True.
   - `test_probe_fails_on_health_check_failure` — /mcp/health
     returns 500 → probe returns False.
   - `test_probe_fails_on_list_tools_failure` — /mcp/tools 500 →
     False.
   - `test_probe_passes_with_tool_errors` — tool returns `{error:
     "..."}` (e.g. TAVILY_API_KEY missing) → probe still passes
     (tool errors не critical для MCP Server preview pilot).
   - `test_get_minimal_args_per_tool` — verify each known tool has
     minimal args.

Definition of Done:
- `scripts/probe_mcp_server.py` создан с `probe_mcp_server` async
  function + `main()` CLI.
- CLI: `python scripts/probe_mcp_server.py --url
  http://localhost:8000` → exit 0 on success, exit 1 on failure.
- Probe проверяет: /mcp/health, /mcp/tools (list), /mcp/tools/{name}
  (call для каждого tool), /mcp/tools/web_search/stream (SSE).
- 5+ integration тестов зелёные (mocked HTTP).
- Manual run: start agent-service с MCP_SERVER_ENABLED=true, run
  probe — exit 0.

Антипаттерны:
- НЕ делай probe блокирующим на tool-specific errors — tool errors
  (e.g. TAVILY_API_KEY missing) не critical для MCP Server
  infrastructure validation.
- НЕ хардкодь minimal args — вынеси в helper function for
  extensibility (new tools могут быть добавлены в Phase 4+).
- НЕ делай probe без /mcp/health first — discovery protocol требует
  health check before list_tools (external clients могут probe
  /mcp/health before /mcp/tools).

Связанные ADR:
- Реализует: ADR-004 ускорение pilot probe (критично для Approved
  per ROADMAP §14.1).
- Применяет: закон 4.6 ТРИЗ (переход в надсистему — external client
  probe validates integration).
- Зависит от: Блок H-1 (McpServer), Блок H-2 (registry), Блок H-3
  (SSE transport).
- Расширяется в: Phase 4 — `agent_run` MCP tool probe (executes full
  agent graph, longer-running); probe v2 с full conversation flow.
- Не затрагивает: ADR-010, ADR-013, ADR-014.
```

---

## 6. Блок G. UI-расширения Phase 3 (опционально)

Блок G — опциональные UI-расширения для управляемости Phase 3 абстракциями (`LLMRouter`, `ToolCallingAdapter`, MCP Server). **Не входит в оценку `ROADMAP.md` v1.2.0 §7.2** (Phase 3 = 31 чел-дн ADR + 2.5 overhead); добавлен в BETA-PROMPTS v1.0.0 по аналогии с ALPHA-PROMPTS v1.1.0 (который добавил G-1..G-4 Phase 2 поверх оценки ROADMAP).

Блок G состоит из 3 prompts (~1.5 чел-дн total):
- **G-1**: settings panel extension для `LLMRouter` policy selector (cost/latency/quality/privacy).
- **G-2**: settings panel extension для `ToolCallingMode` toggle (native/react/hybrid).
- **G-3**: MCP Server mode on/off toggle + endpoint URL display.

Если команда ограничена по времени, Блок G можно отложить до Phase 4.

---

### G-1. `render_router_policy` (settings panel extension для LLMRouter)

```
Ты — Frontend-разработчик LLM Client. Расширь существующий
`render_settings_panel` (Phase 2 G-4, `src/llm_client/ui/streamlit_client.py`)
с selector для `LLMRouter` policy (cost / latency / quality / privacy).
Это опциональное UI-расширение для ADR-015 управляемости.

Контекст:
- Phase 2 G-4 (ALPHA-PROMPTS.md Блок G-4) создал `render_settings_panel`
  в `StreamlitClient` (Phase 2 UI-расширение).
- Блок C-2 (Phase 3) создал `LLMRouter` с `RoutingPolicy` enum
  (COST, LATENCY, QUALITY, PRIVACY) + Settings
  `llm_router_default_policy`.
- ARCHITECT.md v1.3.0 §5.1 (Presentation Layer) — UI должен
  expose router policy для user control.
- ADR-015 (TRIZ §11): user может выбрать policy per-session (cost
  для dev/test, quality для production demos).

Задача:
1. Расширь `src/llm_client/ui/streamlit_client.py` — добавь
   `render_router_policy` method в `StreamlitClient`:
   ```python
   # in StreamlitClient class
   def render_router_policy(self, key: str = "router_policy") -> str:
       """Renders a selectbox for LLMRouter policy. Returns selected
       policy string."""
       import streamlit as st
       options = ["cost_priority", "latency_priority",
                  "quality_priority", "privacy_priority"]
       # Default from Settings.llm_router_default_policy
       from ..config import get_settings
       default_idx = options.index(get_settings().llm_router_default_policy) \
           if get_settings().llm_router_default_policy in options else 0
       selected = st.selectbox(
           "LLM Router Policy",
           options=options,
           index=default_idx,
           format_func=lambda x: x.replace("_", " ").title(),
           key=key,
           help="Cost: cheapest model. Latency: fastest p50. "
                "Quality: best model. Privacy: zero-retention.",
       )
       st.session_state["router_policy"] = selected
       return selected
   ```

2. Вызови `render_router_policy` из `render_settings_panel`:
   ```python
   # in render_settings_panel (existing Phase 2 G-4 method)
   # ... existing tools on/off, retrieval_strategy, reranker ...
   # NEW Phase 3 G-1:
   self.render_router_policy()
   ```

3. Передай selected policy в agent-service request:
   ```python
   # in StreamlitClient.send_message
   async def send_message(self, message: str) -> AsyncIterator[dict]:
       # ... existing ...
       policy = st.session_state.get("router_policy", "cost_priority")
       request = {
           "message": message,
           "session_id": st.session_state["session_id"],
           # NEW Phase 3 G-1:
           "router_policy": policy,
       }
       # ... existing POST /chat ...
   ```

4. Обнови `src/llm_client/ui/client.py` `UIClient` abstraction —
   добавь `render_router_policy` abstract method (для
   `ChainlitClient` Phase 5 implementation).

5. Тесты в `tests/unit/test_ui_router_policy.py`:
   - `test_render_router_policy_default_cost` — Settings default
     `cost_priority` → selectbox index=0.
   - `test_render_router_policy_user_selects_quality` — user
     selects `quality_priority` → `st.session_state["router_policy"]
     = "quality_priority"`.
   - `test_send_message_includes_router_policy` — verify POST
     request body contains `"router_policy": "..."`.

Definition of Done:
- `StreamlitClient.render_router_policy` существует с selectbox
  (4 options, format_func для title case).
- `render_settings_panel` включает router policy selector.
- POST `/chat` request body includes `router_policy` field.
- `UIClient` abstraction extended с `render_router_policy` abstract
  method.
- 3+ unit тестов зелёные.
- Существующие тесты Phase 2 (`test_ui_settings_panel.py`) — не
  регрессируют (additive extension).

Антипаттерны:
- НЕ хардкодь 4 options в UI коде — вынеси в `RoutingPolicy` enum
  values (Блок C-2).
- НЕ делай router policy mandatory UI element — opt-in (если user
  не выбрал, default из Settings).
- НЕ забудь `key` parameter для Streamlit selectbox — уникальный
  widget key (avoid duplicate widget ID).

Связанные ADR:
- Реализует: UI управляемость для ADR-015 router.
- Применяет: Phase 2 G-4 (pattern для settings_panel extension),
  ADR-015 (user-facing policy control).
- Зависит от: Блок C-2 (`RoutingPolicy` enum), Phase 2 G-4
  (`render_settings_panel`).
- Расширяется в: Phase 4 — `render_router_circuit_breaker_status`
  (live Prometheus gauge display), `render_router_budget_usage`
  (progress bar).
- Не затрагивает: ADR-010, ADR-013, ADR-014 (UI independent).
```

### G-2. `render_tool_calling_mode` (settings panel для ToolCallingMode)

```
Ты — Frontend-разработчик LLM Client. Расширь `render_settings_panel`
с toggle для `ToolCallingMode` (native / react / hybrid). Это
опциональное UI-расширение для ADR-016 управляемости (особенно при
debugging ReAct mode на Ollama pilot).

Контекст:
- Phase 2 G-4 создал `render_settings_panel`.
- Блок D-2 (Phase 3) создал `ToolCallingMode` enum (NATIVE, REACT,
  HYBRID).
- ARCHITECT.md v1.3.0 §5.1 (Presentation Layer) — UI должен
  expose mode для debugging.
- ADR-016 (TRIZ §11): pilot на Ollama + Llama 3.1 — user может
  форсировать REACT mode для debugging.

Задача:
1. Расширь `StreamlitClient` — добавь `render_tool_calling_mode`:
   ```python
   def render_tool_calling_mode(self, key: str = "tool_calling_mode") -> str:
       """Renders a selectbox for ToolCallingMode."""
       import streamlit as st
       options = ["auto", "native", "react", "hybrid"]
       # "auto" = None (let adapter choose via capability matrix)
       selected = st.selectbox(
           "Tool Calling Mode",
           options=options,
           index=0,  # default: auto
           format_func=lambda x: x.title(),
           key=key,
           help="Auto: choose via capability matrix. Native: OpenAI-style "
                "function calling. ReAct: system prompt emulation. Hybrid: "
                "native with ReAct fallback.",
       )
       st.session_state["tool_calling_mode"] = selected
       return selected
   ```

2. Вызови из `render_settings_panel` (после G-1 router policy):
   ```python
   # in render_settings_panel
   self.render_router_policy()
   # NEW Phase 3 G-2:
   self.render_tool_calling_mode()
   ```

3. Передай selected mode в agent-service request:
   ```python
   # in send_message
   mode = st.session_state.get("tool_calling_mode", "auto")
   request["tool_calling_mode"] = None if mode == "auto" else mode
   ```

4. Тесты в `tests/unit/test_ui_tool_calling_mode.py`:
   - `test_render_tool_calling_mode_default_auto` — default index=0
     (auto).
   - `test_render_tool_calling_mode_user_selects_react` — user
     selects `react` → session_state.
   - `test_send_message_includes_tool_calling_mode` — request body
     contains `"tool_calling_mode": "react"` (или `null` if auto).

Definition of Done:
- `StreamlitClient.render_tool_calling_mode` существует с selectbox
  (4 options: auto, native, react, hybrid).
- `render_settings_panel` включает tool calling mode selector.
- POST `/chat` request body includes `tool_calling_mode` field
  (None if auto, string otherwise).
- 3+ unit тестов зелёные.

Антипаттерны:
- НЕ делай tool_calling_mode mandatory UI — opt-in (default auto =
  adapter chooses).
- НЕ хардкодь mode options — вынеси в `ToolCallingMode` enum values
  + "auto" prefix.

Связанные ADR:
- Реализует: UI управляемость для ADR-016.
- Применяет: Phase 2 G-4 (pattern), Блок D-2 (`ToolCallingMode`).
- Зависит от: Блок D-2 (`ToolCallingMode` enum), Phase 2 G-4.
- Расширяется в: Phase 4 — `render_tool_calling_mode_status`
  (live display of selected mode + actual mode after adapter
  resolution).
- Не затрагивает: ADR-010, ADR-013, ADR-014.
```

### G-3. `render_mcp_server_toggle` (MCP Server on/off + endpoint URL)

```
Ты — Frontend-разработчик LLM Client. Расширь `render_settings_panel`
с toggle для MCP Server mode on/off + endpoint URL display. Это
опциональное UI-расширение для ADR-004 ускорение управляемости.

Контекст:
- Phase 2 G-4 создал `render_settings_panel`.
- Блок H-1 (Phase 3) создал `McpServer` с `/mcp/*` routes.
- Settings (Блок H-1): `mcp_server_enabled` (default False), `mcp_server_transport`.
- ARCHITECT.md v1.3.0 §5.1 (Presentation Layer) — UI должен
  expose MCP Server toggle для user control.

Задача:
1. Расширь `StreamlitClient` — добавь `render_mcp_server_toggle`:
   ```python
   def render_mcp_server_toggle(self, key: str = "mcp_server_enabled") -> bool:
       """Renders a checkbox for MCP Server mode on/off + endpoint
       URL display."""
       import streamlit as st
       from ..config import get_settings
       settings = get_settings()

       enabled = st.checkbox(
           "Enable MCP Server (preview)",
           value=settings.mcp_server_enabled,
           key=key,
           help="Exposes LLM Client tools (rag_query, file_export, "
                "web_search) as MCP tools for external clients.",
       )

       if enabled:
           st.info(
               f"MCP Server endpoint: `http://localhost:8000/mcp/tools`\n\n"
               f"Transport: {settings.mcp_server_transport.upper()}\n\n"
               f"Tools: rag_query, file_export, web_search"
           )
           # Show health status
           if st.button("Check MCP Server Health", key="mcp_health"):
               import httpx
               try:
                   resp = httpx.get("http://localhost:8000/mcp/health", timeout=5.0)
                   if resp.status_code == 200:
                       data = resp.json()
                       st.success(f"OK — {data['tools_count']} tools registered")
                   else:
                       st.error(f"Health check failed: {resp.status_code}")
               except Exception as e:
                   st.error(f"Cannot reach MCP Server: {e}")

       return enabled
   ```

2. Вызови из `render_settings_panel`:
   ```python
   # in render_settings_panel
   self.render_router_policy()
   self.render_tool_calling_mode()
   # NEW Phase 3 G-3:
   self.render_mcp_server_toggle()
   ```

3. Тесты в `tests/unit/test_ui_mcp_server_toggle.py`:
   - `test_render_mcp_server_toggle_default_off` — Settings
     `mcp_server_enabled=False` → checkbox unchecked.
   - `test_render_mcp_server_toggle_user_checks` — user checks →
     returns True, info message shown.
   - `test_render_mcp_server_toggle_shows_endpoint_url` — when
     enabled, info contains endpoint URL.

Definition of Done:
- `StreamlitClient.render_mcp_server_toggle` существует с checkbox
  + info message + health check button.
- `render_settings_panel` включает MCP Server toggle.
- 3+ unit тестов зелёные.

Антипаттерны:
- НЕ делай MCP Server toggle persistent across sessions — это admin
  setting (per-deployment, не per-session). UI checkbox — read-only
  display of current setting; actual toggle via env var.
- НЕ делай health check blocking — async (httpx sync OK для
  Streamlit, but use asyncio in production via background thread).

Связанные ADR:
- Реализует: UI управляемость для ADR-004 ускорение.
- Применяет: Phase 2 G-4 (pattern), Блок H-1 (McpServer).
- Зависит от: Блок H-1 (`McpServer`), Phase 2 G-4.
- Расширяется в: Phase 6 — `render_mcp_server_auth_status` (OAuth
  2.0 status display), `render_mcp_external_clients` (list of
  connected external clients).
- Не затрагивает: ADR-010, ADR-013, ADR-014.
```

---

## 7. Блок E. Тесты и CI для Phase 3

Блок E содержит integration tests и CI pipeline расширения для Phase 3 ADR-011/015/016/004 pilot criteria validation.

- **E-1**: Semantic cache hit-rate test (ADR-011 pilot).
- **E-2**: Cost predictability shadow-mode test (ADR-015 pilot).
- **E-3**: ReAct success-rate test on Ollama (ADR-016 pilot).
- **E-4**: MCP Server preview probe (ADR-004 pilot).
- **E-5**: Phase 3 CI pipeline extension.

---

### E-1. Semantic cache hit-rate test (ADR-011 pilot)

```
(См. Блок B-6 `scripts/ab_test_semantic_cache.py` — full implementation
already covers pilot criterion "hit rate >15%, stale <1%, latency cache
hit <100ms". E-1 фиксирует CI integration.)

Контекст:
- Блок B-6 создал `scripts/ab_test_semantic_cache.py` + dataset
  `datasets/rag_eval/phase3_semantic_cache_eval.jsonl`.
- ROADMAP §14.1 ADR-011 pilot: 100 запросов, hit rate >15%, stale
  <1%, latency cache hit <100ms.

Задача:
1. Добавь в CI pipeline `scripts/ci-local-staging.sh`:
   ```bash
   # existing Phase 2 staging CI
   pytest tests/integration/ -k "phase2 or reranker or hybrid_retriever"

   # NEW Phase 3 E-1: ADR-011 pilot
   python scripts/ab_test_semantic_cache.py \
     --queries-file datasets/rag_eval/phase3_semantic_cache_eval.jsonl \
     --iterations 2
   ```

2. Создай alerting rule в `ops/grafana/provisioning/alerting/rules.yml`
   для ADR-011:
   ```yaml
   - alert: SemanticCacheStaleRateHigh
     expr: |
       (sum(rate(semantic_cache_hits_total{status="stale"}[5m])) /
        sum(rate(semantic_cache_hits_total[5m]))) > 0.01
     for: 5m
     labels:
       severity: warning
     annotations:
       summary: "Semantic cache stale rate >1% (ADR-011 pilot risk)"
   - alert: SemanticCacheHitRateLow
     expr: |
       (sum(rate(semantic_cache_hits_total{status="hit"}[5m])) /
        sum(rate(semantic_cache_hits_total[5m]))) < 0.10
     for: 10m
     labels:
       severity: warning
     annotations:
       summary: "Semantic cache hit rate <10% (rollback criterion)"
   ```

Definition of Done:
- CI pipeline `scripts/ci-local-staging.sh` запускает
  `ab_test_semantic_cache.py` перед deploy.
- Grafana alerting rules для semantic cache (stale rate, hit rate).
- Блок B-6 existing tests покрыты.
- ADR-011 pilot pass/rollback verdict visible в CI output.
```

### E-2. Cost predictability shadow-mode test (ADR-015 pilot)

```
Ты — ML/Backend-разработчик LLM Client. Создай cost predictability
shadow-mode test для ADR-015 — 1-month shadow mode run, проверка
cost predictability ±10%, cost overrun <20%.

Контекст:
- Блок C-2/C-3/C-6 реализовали `LLMRouter` + `CostGuard` + shadow
  mode migration.
- Блок C-7 реализовал `RouterMetricsLogger` для switching decisions
  logging.
- ROADMAP §14.1 ADR-015 pilot: 1 месяц shadow mode — cost
  predictability ±10%, cost overrun <20%, логирование switching
  decisions в observability.
- Rollback: cost overrun >20% OR unacceptable routing decisions.

Задача:
1. Создай `scripts/ab_test_router_shadow_mode.py`:
   ```python
   """A/B test for ADR-015 LLMRouter shadow mode (Phase 3).

   Runs in parallel with existing LLMProviderFactory.create() calls;
   logs shadow decisions via RouterMetricsLogger (Блок C-7).

   Pilot criteria (ROADMAP §14.1):
   - Cost predictability ±10% (router-predicted cost vs actual)
   - Cost overrun <20% (router decisions don't cause budget overrun)
   - Switching decisions logged

   Rollback: cost overrun >20% OR unacceptable routing decisions.
   """
   import argparse
   import asyncio
   import json
   import logging
   import statistics
   from dataclasses import dataclass
   from datetime import datetime, timedelta

   from llm_client.agent.router import RoutingPolicy, get_llm_router
   from llm_client.observability.router_metrics_logger import get_router_metrics_logger

   logger = logging.getLogger(__name__)


   @dataclass
   class ShadowModeResult:
       total_requests: int
       router_predicted_costs: list[float]
       actual_costs: list[float]
       switching_decisions_logged: int
       cost_overrun_count: int  # requests where router decision led to overrun

       def cost_predictability(self) -> float:
           """Returns standard deviation of (actual - predicted) /
           predicted ratios. Lower = more predictable."""
           if not self.router_predicted_costs:
               return 0.0
           ratios = []
           for pred, actual in zip(self.router_predicted_costs, self.actual_costs):
               if pred > 0:
                   ratios.append((actual - pred) / pred)
           return statistics.stdev(ratios) if len(ratios) > 1 else 0.0

       def cost_overrun_rate(self) -> float:
           return self.cost_overrun_count / self.total_requests if self.total_requests else 0.0

       def pilot_pass(self) -> bool:
           return (
               self.cost_predictability() <= 0.10  # ±10%
               and self.cost_overrun_rate() <= 0.20  # <20% overrun
               and self.switching_decisions_logged == self.total_requests
           )

       def rollback_required(self) -> bool:
           return self.cost_overrun_rate() > 0.20


   async def run_shadow_mode(duration_minutes: int = 60) -> ShadowModeResult:
       """Run shadow mode for `duration_minutes` minutes. Each request
       routed via existing LLMProviderFactory, but router.route_shadow
       called in parallel."""
       # ... implementation details omitted for brevity ...
       pass


   def main():
       parser = argparse.ArgumentParser()
       parser.add_argument("--duration-minutes", type=int, default=60)
       args = parser.parse_args()
       result = asyncio.run(run_shadow_mode(args.duration_minutes))
       print(f"=== ADR-015 Pilot: LLMRouter Shadow Mode ===")
       print(f"Total requests: {result.total_requests}")
       print(f"Cost predictability (stdev of ratios): {result.cost_predictability():.3f}")
       print(f"Cost overrun rate: {result.cost_overrun_rate():.1%}")
       print(f"Switching decisions logged: {result.switching_decisions_logged}")
       if result.rollback_required():
           print("❌ ROLLBACK REQUIRED (cost overrun >20%)")
       elif result.pilot_pass():
           print("✅ PILOT PASS — ADR-015 Approved")
       else:
           print("⚠️  PILOT PARTIAL")


   if __name__ == "__main__":
       main()
   ```

2. Добавь в CI pipeline (ноябрь — month-long pilot run, не в regular
   CI):
   ```bash
   # Phase 3 E-2: ADR-015 shadow mode pilot (1 month run; scheduled
   # via external cron, not in regular CI)
   # Run: python scripts/ab_test_router_shadow_mode.py --duration-minutes 43200
   ```

3. Тесты в `tests/unit/test_ab_test_router_shadow_mode.py`:
   - `test_shadow_mode_result_predictability_under_10pct` —
     ratios=[0.05, -0.03, 0.04, -0.02] → stdev <0.10 → pass.
   - `test_shadow_mode_result_overrun_rate_under_20pct` — 10/100
     overruns → 10% <20% → pass.
   - `test_shadow_mode_result_rollback_when_overrun_25pct` — 25/100
     → 25% >20% → rollback.
   - `test_shadow_mode_result_all_decisions_logged` — 100/100
     logged → pass.

Definition of Done:
- `scripts/ab_test_router_shadow_mode.py` создан с `run_shadow_mode`
  + `ShadowModeResult` + `main()` CLI.
- 4+ unit тестов зелёные.
- Pilot run procedure documented in `docs/adr_015_pilot.md`:
  - Day 1-7: shadow mode (router.route_shadow only, no traffic
    switch).
  - Day 8-14: 5% traffic via router.
  - Day 15-21: 50% traffic.
  - Day 22-28: 100% traffic (if no rollback).
  - Day 28-30: review + Approved/rollback decision.
```

### E-3. ReAct success-rate test on Ollama (ADR-016 pilot)

```
(См. Блок D-6 `scripts/pilot_ollama_react.py` — full implementation
already covers pilot criterion "ReAct success rate ≥80%". E-3
фиксирует manual pilot procedure.)

Контекст:
- Блок D-6 создал `scripts/pilot_ollama_react.py` + `PilotResult`.
- ROADMAP §14.1 ADR-016 pilot: Ollama + Llama 3.1 success rate
  ≥80% (vs native ≥95%). Rollback: success <60%.

Задача:
1. Создай `docs/adr_016_pilot.md` (manual procedure, не CI test):
   ```markdown
   # ADR-016 Pilot Procedure (Phase 3)

   ## Prerequisites
   - Local Ollama installed (https://ollama.com)
   - Llama 3.1 model pulled: `ollama pull llama3.1:8b`
   - LLM Client repo cloned + dependencies installed

   ## Steps
   1. Start Ollama: `ollama serve` (default port 11434)
   2. Verify model available: `ollama list` should show `llama3.1:8b`
   3. Run pilot:
      ```bash
      python scripts/pilot_ollama_react.py \
        --ollama-url http://localhost:11434 \
        --model llama3.1:8b
      ```
   4. Review output:
      - ✅ PILOT PASS — success rate ≥80%, ADR-016 Approved
      - ⚠️  PILOT PARTIAL — 60-80%, tune ReAct prompt variant (D-4),
        re-run
      - ❌ ROLLBACK REQUIRED — <60%, ADR-016 rollback; investigate
        capability matrix entries

   ## Tuning
   If success rate is 60-80%, try different ReAct prompt variants
   (D-4): `REACT_PROMPT_VARIANT=v2_tolerant` or `v3_cot`.
   ```

2. Тесты (manual, не CI):
   - Local run with Ollama + Llama 3.1.
   - Verify success rate measured and verdict printed.

Definition of Done:
- `docs/adr_016_pilot.md` создан с manual procedure.
- Local pilot run procedure works (verified by developer).
- Success rate criterion ≥80% achievable with default v1_strict
  prompt OR after tuning v2_tolerant/v3_cot.
```

### E-4. MCP Server preview probe (ADR-004 pilot)

```
(См. Блок H-4 `scripts/probe_mcp_server.py` — full implementation
already covers pilot criterion "LLM Client in MCP Server mode
answers list_tools and call_tool". E-4 фиксирует CI integration.)

Контекст:
- Блок H-4 создал `scripts/probe_mcp_server.py`.
- ROADMAP §14.1 ADR-004 preview pilot: external MCP client
  successfully calls list_tools и call_tool.

Задача:
1. Добавь в CI pipeline `scripts/ci-local-staging.sh`:
   ```bash
   # NEW Phase 3 E-4: ADR-004 preview probe
   # Start agent-service with MCP_SERVER_ENABLED=true
   MCP_SERVER_ENABLED=true python -m llm_client.agent &
   AGENT_PID=$!
   sleep 5  # wait for startup
   python scripts/probe_mcp_server.py --url http://localhost:8000
   PROBE_EXIT=$?
   kill $AGENT_PID
   exit $PROBE_EXIT
   ```

2. Тесты в `tests/integration/test_mcp_server_probe.py` (Блок H-4
   already created) — verify in CI.

Definition of Done:
- CI pipeline `scripts/ci-local-staging.sh` запускает
  `probe_mcp_server.py` после deploy на staging.
- Probe exit code проверяется (0 = pass, 1 = fail).
- ADR-004 preview pass/rollback visible в CI output.
```

### E-5. Phase 3 CI pipeline extension

```
Ты — DevOps-разработчик LLM Client. Расширь existing CI pipeline
(`scripts/ci-local-staging.sh` Phase 2) с Phase 3-specific tests и
checks.

Контекст:
- Phase 2 `scripts/ci-local-staging.sh` содержит Phase 2 staging
  CI (reranker, hybrid retriever, integration tests).
- Блоки E-1, E-2, E-3, E-4 добавили Phase 3 pilot tests.
- ARCHITECT.md v1.3.0 §6 Grafana dashboards: existing
  `idealidad.json`, `checkpoint-latency.json`, etc. Phase 3
  добавит `llm-cost-router.json` (Блок F-2).

Задача:
1. Обнови `scripts/ci-local-staging.sh` — добавь Phase 3 checks:
   ```bash
   #!/usr/bin/env bash
   set -e

   echo "=== Phase 1/2 staging CI (existing) ==="
   pytest tests/unit/ tests/integration/ -k "not phase3" -v
   pytest tests/staging_load/ -v

   echo "=== Phase 3 E-1: ADR-011 Semantic Cache pilot ==="
   pytest tests/integration/test_stale_answer_guard.py -v
   pytest tests/integration/test_semantic_cache_integration.py -v
   python scripts/ab_test_semantic_cache.py \
     --queries-file datasets/rag_eval/phase3_semantic_cache_eval.jsonl \
     --iterations 2

   echo "=== Phase 3 E-2: ADR-015 LLMRouter shadow mode (smoke) ==="
   # Note: full 1-month shadow mode is external scheduled run
   # Smoke test: verify router can be imported and route() works
   pytest tests/unit/test_llm_router.py -v
   pytest tests/unit/test_cost_guard.py -v
   pytest tests/unit/test_circuit_breaker.py -v

   echo "=== Phase 3 E-3: ADR-016 Tool Calling Adapter ==="
   pytest tests/unit/test_capability_matrix.py -v
   pytest tests/unit/test_tool_calling_mode.py -v
   pytest tests/unit/test_tool_calling_adapter.py -v
   pytest tests/unit/test_react_prompt_builder.py -v
   # Pilot on Ollama is manual (see docs/adr_016_pilot.md)

   echo "=== Phase 3 E-4: ADR-004 MCP Server preview probe ==="
   MCP_SERVER_ENABLED=true python -m llm_client.agent &
   AGENT_PID=$!
   sleep 5
   python scripts/probe_mcp_server.py --url http://localhost:8000
   PROBE_EXIT=$?
   kill $AGENT_PID
   if [ $PROBE_EXIT -ne 0 ]; then
     echo "❌ MCP Server probe failed"
     exit $PROBE_EXIT
   fi

   echo "=== Phase 3 E-5: Phase 3 complete — all tests passed ==="
   ```

2. Обнови `scripts/ci-local-quick.sh` (existing Phase 1/2 quick CI):
   ```bash
   #!/usr/bin/env bash
   set -e
   # Quick CI: unit tests only, no integration, no pilots
   pytest tests/unit/ -k "not integration and not staging_load" -v --maxfail=3
   ```

3. Обнови `scripts/ci-local-integration-staging.sh` (existing):
   ```bash
   #!/usr/bin/env bash
   set -e
   # Integration CI: requires docker-compose up (Redis, PostgreSQL,
   # MinIO, Vault)
   pytest tests/integration/ -v
   # Phase 3 additions:
   pytest tests/integration/test_stale_answer_guard.py -v
   pytest tests/integration/test_semantic_cache_integration.py -v
   pytest tests/integration/test_facts_extractor_integration.py -v
   pytest tests/integration/test_cache_aware_llm_integration.py -v
   pytest tests/integration/test_graph_cache_e2e.py -v
   pytest tests/integration/test_llm_router_integration.py -v
   pytest tests/integration/test_react_e2e.py -v
   pytest tests/integration/test_mcp_server_e2e.py -v
   pytest tests/integration/test_mcp_server_with_registry.py -v
   ```

Definition of Done:
- `scripts/ci-local-staging.sh` содержит Phase 3 checks (E-1..E-4).
- `scripts/ci-local-quick.sh` — Phase 3 unit tests включены.
- `scripts/ci-local-integration-staging.sh` — 9 new Phase 3
  integration tests включены.
- CI runs end-to-end without errors на staging.
- Pilot verdicts (PASS/ROLLBACK/PARTIAL) visible в CI output.

Антипаттерны:
- НЕ делай Phase 3 pilot tests blocking для PR — pilots (E-1, E-3,
  E-4) могут быть non-blocking warnings initially, blocking только
  после 1 sprint stability.
- НЕ хардкодь ports/URLs — используй env vars (LLM_CLIENT_URL,
  MCP_SERVER_URL).
- НЕ делай integration tests без docker-compose up precondition —
  `ci-local-integration-staging.sh` должен проверять
  `docker-compose ps` перед runs.
```

---

## 8. Блок F. Документация и метрика идеальности

Блок F закрывает Phase 3 документацией:
- **F-1**: `ARCHITECT.md` update (v1.3.0 → v1.4.0) — добавляет
  ADR-011/015/016 + ADR-004 ускорение; обновляет §8 Trade-offs (C-6
  fully, C-7, C-9 resolved), §12 (Q-5 closed).
- **F-2**: Grafana dashboard `llm-cost-router.json` Phase 3 control
  point (Δф/Δсложности = 4/2 = 2.0).

---

### F-1. `ARCHITECT.md` update (v1.3.0 → v1.4.0)

```
Ты — Архитектор/Tech-писатель LLM Client. Обнови `ARCHITECT.md` с
Phase 3 deliverables — version bump v1.3.0 → v1.4.0.

Контекст:
- Phase 2 ALPHA-PROMPTS F-1 обновил `ARCHITECT.md` до v1.3.0.
- Phase 3 завершена: ADR-011 (semantic cache), ADR-015 (cost-aware
  router), ADR-016 (tool capability adapter), ADR-004 ускорение (MCP
  server preview) — все Approved.
- ROADMAP §7.7 exit criterion #6: "Документация обновлена:
  ARCHITECT.md § 7 ADR обновлён; § 8 Trade-offs обновлён (C-6 fully,
  C-7, C-9 помечены как resolved); § 12 Q-5 (cost risk) закрыт".

Задача:
1. Обнови header table `analytics/ARCHITECT.md`:
   ```markdown
   | Версия документа | 1.4.0 |
   | Дата | <Phase 3 completion date> |
   | Changelog | 1.4.0 (YYYY-MM-DD): Phase 3 завершена — добавлены
     ADR-011, ADR-015, ADR-016, ADR-004 ускорение; C-6 помечено
     [RESOLVED fully]; C-7, C-9 помечено [RESOLVED]; Q-5 [CLOSED];
     Q-1 [PARTIALLY CLOSED preview]; компонентная диаграмма обновлена
     с LLMRouter, ModelCapabilityMatrix, ToolCallingAdapter,
     SemanticAnswerCache, FactsExtractor, documents_facts table,
     Redis DB 2, MCP Server preview endpoint; §5.2.3 LLM Provider
     Layer обновлён с LLMRouter (Supersedes ADR-005 fallback_chain);
     §5.2.4 Tool Layer обновлён с ToolCallingAdapter (native/react/
     hybrid); §5.2.5 RAG Layer обновлён с three-tier cache; §5.2.6
     MCP Layer обновлён с MCP Server preview; ADR-011/015/016 помечены
     Approved в §7. | 1.3.0 (2026-09-30): Phase 2 завершена ... |
   ```

2. Обнови §4 (контейнерная диаграмма) — добавь компоненты:
   - `LLMRouter` (обёртывает `LLMProviderFactory`)
   - `ModelCapabilityMatrix` (YAML-driven registry)
   - `ToolCallingAdapter` (native/react/hybrid)
   - `SemanticAnswerCache` (Redis DB 2, Tier-3)
   - `FactsExtractor` (LLM call на indexing-time, Tier-1)
   - `documents_facts` table (PostgreSQL, Alembic migration 009)
   - `MCP Server preview` (FastAPI routes `/mcp/*`, SSE transport)
   - `CostGuard` (monthly budget, 80% threshold)
   - `CircuitBreaker` (per-provider, Prometheus gauge)

3. Обнови §5.2.3 (LLM Provider Layer) — ADR-015 LLMRouter:
   - `LLMRouter` с policies cost/latency/quality/privacy.
   - `LLMProviderFactory` обёрнут router (не заменён).
   - ADR-005 `fallback_chain` помечен **Superseded by ADR-015**.

4. Обнови §5.2.4 (Tool Layer) — ADR-016 ToolCallingAdapter:
   - `ToolCallingAdapter.bind_tools(llm, tools, mode)` заменяет
     direct `llm.bind_tools(tools)`.
   - `ModelCapabilityMatrix` (YAML config).
   - `ToolCallingMode` enum (native/react/hybrid).
   - `ReActBoundModel` + `HybridBoundModel`.

5. Обнови §5.2.5 (RAG Layer) — ADR-011 three-tier cache:
   - Tier-3: `SemanticAnswerCache` (Redis DB 2, cosine sim >0.92,
     TTL=24h).
   - Tier-1: `FactsExtractor` (`documents_facts` table).
   - Tier-2: existing (Phase 2 ADR-017/020, не тронут).
   - `CacheInvalidator` (mark stale on doc update/delete).
   - `CacheAwareLLMClient` wrapper (transparent перехват LLM call).

6. Обнови §5.2.6 (MCP Layer) — ADR-004 ускорение:
   - `McpServer` class (FastAPI routes `/mcp/tools`, `/mcp/tools/{name}`,
     `/mcp/health`).
   - `ExposedToolRegistry` (registers rag_query, file_export,
     web_search).
   - SSE transport per ADR-007.
   - Phase 6: WebSocket + OAuth 2.0 + signed manifests ADR-019.

7. Обнови §5.2.7 (Persistence) — `documents_facts` table +
   Redis DB 2:
   - Alembic migration `009_create_documents_facts.py`.
   - `DocumentFact` ORM model.
   - Redis DB 2 namespace `sem_cache:*`.

8. Обнови §7 (ADRs) — ADR-011, ADR-015, ADR-016, ADR-004 ускорение
   помечены Approved.

9. Обнови §8 (Trade-offs):
   - C-6 [RESOLVED fully] — ADR-011 closed cost component.
   - C-7 [RESOLVED] — ADR-015 cost-aware router.
   - C-9 [RESOLVED] — ADR-016 tool capability adapter.
   - ИКР-0 [PREVIEW] — ADR-004 ускорение.

10. Обнови §12 (Open Questions):
    - Q-5 [CLOSED] — ADR-011 + ADR-015 closed fully.
    - Q-1 [PARTIALLY CLOSED — preview] — ADR-016 + ADR-015 open
      path; full Ollama integration в Phase 4.

Definition of Done:
- `analytics/ARCHITECT.md` обновлён до v1.4.0.
- Header changelog упоминает все Phase 3 deliverables.
- §4 component diagram содержит 9 new components.
- §5.2.3-§5.2.7 обновлены с Phase 3 details.
- §7 ADRs: ADR-011, ADR-015, ADR-016, ADR-004 ускорение — Status
  Approved.
- §8: C-6 fully resolved, C-7 resolved, C-9 resolved, ИКР-0 preview.
- §12: Q-5 closed, Q-1 partially closed.
- Cross-references to `BETA-PROMPTS.md` v1.0.0 в Source line.

Антипаттерны:
- НЕ удаляй существующий контент Phase 1/2 — additive update.
- НЕ забудь version bump в header table.
- НЕ пропусти `Supersedes` relationship ADR-015 → ADR-005 в §7.

Связанные ADR:
- Реализует: ROADMAP §7.7 exit criterion #6 (документация updated).
- Применяет: принцип #35 ТРИЗ (изменение свойств — v1.3.0 → v1.4.0).
- Зависит от: All Phase 3 Блоки (A, B, C, D, H, опционально G).
- Расширяется в: Phase 4 — ADR-009 (plugin registry), ADR-012 (MCP
  auto-negotiation), расш. ADR-001 (cycle detection with embeddings),
  AG-7 (mcp_call tool) — все require ARCHITECT.md v1.5.0+ update.
- Не затрагивает: ADR-010, ADR-013, ADR-014 (Phase 1/2 ADRs preserved).
```

### F-2. Grafana dashboard `llm-cost-router.json` Phase 3 control point

```
Ты — Observability/DevOps-разработчик LLM Client. Создай Grafana
dashboard `ops/grafana/dashboards/llm-cost-router.json` для Phase 3
control point (Δф/Δсложности = 4/2 = 2.0). Dashboard отображает
Phase 3 metrics: router decisions, cost guard, circuit breaker,
semantic cache, ReAct success rate, MCP server calls.

Контекст:
- Phase 2 уже имеет dashboards: `idealidad.json`,
  `checkpoint-latency.json`, `checkpoint-recovery.json`,
  `hybrid-recall.json`.
- Блок A-2 (Phase 3) создал Prometheus metrics:
  `llm_call_total`, `llm_tokens_total`, `llm_cost_usd_total`,
  `llm_call_latency_seconds`, `llm_error_rate_5m`,
  `llm_monthly_budget_usage_ratio`, `semantic_cache_hits_total`.
- Блок C-7 (Phase 3) created Grafana panel structure (decisions by
  policy, cost guard triggers, circuit breaker activations).
- ROADMAP §15.3 Phase 3 control point: Δф=+4 capabilities
  (semantic cache, cost-aware router, tool capability adapter, MCP
  server preview), Δсложности=+3 abstractions (LLMRouter,
  ToolCallingAdapter, ModelCapabilityMatrix) — но `Δсложности`
  компенсируется упразднением `fallback_chain` (-1) — net +2. Итог
  4/2 = 2.0 ≥ 1.

Задача:
1. Создай `ops/grafana/dashboards/llm-cost-router.json`:
   ```json
   {
     "title": "Phase 3 — Cost-Aware Router & Cache (control point 4/2=2.0)",
     "panels": [
       {
         "title": "Router Decisions by Policy (last 1h)",
         "type": "pie",
         "targets": [{"expr": "sum by (policy) (router_decisions_total[1h])"}],
         "gridPos": {"h": 8, "w": 6, "x": 0, "y": 0}
       },
       {
         "title": "Cost Guard Triggers (last 24h)",
         "type": "stat",
         "targets": [{"expr": "sum(router_decisions_total{reason=~\".*Budget.*\"})[24h]"}],
         "gridPos": {"h": 4, "w": 4, "x": 6, "y": 0}
       },
       {
         "title": "Circuit Breaker Activations (last 1h)",
         "type": "stat",
         "targets": [{"expr": "sum(router_decisions_total{circuit_breaker_active=\"true\"}[1h])"}],
         "gridPos": {"h": 4, "w": 4, "x": 10, "y": 0}
       },
       {
         "title": "Monthly Budget Usage",
         "type": "gauge",
         "targets": [{"expr": "llm_monthly_budget_usage_ratio"}],
         "fieldConfig": {
           "defaults": {"thresholds": {"0.8": "orange", "1.0": "red"}}
         },
         "gridPos": {"h": 4, "w": 4, "x": 14, "y": 0}
       },
       {
         "title": "LLM Calls by Provider/Model (last 1h)",
         "type": "bar",
         "targets": [{"expr": "sum by (provider, model) (rate(llm_call_total[1h]))"}],
         "gridPos": {"h": 8, "w": 12, "x": 0, "y": 8}
       },
       {
         "title": "LLM Latency p50/p99",
         "type": "graph",
         "targets": [
           {"expr": "histogram_quantile(0.5, rate(llm_call_latency_seconds_bucket[5m]))"},
           {"expr": "histogram_quantile(0.99, rate(llm_call_latency_seconds_bucket[5m]))"}
         ],
         "gridPos": {"h": 8, "w": 12, "x": 12, "y": 8}
       },
       {
         "title": "Semantic Cache Hit/Miss/Stale Rate",
         "type": "graph",
         "targets": [
           {"expr": "sum(rate(semantic_cache_hits_total{status=\"hit\"}[5m])) / sum(rate(semantic_cache_hits_total[5m]))"},
           {"expr": "sum(rate(semantic_cache_hits_total{status=\"miss\"}[5m])) / sum(rate(semantic_cache_hits_total[5m]))"},
           {"expr": "sum(rate(semantic_cache_hits_total{status=\"stale\"}[5m])) / sum(rate(semantic_cache_hits_total[5m]))"}
         ],
         "gridPos": {"h": 8, "w": 12, "x": 0, "y": 16}
       },
       {
         "title": "Tool Calling Mode Distribution",
         "type": "pie",
         "targets": [{"expr": "sum by (mode) (rate(llm_call_total[1h]))"}],
         "gridPos": {"h": 8, "w": 12, "x": 12, "y": 16}
       },
       {
         "title": "Phase 3 Ideality Metric (Δф/Δсложности)",
         "type": "stat",
         "targets": [{"expr": "4/2"}],
         "fieldConfig": {
           "defaults": {
             "thresholds": {"1.0": "red", "1.5": "yellow", "2.0": "green"},
             "mappings": [{"type": "constant", "value": "2.0 — Phase 3 PASS"}]
           }
         },
         "gridPos": {"h": 4, "w": 6, "x": 0, "y": 24}
       }
     ],
     "schemaVersion": 30,
     "time": {"from": "now-1h", "to": "now"},
     "refresh": "30s"
   }
   ```

2. Обнови `ops/grafana/provisioning/dashboards/provider.yml` —
   добавь новый dashboard:
   ```yaml
   apiVersion: 1
   providers:
     - name: 'Phase 3 Dashboards'
       folder: 'Phase 3'
       type: file
       options:
         path: /var/lib/grafana/dashboards
   ```

3. Тесты в `tests/unit/test_grafana_dashboard_llm_cost_router.py`:
   - `test_dashboard_json_valid` — JSON parses without error.
   - `test_dashboard_contains_required_panels` — verify contains
     "Router Decisions", "Cost Guard", "Circuit Breaker", "Budget
     Usage", "LLM Calls", "Latency", "Semantic Cache", "Tool Calling
     Mode", "Ideality Metric".
   - `test_panels_have_valid_prometheus_queries` — each panel
     `targets[0].expr` is a non-empty string.

Definition of Done:
- `ops/grafana/dashboards/llm-cost-router.json` создан с 9 panels.
- `ops/grafana/provisioning/dashboards/provider.yml` обновлён.
- Dashboard visible в Grafana at http://localhost:3000 → "Phase 3"
  folder → "Phase 3 — Cost-Aware Router & Cache".
- 3+ unit тестов зелёные.
- Phase 3 control point Δф/Δсложности = 4/2 = 2.0 displayed as
  stat panel.

Антипаттерны:
- НЕ хардкодь PromQL expressions с absolute time ranges — используй
  `[5m]`, `[1h]`, `[24h]` relative ranges.
- НЕ делай dashboard без `refresh: 30s` — ops needs live data.
- НЕ делай "Ideality Metric" panel как PromQL query — hardcoded
  `4/2` value с mapping display (stat panel).

Связанные ADR:
- Реализует: ROADMAP §15.3 Phase 3 control point visualization.
- Применяет: принцип #23 ТРИЗ (обратная связь — dashboard for
  real-time metric monitoring).
- Зависит от: Блок A-2 (Prometheus metrics), Блок C-7 (router
  decisions logger), все Phase 3 Блоки.
- Расширяется в: Phase 4 — `local_llm_dashboard.json` (Ollama
  metrics, GPU memory, queue depth), Phase 5 — `session_store_
  dashboard.json`.
- Не затрагивает: Phase 1/2 dashboards (existing preserved).
```

---

## 9. Приложение: чек-лист выхода из Phase 3

| # | Критерий | Где проверяется | Соответствующий блок промптов |
|---|---|---|---|
| 1 | ADR-011 Approved: hit rate cache >15% | `scripts/ab_test_semantic_cache.py` exit 0 | B-6, E-1 |
| 2 | ADR-011 Approved: stale answers <1% | `tests/integration/test_stale_answer_guard.py` | B-7, E-1 |
| 3 | ADR-011 Approved: latency cache hit <100мс | `scripts/ab_test_semantic_cache.py` (avg_latency_hit_ms < 100.0) | B-6 |
| 4 | ADR-011 rollback not triggered | `ab_test_semantic_cache.py` verdict ≠ "ROLLBACK" | B-6 |
| 5 | ADR-015 Approved: 1 месяц shadow mode | `scripts/ab_test_router_shadow_mode.py` (manual, 30-day run) | C-7, E-2 |
| 6 | ADR-015 Approved: cost predictability ±10% | `ShadowModeResult.cost_predictability() <= 0.10` | E-2 |
| 7 | ADR-015 Approved: cost overrun <20% | `ShadowModeResult.cost_overrun_rate() <= 0.20` | E-2 |
| 8 | ADR-015 Approved: switching decisions logged | operational stream contains `event_type: "router_decision"` | C-7 |
| 9 | ADR-016 Approved: pilot на Ollama success rate ≥80% | `scripts/pilot_ollama_react.py` verdict = PASS | D-6, E-3 |
| 10 | ADR-016 Approved: capability matrix покрывает все модели в `LLMRouter` | `config/model_capabilities.yaml` entries match router providers | D-1 |
| 11 | ADR-016 rollback not triggered | `pilot_ollama_react.py` verdict ≠ "ROLLBACK" | D-6 |
| 12 | ADR-004 preview Approved: LLM Client отвечает на `list_tools` от external MCP client | `scripts/probe_mcp_server.py` exit 0 | H-4, E-4 |
| 13 | ADR-004 preview Approved: LLM Client отвечает на `call_tool` от external MCP client | `scripts/probe_mcp_server.py` (per-tool call) | H-4, E-4 |
| 14 | Метрика идеальности Phase 3: Δф=+4, Δсложности=+2 (net after `fallback_chain` упразднение) | `ARCHITECT.md` §15.3 + Grafana dashboard | F-1, F-2 |
| 15 | `ARCHITECT.md` § 7 ADR обновлён | `analytics/ARCHITECT.md` v1.4.0 contains ADR-011/015/016 + ADR-004 ускорение — Status Approved | F-1 |
| 16 | `ARCHITECT.md` § 8 Trade-offs: C-6 fully resolved, C-7, C-9 resolved | `ARCHITECT.md` §8 | F-1 |
| 17 | `ARCHITECT.md` § 12 Q-5 closed | `ARCHITECT.md` §12 | F-1 |
| 18 | Phase 3 CI pipeline runs green | `scripts/ci-local-staging.sh` exit 0 | E-5 |
| 19 | All Phase 3 unit tests pass | `pytest tests/unit/ -k "phase3"` | All |
| 20 | All Phase 3 integration tests pass | `pytest tests/integration/` (9 new Phase 3 tests) | All |
| 21 | Phase 3 control point Grafana dashboard visible | http://localhost:3000 → "Phase 3" folder | F-2 |
| 22 | Anthropic case в `LLMProviderFactory` unblocked | `LLMProviderFactory.create("anthropic", ...)` returns `ChatAnthropic` (не NotImplementedError) | C-5 |
| 23 | ADR-005 `fallback_chain` Superseded | `provider.py` comment updated; ADR-015 migration plan executed | C-6 |
| 24 | Three-tier cache: Tier-3 Redis DB 2 active | `python scripts/verify_redis_db2.py` OK | A-1, B-1 |
| 25 | Three-tier cache: Tier-1 `documents_facts` table created | `alembic upgrade head` succeeds | A-3, B-2 |
| 26 | MCP Server `/mcp/tools` returns 4 tools | `curl http://localhost:8000/mcp/tools` returns 4 entries | H-1, H-2 |
| 27 | ToolCallingAdapter mode selection works | `pytest tests/unit/test_tool_calling_adapter.py` | D-3, D-5 |

**При невыполнении п.1-4 (ADR-011)**: rollback semantic cache (set `SEMANTIC_CACHE_ENABLED=false`); investigate invalidation logic (B-3) or cosine sim threshold (B-1) или embedding model quality.

**При невыполнении п.5-8 (ADR-015)**: rollback router (set `LLM_ROUTER_ENABLED=false`); investigate circuit breaker threshold (C-4) or cost table accuracy (C-1) или budget threshold (C-3).

**При невыполнении п.9-11 (ADR-016)**: rollback tool calling adapter (keep using `llm.bind_tools` directly); investigate ReAct prompt variant (D-4) или capability matrix entries (D-1) или parse logic (D-3).

**При невыполнении п.12-13 (ADR-004 preview)**: rollback MCP Server (set `MCP_SERVER_ENABLED=false`); investigate route registration (H-1) или tool registry (H-2) или SSE transport (H-3).

**При невыполнении п.14 (метрика идеальности)**: Phase 3 не закрыт; повторный ТРИЗ-анализ (ROADMAP §18.6) — определить, какие абстракции over-engineered (ROADMAP §13.1 риск); consider Speculative label (ROADMAP §13.6 "Implemented but unused").

**При невыполнении п.15-17 (документация)**: docs lag; allocate 1 чел-дн на F-1 + F-2 (бюджет заложен в Phase 3 estimate).

---

## 10. Карта промптов для быстрого навигации

| ID | Промпт | Зависимости | Срок (чел-дн) |
|---|---|---|---|
| A-1 | Redis DB 2 для semantic cache | Phase 2 ADR-010 (Redis DB 1 pattern) | 0.5 |
| A-2 | Prometheus exporter для LLM call metrics | Phase 1 AG-2 TokenUsageTracker | 1.0 |
| A-3 | Alembic миграция `009_create_documents_facts` | Phase 2 migration 008 | 1.0 |
| B-1 | `SemanticAnswerCache` (Tier-3) | A-1, A-2 | 1.5 |
| B-2 | `FactsExtractor` (Tier-1) | A-3 | 1.5 |
| B-3 | `CacheInvalidator` | B-1 | 1.0 |
| B-4 | `CacheAwareLLMClient` wrapper | B-1 | 1.0 |
| B-5 | Pipeline integration (graph + cache) | B-4 | 1.0 |
| B-6 | Metrics + A/B test framework | B-1, A-2 | 1.0 |
| B-7 | Stale-answer guard (integration test) | B-1, B-3 | 1.0 |
| C-1 | `ModelCostTable` (формализация `_COST_PER_1M`) | Phase 1 AG-2 | 1.0 |
| C-2 | `LLMRouter` interface + policies | C-1, A-2 | 2.0 |
| C-3 | `CostGuard` (monthly budget, 80% threshold) | C-2, A-2 | 1.0 |
| C-4 | `CircuitBreaker` (per-provider) | C-2, A-2 | 1.0 |
| C-5 | Anthropic case в `LLMProviderFactory` | Phase 1 AG-2 | 0.5 |
| C-6 | Migration plan: `fallback_chain` → `LLMRouter` | C-2 | 0.5 |
| C-7 | Shadow-mode metrics logger | C-2, Phase 1 ADR-014 | 1.0 |
| D-1 | `ModelCapabilityMatrix` + YAML registry | C-1 (pattern) | 1.0 |
| D-2 | `ToolCallingMode` enum | D-1 | 0.5 |
| D-3 | `ToolCallingAdapter` (native/react/hybrid) | D-1, D-2 | 2.0 |
| D-4 | `ReactToolCallPromptBuilder` | D-3 | 1.0 |
| D-5 | Integration в `build_agent_graph` | D-3, B-5 | 1.0 |
| D-6 | Pilot на Ollama + Llama 3.1 | D-3, D-5 | 0.5 |
| H-1 | `McpServer` class (FastAPI routes) | Phase 1 AG-0, Phase 2 AG-5/AG-6 | 3.0 |
| H-2 | `ExposedToolRegistry` | H-1 | 1.0 |
| H-3 | Transport: SSE per ADR-007 | H-1, Phase 1 AG-3 | 1.0 |
| H-4 | Probe / health-check от external MCP client | H-1, H-2, H-3 | 1.0 |
| G-1 | `render_router_policy` (settings panel) | C-2, Phase 2 G-4 | 0.5 |
| G-2 | `render_tool_calling_mode` (settings panel) | D-2, Phase 2 G-4 | 0.5 |
| G-3 | `render_mcp_server_toggle` (settings panel) | H-1, Phase 2 G-4 | 0.5 |
| E-1 | Semantic cache hit-rate test CI integration | B-6 | 0.3 |
| E-2 | Cost predictability shadow-mode test | C-7 | 0.5 |
| E-3 | ReAct success-rate test procedure | D-6 | 0.3 |
| E-4 | MCP Server preview probe CI integration | H-4 | 0.3 |
| E-5 | Phase 3 CI pipeline extension | E-1..E-4 | 1.1 |
| F-1 | `ARCHITECT.md` update v1.3.0 → v1.4.0 | All Phase 3 blocks | 1.0 |
| F-2 | Grafana dashboard `llm-cost-router.json` | A-2, all blocks | 1.5 |
| **Итого** | **37 промптов** | | **~35.5 чел-дн** |
| | (без Блока G опционального: ~33.5 чел-дн per ROADMAP §7.2) | | |

**Параллелизация**

При команде из 3 разработчиков:

- **Dev 1 (Backend/ML, focus ADR-011)**: A-1 (0.5) → B-1 (1.5) → B-2 (1.5) → B-3 (1.0) → B-4 (1.0) → B-5 (1.0) → B-6 (1.0) → B-7 (1.0) = **8.5 чел-дн**
- **Dev 2 (Backend, focus ADR-015 + ADR-016)**: A-2 (1.0) → C-1 (1.0) → C-2 (2.0) → C-3 (1.0) → C-4 (1.0) → C-5 (0.5) → C-6 (0.5) → C-7 (1.0) → D-1 (1.0) → D-2 (0.5) → D-3 (2.0) → D-4 (1.0) → D-5 (1.0) → D-6 (0.5) = **14.5 чел-дн**
- **Dev 3 (Backend/DevOps, focus ADR-004 + tests + docs)**: A-3 (1.0) → H-1 (3.0) → H-2 (1.0) → H-3 (1.0) → H-4 (1.0) → E-1 (0.3) → E-2 (0.5) → E-3 (0.3) → E-4 (0.3) → E-5 (1.1) → F-1 (1.0) → F-2 (1.5) = **12.0 чел-дн**
- (опционально Dev 4 Frontend): G-1 (0.5) + G-2 (0.5) + G-3 (0.5) = **1.5 чел-дн**

Сумма: 8.5 + 14.5 + 12.0 + 1.5 = 36.5 чел-дн (близко к оценке 35.5; отличие от 35.5 за счёт overhead на coordination, код review).

**Зависимости между блоками**

1. **A → B/C/D**: инфра (Redis DB 2, Prometheus metrics, documents_facts table) требуется для всех 3 ADR.
2. **C-1 → C-2 → C-3/C-4**: `ModelCostTable` → `LLMRouter` → `CostGuard` / `CircuitBreaker`.
3. **D-1 → D-2 → D-3 → D-5**: `ModelCapabilityMatrix` → `ToolCallingMode` → `ToolCallingAdapter` → graph integration.
4. **B-1 → B-3 → B-7**: cache → invalidator → stale-answer guard.
5. **H-1 → H-2 → H-3 → H-4**: McpServer → registry → SSE transport → probe.
6. **C-5 (Anthropic unblock) параллелен D-1**: разные subsystems, могут делаться simultaneously.
7. **G-1/G-2/G-3 (optional UI)**: после C-2/D-2/H-1 соответственно, для backends готовы.
8. **E-1..E-5 (tests/CI)**: после соответствующих блоков B/C/D/H.
9. **F-1/F-2 (docs)**: финальные, после всех остальных.

**Переход к Phase 4 (Local LLM)**

Phase 4 добавляет (per `ROADMAP.md` v1.2.0 §8 + `BACKLOG.md` v1.1.0 §3.4):
- **ADR-009**: Plugin registry (расш. ADR-001 cycle detection with embeddings; local LLM plugin via Ollama).
- **AG-7**: `mcp_call` tool / `mcp_invoker` нода (LLM Client as MCP **client** для вызова external MCP servers).
- **Full Ollama case** в `LLMProviderFactory.create("ollama")` (pilot ADR-016 validated in Phase 3, full integration in Phase 4).
- **BGE local embeddings** для semantic cache (Блок B-1 Phase 3 used OpenAIEmbeddings; Phase 4 — local BGE via sentence-transformers, no OpenAI API per cache write).
- **Redis Vector Library** (HNSW index) для semantic cache (Блок B-1 Phase 3 used SCAN O(N); Phase 4 — O(log N) similarity search).
- **Custom ReAct prompts per model family** (Llama vs Mistral имеют разные prompt preferences).

См. `BETA-PROMPTS.md` v1.0.0 (этот документ — завершение Phase 3) → `GAMMA-PROMPTS.md` или `PHASE4-PROMPTS.md` (Phase 4, future, создать в Phase 3 конце).

---

## 11. История изменений

| Версия | Дата | Изменение |
|---|---|---|
| 1.0.0 | 2026-09-30 | Initial draft. Создан в конце Phase 2 (Alpha) / начале Phase 3 (Beta) per `ALPHA-PROMPTS.md` v1.1.0 §10 closing paragraph: "См. `BETA-PROMPTS.md` (драфт, создать в Phase 2 конце)". Содержит 37 промптов в 8 блоках (A — инфра Phase 3; B — ADR-011 Semantic Cache; C — ADR-015 Cost-Aware Router; D — ADR-016 Tool Capability Adapter; H — ADR-004 ускорение MCP Server preview; G — опциональные UI-расширения; E — тесты/CI; F — документация и метрика идеальности). Покрывает Phase 3 = 31 чел-дн ADR-работы + 2.5 чел-дн overhead = 33.5 чел-дн per `ROADMAP.md` v1.2.0 §7.2 (без опционального Блока G). Резолвит C-6 (fully), C-7, C-9, ИКР-0 (preview); Q-5 (fully closed), Q-1 (partially closed preview). Предусловие: Phase 2 завершена (`ARCHITECT.md` v1.3.0, `ALPHA-PROMPTS.md` v1.1.0). |

# ROADMAP.md — Дорожная карта развития LLM Client

| Атрибут | Значение |
|---|---|
| Версия документа | 1.2.0 |
| Дата | 2026-09-26 |
| Changelog | 1.2.0 (2026-09-26): AG-составляющая (agent-service) добавлена в Phase 1 (новый §5.8 + строка 5.2.5 в таблице работ + п.6–10 в §5.6 критерии выхода) — применение принципа ТРИЗ #19 (переход в другое измерение) и закрытие пробелов D–G из `BACKLOG.md` v1.1.0 §2.3. В Phase 1 добавлены AG-0..AG-4 (scaffold FastAPI + LangGraph graph + LLMProviderFactory + SSE event protocol + file_export tool, суммарно +7.5 чел-дн); Phase 1 суммарно: 14.5 → 22.5 чел-дн. Phase 2: +5 чел-дн (AG-5 web_search + AG-6 rag_query). Phase 4: +3 чел-дн (AG-7 mcp_call). §15.2 метрика идеальности Phase 1 пересчитана (Δф=+6, Δсложности=+3 → 2.0). Источники патча: `BACKLOG.md` v1.1.0, `AG-PROMPTS.md` v1.0.0. \| 1.1.0 (2026-09-23): `UIClient` abstraction вынесена из Phase 5 (внутри ADR-018) в Phase 1 (новый §5.7) — применение принципа ТРИЗ #16. В Phase 1 добавлены UI-0..UI-3 (+6.5 чел-дн); Phase 1: 8 → 14.5 чел-дн. Phase 5 ADR-018 сужен до `SessionStore` + `RedisSessionStore`. \|
| Статус | Draft → Review → Approved |
| Аудитория | Tech-лид + команда разработки LLM Client |
| Связанные документы | `ARCHITECT.md` v1.2.0, `TRIZ-ANALYSIS.md` v1.0.0, `BACKLOG.md` v1.1.0, `UI-PROMPTS.md` v1.0.0, `AG-PROMPTS.md` v1.0.0 |
| Период планирования | 14–16 недель при команде из 2 разработчиков |
| Суммарная оценка | ~134.5 чел-дн (v1.0.0: ~110; v1.1.0: ~121.5 (+6.5 на UI-0..UI-3 Phase 1, +6 на UI-5 Phase 5); v1.2.0: +13 на AG-0..AG-4 Phase 1, +5 на AG-5/AG-6 Phase 2, +3 на AG-7 Phase 4) на 12 новых ADR + 3 расширения существующих ADR + UI-0..UI-3 (Phase 1) + UI-5 (Phase 5) + AG-0..AG-7 (Phase 1, 2, 4) |
| Принцип планирования | Фазирование по этапам зрелости MVP → Alpha → Beta → Local LLM → Scale → Interoperability |
| Привязка к ТРИЗ | Каждая фаза резолвит явный набор противоречий из `TRIZ-ANALYSIS.md` § 10 |

---

## 1. Введение

### 1.1 Назначение документа

`ROADMAP.md` фиксирует упорядоченный план внедрения архитектурных изменений в LLM Client, выведенных из ТРИЗ-анализа (`TRIZ-ANALYSIS.md` v1.0.0). Документ не вводит новые архитектурные решения — он задаёт **последовательность и условия их внедрения**, привязывая каждое решение (ADR) к конкретной фазе развития продукта. Каждая фаза преследует ясную бизнес-цель, имеет формальные критерии выхода и ограниченный набор зависимостей. Это исключает две типовые болезни дорожных карт: «внедрить всё сразу» (over-engineering) и «внедрять без приоритетов» (ad-hoc рефакторинг).

Документ предназначен для использования на трёх уровнях принятия решений. **Архитектурный комитет** использует `ROADMAP.md` как реестр запланированных ADR с приоритетами и формальными критериями готовности. **Tech-лид** использует его как инструмент планирования спринтов: каждая фаза декомпозируется в набор задач с оценкой в чел-дн. **Команда разработки** использует его как путеводитель по контексту каждого ADR: какие противоречия он резолвит, от чего зависит, какие риски несёт.

### 1.2 Связь с `ARCHITECT.md` и `TRIZ-ANALYSIS.md`

`ARCHITECT.md` v1.0.0 фиксирует текущее состояние архитектуры LLM Client: 7 слоёв (Presentation, Orchestration, LLM Provider, Tool, RAG, MCP Client, Persistence), 8 принятых ADR (ADR-001..ADR-008), явный список Trade-offs и Открытых вопросов. Документ описывает систему «как есть».

`TRIZ-ANALYSIS.md` v1.0.0 применяет к текущей архитектуре аппарат ТРИЗ: формулирует 15 технических противоречий (C-1..C-15), 4 ключевые вепольные триады, ИКР-0..ИКР-7 и предлагает 12 новых ADR (ADR-009..ADR-020) + 3 расширения существующих ADR для их разрешения. Документ описывает систему «как должно быть».

`ROADMAP.md` — мостовый документ: он описывает **путь** от «как есть» к «как должно быть», разбитый на 6 фаз с явными критериями выхода, оценкой трудозатрат и зависимостями. Каждое архитектурное решение внедряется не ранее, чем система достигает фазы, для которой это решение предназначено.

### 1.3 Принципы планирования

План построен на пяти принципах, вытекающих из ТРИЗ-методологии и инженерной практики:

1. **Принцип фазовой готовности.** Каждый ADR внедряется только в той фазе, к которой он привязан. Внедрение ADR-019 (signed manifests) в Phase 1 — over-engineering; внедрение ADR-013 (SSE+cancel) в Phase 6 — упущенная выгода. Фаза задаёт контекст, в котором ADR окупается.

2. **Принцип минимальной достаточности.** На каждой фазе внедряется ровно тот набор ADR, который нужен для перехода в следующую фазу. «Хороший план» — не «всё, что можно», а «всё, что необходимо». Избыточные ADR откладываются или отбрасываются.

3. **Принцип контроля идеальности.** Каждый ADR оценивается по метрике `Δфункциональности / Δсложности ≥ 1`. Если после внедрения ADR метрика падает — ADR откатывается (см. § 15). Это защита от «ложной зрелости» — ситуации, когда система выглядит «взрослой», но фактически перегружена абстракциями.

4. **Принцип пилотного внедрения.** Ни один ADR с уровнем сложности Medium или High не внедряется в production без пилотного теста на staging (см. § 14). Пилот провалился → ADR пересматривается, не внедряется. Это снижает риск регресса архитектуры.

5. **Принцип явной суперседенции.** Каждый новый ADR, противоречащий существующему, обязан содержать раздел `Supersedes:` с указанием заменяемого ADR и `Migration plan:`. Архитектурный комитет ревьюит конфликты перед approval. Это предотвращает накопление «зомби-ADR» — принятых, но фактически упразднённых решений.

### 1.4 Как читать документ

Документ структурирован по линии «стратегия → фазы → риски → процесс»:

- **Раздел 2** описывает контекст: бизнес-цели G-1..G-5, текущее состояние, ограничения.
- **Раздел 3** вводит принципы фазирования и критерии перехода.
- **Раздел 4** даёт сводную таблицу всех фаз с суммарными оценками.
- **Разделы 5–10** детализируют каждую из 6 фаз: цели, состав работ, ссылки на ADR, критерии выхода.
- **Раздел 11** описывает критический путь и возможности параллелизации.
- **Раздел 12** фиксирует quick wins для немедленного внедрения.
- **Раздел 13** перечисляет риски и контр-меры.
- **Раздел 14** описывает пилотное тестирование и метрики успеха.
- **Раздел 15** вводит метрику идеальности и контрольные точки.
- **Раздел 16** описывает процесс ревью и принятия ADR.
- **Раздел 17** переносит открытые вопросы из `ARCHITECT.md`.
- **Раздел 18** фиксирует ближайшие шаги.
- **Раздел 19** содержит глоссарий и ссылки на связанные документы.

Каждая фаза описана по единому шаблону: **цели фазы → состав работ → детализация ADR → критерии выхода**. ADR с уровнем `Low` описаны кратко (1–2 абзаца), `Medium` и `High` — с существенными деталями и контекстом.

---

## 2. Контекст и стратегические цели

### 2.1 Бизнес-цели (G-1..G-5)

LLM Client преследует пять бизнес-целей, зафиксированных в `ARCHITECT.md` § 2. Эти цели являются верхнеуровневой системой координат, относительно которой измеряется прогресс каждой фазы:

| ID | Функция | Главная полезность | Где реализована |
|---|---|---|---|
| G-1 | RAG-поиск по документам | Сокращение времени аналитика на поиск по корпоративному корпусу | RAG Layer + Tool Layer (`rag_query`) |
| G-2 | Унифицированный доступ к LLM | Один UI для всех провайдеров (OpenAI, Anthropic, локальные) | LLM Provider Layer + Settings Panel |
| G-3 | Инструментальный слой | Автоматизация рутины (веб-поиск, файловый экспорт, MCP-вызовы) | Tool Layer + MCP Client Layer |
| G-4 | Аудит и воспроизводимость | 100% логирование с trace, retention 90+ дней | Persistence Layer + Observability |
| G-5 | MVP за 3 недели | Time-to-MVP ≤ 15 чел-дн | Streamlit + LangGraph как ускорители |

Каждый ADR в `ROADMAP.md` явно помечен, какие из G-1..G-5 он улучшает, а какие может ухудшить (см. § 4 сводную таблицу фаз). Это позволяет архитектурному комитету видеть чистый эффект каждого решения.

### 2.2 Текущее состояние архитектуры

На момент составления плана (`ARCHITECT.md` v1.0.0) LLM Client находится в стадии «работающий MVP»: базовая функциональность (RAG, LLM-чат, инструменты, MCP) реализована и работает в единичном инстансе; архитектура зафиксирована в 8 ADR; но накопленные Trade-offs (8 штук в `ARCHITECT.md` § 8) и 5 открытых вопросов (Q-1..Q-5 в `ARCHITECT.md` § 12) указывают на неразрешённые противоречия. Эти противоречия не блокируют работу MVP, но блокируют масштабирование до production-нагрузки и расширение до multi-instance.

Ключевые узкие места текущей архитектуры (см. `TRIZ-ANALYSIS.md` § 4 — анализ по 9 законам развития):

- **Presentation Layer** — Streamlit single-instance, sticky session, синхронный file rendering. Блокирует horizontal scale.
- **Orchestration Layer** — синхронный PostgreSQL checkpoint на каждом node transition (50–200 мс на цикл). Блокирует рост RPS.
- **LLM Provider Layer** — `fallback_chain` без учёта стоимости. Блокирует предсказуемость budget.
- **Tool Layer** — нативный function calling без ReAct-fallback. Блокирует локальные модели без tool-mode.
- **RAG Layer** — triple store (Chroma/Qdrant/pgvector) с factory-паттерном, pure vector retrieval без reranker. Переразвит по числу хранилищ, недоразвит по качеству поиска.
- **MCP Client Layer** — жёсткая привязка транспорта в конфиге, нет signed manifests. Блокирует доверенную интеграцию с внешними MCP-серверами.
- **Persistence Layer** — local file storage в MVP, отсутствие tiered storage, ежедневные dump-ы вместо PITR. Блокирует multi-instance и audit-compliance.

ТРИЗ-анализ показал, что 8 из 15 противоречий имеют приоритет **High** (блокируют Production): C-1 (Streamlit+scale), C-2 (PG checkpoint latency), C-4 (SSE one-way), C-6 (RAG context cost), C-7 (fallback cost), C-8 (MCP stdio docker), C-11 (PII vs observability), C-12 (MCP trust). Они получают приоритет в ранних фазах плана.

### 2.3 Ключевые ограничения и предположения

План построен при следующих предположениях. Отклонение от любого из них требует ревизии плана архитектурным комитетом.

1. **Размер команды.** Постоянная команда — 2 backend-разработчика с опытом Python/LangChain. Дополнительно: 1 DevOps-инженер на 0.3 FTE (для инфраструктурных ADR — ADR-014 KMS, ADR-019 Vault, ADR-010 Redis). Без DevOps-поддержки фазы 1–2 задерживаются на 30%.

2. **Инфраструктура.** Доступно: PostgreSQL 15+, Redis 7+, MinIO/S3-совместимое хранилище, Docker Compose для dev/staging. Недоступно: managed K8s (до Phase 5), managed Vector DB (до Phase 3), выделенный KMS (до Phase 1 — fallback на local Vault dev-mode).

3. **Внешние API.** OpenAI и Anthropic доступны и бюджетированы (Q-2 в `ARCHITECT.md` — LangSmith pricing — отдельный вопрос). Cohere Rerank опционален — fallback на локальный `bge-reranker-base`. Внешние MCP-серверы (filesystem, github) — текущий набор; новые добавляются по запросу.

4. **Совместимость.** Все новые ADR обратно совместимы с существующим API LLM Client на уровне контракта `BaseChatModel` / `StateGraph` / `VectorStore`. Любой ADR, ломающий совместимость — помечен `Breaking:` и требует явного `Migration plan:`.

5. **Тестирование.** Минимальное покрытие unit-тестами — 70% на новых модулях. Для ADR с уровнем `High` обязательно пилотное внедрение на staging с метриками успеха (см. § 14).

6. **Документация.** Каждый ADR сопровождается: обновлением `ARCHITECT.md` (раздел ADR/Trade-offs), код-примером, паттерном unit-теста. Onboarding-session для команды — обязательна.

---

## 3. Принципы фазирования

### 3.1 Логика разбиения на фазы

Фазы соответствуют стандартному roadmap-у для LLM-стека: **MVP → Alpha → Beta → Local LLM → Scale → Interoperability**. Каждая фаза имеет явный фокус — набор противоречий, которые она резолвит, и набор ADR, которые она внедряет. Фазы не изолированы: каждая следующая фаза предполагает, что предыдущая выполнена полностью (или частично при явном параллелизме — см. § 11).

| Фаза | Фокус | Резолвимые противоречия (из `TRIZ-ANALYSIS.md` § 10) | Главные улучшаемые G |
|---|---|---|---|
| **Phase 1 — MVP** | UX-cancel, PII compliance, dev-prod parity | C-4, C-11, C-15 | G-4, G-5 |
| **Phase 2 — Alpha** | Latency, RAG quality | C-2, C-6 (частично) | G-1, G-4 |
| **Phase 3 — Beta** | Cost, model portability, надсистема | C-6 (полностью), C-7, C-9 | G-2, G-3 |
| **Phase 4 — Local LLM** | Плагины, MCP parity, determinism | C-3, C-5, C-8, C-14 | G-2, G-3 |
| **Phase 5 — Scale** | Multi-instance, security, async file | C-1, C-10, C-12, C-13 | G-1, G-4 |
| **Phase 6 — Interoperability** | MCP Server, embed mode | ИКР-0 (надсистема) | G-3 |

Фаза 1 завершается полным отказом от MVP-компромиссов (single instance, sync file rendering, local storage). Фаза 3 — переходом к production-ready (cost predictability, semantic cache, MCP server). Фаза 6 — переходом в надсистему (LLM Client как MCP-сервер для других инструментов) — реализация ИКР-0.

### 3.2 Критерии перехода между фазами

Переход из фазы N в фазу N+1 требует **одновременного** выполнения трёх условий:

1. **Все ADR фазы N имеют статус `Approved` или `Superseded`**. Статус `Proposed` или `Needs revision` блокирует переход. Архитектурный комитет ревьюит статусы в конце фазы.

2. **Все пилоты фазы N успешны**. Метрики успеха (см. § 14) достигнуты. Критерий отката ни для одного пилота не сработал. Если пилот провалился — ADR возвращается на доработку, фаза продлевается.

3. **Метрика идеальности системы не упала** (см. § 15). Значение `Δф / Δсложности` на конец фазы ≥ значения на конец предыдущей фазы. Падение метрики — триггер для ревизии плана.

Дополнительно: переход в Phase 5 (Scale) требует, чтобы инфраструктура (K8s или аналог) была готова. Переход в Phase 6 (Interoperability) требует, чтобы ADR-004 (MCP Server mode, ускоренный в Phase 3) был полностью внедрён.

### 3.3 Принцип «delta функциональности / delta сложности ≥ 1»

Каждый ADR оценивается по вкладу в идеальность системы — фундаментальный закон развития технических систем (закон 4.4 в `TRIZ-ANALYSIS.md`):

```
Идеальность = Σ функциональных возможностей / Σ сложности компонентов
```

`Σ функциональности` измеряется числом capabilities (RAG, tools, MCP, streaming, etc.) и метриками качества (recall, precision, latency).
`Σ сложности` измеряется числом ADR, числом абстракций, LOC, числом внешних зависимостей.

**Контрольное неравенство**: для каждого нового ADR `Δфункциональности / Δсложности ≥ 1`. Это значит: каждый новый ADR должен добавлять не меньше функциональности, чем сложности.

Пример нарушения: ADR добавляет 1 новую capability и 3 новые абстракции. `1/3 < 1` — ADR откатывается или пересматривается.

Пример выполнения: ADR-011 (semantic cache) добавляет 1 capability (semantic cache) и 1 абстракцию (Tier-3 cache), но упраздняет явный context-compression — суммарная `Δф=+1, Δсложности=0` — ADR Approved.

### 3.4 Защита от over-engineering

ТРИЗ-анализ предлагает 12 новых ADR. Внедрение всех разом превратит архитектуру в «франкенштейна» с избыточной абстракцией. ТРИЗ даёт явный инструмент защиты — принцип #16 (частичное/избыточное действие): **внедрять абстракцию «избыточно» (полный interface), но имплементировать «частично» (одна реализация). Когда появится вторая реализация — interface уже готов.**

Конкретные применения:

- `UIClient` abstraction: interface полный (4 метода — `render_message`, `render_artifact`, `stream_token`, `handle_user_input`), имплементация — только `StreamlitClient` (**Phase 1**, см. §5.7 и `UI-PROMPTS.md` Блок U2). Когда появится `ChainlitClient` (Phase 5, UI-5 из `BACKLOG.md` §3.3) — добавляется имплементация, interface не меняется. Когда появится `FastAPIClient` (Phase 5+, UI-6) — то же самое. До патча v1.1.0 `UIClient` неявно относился к Phase 5 (внутри ADR-018); патч выносит его в Phase 1 как применение принципа #16 — иначе весь UI-код Phase 1–4 пишется под Streamlit-specific API, и Phase 5 становится переписыванием, а не добавлением имплементации.
- `MCPTransport`: interface полный, имплементация — только StdioTransport + SSETransport. WebSocket добавляется при появлении прод-сценария.
- `VectorStoreRegistry`: registry полный, имплементации — Chroma, Qdrant, pgvector. Четвёртая имплементация (Weaviate?) добавляется по требованию.
- `ToolCallingAdapter`: adapter полный, режимы — native + react. Hybrid mode добавляется при появлении модели, где native unstable.
- `LLMRouter`: router полный, политики — cost/latency. Privacy policy добавляется при появлении zero-retention требований.

Это позволяет не плодить «мёртвые» имплементации, но держать архитектуру готовой к расширению.

---

## 4. Сводная таблица фаз

| Фаза | ADR в фазе | Суммарная сложность | Срок (чел-дн) | Главный эффект | Зависимости |
|---|---|---|---|---|---|
| **Phase 1 — MVP** | ADR-013, ADR-014, (расш. ADR-008), **UI-0..UI-3 (new в v1.1.0)** | Low + Medium + Low + Low×3 | **14.5** (было 8 в v1.0.0; +6.5 на UI-0..UI-3) | UX: cancel работает, UI scaffold + base elements + UIClient abstraction; Compliance: PII+trace; Dev-prod parity; Подготовка к Phase 5 (UIClient готов, Phase 5 = добавление ChainlitClient без переписывания) | Redis, KMS/Vault, MinIO |
| **Phase 2 — Alpha** | ADR-010, ADR-017, ADR-020 | Medium × 3 | **14** | Latency ↓ 50–200 мс; RAG precision ↑ 20–30%; Recall ↑ для точных терминов | Redis, bge-reranker, PostgreSQL tsvector |
| **Phase 3 — Beta** | ADR-011, ADR-015, ADR-016, ADR-004 ускорить | High × 4 | **31** | LLM cost ↓ 60–80%; Cost predictability; Model portability; Переход в надсистему | Redis, Observability stack, — |
| **Phase 4 — Local LLM** | ADR-009, ADR-012, (расш. ADR-001) | Medium × 2 + Low | **13** | VectorStore extensibility; Dev-prod parity MCP; Determinism | —, —, Embeddings model |
| **Phase 5 — Scale** | ADR-018 (сужен: только SessionStore), ADR-019, (расш. ADR-008), (новый) ABAC+RBAC, **UI-5 (ChainlitClient, new в v1.1.0)** | Medium + High + Medium + High + High | **31** (v1.0.0: 25; +6 на UI-5 — становится явным) | Multi-instance; Security; Latency ↓ file ops; Granular access; **UI: ChainlitClient как вторая имплементация UIClient** | Redis, Vault+signing, Worker, Auth provider |
| **Phase 6 — Interoperability** | MCP Server mode (full), Embed mode (UI-7) | High + Medium | **18** | LLM Client как MCP-сервер; Встраивание в IDE/Confluence; UI: embed mode использует UIClient interface | ADR-004, — |
| **ИТОГО** | 12 новых ADR + 3 расширения + UI-0..UI-3 (Phase 1, new в v1.1.0) + UI-5 (Phase 5, new в v1.1.0) | — | **~121.5 чел-дн** (v1.0.0: ~110; +6.5 на UI-0..UI-3 Phase 1, +6 на UI-5 Phase 5, остальное UI-7 уже учтено в Phase 6; -1 за счёт округления) | +5 capabilities (cancel, dual-logging, dev-prod parity, UI scaffold + UIClient abstraction), −2 упразднённых (LocalFileStorage, fallback_chain) | — |

**Распределение по приоритету противоречий** (из 15 противоречий в `TRIZ-ANALYSIS.md` § 10):

- 8 High-приоритетных противоречий (C-1, C-2, C-4, C-6, C-7, C-8, C-11, C-12) — резолвятся в Phase 1 (2 шт полностью + C-1 частично через `UIClient`/`Streamlit fragments` в v1.1.0), Phase 2 (1 шт), Phase 3 (3 шт), Phase 5 (2 шт + C-1 полностью через `SessionStore`/`ChainlitClient`).
- 7 Medium-приоритетных противоречий (C-3, C-5, C-9, C-10, C-13, C-14, C-15) — резолвятся в Phase 1 (1 шт), Phase 4 (3 шт), Phase 5 (2 шт), Phase 6 (1 шт).

Все 8 High-приоритетных противоречий резолвятся до конца Phase 5 — это формальный критерий готовности к Production. В v1.1.0 C-1 начинает резолвиться раньше (Phase 1 — частично, через `UIClient` abstraction и `Streamlit fragments`), что приближает финальную резолюцию в Phase 5.

---

## 5. Phase 1 — MVP

### 5.1 Цели фазы

Phase 1 завершает MVP-стадию, устраняя три наиболее критичных компромисса, оставшихся после первоначального MVP (`ARCHITECT.md` § 8 Trade-offs): (а) невозможность отменить запущенный LLM-вызов, (б) отсутствие PII-маскирования в логах, (в) расхождение dev- и prod-окружений из-за локального file storage. Каждое из этих противоречий не блокирует работу MVP в single-instance, но блокирует переход к Alpha: без cancel-кнопки UX остаётся неприемлемым для длинных LLM-вызовов; без PII-маскирования логи нельзя отдавать в общий observability stack; без dev-prod parity каждое расхождение окружений — отдельный класс багов.

В v1.1.0 к Phase 1 добавлена четвёртая цель — **UI-составляющая**: формализация scaffold Streamlit-приложения (UI-0, ранее подразумевавшегося как данное, см. `BACKLOG.md` §2.1 Пробел A), базовые UI-элементы — sidebar истории, кнопки скачивания артефактов, индикатор статуса, бейдж PII (UI-1, ранее не формализованные, см. Пробел B), `UIClient` abstraction с одной имплементацией `StreamlitClient` (UI-2, ранее отложенной в Phase 5, см. Пробел C), и `@st.fragment` для изоляции chat/sidebar re-runs (UI-3, рекомендация из `TRIZ-ANALYSIS.md` §4.3). Без UI-составляющей промпт `C-5` из `MVP-PROMPTS.md` (UI watcher для auto-cancel) не имеет точки интеграции — некуда инжектить JS-фрагмент.

В v1.2.0 к Phase 1 добавлена пятая цель — **AG-составляющая** (agent-service): формализация контейнера `agent-service` из `ARCHITECT.md` §4 (строка 124) как FastAPI-приложения с SSE-эндпоинтами (AG-0, ранее подразумевавшегося как «существующий», см. `BACKLOG.md` §2.3 Пробел D), LangGraph-граф с минимальными нодами `planner` + `final_answer` (AG-1, ранее не формализованный, см. Пробел E), `LLMProviderFactory` с OpenAI через `langchain-openai` (AG-2, ранее не формализованный, см. Пробел F), SSE event protocol — `event: token` / `metadata` / `artifact_ready` / `cancelled` / `error` / `done` (AG-3, ранее не формализованный, см. Пробел G), и `file_export` tool для сохранения артефактов в S3 (AG-4). Без AG-составляющей UI-0 смотрит на `AGENT_SERVICE_URL` где пусто (только `mock_agent_service.py`), UI-1 (PII badge, download buttons, cancelled badge) работает «вхолостую» — нет источника SSE events, ADR-001 (LangGraph) и ADR-007 (SSE) формально приняты, но не имеют имплементации. См. подробное обоснование в `BACKLOG.md` v1.1.0 §2.3–§2.4.

Контрольные цели фазы:

1. **UX cancel**: пользователь может отменить запущенный LLM-вызов в течение 100 мс. UI автоматически отменяет сессию при закрытии вкладки. **UI-часть**: в Streamlit UI есть кнопка Stop, индикатор streaming/cancelled/error (UI-1). **AG-часть**: `event: cancelled` эмитится < 200 мс после `POST /cancel` (AG-3).
2. **Compliance PII + trace**: в operational логах отсутствуют PII (детектированные через Presidio); forensic stream хранит полный trace 90 дней с шифрованием AES-256-GCM. **UI-часть**: PII score отображается бейджем для каждого user message (UI-1). **AG-часть**: `event: metadata` с `pii_score` и `pii_entities` (только типы и span'ы, без PII-текста) эмитится из agent-service (AG-3).
3. **Dev-prod parity**: одно и то же S3-совместимое хранилище (MinIO в dev, S3 в prod) используется для всех файловых артефактов. LocalFileStorage упразднён. **UI-часть**: кнопки скачивания артефактов работают с 4 форматами (md/txt/pdf/docx) через `UIClient.render_artifact` (UI-1). **AG-часть**: `file_export` tool сохраняет артефакты в S3 через `create_file_storage()` (AG-4), `event: artifact_ready` эмитится из agent-service (AG-3).
4. **UI-составляющая (new в v1.1.0)**: `UIClient` ABC существует с 4 методами; `StreamlitClient` — единственная имплементация; весь UI-код ходит через interface, не через Streamlit-specific API. `@st.fragment` применяется к chat area и sidebar. Latency-бенчмарк (U3-3) показывает прирост FPS стриминга ≥30% после fragments. Критерий готовности к Phase 5: добавление `ChainlitClient` не требует переписывания UI-кода — только новой имплементации interface.
5. **AG-составляющая (new в v1.2.0)**: `python -m llm_client.agent` поднимает FastAPI на `:8000` (AG-0); `build_agent_graph(llm, token)` возвращает compiled graph с `planner` + `final_answer` нодами, `graph.astream(...)` отдаёт токены, cancel прерывает граф между нодами (AG-1); `LLMProviderFactory.create("openai", ...)` возвращает `ChatOpenAI`, `token_usage_tracker` логирует usage в operational stream (AG-2); SSE event protocol эмитит token/metadata/cancelled/error/done/artifact_ready (AG-3); `file_export` tool сохраняет артефакты в S3 (AG-4). Критерий готовности к Phase 2: ADR-001 (LangGraph) и ADR-007 (SSE) не просто приняты в `ARCHITECT.md`, но имеют рабочую имплементацию в `src/llm_client/agent/`.

### 5.2 Состав работ

| # | Работа | ADR | Сложность | Срок (чел-дн) | Зависимости |
|---|---|---|---|---|---|
| 5.2.1 | Реализация SSE+HTTP cancel endpoint + Redis pub/sub | ADR-013 | Low | 2 | Redis |
| 5.2.2 | Реализация DualStreamLogger (operational + forensic) | ADR-014 | Medium | 4 | KMS/Vault |
| 5.2.3 | Миграция LocalFileStorage → S3 (MinIO в dev) | (расш. ADR-008) | Low | 2 | MinIO |
| 5.2.4 | **UI-составляющая (new в v1.1.0)**: UI-0 scaffold Streamlit + UI-1 base elements (sidebar/downloads/status/PII badge) + UI-2 `UIClient` ABC + `StreamlitClient` + UI-3 `@st.fragment` для chat/sidebar | (не ADR; формализация Phase 0 + применение ADR-002 + подготовка к ADR-018) | Low + Low + Medium + Low | **6.5** | ADR-001, ADR-002, ADR-007, расш. ADR-008, ADR-013, ADR-014 |
| 5.2.5 | **AG-составляющая (new в v1.2.0)**: AG-0 scaffold FastAPI + AG-1 LangGraph graph (planner + final_answer) + AG-2 `LLMProviderFactory` (OpenAI only) + AG-3 SSE event protocol (token/metadata/artifact_ready/cancelled/error/done) + AG-4 `file_export` tool | (не ADR; формализация контейнера agent-service из ARCHITECT.md §4 + применение ADR-001/ADR-006/ADR-007 + закрытие пробелов D–G из BACKLOG.md v1.1.0 §2.3) | Low + Medium + Low + Medium + Low | **7.5** | ADR-001, ADR-006, ADR-007, расш. ADR-008, ADR-013, ADR-014, B-3 (cycle detection), C-1..C-4 (cancel), D-1/D-5 (PII) |
| — | **Итого Phase 1** | — | — | **22.5** (v1.0.0: 8; v1.1.0: 14.5; v1.2.0: +7.5 на AG) | — |

### 5.3 ADR-013: SSE + HTTP Cancel Endpoint

**Резолвит**: противоречие C-4 (SSE one-way vs interactivity).
**Принципы ТРИЗ**: 15 (динамичность), 26 (переход к другому измерению), 13 (наоборот), 17 (переход в другое измерение).
**Связанные G**: G-4 (аудитируемость — cancel логируется), G-5 (UX MVP).

**Суть**: ADR-007 зафиксировал SSE для streaming LLM-ответов, но отметил: «One-way only: для интерактивных прерываний нужен доп. HTTP endpoint». Решение — dual-channel архитектура: data-plane остаётся SSE (без изменений), control-plane — HTTP POST `/sessions/{id}/cancel` + Redis pub/sub `session:{id}:cancel` для уведомления агента. На стороне агента вводится `CancellationToken`, проверяемый между node-ами графа; при получении cancel-сигнала граф прерывает upstream LLM-вызов и возвращает partial answer. UI-клиент детектирует обрыв SSE-соединения (visibility change / beforeunload) и автоматически шлёт cancel.

**Эффект**:

- (+) Cancel работает мгновенно (Redis pub/sub latency <5 мс).
- (+) Авто-cancel при закрытии вкладки — UX improvement.
- (+) Не нарушает ADR-007 (SSE остаётся для данных).
- (-) Добавляется Redis pub/sub как dependency для control-plane.
- (-) Граф должен явно проверять `CancellationToken` — дополнительный код в каждом node.

**Критерий готовности**: cancel срабатывает за <100 мс в 99% случаев; partial answer возвращается пользователю; forensic stream фиксирует cancel-событие с reason.

### 5.4 ADR-014: Dual-Stream Logging (Encrypted + Masked)

**Резолвит**: противоречие C-11 (PII masking vs observability).
**Принципы ТРИЗ**: 17 (другое измерение), 3 (местное качество), 22 (обратить вред в пользу), 26 (переход к другому измерению).
**Связанные G**: G-4 (compliance + воспроизводимость).

**Суть**: § 9.4 Security требует PII masking, § 9.6 Observability требует full trace retention 90 дней. Противоречие: маскирование ломает воспроизводимость, отсутствие маскирования ломает compliance. Решение — `DualStreamLogger` с двумя потоками: (1) operational stream — маскированный (Presidio + custom regex), отправляется в stdout/Loki/ELK, retention 30 дней, доступ команды для debugging; (2) forensic stream — зашифрованный (AES-256-GCM с ключом из Vault/KMS), отправляется в отдельное S3 bucket с server-side encryption, retention 90+ дней, доступ через отдельный RBAC (security officer + аудит-комитет). PII detection score сохраняется в `messages` таблице как metadata для аналитики. В dev-окружении forensic stream отключён, только operational.

**Эффект**:

- (+) Compliance удовлетворён (PII не в operational логах).
- (+) Воспроизводимость сохранена (forensic логи).
- (+) Аналитика по sensitive data (через PII score).
- (-) Двойная стоимость хранения логов.
- (-) Сложность доступа к forensic (отдельный RBAC, аудит).
- (-) Ключи шифрования в KMS — ещё одна зависимость.

**Критерий готовности**: PII leaks в operational stream = 0 (автоматизированный audit); forensic stream доступен security officer в течение 24 часов по запросу; retention 90 дней обеспечен.

### 5.5 (расш. ADR-008): Single S3 Storage

**Резолвит**: противоречие C-15 (Local file storage vs multi-instance).
**Принципы ТРИЗ**: 17 (другое измерение), 13 (наоборот), 28 (замена механической схемы), 5 (объединение).
**Связанные G**: G-5 (dev-prod parity), G-4 (аудитируемость).

**Суть**: ADR-008 зафиксил `LocalFileStorage` для MVP — быстрый старт, но ломает multi-instance (файл сохранён на одном инстансе, недоступен на других) и dev-prod parity (dev использует локальный диск, prod — S3). Расширение ADR-008 упраздняет `LocalFileStorage` и делает S3-совместимое хранилище (MinIO в dev, S3 в prod) единственной имплементацией `FileStorage` interface. Контракт `FileStorage` не меняется — миграция прозрачна для caller-кода.

**Эффект**:

- (+) Dev-prod parity: одно хранилище, одно поведение.
- (+) Multi-instance: любой инстанс читает любой файл.
- (+) Аудитируемость: S3 access logs интегрируются в forensic stream.
- (-) MinIO в dev — ещё один контейнер в docker-compose.
- (-) Latency файловых операций возрастает на 10–50 мс (network vs disk).

**Критерий готовности**: `LocalFileStorage` удалён из кодовой базы; все тесты проходят с MinIO; dev/staging/prod используют один `FileStorage` контракт.

### 5.6 Критерии выхода из фазы

Phase 1 считается завершённой при одновременном выполнении:

1. **ADR-013 Approved**: cancel latency <100 мс в 99% случаев на staging-нагрузке.
2. **ADR-014 Approved**: PII leaks = 0 (automated audit); forensic stream retention 90 дней обеспечен.
3. **(расш. ADR-008) Approved**: `LocalFileStorage` удалён; dev/staging/prod используют S3-only.
4. **UI-составляющая Approved (new в v1.1.0)**: см. `BACKLOG.md` §5.1. UI-0 (scaffold) + UI-1 (sidebar/downloads/status/PII badge) + UI-2 (`UIClient` ABC + `StreamlitClient`, весь UI-код ходит через interface — `grep -r "st\.chat_message\|st\.chat_input\|st\.write_stream" src/llm_client/ui/ | grep -v streamlit_client.py | wc -l` = 0) + UI-3 (`@st.fragment` для chat и sidebar, latency-бенчмарк U3-3 показывает прирост FPS ≥30%).
5. **AG-составляющая Approved (new в v1.2.0)**: см. `BACKLOG.md` §5.2. AG-0 (`python -m llm_client.agent` поднимает FastAPI на `:8000`, `/health` отдаёт 200, `POST /sessions/{id}/chat` принимает промпт, `GET /sessions/{id}/stream` отдаёт SSE-стрим) + AG-1 (`build_agent_graph(llm, token)` возвращает compiled graph; `graph.astream(...)` отдаёт токены; при `token.cancel()` — выход с partial answer на следующем conditional edge; `IterationMonitor` срабатывает на 2 одинаковых итерациях подряд) + AG-2 (`LLMProviderFactory.create("openai", "gpt-4o-mini")` с валидным `OPENAI_API_KEY` возвращает `ChatOpenAI`; `token_usage_tracker` логирует usage в operational stream; `LLM_PROVIDER=anthropic` → `NotImplementedError("Phase 3 (ADR-015)")`) + AG-3 (после `POST /chat` + `GET /stream` UI получает `event: token` × N, `event: metadata` с `pii_score` и `pii_entities` (без PII-текста), `event: done`. При cancel — `event: cancelled` < 200 мс. При exception — `event: error` с `{message, type}`) + AG-4 (LLM prompt «save 'hello' as markdown» → `file_export` tool → S3 объект в bucket `llm-client-files` → UI-1 download button активируется, клик скачивает `.md`. Для `format: "pdf"` — 503 + retry (stub 2 сек)).
6. **Метрика идеальности не упала**: `Δф=+6 capabilities (cancel, dual-logging, dev-prod parity, UI scaffold + UIClient abstraction, agent-service scaffold + LangGraph orchestration), Δсложности=+3 dependencies (KMS/Vault, UIClient abstraction, LangGraph + LLM provider) → Δф/Δсложности = 2 ≥ 1` (см. §15.2, обновлено в v1.2.0). Заметка: в v1.1.0 расчёт был `Δф=+4, Δсложности=+2, ratio=2`. В v1.2.0 добавлены 2 capabilities (agent-service scaffold, LangGraph orchestration) и 1 dependency (LangGraph + LLM provider) — суммарно по фазе: `+6 caps / +3 deps = 2`, та же оценка, не нарушает порог. Если AG-2 (LLMProviderFactory) откатывается (например, OpenAI API pricing меняется, или команда решает отложить интеграцию до Phase 3): 5 caps / 3 deps = 1.67 ≥ 1 — порог соблюдён.
7. **Документация обновлена**: `ARCHITECT.md` § 7 ADR обновлён (ADR-013, ADR-014 добавлены; ADR-008 расширен; ADR-002 уточнён — UI-0 формализует scaffold; §5.1 строка 357 уточнена — AG-0 фиксирует FastAPI + SSE как единственную MVP-реализацию, in-process опция не используется). § 8 Trade-offs обновлён (C-4, C-11, C-15 помечены как resolved; C-1 — частично resolved через UI-2/UI-3, полная — в Phase 5 через ADR-018; C-2, C-5 — частично resolved через AG-1/AG-3, полная — в Phase 4 через расш. ADR-001). `BACKLOG.md` v1.1.0, `UI-PROMPTS.md` v1.0.0 и `AG-PROMPTS.md` v1.0.0 в реестре связанных документов.

При невыполнении любого из п.1–5 — фаза продлевается на 1 sprint; при невыполнении п.6 — ADR/UI-элемент/AG-элемент пересматривается (см. `BACKLOG.md` §6.2 — UI-3 может быть откатан, если бенчмарк не показывает прироста; `BACKLOG.md` §6.4 — AG-0 может быть пересмотрен, если архитектурный комитет сочтёт FastAPI + SSE преждевременным в Phase 1); при невыполнении п.7 — документационный долг, блокирует старт Phase 2.

### 5.7 UI-составляющая Phase 1 (new в v1.1.0)

**Резолвит**: противоречие C-1 (частично — interface aspect; полная резолюция — Phase 5 через ADR-018 `SessionStore`); частично C-4 (UI-часть ADR-013 — кнопка Stop, индикатор статуса).
**Принципы ТРИЗ**: 16 (частичное/избыточное действие — применён к `UIClient`), 1 (дробление — `@st.fragment` разделяет static shell и dynamic content), 17 (переход в другое измерение — UI-код изолирован от Streamlit-specific API через `UIClient`).
**Связанные G**: G-5 (UX MVP — UI-0/UI-1 дают полный chat UX), G-1 (multi-instance prep — UI-2 готовит Phase 5 без переписывания).

**Суть**: в v1.0.0 `ROADMAP.md` `UIClient` abstraction неявно относилась к Phase 5 (упомянута в §3.4 как применение принципа #16, но без явной фазы; в §9.3 ADR-018 описана как часть ADR-018 «`UIClient` abstraction позволяет переключать UI backend»). Это означало, что весь UI-код Phase 1–4 пишется под Streamlit-specific API (`st.chat_message`, `st.chat_input`, `st.write_stream`), и миграция в Phase 5 становится переписыванием, а не добавлением имплементации — прямое нарушение принципа #16. Патч v1.1.0 выносит `UIClient` в Phase 1 как самостоятельную UI-составляющую (не ADR — формализация + применение ADR-002).

Состав UI-составляющей (см. `BACKLOG.md` §3.3 и `UI-PROMPTS.md` §1–§4):

- **UI-0** (1.5 чел-дн): формализация «Phase 0» — scaffold Streamlit-приложения (`app.py`, `chat.py`, `session.py`, `render.py`), который в v1.0.0 подразумевался как данное (см. `MVP-PROMPTS.md` §1, A-1: «существующий docker-compose уже содержит PostgreSQL и Streamlit-сервис»). Без UI-0 промпт `C-5` (UI watcher) не имеет точки интеграции.
- **UI-1** (1.5 чел-дн): базовые UI-элементы, заявленные в `ARCHITECT.md` §4.1 (строка 172: «Чат UI, история сессий, кнопки скачивания»), но не реализованные промптами Phase 1–3: sidebar истории, кнопки скачивания артефактов (4 формата), индикатор статуса (streaming/cancelled/error), бейдж PII score.
- **UI-2** (2.5 чел-дн): `UIClient` ABC с 4 методами (`render_message`, `render_artifact`, `stream_token`, `handle_user_input`) + единственная имплементация `StreamlitClient`. Весь последующий UI-код пишет против interface. В Phase 5 добавится `ChainlitClient` (UI-5 из `BACKLOG.md`), в Phase 5+ — `FastAPIClient` (UI-6). Interface не меняется — применяется принцип #16.
- **UI-3** (1.0 чел-дн): `@st.fragment` для chat area и sidebar (Streamlit 1.40+). Снимает узкое место из C-1 (`TRIZ-ANALYSIS.md` §4.3, строка 240: «Streamlit re-runs конфликтует с низколатентным streaming»). Latency-бенчмарк (U3-3) — критерий готовности: прирост FPS ≥30% — иначе откат.

**Эффект**:

- (+) Phase 5 ADR-018 (External Session Store) сужен до `SessionStore` + `RedisSessionStore` — `UIClient` уже в Phase 1, не дублируется.
- (+) Phase 5 добавление `ChainlitClient` (UI-5) — добавление новой имплементации interface, а не переписывание UI-кода.
- (+) `@st.fragment` снимает локальное узкое место C-1 — Phase 5 multi-instance начинает с лучшей позиции.
- (+) UI-часть ADR-013 (cancel button, индикатор статуса) формализована — `C-5` (UI watcher) теперь имеет точку интеграции.
- (-) Phase 1 увеличивается с 8 до 14.5 чел-дн (+82%). Без увеличения команды — критический путь Phase 1 удлиняется на 6.5 чел-дн (см. §11).
- (-) `UIClient` abstraction в Phase 1 — +1 абстракция, +1 кривая обучения. Контр-мера — `BACKLOG.md` §6.1: метрика идеальности считается по Phase 1 целиком, не по отдельным UI-N.

**Критерий готовности**: см. §5.6 п.4. Если UI-3 (fragments) не показывает прироста в бенчмарке U3-3 — UI-3 откатывается, `@st.fragment` удаляется, метрика идеальности пересчитывается без UI-3 (Δф=+3 caps, Δсложности=+2 deps → 1.5 ≥ 1 — порог соблюдён).

**Supersedes**: часть ADR-018 (Phase 5) — `UIClient` abstraction перенесена в Phase 1. ADR-018 в Phase 5 сужен до `SessionStore` + `RedisSessionStore` (см. §9.3).

### 5.8 AG-составляющая Phase 1 (new в v1.2.0)

**Резолвит**: противоречие C-4 (полная резолюция — cancel wiring в графе + `event: cancelled` через SSE); C-2 (частично — agent-service получает граф, к которому подключается ADR-010 checkpointer в Phase 2); C-5 (частично — `IterationMonitor` интегрируется в граф из B-3 Quick Win).
**Принципы ТРИЗ**: 19 (переход в другое измерение — вынос agent-service в отдельный процесс FastAPI, не in-process Streamlit), 16 (частичное/избыточное действие — interface `POST /sessions/{id}/chat` + `GET /sessions/{id}/stream` + SSE event protocol фиксируется «избыточно» с первого дня, имплементация графа «частичная» — только `planner` + `final_answer`, остальное в Phase 2/4), 2 (вынесение — инфраструктура отделена, agent-service формализован как отдельное изделие).
**Связанные G**: G-2 (унифицированный доступ к LLM — AG-2 `LLMProviderFactory`), G-3 (инструментальный слой — AG-4 `file_export` частично), G-5 (MVP за счёт agent-service, а не mock).

**Суть**: в v1.1.0 `ROADMAP.md` agent-service неявно предполагался как «уже работающий» (см. `MVP-PROMPTS.md` §1 A-1: «существующий docker-compose уже содержит PostgreSQL и Streamlit-сервис», `UI-PROMPTS.md` §1 промпт UI-0: «ADR-001: LangGraph-агент с существующим SSE endpoint»). В кодовой базе Phase 1 (после v1.1.0) этого нет — UI смотрит на `AGENT_SERVICE_URL=http://localhost:8000`, где работает только `scripts/mock_agent_service.py` (FastAPI-мок для UI latency benchmark). ADR-001 (LangGraph) и ADR-007 (SSE) формально приняты в `ARCHITECT.md`, но не имеют имплементации в `src/llm_client/agent/` (только `IterationMonitor` из B-3 Quick Win). Это создаёт Пробелы D–G (`BACKLOG.md` v1.1.0 §2.3): нет scaffold agent-service (D), нет LangGraph graph (E), нет `LLMProviderFactory` (F), нет SSE event protocol emission (G). Патч v1.2.0 формализует AG-составляющую в Phase 1.

Состав AG-составляющей (см. `BACKLOG.md` v1.1.0 §3.4 и `AG-PROMPTS.md` v1.0.0 §1–§5):

- **AG-0** (1.5 чел-дн): формализация контейнера `agent-service` из `ARCHITECT.md` §4 (строка 124) и §5.1 (строка 357: «FastAPI + SSE для multi-instance») — FastAPI-приложение `src/llm_client/agent/service.py` с маршрутами `POST /sessions/{id}/chat`, `GET /sessions/{id}/stream`, `GET /health`, `POST /sessions/{id}/cancel` (делегирует в существующий `CancelPublisher` из C-2). Запуск через `python -m llm_client.agent` или `uvicorn`. Сервис в `docker-compose.yml` с depends_on redis/minio/vault.
- **AG-1** (2.5 чел-дн): LangGraph graph `src/llm_client/agent/graph.py` — `build_agent_graph(llm, token, tools)` возвращает `CompiledStateGraph` с нодами `planner` + `final_answer`, conditional edges `route_after_planner` (проверка `token.is_cancelled` между нодами — C-4 wiring) + `route_after_final_answer` (END). Интеграция `IterationMonitor` (B-3 Quick Win, уже реализовано) как callback после каждой ноды. Минимальный `AgentState` (messages, user_id, session_id, provider, model_name, iteration, max_iterations=10, final_answer). В Phase 1 без `tool_executor` / `rag_retriever` / `mcp_invoker` — они приходят с AG-4 / AG-6 (Phase 2) / AG-7 (Phase 4).
- **AG-2** (1 чел-дн): `LLMProviderFactory` `src/llm_client/agent/provider.py` — factory с `create(provider, model, **kwargs) -> BaseChatModel`. OpenAI через `langchain_openai.ChatOpenAI` (streaming=True по умолчанию, ADR-007). Anthropic/Ollama — stub `NotImplementedError` с указанием фазы (Phase 3 / Phase 4). Расширение `Settings`: `llm_provider`, `openai_api_key`, `openai_model`, `anthropic_api_key`, `anthropic_model` (заготовка). Валидация: при `LLM_PROVIDER=openai` и пустом `OPENAI_API_KEY` — startup fail fast. `token_usage_tracker` (BaseCallbackHandler) логирует `prompt_tokens` / `completion_tokens` / `cost_estimate` в operational stream (D-2). `retry_decorator` на 429/500/503, max 3 retry. Без `fallback_chain` — это Phase 3 (ADR-015).
- **AG-3** (1.5 чел-дн): SSE event protocol emission в `src/llm_client/agent/service.py` — `GET /sessions/{id}/stream` как async generator, эмитит события в формате RFC 8895-style (тот же, что парсит `src/llm_client/ui/chat.py` `iter_sse_events`): `event: token` (для каждого токена из `graph.astream`), `event: metadata` (PII score + entities из `PIIDetector.detect`, без PII-текста — D-5), `event: artifact_ready` (при `ToolMessage` от `file_export`, AG-4), `event: cancelled` (при `CancellationToken.is_cancelled`, C-4, latency < 200 мс), `event: error` (`{message, type}`, traceback в forensic stream, не в SSE — security), `event: done` (normal completion). Heartbeat `: keepalive\n\n` каждые 15 сек.
- **AG-4** (1 чел-дн): `file_export` tool `src/llm_client/agent/tools/file_export.py` — `@tool(args_schema=FileExportArgs)` декоратор (ARCHITECT.md §5.2.4), сохраняет контент в S3 через `create_file_storage()` (расш. ADR-008, уже реализовано). Форматы: `md`/`txt` синхронно (быстрый путь, < 100 мс), `pdf`/`docx`/`odt`/`xls`/`xlsx` асинхронно (stub `asyncio.sleep(2)` + 503 для UI retry, реальный worker — Phase 5 ADR-018). Path traversal protection через `pathlib.Path(filename).name`. Интеграция в AG-1 graph через `bind_tools([file_export])` (ADR-006) + `tool_executor` нода (единственная tool-нода в Phase 1). `GET /artifacts/{artifact_id}` endpoint для UI-1 download buttons (контракт совпадает с `fetch_artifact_content` в `src/llm_client/ui/render.py`).

**Эффект**:

- (+) UI-0..UI-3 работают с реальным agent-service, а не `mock_agent_service.py` — стриминг, PII badge, download buttons, cancelled badge активируются с реальными событиями.
- (+) ADR-001 (LangGraph) и ADR-007 (SSE) перестают быть «формально принятыми, но без имплементации» — получают рабочую кодовую базу в `src/llm_client/agent/`.
- (+) C-4 (cancel) получает полную резолюцию: cancel wiring в графе (AG-1) + `event: cancelled` через SSE (AG-3) + `POST /cancel` endpoint (AG-0, делегирует в C-2). Latency < 200 мс.
- (+) Phase 2 ADR-010 (Redis+PG checkpointer) подключается к существующему графу AG-1, не требует создания графа с нуля.
- (+) Phase 4 расш. ADR-001 (state-delta cycle detection с embeddings) расширяет существующий `IterationMonitor`, не создаёт новый.
- (+) Phase 5 multi-instance (UI-4/UI-5) работает с тем же контрактом `AGENT_SERVICE_URL` — agent-service уже отдельный процесс, добавление второго инстанса за LB не требует переписывания UI-кода (принцип #16, применённый к AG-0).
- (-) Phase 1 увеличивается с 14.5 до 22.5 чел-дн (+55% к v1.1.0, +181% к v1.0.0). Без увеличения команды — критический путь Phase 1 удлиняется на 7.5 чел-дн (см. §11).
- (-) Добавляется зависимость от OpenAI API (AG-2). В dev-окружении без `OPENAI_API_KEY` — startup fail fast. Контр-мера: `LLM_PROVIDER` env var позволяет переключить на mock-LLM (`FakeListChatModel` из `langchain_core`) для dev/CI без реальных API-вызовов.
- (-) LangGraph + LangChain как новые runtime-зависимости (уже декларированы в `pyproject.toml`, но не импортируемые до AG-1) — +1 к complexity delta. Контр-мера — `BACKLOG.md` §6.4: метрика идеальности считается по Phase 1 целиком (6 caps / 3 deps = 2.0, порог соблюдён).

**Критерий готовности**: см. §5.6 п.5. Если AG-2 (LLMProviderFactory) откатывается (например, OpenAI API pricing неприемлем для команды): Phase 1 завершается без реальной LLM-интеграции, AG-1 graph работает с mock-LLM (`FakeListChatModel`), UI-0 стриминг работает с заглушкой. Метрика идеальности: 5 caps / 3 deps = 1.67 ≥ 1 — порог соблюдён. AG-2 переносится в Phase 3 (ADR-015 cost-aware router вместе с Anthropic).

**Supersedes**: часть `MVP-PROMPTS.md` §1 A-1 (предположение «существующий docker-compose уже содержит Streamlit-сервис») — AG-0 формализует agent-service как создаваемый, а не данный. `ARCHITECT.md` §5.1 строка 357 (in-process опция) — помечается как «не используется; AG-0 фиксирует FastAPI + SSE как единственную MVP-реализацию» (см. `BACKLOG.md` §6.4).

---

## 6. Phase 2 — Alpha

### 6.1 Цели фазы

Phase 2 переводит LLM Client из MVP в Alpha: система начинает оптимизироваться под качество и производительность. Три ключевых улучшения: (а) async checkpoint write-behind log снимает latency bottleneck оркестратора (противоречие C-2); (б) reranker в RAG повышает precision поиска (часть противоречия C-6); (в) hybrid BM25+vector retrieval по умолчанию повышает recall для точных терминов (вторая часть C-6). После Phase 2 RAG и Orchestration-слои достигают production-качества; Persistence и Presentation остаются в MVP-состоянии до Phase 5.

Контрольные цели фазы:

1. **Latency checkpoint**: средняя latency checkpointing снижена с 10–50 мс до <1 мс; PostgreSQL не нагружается на каждом node transition.
2. **RAG precision**: recall@5 повышен на 15–25% (A/B test 2 недели) при сохранении latency retrieval <500 мс.
3. **RAG recall для точных терминов**: hybrid retrieval по умолчанию, recall для запросов с product SKU / error codes повышен на 30–50%.

### 6.2 Состав работ

| # | Работа | ADR | Сложность | Срок (чел-дн) | Зависимости |
|---|---|---|---|---|---|
| 6.2.1 | Реализация `RedisPostgresCheckpointer` (composite, async) | ADR-010 | Medium | 5 | Redis, AG-1 (graph из Phase 1) |
| 6.2.2 | Внедрение `bge-reranker-base` в RAG pipeline + RerankerRegistry | ADR-017 | Medium | 4 | bge-reranker |
| 6.2.3 | Внедрение hybrid retrieval (BM25 + vector) по умолчанию | ADR-020 | Medium | 5 | PostgreSQL tsvector |
| 6.2.4 | **AG-5 `web_search` tool via Tavily (new в v1.2.0)** — `@tool` для вызова Tavily API, интеграция в graph AG-1 через `bind_tools([file_export, web_search])` | (применение ADR-005) | Low | 1 | AG-1 (Phase 1), Tavily API |
| 6.2.5 | **AG-6 `rag_query` tool + base RAG pipeline (new в v1.2.0)** — `@tool` + `rag_retriever` нода в graph, базовый vector retrieval; расширяется ADR-017 (reranker) и ADR-020 (hybrid) в этом же Phase 2 | (применение ADR-003, расширяется ADR-017/020) | Medium | 4 | AG-1 (Phase 1), ADR-003, ADR-017 (этот Phase), ADR-020 (этот Phase) |
| — | **Итого Phase 2** | — | — | **19** (v1.0.0: 14; v1.2.0: +5 на AG-5+AG-6) | — |

### 6.3 ADR-010: Async Checkpoint Write-Behind Log

**Резолвит**: противоречие C-2 (PG checkpoint vs latency).
**Принципы ТРИЗ**: 9 (предварительное действие), 19 (переход в другое измерение), 28 (замена механической схемы), 35 (изменение физических свойств).
**Связанные G**: G-1 (RAG perf), G-4 (durability).

**Суть**: ADR-001 использует `PostgresSaver` для LangGraph checkpointer с синхронной записью в `agent_checkpoints` на каждом node transition. Это добавляет 10–50 мс на каждый переход, суммарно 50–200 мс на типовой агентский цикл, что становится bottleneck при росте RPS. Решение — composite checkpointer `RedisPostgresCheckpointer` с двухуровневой схемой: (1) `RedisCheckpointer` — synchronous write в Redis (latency <1 мс, TTL=24h); (2) `PostgresCheckpointer` — asynchronous batched write (background task каждые 5 сек или N checkpoints). Восстановление при restart: сначала из PostgreSQL (snapshot), затем replay из Redis (delta). `BaseCheckpointSaver` interface остаётся совместимым с LangGraph.

**Эффект**:

- (+) Latency checkpointing снижается с 10–50 мс до <1 мс.
- (+) PostgreSQL не нагружается на каждом node transition.
- (+) Resume-after-restart сохраняется (Redis + PostgreSQL).
- (-) Добавляется Redis как mandatory dependency для checkpointing (раньше опциональный).
- (-) Возможна потеря последних 5 сек checkpoint-ов при одновременном отказе Redis и PostgreSQL.
- (-) Сложнее тестировать (два хранилища вместо одного).

**Критерий готовности**: latency checkpoint <2 мс в 99% случаев на staging; восстановление при restart корректно (snapshot + replay); потеря состояния при одновременном отказе Redis+PG не происходит в пилотной неделе.

### 6.4 ADR-017: Reranker Model in RAG

**Резолвит**: часть противоречия C-6 (long RAG context vs cost).
**Принципы ТРИЗ**: 16 (частичное/избыточное действие), 21 (проникновение разрушения), 9 (предварительное), 17 (другое измерение).
**Связанные G**: G-1 (RAG precision).

**Суть**: § 5.2.5 упоминает MMR reranking, но без ML-reranker. Cross-encoder reranker даёт значительное улучшение precision (типично +20–30% recall@5). Решение — ввести cross-encoder reranker в RAG pipeline: (1) default reranker — `bge-reranker-base` (локальная модель, нет external API, ~600MB RAM); (2) опционально — Cohere Rerank API (если доступен и budget позволяет); (3) pipeline — vector retrieval (top-20) → BM25 retrieval (top-20) → fusion (RRF, top-50) → reranker (top-5); (4) reranker — pluggable через `RerankerRegistry` (как VectorStore в ADR-009).

**Эффект**:

- (+) Значительное улучшение precision и recall.
- (+) Снижение контекста LLM (5 качественных чанков вместо 20 шумных).
- (-) Дополнительная latency (50–200 мс на reranking).
- (-) bge-reranker-base требует ~600MB RAM для in-process.
- (-) Cohere Rerank — внешняя зависимость с отдельной стоимостью.

**Критерий готовности**: A/B test 2 недели — recall@5 ↑ ≥15% vs baseline; latency retrieval ↑ <100 мс; bge-reranker загружается в in-process за <5 сек при старте.

### 6.5 ADR-020: Hybrid (BM25 + Vector) RAG по умолчанию

**Резолвит**: вторая часть противоречия C-6.
**Принципы ТРИЗ**: стандарт 1.1.5 (введение второго поля в веполь).
**Связанные G**: G-1 (RAG recall для точных терминов).

**Суть**: § 5.2.5 упоминает hybrid search (BM25 + vector), но как опция. Pure vector retrieval плохо находит точные совпадения (product SKU, error codes). Решение — сделать hybrid retrieval (BM25 + vector) default: (1) в `RetrieverConfig` добавить `retrieval_strategy: "vector"|"bm25"|"hybrid"` (default: `hybrid`); (2) BM25 index строится параллельно с vector index при индексации документа; (3) hybrid retrieval — vector top-20 + BM25 top-20 → RRF fusion → top-K; (4) reranker (см. ADR-017) применяется после fusion; (5) хранение — `documents` таблица получает полнотекстовый индекс (PostgreSQL `tsvector` или OpenSearch).

**Эффект**:

- (+) Значительное улучшение recall для запросов с точными терминами.
- (+) Best of both worlds: semantic + lexical.
- (-) Дополнительное хранилище для BM25 index.
- (-) Latency retrieval возрастает на 30–50% (двойной запрос).
- (-) Reranker обязателен (без него noise от fusion).

**Критерий готовности**: A/B test 1 неделя — recall ↑ для точных терминов ≥30%; latency retrieval ↑ <50%; BM25 index строится синхронно с vector index при индексации.

### 6.6 Критерии выхода из фазы

1. **ADR-010 Approved**: latency checkpoint <2 мс; восстановление при restart корректно.
2. **ADR-017 Approved**: recall@5 ↑ ≥15%; latency retrieval ↑ <100 мс.
3. **ADR-020 Approved**: recall ↑ для точных терминов ≥30%; latency retrieval ↑ <50%.
4. **Метрика идеальности**: `Δф=+3 capabilities (async checkpoint, reranker, hybrid retrieval), Δсложности=+2 dependencies (bge-reranker, tsvector) → Δф/Δсложности = 1.5 ≥ 1`.
5. **Документация обновлена**: `ARCHITECT.md` § 7 ADR обновлён; § 8 Trade-offs обновлён (C-2, C-6 помечены как resolved).

---

## 7. Phase 3 — Beta

### 7.1 Цели фазы

Phase 3 переводит LLM Client в состояние Beta: система достигает cost-predictability и model portability, необходимые для production-запуска, и начинает переход в надсистему. Четыре архитектурных изменения: (а) hybrid semantic cache для LLM-ответов снимает основное давление на LLM-бюджет (полное разрешение C-6); (б) cost-aware routing заменяет fallback chain, делая стоимость предсказуемой (C-7); (в) tool capability adapter снимает привязку к моделям с native function calling, открывая путь к локальным моделям в Phase 4 (C-9); (г) ускорение ADR-004 (MCP Server mode) начинает переход LLM Client из standalone-продукта в компонент надсистемы (реализация ИКР-0).

Контрольные цели фазы:

1. **Cost ↓**: средний monthly LLM-cost снижен на 60–80% за счёт semantic cache; cost variance ≤ ±10% от плана.
2. **Model portability**: система работает с любой моделью из `ModelCapabilityMatrix`, включая модели без native function calling (через ReAct-эмуляцию).
3. **Надсистема**: LLM Client может быть подключён как MCP-сервер к другим клиентам (IDE, боты) — preview-режим, full — в Phase 6.

### 7.2 Состав работ

| # | Работа | ADR | Сложность | Срок (чел-дн) | Зависимости |
|---|---|---|---|---|---|
| 7.2.1 | Реализация three-tier semantic cache (Tier-3 answer cache, Tier-1 facts cache, Tier-2 vector retrieval) | ADR-011 | High | 8 | Redis |
| 7.2.2 | Реализация `LLMRouter` с политиками cost/latency/quality/privacy + cost guard | ADR-015 | High | 7 | Observability stack |
| 7.2.3 | Реализация `ModelCapabilityMatrix` + `ToolCallingAdapter` (native/react/hybrid) | ADR-016 | High | 6 | — |
| 7.2.4 | Ускорение ADR-004: реализация MCP Server mode (preview) | ADR-004 ускорить | High | 10 | — |
| — | **Итого Phase 3** | — | — | **31** | — |

### 7.3 ADR-011: Hybrid Semantic Cache for LLM

**Резолвит**: противоречие C-6 (long RAG context vs cost) — полностью.
**Принципы ТРИЗ**: 16 (частичное/избыточное действие), 21 (проникновение разрушения), 9 (предварительное), 17 (другое измерение).
**Связанные G**: G-2 (cost reduction), G-4 (reproducibility).

**Суть**: § 12 Q-5 фиксирует риск стоимости LLM при >50k токенов контекста. Текущая митигация (context compression, map-reduce) снижает, но не устраняет проблему. Решение — three-tier cache: (1) Tier 3 — Semantic answer cache: cache полных LLM-ответов по embedding similarity запроса. Threshold: cosine similarity > 0.92. Storage: Redis с TTL=24h. Invalidation: при изменении любого документа в RAG, на который ссылался ответ. (2) Tier 1 — Facts cache: при индексации документа извлекаются факты (LLM-call), хранятся в `documents_facts` таблице, индексируются в векторном хранилище как metadata. (3) Tier 2 — Vector retrieval остаётся как есть, но с reranker (см. ADR-017).

**Эффект**:

- (+) Среднее число токенов в контексте LLM снижается на 60–80%.
- (+) Повторные запросы возвращают ответ из cache (latency <100 мс вместо 5–30 сек).
- (-) Risk stale answers — требуется аккуратная инвалидация.
- (-) Дополнительный LLM-call при индексации (но одноразовый, не per-request).
- (-) Хранение embeddings ответов в Redis увеличивает memory footprint.

**Критерий готовности**: hit rate cache >15% на staging-нагрузке (100 запросов); stale answers <1%; latency cache hit <100 мс.

### 7.4 ADR-015: Cost-Aware Routing

**Резолвит**: противоречие C-7 (Fallback chain vs cost predictability).
**Принципы ТРИЗ**: 35 (изменение физических свойств), 16 (частичное/избыточное действие), 13 (наоборот), 23 (обратная связь).
**Связанные G**: G-2 (cost predictability).

**Суть**: § 5.2.3 описывает `fallback_chain` — автоматический fallback при 5 ошибках подряд. Это не учитывает стоимость (GPT-4o vs Claude 3.5 Sonnet различаются в 1.7×) и не предотвращает превышение бюджета. Решение — заменить `fallback_chain` на `LLMRouter`: (1) `LLMRouter` хранит политики выбора (`cost_priority`, `latency_priority`, `quality_priority`, `privacy_priority`); (2) на каждый запрос router учитывает: текущую нагрузку на провайдера (circuit breaker), текущий расход бюджета (cost guard), требования к приватности (zero-retention policy), capability matrix модели (см. ADR-016); (3) при достижении 80% месячного бюджета автоматически переключается на cheapest available (GPT-4o-mini / Claude Haiku / Ollama); (4) fallback — крайний случай; обычно routing распределяет трафик 70/30 между провайдерами; (5) метрики от `token_usage_tracker` и `cost_tracker` идут в router в real-time.

**Supersedes**: часть ADR-005 (fallback chain) — упраздняется, заменяется на cost-aware routing.

**Эффект**:

- (+) Предсказуемость стоимости (cost guard).
- (+) Availability выше (load balancing вместо fallback).
- (+) Поддержка Ollama как cheap-tier.
- (-) Усложнение LLM Provider Layer.
- (-) Возможны surprises: router выбрал GPT-4o-mini вместо GPT-4o — нужно явное логирование.

**Критерий готовности**: 1 месяц shadow mode — cost predictability ±10%; cost overrun <20%; логирование switching decisions доступно в observability.

### 7.5 ADR-016: Tool Capability Adapter

**Резолвит**: противоречие C-9 (Tool calling API vs portability).
**Принципы ТРИЗ**: 13 (наоборот), 35 (изменение физических свойств), 1 (дробление), 25 (упреждение).
**Связанные G**: G-2 (model portability), G-3 (tools для локальных моделей).

**Суть**: ADR-006 зафиксировал нативный tool calling через `bind_tools()`, что блокирует модели без function calling (Llama 3.1 base). Это противоречит плану Phase 4 (Ollama). Решение — ввести `ModelCapabilityMatrix` и `ToolCallingAdapter`: (1) `ModelCapabilityMatrix` — для каждой модели декларируются: `supports_native_tools`, `supports_streaming`, `supports_vision`, `context_window`, `cost_per_1m_tokens`, `latency_p50`, `latency_p99`; (2) `ToolCallingMode` enum: `native` (function calling API), `react` (system prompt emulation), `hybrid` (native с fallback на ReAct при ошибке парсинга); (3) `ToolCallingAdapter` выбирает режим по capability matrix; (4) для моделей без native function calling автоматически включается ReAct-эмуляция; (5) `LLMRouter` (ADR-015) использует capability matrix для маршрутизации.

**Эффект**:

- (+) Поддержка локальных моделей (Ollama, Llama, Mistral) без function calling.
- (+) Явные capabilities вместо неявных предположений.
- (+) ReAct как fallback для любой модели.
- (-) ReAct-эмуляция менее надёжна, чем native tool calling.
- (-) Поддержка двух режимов = больше кода в adapter.

**Критерий готовности**: ADR-016 pilot — Llama 3.1 через Ollama успешно вызывает tools через ReAct-эмуляцию; success rate ≥80% (vs native ≥95%); capability matrix покрывает все модели в `LLMRouter`.

### 7.6 ADR-004 (ускорение): MCP Server Mode (Preview)

**Резолвит**: ИКР-0 (переход в надсистему).
**Принципы ТРИЗ**: закон перехода в надсистему (4.6).
**Связанные G**: G-3 (LLM Client как компонент надсистемы).

**Суть**: ADR-004 отложил MCP Server mode до Phase 6. ТРИЗ-анализ ускоряет этот шаг до Phase 3 (preview) — full внедрение в Phase 6. Решение — реализовать preview-режим MCP Server: LLM Client экспонирует свои capabilities (rag_query, file_export, web_search) как MCP tools, доступные другим клиентам (IDE, боты, другие LLM-клиенты). Transport: SSE в preview (ready для production в Phase 6). Это первый шаг к ИКР-0 — система начинает «исчезать» как отдельный продукт, встраиваясь в другие инструменты.

**Эффект**:

- (+) LLM Client становится источником tools для других клиентов.
- (+) Путь к IDE-интеграции (VS Code, JetBrains) открывается.
- (+) ИКР-0 начинает реализовываться.
- (-) Двойная роль: LLM Client — и MCP client (ADR-012), и MCP server (ADR-004).
- (-) Расширение surface area для security-аудита.

**Критерий готовности**: LLM Client в MCP Server mode отвечает на `list_tools` и `call_tool` запросы от внешнего MCP client; ADR-019 (signed manifests) в Phase 5 распространяется и на собственные tools LLM Client.

### 7.7 Критерии выхода из фазы

1. **ADR-011 Approved**: hit rate cache >15%; stale answers <1%.
2. **ADR-015 Approved**: 1 месяц shadow mode — cost predictability ±10%; cost overrun <20%.
3. **ADR-016 Approved**: pilot на Ollama success rate ≥80%; capability matrix покрывает все модели.
4. **ADR-004 preview Approved**: LLM Client отвечает на `list_tools` и `call_tool` от внешнего MCP client.
5. **Метрика идеальности**: `Δф=+4 capabilities (semantic cache, cost-aware router, tool capability adapter, MCP server preview), Δсложности=+3 абстракций (LLMRouter, ToolCallingAdapter, ModelCapabilityMatrix) → Δф/Δсложности = 1.33 ≥ 1`. При этом `Δсложности` компенсируется упразднением `fallback_chain` (`-1`) — net `+2`. Итог `4/2 = 2 ≥ 1`.
6. **Документация обновлена**: `ARCHITECT.md` § 7 ADR обновлён; § 8 Trade-offs обновлён (C-6 fully, C-7, C-9 помечены как resolved); § 12 Q-5 (cost risk) закрыт.

---

## 8. Phase 4 — Local LLM

### 8.1 Цели фазы

Phase 4 вводит локальные LLM как first-class citizen в LLM Client. Три архитектурных изменения: (а) plugin-based VectorStore registry снимает привязку к трём хардкоденным хранилищам, делая добавление нового адаптера конфигурацией, а не код-изменением (C-3, C-14); (б) MCP transport auto-negotiation снимает жёсткую привязку транспорта, обеспечивая dev-prod parity для MCP-серверов (C-8); (в) cycle detection в графе агента на основе state-delta снимает проблему недетерминизма при циклах LangGraph (C-5). После Phase 4 система готова к запуску на изолированном окружении с локальными моделями — необходимый шаг для сценариев с приватностью.

Контрольные цели фазы:

1. **Plugin extensibility**: новый VectorStore-адаптер добавляется через `entrypoint` в `pyproject.toml` без изменения core-кода.
2. **MCP dev-prod parity**: один `mcp_servers.json` работает в dev (stdio) и prod (SSE) без изменений.
3. **Determinism**: циклы в графе агента детектируются и прерываются по семантическому критерию, а не по счётчику итераций.

### 8.2 Состав работ

| # | Работа | ADR | Сложность | Срок (чел-дн) | Зависимости |
|---|---|---|---|---|---|
| 8.2.1 | Реализация `VectorStoreRegistry` + entrypoint-based plugin loading + Core/Extended interfaces | ADR-009 | Medium | 5 | — |
| 8.2.2 | Реализация `MCPTransport` abstraction + StdioTransport + SSETransport + auto-negotiation | ADR-012 | Medium | 5 | — |
| 8.2.3 | Реализация state-delta cycle detection в `planner` node | (расш. ADR-001) | Low | 3 | Embeddings model |
| 8.2.4 | **AG-7 `mcp_call` tool / `mcp_invoker` нода (new в v1.2.0)** — `@tool` + нода в graph AG-1, использует `MCPTransport` из ADR-012 (этот Phase) для вызова внешних MCP-серверов | (применение ADR-004, зависит от ADR-012) | Medium | 3 | AG-1 (Phase 1), ADR-012 (этот Phase) |
| — | **Итого Phase 4** | — | — | **16** (v1.0.0: 13; v1.2.0: +3 на AG-7) | — |

### 8.3 ADR-009: Plugin-based VectorStore Registry

**Резолвит**: противоречия C-3 (Triple vector store vs testing) и C-14 (Vector store parity vs feature parity).
**Принципы ТРИЗ**: 1 (дробление), 3 (местное качество), 25 (упреждение), 5 (объединение).
**Связанные G**: G-1 (RAG extensibility).

**Суть**: ADR-003 вводит три адаптера векторных хранилищ через `VectorStoreFactory` с `match kind:`. Это создаёт три проблемы: (1) добавление нового адаптера требует изменения factory; (2) выбор адаптера по имени, а не по capabilities; (3) три разных surface area для тестирования. Решение — заменить `VectorStoreFactory` на `VectorStoreRegistry`, наполняемый через entrypoints (`pyproject.toml` `[project.entry-points."llm_client.vector_stores"]`). Каждый адаптер декларирует: имя, профиль (`embedded`/`distributed`/`colocated_with_pg`), поддерживаемые интерфейсы (`CoreVectorStore`, `ExtendedVectorStore`). `RetrieverConfig` выбирает адаптер по профилю и требуемому интерфейсу, не по имени. Ввести два уровня интерфейсов: `CoreVectorStore` (`similarity_search`, `add_texts`, `delete` — поддерживается всеми) и `ExtendedVectorStore` (`hybrid_search`, `metadata_filtering`, `mmr_search`, `batch_upsert` — поддерживается Qdrant и pgvector, не Chroma).

**Эффект**:

- (+) Новые адаптеры добавляются без изменения core-кода.
- (+) Feature-parity проверяема на уровне интерфейсов.
- (+) Chroma явно позиционируется как dev-only, не вводит в заблуждение.
- (-) Дополнительная абстракция (два интерфейса вместо одного).
- (-) Требуется рефакторинг существующего `VectorStoreFactory`.

**Критерий готовности**: добавление нового адаптера (например, Weaviate) — только запись в `pyproject.toml` + имплементация интерфейса, без изменения core-кода; Chroma декларирует только `CoreVectorStore`, runtime не падает при запросе Extended operations.

### 8.4 ADR-012: MCP Transport Auto-Negotiation

**Резолвит**: противоречие C-8 (MCP stdio in docker vs isolation).
**Принципы ТРИЗ**: 17 (другое измерение), 2 (выведение), 28 (замена механической схемы), 1 (дробление).
**Связанные G**: G-3 (MCP dev-prod parity).

**Суть**: § 12 Q-3 фиксирует сложность MCP-серверов с stdio в docker-compose. Текущая конфигурация `mcp_servers.json` жёстко задаёт `transport: "stdio"|"sse"` для каждого сервера. Решение — ввести `MCPTransport` abstraction: (1) `MCPTransport` interface с методами `probe()`, `connect()`, `call_tool()`, `list_tools()`; (2) `StdioTransport` — для dev, subprocess; (3) `SSETransport` — для docker/prod, HTTP+SSE; (4) при подключении сервера `MCPClientManager` probe-ит оба транспорта (SSE healthcheck, stdio spawn) и выбирает живой; (5) конфигурация `mcp_servers.json` опционально содержит `transport`, но если не указан — auto-negotiation; (6) в docker-compose каждый MCP-сервер — отдельный сервис с healthcheck.

**Эффект**:

- (+) Dev/prod parity: один конфиг работает везде.
- (+) Изоляция MCP-серверов в docker (sidecar, не subprocess).
- (+) Cold start MCP-серверов устраняется (долгоживущие сервисы).
- (-) Дополнительная сложность в `MCPClientManager`.
- (-) Для stdio-серверов без SSE-режима требуется обёртка (mcp-proxy).

**Критерий готовности**: один `mcp_servers.json` работает в dev (stdio) и docker-compose (SSE) без изменений; probe-логика выбирает живой транспорт за <500 мс; cold start MCP-серверов <5 сек (vs subprocess spawn 2–10 сек).

### 8.5 (расш. ADR-001): State-Delta Cycle Detection

**Резолвит**: противоречие C-5 (LangGraph cycles vs determinism).
**Принципы ТРИЗ**: 19 (переход в другое измерение), 23 (обратная связь), 22 (обратить вред в пользу), 11 (заранее подложенная подушка).
**Связанные G**: G-4 (determinism).

**Суть**: ADR-001 использует `max_iterations` для предотвращения бесконечных циклов в графе агента. Это грубый механизм — не отличает продуктивные итерации (agent приближается к ответу) от непродуктивных (agent зациклился). Решение — расширение ADR-001: ввести state-delta cycle detection. После каждой итерации вычисляется embedding similarity между текущим `AgentState` и предыдущим. Если similarity > 0.95 на 3 итерациях подряд — цикл детектирован, граф прерывается с semantic reason «state not progressing». `max_iterations` остаётся как hard cap, но semantic detection срабатывает раньше. Embeddings model — любая из `ModelCapabilityMatrix` (см. ADR-016).

**Эффект**:

- (+) Детектирование реальных циклов, а не грубый cap.
- (+) Продуктивные длинные итерации не прерываются.
- (+) Семантический reason прерывания — debugging-friendly.
- (-) Дополнительный LLM-call (или embeddings call) на каждой итерации.
- (-) Порог 0.95 — настраиваемый, требует калибровки.

**Критерий готовности**: на 10 тестовых кейсах (5 продуктивных циклов, 5 зацикливаний) cycle detection срабатывает корректно в 9/10; false positive rate <10%; false negative rate <5%.

### 8.6 Критерии выхода из фазы

1. **ADR-009 Approved**: добавление Weaviate-адаптера — только `pyproject.toml` + имплементация интерфейса.
2. **ADR-012 Approved**: один `mcp_servers.json` работает в dev и docker-compose без изменений.
3. **(расш. ADR-001) Approved**: cycle detection срабатывает корректно в 9/10 тестовых кейсов.
4. **Метрика идеальности**: `Δф=+3 capabilities (plugin registry, auto-transport, cycle detection), Δсложности=+3 абстракций (VectorStoreRegistry, MCPTransport, state-delta detector) → Δф/Δсложности = 1 ≥ 1` (граничный случай; ADR пересматривается, если эффект ниже ожидаемого).
5. **Документация обновлена**: `ARCHITECT.md` § 7 ADR обновлён; § 8 Trade-offs обновлён (C-3, C-5, C-8, C-14 помечены как resolved); § 12 Q-3 закрыт.

---

## 9. Phase 5 — Scale

### 9.1 Цели фазы

Phase 5 переводит LLM Client в состояние Production-ready с horizontal scale. Четыре архитектурных изменения: (а) external session store снимает привязку Streamlit-сессии к конкретному инстансу, обеспечивая multi-instance без sticky session (C-1); (б) MCP server signed manifests вводят доверенную модель для внешних MCP-серверов (C-12); (в) async file rendering разделяет fast/slow paths, убирая latency bottleneck в операциях с файлами (C-10); (г) гибридная ABAC+RBAC модель обеспечивает гранулярный доступ без ущерба usability (C-13). После Phase 5 все 8 High-приоритетных противоречий из `TRIZ-ANALYSIS.md` § 10 резолвятся — система формально готова к Production.

Контрольные цели фазы:

1. **Multi-instance**: 2+ инстанса LLM Client работают за load balancer без sticky session; сессия восстанавливается при переключении инстансов.
2. **MCP security**: каждый внешний MCP-сервер имеет подписанный манифест; destructive operations требуют подтверждения пользователя.
3. **Async rendering**: latency файловых операций (PDF/DOCX rendering) для пользователя <200 мс; фактический рендеринг происходит в background worker.
4. **Granular access**: ABAC-политики покрывают 100% destructive operations; RBAC остаётся для coarse-grained доступа.

### 9.2 Состав работ

| # | Работа | ADR | Сложность | Срок (чел-дн) | Зависимости |
|---|---|---|---|---|---|
| 9.2.1 | Реализация `SessionStore` abstraction + `RedisSessionStore` + sync с Streamlit `session_state` (без `UIClient` — он в Phase 1) | ADR-018 (сужен в v1.1.0) | Medium | 4 | Redis, UI-2 (Phase 1) |
| 9.2.2 | Реализация `MCPManifest` (YAML, ed25519 signed) + allow-list из Vault + anomaly detection | ADR-019 | High | 8 | Vault, signing infra |
| 9.2.3 | Разделение fast/slow paths для файловых операций + Playwright PDF worker | (расш. ADR-008) | Medium | 5 | Worker |
| 9.2.4 | Реализация гибридной ABAC+RBAC модели + auto-approval для безопасных операций | (новый ADR) | High | 8 | Auth provider |
| 9.2.5 | **UI-5 `ChainlitClient` (new в v1.1.0)** — вторая имплементация `UIClient` interface (из Phase 1), использует `SessionStore` (9.2.1) | (применение ADR-002 миграции + UI-2) | High | 6 | UI-2 (Phase 1), 9.2.1 |
| — | **Итого Phase 5** | — | — | **31** (v1.0.0: 25; +6 на UI-5 — становится явным) | — |

### 9.3 ADR-018: External Session Store for Streamlit (сужен в v1.1.0)

**Резолвит**: противоречие C-1 (Streamlit vs horizontal scale) — runtime aspect (session state). Interface aspect (`UIClient` abstraction) резолвится в Phase 1 (см. §5.7).
**Принципы ТРИЗ**: 1 (дробление), 15 (динамичность), 17 (другое измерение), 35 (изменение физических свойств).
**Связанные G**: G-1 (multi-instance scale).

**Суть**: ADR-002 фиксирует Streamlit для MVP, признаёт проблему multi-instance (sticky session). Решение — ввести `SessionStore` abstraction с реализацией `RedisSessionStore`: (1) `SessionStore` interface: `get_session(id)`, `save_session(id, state)`, `list_sessions(user_id)`; (2) `RedisSessionStore` — primary, TTL=24h, JSON serialization; (3) `LocalSessionStore` — для unit-тестов; (4) Streamlit `session_state` синхронизируется с `SessionStore` через callback.

**v1.1.0 сужение**: в v1.0.0 в §9.3 упоминалось «(5) `UIClient` abstraction (см. противоречие C-1) позволяет переключать UI backend без потери session state». В v1.1.0 `UIClient` вынесен в Phase 1 (см. §5.7). ADR-018 фокусируется на runtime aspect (session state persistence) и предполагает, что `UIClient` interface уже существует (из Phase 1). Добавление `ChainlitClient` (UI-5 из `BACKLOG.md`) в Phase 5 — добавление новой имплементации `UIClient`, использующей тот же `SessionStore` — interface `UIClient` не меняется.

**Supersedes**: часть ADR-002 (Streamlit native `session_state`) — заменяется на Redis-backed session store. **Не затрагивает** `UIClient` (уже в Phase 1).

**Эффект**:

- (+) Multi-instance без sticky session.
- (+) Session survives Streamlit restart.
- (+) Путь к Chainlit/FastAPI без переписывания session logic (через `UIClient` из Phase 1).
- (-) Redis становится mandatory dependency.
- (-) Сериализация `session_state` в JSON — потенциальные проблемы с custom types.

**Критерий готовности**: 2 инстанса LLM Client за load balancer обрабатывают сессию пользователя без потери состояния при переключении; session восстанавливается при restart Streamlit в течение <1 сек. **Дополнительно в v1.1.0**: `ChainlitClient` (UI-5) реализован как вторая имплементация `UIClient` interface, использует тот же `SessionStore` — UI-код из Phase 1 работает без изменений.

### 9.4 ADR-019: MCP Server Signed Manifests

**Резолвит**: противоречие C-12 (MCP trust vs extensibility).
**Принципы ТРИЗ**: 35 (изменение физических свойств), 23 (обратная связь), 9 (предварительное), 22 (обратить вред в пользу).
**Связанные G**: G-4 (security), G-3 (MCP trust).

**Суть**: § 9.4 Security фиксирует «MCP server trust — Production: signed manifests, allow-list», но формат манифеста и механизм проверки не определены. Решение — ввести `MCPManifest` формат (YAML, ed25519 signed): (1) manifest содержит: `name`, `version`, `publisher`, `signature`, `tools[]` с `name`, `side_effects`, `required_permissions`, `requires_user_confirmation`; (2) `MCPClientManager` при подключении сервера: проверяет подпись по allow-list (из Vault), регистрирует только tools из манифеста; (3) tools с `requires_user_confirmation: true` автоматически попадают в `human_review` node графа; (4) manifest хранится в `mcp_servers/{name}/manifest.yaml` в репозитории MCP-сервера; (5) anomaly detection (фоновая задача) — Z-score на частоте вызовов каждого tool.

**Эффект**:

- (+) Явный контракт для MCP-серверов.
- (+) Destructive операции требуют подтверждения пользователя.
- (+) Anomaly detection как defence-in-depth.
- (-) Разработчикам MCP-серверов нужно генерировать подписи.
- (-) Allow-list в Vault — дополнительная операционная нагрузка.

**Критерий готовности**: 5 MCP-серверов (filesystem, github + 3 внутренних) имеют подписанные манифесты; destructive operations (write_file, create_repo) требуют подтверждения в UI; anomaly detection корректно срабатывает на тестовом аномальном трафике.

### 9.5 (расш. ADR-008): Async File Rendering

**Резолвит**: противоречие C-10 (Sync file rendering vs latency).
**Принципы ТРИЗ**: 9 (предварительное), 19 (переход в другое измерение), 28 (замена механической схемы), 21 (проникновение разрушения).
**Связанные G**: G-3 (file ops UX).

**Суть**: ADR-008 рендерит файлы (PDF/DOCX) синхронно в request-цикле — Playwright PDF generation занимает 2–10 сек, блокируя LLM-ответ. Решение — расширение ADR-008: разделить fast/slow paths. Fast path — preview (HTML rendering, markdown-to-html, instant). Slow path — full rendering (PDF/DOCX, Playwright worker, 2–10 сек) — в background worker. UI получает preview мгновенно, full file — по готовности через SSE notification или polling. Worker — отдельный сервис в docker-compose, общается через Redis queue.

**Эффект**:

- (+) Latency файловых операций для пользователя <200 мс (preview).
- (+) LLM-ответ не блокируется рендерингом.
- (+) Worker масштабируется горизонтально.
- (-) Двойная имплементация rendering logic (preview + full).
- (-) Worker — ещё один сервис в docker-compose.
- (-) Sync между preview и full file — потенциальный source of bugs.

**Критерий готовности**: preview отдаётся за <200 мс в 99% случаев; full file отдаётся за <30 сек в 99% случаев; sync между preview и full file корректен (preview — подмножество full).

### 9.6 (новый ADR): Hybrid ABAC+RBAC

**Резолвит**: противоречие C-13 (RBAC vs usability).
**Принципы ТРИЗ**: 1 (дробление), 13 (наоборот), 35 (изменение физических свойств), 22 (обратить вред в пользу).
**Связанные G**: G-4 (granular access).

**Суть**: текущая модель — RBAC (role-based access control): аналитик, admin, security officer. Это грубо — все аналитики видят все документы, хотя логично ограничить по проекту/клиенту. Решение — гибридная ABAC+RBAC: (1) RBAC остаётся для coarse-grained (аналититик vs admin); (2) ABAC (attribute-based) добавляется для fine-grained — доступ определяется атрибутами user (department, project), resource (sensitivity, project) и environment (time, ip); (3) auto-approval для безопасных операций (read non-sensitive doc в рабочее время); (4) manual approval для destructive operations (delete file, modify config).

**Эффект**:

- (+) Granular access без ущерба usability (auto-approval).
- (+) Compliance с корпоративными политиками.
- (+) Audit trail для каждого решения о доступе.
- (-) Сложность настройки ABAC-политик.
- (-) Auth provider — внешняя зависимость.
- (-) Potential для "false deny" —用户体验 деградирует.

**Критерий готовности**: ABAC-политики покрывают 100% destructive operations; auto-approval срабатывает корректно в 95%+ safe requests; false deny rate <5%.

### 9.7 Критерии выхода из фазы

1. **ADR-018 Approved (сужен в v1.1.0)**: 2 инстанса обрабатывают сессию без sticky; session survives restart. `UIClient` interface (из Phase 1) не модифицируется.
2. **UI-5 Approved (new в v1.1.0)**: `ChainlitClient` — вторая имплементация `UIClient` interface; UI-код из Phase 1 (scaffold, base elements, fragments) работает без изменений; `SessionStore` используется обеими имплементациями (`StreamlitClient`, `ChainlitClient`).
3. **ADR-019 Approved**: 5 MCP-серверов с подписанными манифестами; destructive ops подтверждаются.
4. **(расш. ADR-008) Approved**: preview <200 мс; full file <30 сек.
5. **(новый) ABAC+RBAC Approved**: 100% destructive ops покрыты; auto-approval 95%+; false deny <5%.
6. **Метрика идеальности (v1.1.0)**: `Δф=+5 capabilities (multi-instance, MCP security, async rendering, granular access, ChainlitClient), Δсложности=+4 dependencies (Redis SessionStore, Vault, Worker, Auth provider) → Δф/Δсложности = 1.25 ≥ 1` (улучшение vs v1.0.0: было 4/4=1.0, стало 5/4=1.25 за счёт явной UI-5).
7. **Документация обновлена**: `ARCHITECT.md` § 7 ADR обновлён (ADR-018 сужен, UI-5 упомянут как применение `UIClient`); § 8 Trade-offs обновлён (C-1, C-10, C-12, C-13 помечены как resolved). **Все 8 High-приоритетных противоречий закрыты — формальный Production-ready**.

---

## 10. Phase 6 — Interoperability

### 10.1 Цели фазы

Phase 6 завершает эволюцию LLM Client, реализуя ИКР-0 (система исчезает как standalone-продукт, функции встраиваются в инструменты аналитика). Два архитектурных изменения: (а) MCP Server mode (full) — LLM Client полностью экспонирует свои capabilities как MCP tools для других клиентов (IDE, боты, Confluence); (б) embed mode — LLM Client встраивается в iframe / через JS API в внешние приложения. После Phase 6 LLM Client перестаёт быть отдельным приложением — он становится «функцией в IDE» / «плагином для Confluence» / «ботом в Slack».

Контрольные цели фазы:

1. **MCP Server (full)**: все capabilities LLM Client (rag_query, file_export, web_search, agent_run) доступны внешним MCP-клиентам с signed manifests (распространение ADR-019 на собственные tools).
2. **Embed mode**: LLM Client встраивается в iframe/JS API в external приложение; session синхронизирована с host-приложением.

### 10.2 Состав работ

| # | Работа | ADR | Сложность | Срок (чел-дн) | Зависимости |
|---|---|---|---|---|---|
| 10.2.1 | Реализация MCP Server mode (full): все capabilities экспонируются, signed manifest на собственные tools | MCP Server mode (full) | High | 12 | ADR-004 (preview из Phase 3) |
| 10.2.2 | Реализация embed mode: iframe API + JS SDK + session sync с host | Embed mode (iframe API) | Medium | 6 | — |
| — | **Итого Phase 6** | — | — | **18** | — |

### 10.3 MCP Server Mode (Full)

**Резолвит**: ИКР-0 (переход в надсистему — полностью).
**Принципы ТРИЗ**: закон перехода в надсистему (4.6), закон динамизации (4.9).
**Связанные G**: G-3 (LLM Client как компонент надсистемы — полностью).

**Суть**: В Phase 3 (ADR-004 preview) LLM Client начал экспонировать свои capabilities как MCP tools. Phase 6 завершает этот переход: (1) все capabilities доступны — rag_query, file_export, web_search, agent_run, mcp_proxy (проксирование к другим MCP-серверам); (2) собственные tools LLM Client имеют подписанные манифесты (расширение ADR-019 на self); (3) transport — SSE в production, WebSocket опционально; (4) authentication — через OAuth 2.0 к host-приложению (IDE, Confluence).

**Эффект**:

- (+) LLM Client — полноценный MCP-сервер, доступный любому MCP-клиенту.
- (+) ИКР-0 реализован — LLM Client «исчез» как отдельный продукт.
- (+) Self-hosting: один install LLM Client обслуживает несколько IDE/ботов.
- (-) Двойная роль: client + server — surface area для security-аудита удваивается.
- (-) OAuth flow — дополнительная сложность.

**Критерий готовности**: LLM Client в MCP Server mode подключается из VS Code (через Claude/Continue плагин), из Slack-бота, из Confluence app; signed manifest на собственные tools проверяется корректно.

### 10.4 Embed Mode (iframe API)

**Резолвит**: ИКР-1 (UI адаптивен, не отдельное приложение).
**Принципы ТРИЗ**: 15 (динамичность), 17 (другое измерение).
**Связанные G**: G-1 (UI как компонент host-приложения).

**Суть**: Streamlit-приложение в Phase 1–5 работает как standalone web app. Phase 6 добавляет embed mode: LLM Client встраивается в iframe в external приложение (Confluence page, internal portal) или через JS SDK (custom integration). Session sync — через postMessage API: host-приложение передаёт user_id и session context, LLM Client использует их для авторизации и инициализации. UI адаптируется к контексту host (light/dark theme, locale).

**Эффект**:

- (+) LLM Client встраивается в любой web-app через iframe/JS.
- (+) Session не требует повторного логина в embedded-режиме.
- (+) UI автоматически адаптируется к host-стилю.
- (-) postMessage API — potential security risk (нужно строго валидировать origin).
- (-) Адаптация к host-стилю — double rendering logic.

**Критерий готовности**: LLM Client встраивается в Confluence page и internal portal; session sync работает (пользователь не логинится повторно); UI адаптируется к light/dark theme host-приложения.

### 10.5 Критерии выхода из фазы

1. **MCP Server (full) Approved**: LLM Client подключается из VS Code, Slack-бота, Confluence; signed manifests на собственные tools.
2. **Embed mode Approved**: LLM Client встраивается в iframe/JS в external app; session sync работает; UI адаптируется.
3. **Метрика идеальности**: `Δф=+2 capabilities (full MCP server, embed mode), Δсложности=+0 новых абстракций (используются существующие: MCPClientManager, UIClient) → Δф/Δсложности = ∞ ≥ 1`. Идеальность максимальна — система переходит в надсистему без увеличения сложности.
4. **Документация обновлена**: `ARCHITECT.md` § 7 ADR обновлён; § 8 Trade-offs обновлён (ИКР-0 достигнут). **Система формально соответствует ИКР-0 — LLM Client «исчез» как отдельный продукт**.

---

## 11. Критический путь и параллелизация

### 11.1 Критический путь

Критический путь плана — последовательность фаз, не допускающих параллелизации из-за жёстких зависимостей:

```
Phase 1 (22.5 чел-дн, v1.2.0) → Phase 2 (19 чел-дн) → Phase 3 (31 чел-дн) → [branching point]
                                                                              ├─ Phase 4 (16 чел-дн)
                                                                              ├─ Phase 5 (31 чел-дн, partial after Phase 4)
                                                                              └─ Phase 6 (18 чел-дн, после Phase 3 ADR-004 preview + Phase 5 ADR-019)
```

Суммарная длительность критического пути: **22.5 + 19 + 31 + 31 + 18 = 121.5 чел-дн** чистой разработки (v1.2.0) + 16 чел-дн Phase 4 (можно параллелить с Phase 5). С учётом ревью, тестирования и интеграционных итераций — **16–18 недель при команде 2 разработчика** (v1.0.0: 14–16; v1.1.0: 15–17; v1.2.0: +1 неделя на AG-составляющую в Phase 1).

Phase 1–3 — линейный путь. Каждая следующая фаза требует полного завершения предыдущей (см. § 3.2 критерии перехода). Параллелизация невозможна: ADR-010 (Phase 2) требует Redis, введённый в ADR-013 (Phase 1) и graph из AG-1 (Phase 1); ADR-011 (Phase 3) требует PostgreSQL tsvector из ADR-020 (Phase 2); ADR-016 (Phase 3) требует `ModelCapabilityMatrix`, который ссылается на ADR-015 (тоже Phase 3 — внутренняя зависимость).

### 11.2 Возможности параллелизации

После Phase 3 открываются три независимых направления. При увеличении команды до 3+ разработчиков они могут вестись параллельно:

1. **Phase 4 (Local LLM)** — полностью независим от Phase 5. Может вестись параллельно с Phase 5. Требует только завершения Phase 3 (для ADR-016, на который ссылается ADR-009).

2. **Phase 5 (Scale)** — частично зависит от Phase 4 (ADR-019 signed manifests требуют `MCPClientManager` из Phase 4 ADR-012). Однако ADR-018 (SessionStore) и (расш. ADR-008) (async rendering) могут вестись параллельно с Phase 4.

3. **Phase 6 (Interoperability)** — требует ADR-004 preview (Phase 3) и ADR-019 (Phase 5). Не может начинаться раньше завершения Phase 5.

**Оптимальное расписание для команды 3+ разработчиков**:

| Неделя | Разработчик 1 | Разработчик 2 | Разработчик 3 |
|---|---|---|---|
| 1–2 | Phase 1 (ADR-013) | Phase 1 (ADR-014) | Phase 1 (расш. ADR-008) |
| 3–4 | Phase 2 (ADR-010) | Phase 2 (ADR-017) | Phase 2 (ADR-020) |
| 5–8 | Phase 3 (ADR-011) | Phase 3 (ADR-015 + ADR-016) | Phase 3 (ADR-004 preview) |
| 9–10 | Phase 4 (ADR-009) | Phase 5 (ADR-018) | Phase 5 (расш. ADR-008) |
| 11–12 | Phase 4 (ADR-012 + ADR-001) | Phase 5 (ADR-019) | Phase 5 (ABAC+RBAC) |
| 13–14 | — | Phase 5 finalize | Phase 6 (MCP Server full) |
| 15–16 | — | Phase 6 (Embed mode) | — |

Суммарно: 16 недель при команде 3 разработчика (vs 16 недель при команде 2). Увеличение команды сверх 3 разработчиков не ускоряет критический путь — все параллельные задачи уже распределены.

### 11.3 Зависимости ADR

Граф зависимостей ADR (упрощённый):

```
ADR-013 (Phase 1) ──┐
                    ├─→ ADR-010 (Phase 2, Redis WAL)
ADR-014 (Phase 1) ──┘
                    ──→ ADR-020 (Phase 2, hybrid RAG) ──→ ADR-017 (Phase 2, reranker)
                    ──→ ADR-011 (Phase 3, semantic cache, depends on ADR-017)
                    ──→ ADR-015 (Phase 3, router) ──→ ADR-016 (Phase 3, capability matrix)
                    ──→ ADR-004 preview (Phase 3) ──→ ADR-019 (Phase 5) ──→ MCP Server full (Phase 6)
ADR-009 (Phase 4) ──→ (расш. ADR-009 в ADR-017: RerankerRegistry)
ADR-012 (Phase 4) ──→ ADR-019 (Phase 5, MCPClientManager)
(расш. ADR-001) (Phase 4) ──→ использует embeddings из ADR-016
ADR-018 (Phase 5) ──→ (использует UIClient из ADR-004, но preview достаточно)
(расш. ADR-008) async (Phase 5) ──→ независим
(новый) ABAC+RBAC (Phase 5) ──→ независим
Embed mode (Phase 6) ──→ (использует UIClient, но не требует full MCP Server)
```

Внутренние зависимости внутри фазы указаны в таблицах § 5.2–10.2 (столбец «Зависимости»).

---

## 12. Quick Wins для немедленного внедрения

Перед стартом Phase 1 в полном объёме рекомендуется внедрить три quick wins, не требующих полной фазы:

| # | Quick Win | ADR | Срок (чел-дн) | Эффект |
|---|---|---|---|---|
| 12.1 | SSE + HTTP Cancel Endpoint (полная реализация ADR-013) | ADR-013 | 2 | UX: cancel работает за <100 мс |
| 12.2 | Single S3 Storage (MinIO в dev) — упразднение LocalFileStorage | (расш. ADR-008) | 2 | Dev-prod parity |
| 12.3 | State-Delta Cycle Detection (preview, без embeddings integration) | (расш. ADR-001) | 3 | Determinism: циклы детектируются на ранней стадии |

**Суммарно**: 7 чел-дн. При команде 2 разработчика — 1 sprint (2 недели с учётом ревью и тестирования).

Эти три quick wins выбраны по трём критериям: (а) **низкая сложность** (Low уровень) — не требуют новых зависимостей, кроме уже имеющихся (Redis, MinIO); (б) **высокий эффект** — каждый закрывает явное UX или reliability-противоречие; (в) **независимость** — не блокируют остальные ADR Phase 1–4. ADR-014 (DualStreamLogger) не включён в quick wins — требует KMS/Vault, который ещё не развёрнут.

После quick wins Phase 1 сокращается до одного ADR (ADR-014) + 1 день на интеграцию уже готовых quick wins в полноценные ADR-статусы.

---

## 13. Риски и встречные противоречия при внедрении

### 13.1 Риск over-engineering

ТРИЗ-анализ предлагает 12 новых ADR. Внедрение всех разом превратит архитектуру в «франкенштейна» с избыточной абстракцией. Контр-мера: внедрять только те ADR, которые явно соответствуют текущей фазе roadmap. ADR-019 (signed manifests) не нужен в Phase 1, его внедрение в MVP — over-engineering.

**Встречное противоречие**: ТРИЗ-анализ рекомендует много абстракций (`UIClient`, `MCPTransport`, `VectorStoreRegistry`, `ToolCallingAdapter`), но каждая абстракция — это кривая обучения и потенциальная точка отказа. Применить принцип ТРИЗ #16 (частичное/избыточное действие): внедрять абстракцию «избыточно» (полный interface), но имплементировать «частично» (одна реализация). Когда появится вторая реализация — interface уже готов.

**Контроль**: метрика идеальности `Δф/Δсложности ≥ 1` на каждой фазе (см. § 15). Если метрика падает — ADR откатывается.

### 13.2 Риск конфликта с существующими ADR

Некоторые новые ADR явно противоречат существующим (см. § 7.4, § 9.3):

- ADR-015 (Cost-aware router) противоречит ADR-005 (плану fallback chain) — fallback удаляется.
- ADR-018 (External session) противоречит ADR-002 (Streamlit native `session_state`) — требуется sync layer.
- (расш. ADR-008) Single S3 storage противоречит ADR-008 (LocalFileStorage для MVP) — local упраздняется.
- ADR-009 (Plugin registry) противоречит ADR-003 (`VectorStoreFactory` с `match kind:`) — factory заменяется на registry.

**Контр-мера**: каждый новый ADR должен содержать явный раздел `Supersedes:` с указанием заменяемых ADR и `Migration plan:`. Архитектурный комитет ревьюит conflicts перед approval. `Migration plan:` должен включать: (а) период сосуществования старого и нового; (б) критерий полного упразднения старого; (в) rollback-стратегию при провале миграции.

### 13.3 Риск кривой обучения

`UIClient`, `MCPTransport`, `VectorStoreRegistry`, `ToolCallingAdapter`, `LLMRouter`, `ModelCapabilityMatrix`, `DualStreamLogger` — 7 новых абстракций. Команда из 2 разработчиков может потратить больше времени на освоение, чем на имплементацию.

**Контр-мера**: каждая абстракция должна сопровождаться ADR-документом, код-примером и unit-test-паттерном. Onboarding-session для каждой новой абстракции. Метрика: «время от onboarding до первого PR» ≤ 2 дня. Если метрика не выполняется — абстракция пересматривается (возможно, упрощается).

### 13.4 Риск «ложной зрелости»

После внедрения 12 ADR система может казаться «зрелой», но фактически быть перегруженной. Метрики идеальности (из закона 4.4 в `TRIZ-ANALYSIS.md`) должны отслеживаться: `delta функциональности / delta сложности ≥ 1`. Если после внедрения ADR метрика падает — ADR нужно откатить.

**Контр-мера**: метрика идеальности замеряется на границе каждой фазы (см. § 15). Падение метрики — триггер для ревизии плана: либо ADR пересматривается, либо фаза продлевается для дополнительного пилота.

### 13.5 Риск зависимости от внешних сервисов

Новые ADR добавляют зависимости: KMS/Vault (ADR-014), Cohere Rerank (опционально в ADR-017), Prometheus metrics (ADR-015), Auth provider (ABAC+RBAC), Playwright PDF worker. Каждая зависимость — потенциальный single point of failure.

**Контр-мера**: каждая новая зависимость должна иметь in-process fallback или degrade-gracefully поведение. Например:

- KMS недоступен → forensic stream переключается на local encrypted file (с предупреждением в observability).
- Cohere Rerank недоступен → fallback на `bge-reranker-base` (локальный).
- Prometheus недоступен → `LLMRouter` продолжает работать на локальных метриках (с потерей long-term observability).
- Auth provider недоступен → fail-safe режим (deny destructive ops, allow read-only).
- Worker недоступен → fast path продолжается, slow path ставится в Redis queue (с alerting).

### 13.6 Риск «внедрено, но не используется»

Классический риск архитектурного рефакторинга: абстракция внедрена, interface готов, но никто не пишет вторую имплементацию. `VectorStoreRegistry` существует, но используется только Chroma (Qdrant и pgvector не подключены). `MCPTransport` готов, но используется только stdio. В результате — абстракция не оправдана, сложность без пользы.

**Контр-мера**: для каждой абстракции фиксируется «вторая имплементация» как acceptance criteria фазы. Если вторая имплементация не написана к концу следующей фазы — абстракция помечается как `Speculative` и либо получает имплементацию в течение 1 sprint, либо откатывается. Это стимулирует actual use, а не theoretical readiness.

---

## 14. Пилотное внедрение и метрики успеха

Перед полным внедрением каждого ADR с уровнем Medium или High — пилотный тест на staging. Пилот провалился → ADR пересматривается, не внедряется в production. Пилот успешен → full rollout.

### 14.1 Пилоты и метрики

| ADR | Пилот | Метрика успеха | Критерий отката |
|---|---|---|---|
| **ADR-010** (Async checkpoint) | 1 неделя на staging | Latency checkpoint <2 мс; восстановление при restart корректно | Потеря состояния при restart Redis ИЛИ PostgreSQL одновременно |
| **ADR-011** (Semantic cache) | 100 запросов на staging | Hit rate cache >15%; stale answers <1% | Stale answers >1% ИЛИ hit rate <10% |
| **ADR-013** (SSE + cancel) | 1 sprint на dev | Cancel latency <100 мс в 99% случаев | Cancel не доходит до LLM-вызова (race condition) |
| **ADR-014** (DualStreamLogger) | Audit на staging | PII leaks = 0 в operational stream | Forensic stream недоступен >1 час ИЛИ PII leak обнаружен |
| **ADR-015** (Cost-aware router) | 1 месяц shadow mode | Cost predictability ±10%; cost overrun <20% | Cost overrun >20% ИЛИ router делает неприемлемые decisions (e.g., Ollama для high-stakes запроса) |
| **ADR-016** (Tool capability adapter) | Pilot на Ollama | ReAct-эмуляция success rate ≥80% | Success rate <60% ИЛИ false capability matrix entries приводят к runtime errors |
| **ADR-017** (Reranker) | A/B test 2 недели | Recall@5 ↑ ≥15% vs baseline | Latency retrieval ↑ >100 мс ИЛИ recall@5 не вырос |
| **ADR-018** (External session) | 2 инстанса staging | Session survives instance switch; latency <1 сек | Session loss при переключении инстансов |
| **ADR-019** (MCP signed manifests) | 5 MCP-серверов | Подписи валидируются; destructive ops подтверждаются | Подделанная подпись принимается ИЛИ destructive op выполняется без подтверждения |
| **ADR-020** (Hybrid RAG) | A/B test 1 неделя | Recall ↑ для точных терминов ≥30% | Latency retrieval ↑ >50% ИЛИ recall для точных терминов не вырос |

### 14.2 Процесс проведения пилота

1. **Подготовка** (1–2 дня): deploy на staging с feature flag; подготовка метрик-дашборда; написание тестовых сценариев.
2. **Shadow mode** (1 неделя для latency-ADR, 1 месяц для cost-ADR): ADR работает параллельно с существующей реализацией; результаты сравниваются; никаких user-facing изменений.
3. **A/B test** (1–2 недели): ADR работает для 50% трафика; метрики сравниваются с control.
4. **Анализ** (2–3 дня): сбор метрик, проверка критериев успеха и отката.
5. **Решение**: Approved (full rollout) / Needs revision (возврат в разработку) / Rejected (отмена ADR).

Пилоты для quick wins (§ 12) — упрощённые: 1 sprint на dev, без shadow mode.

---

## 15. Управление идеальностью системы

### 15.1 Метрика идеальности

Идеальность = Σ функциональных возможностей / Σ сложности компонентов.

**Σ функциональности** измеряется:

- Числом capabilities (RAG, tools, MCP, streaming, semantic cache, cost-aware routing, MCP server, embed mode, multi-instance, hybrid ABAC+RBAC, etc.).
- Метриками качества (recall@5, latency p99, cost per 1k requests, stale answer rate).
- Числом поддерживаемых моделей (через `ModelCapabilityMatrix`).
- Числом поддерживаемых VectorStore (через `VectorStoreRegistry`).

**Σ сложности** измеряется:

- Числом ADR (включая Proposed и Approved).
- Числом абстракций (interface-ов, registries, adapters, factories).
- LOC core-кода (без тестов и конфигов).
- Числом внешних зависимостей (Redis, PostgreSQL, KMS, Cohere Rerank, Auth provider, etc.).

### 15.2 Контрольные точки ревизии

Метрика идеальности замеряется на границе каждой фазы и сравнивается с предыдущей. Требования:

| После фазы | Минимальное значение Δф/Δсложности | Эффект при нарушении |
|---|---|---|
| Phase 1 (v1.2.0) | ≥ 2.0 (6 new capabilities — cancel, dual-logging, dev-prod parity, UI scaffold + UIClient, agent-service scaffold + LangGraph orchestration — / 3 new deps — KMS/Vault + UIClient abstraction + LangGraph/LLM provider) → ratio = 2.0. Если UI-3 откатывается: 5 caps / 3 deps = 1.67 < 2.0 → UI-2 или AG-2 пересматривается. Если AG-2 откатывается (mock-LLM): 5 caps / 3 deps = 1.67 ≥ 1 — порог соблюдён, но Phase 1 завершается без реальной LLM-интеграции | UI-3 откат (`@st.fragment` удалается, `BACKLOG.md` §6.2) ИЛИ AG-2 откат (LLMProviderFactory, переносится в Phase 3) ИЛИ UI-2 откат до Phase 5 (возврат к v1.0.0 модели) |
| Phase 1 (v1.1.0 — для сравнения) | ≥ 2.0 (4 new capabilities / 2 new deps) → ratio = 2.0 | ADR-014 пересматривается (KMS — потенциально избыточен) ИЛИ UI-2 (`UIClient` abstraction) откатывается до Phase 5 |
| Phase 1 (v1.0.0 — для сравнения) | ≥ 2.0 (2 new capabilities / 1 new dependency) | ADR-014 пересматривается (KMS — потенциально избыточен) |
| Phase 2 (v1.2.0) | ≥ 1.5 (5 new capabilities — async checkpoint, reranker, hybrid retrieval, web_search tool, rag_query tool — / 2 new dependencies — bge-reranker, tsvector) → ratio = 2.5 | Рефакторинг на упрощение reranker (отказ от pluggable registry) |
| Phase 2 (v1.0.0 — для сравнения) | ≥ 1.5 (3 new capabilities / 2 new dependencies) | Рефакторинг на упрощение reranker |
| Phase 3 | ≥ 1.5 (4 new capabilities / 2 net new abstractions — `fallback_chain` упразднён) | Упрощение `LLMRouter` (отказ от privacy policy) |
| Phase 4 (v1.2.0) | ≥ 1.0 (4 new capabilities — plugin registry, auto-transport, cycle detection, mcp_call tool — / 3 new abstractions — VectorStoreRegistry, MCPTransport, state-delta detector) → ratio = 1.33 | ADR пересматривается целиком |
| Phase 4 (v1.0.0 — для сравнения) | ≥ 1.0 (3 new capabilities / 3 new abstractions — граничный случай) | ADR пересматривается целиком |
| Phase 5 | ≥ 1.0 (v1.0.0: 4 caps / 4 deps; v1.1.0: 5 caps / 4 deps → 1.25, граничный) | Отказ от ABAC, retention RBAC; если v1.1.0 — отказ от UI-5 (`ChainlitClient`) и возврат к single-backend (Streamlit-only) |
| Phase 6 | ≥ 5.0 (2 new capabilities / 0 new abstractions — использование существующих) | — (должен выполняться) |

Если метрика падает — архитектурный комитет пересматривает план: либо ADR упрощается, либо фаза продлевается, либо план модифицируется (новые ADR могут быть отложены до следующего ТРИЗ-анализа).

### 15.3 Автоматизация замеров

Метрики Σ функциональности и Σ сложности извлекаются автоматически:

- **Capabilities**: из `ModelCapabilityMatrix` + `VectorStoreRegistry` + `tool_registry` + `MCPClientManager` + `RerankerRegistry`.
- **Complexity**: из `pyproject.toml` (dependencies count) + AST-анализ кода (число interface declarations) + ADR count из `ARCHITECT.md` § 7.

Дашборд в observability stack (Grafana) отображает trend идеальности по фазам. Падение trend — alerting в Slack #architecture.

---

## 16. Процесс ревью и принятия ADR

### 16.1 Архитектурный комитет

Архитектурный комитет — орган принятия решений по ADR. Состав: tech-лид (chair), 2 senior-разработчика, 1 security officer (для ADR с security-импликациями), 1 DevOps (для ADR с инфраструктурными зависимостями). Кворум — 3 члена, включая tech-лид.

Частота заседаний: каждые 2 недели (sprint boundary). На каждом заседании рассматриваются:

- **New ADR proposals**: драфты из текущей фазы.
- **Pilot results**: отчёты по пилотам с метриками (см. § 14).
- **Conflict reviews**: новые ADR, противоречащие существующим (см. § 13.2).
- **Ideality metric**: trend по фазам (см. § 15).

Решения: `Approved` / `Rejected` / `Needs revision`. `Approved` → full rollout. `Rejected` → ADR закрывается, противоречие возвращается в `TRIZ-ANALYSIS.md` § 10. `Needs revision` → возвращается автору с замечаниями, рассматривается на следующем заседании.

### 16.2 Шаблон нового ADR

Каждый новый ADR оформляется по шаблону `ARCHITECT.md` § 7:

````markdown
### ADR-NNN: <Title>

**Status**: Proposed | Approved | Rejected | Superseded by ADR-XXX
**Date**: YYYY-MM-DD
**Decision Makers**: <names>
**Supersedes**: ADR-XXX (если применимо)
**Superseded by**: ADR-XXX (если применимо)
**Related**: ADR-XXX, ADR-YYY
**Phase**: <Phase из ROADMAP.md>
**TRIZ contradiction**: C-X из TRIZ-ANALYSIS.md § 10
**TRIZ principles**: #X, #Y, #Z

**Context**: <описание проблемы и существующего состояния>

**Decision**: <описание принятого решения с деталями имплементации>

**Consequences**:
- (+) <положительные эффекты>
- (-) <отрицательные эффекты>

**Migration plan**: <для ADR с Supersedes — путь миграции>

**Pilot criteria**: <метрики успеха и критерии отката из § 14>

**Open questions**: <вопросы, оставленные на Phase N+1>
````

### 16.3 Критерии Approved / Rejected / Needs revision

**Approved** — ADR соответствует всем критериям:

1. Пилотные метрики успеха достигнуты (см. § 14).
2. Критерии отката не сработали.
3. Метрика идеальности Δф/Δсложности ≥ 1 (см. § 15).
4. Конфликты с существующими ADR разрешены (явный `Supersedes:` + `Migration plan:`).
5. Документация обновлена: `ARCHITECT.md` § 7 (ADR добавлен), § 8 (Trade-off помечен resolved), § 12 (Open questions закрыты при применимости).

**Rejected** — любое из:

- Пилотные метрики не достигнуты.
- Критерий отката сработал.
- Конфликт с существующим ADR не разрешён.

**Needs revision** — недостаточно данных:

- Пилот не завершён или метрики borderline.
- Migration plan неполный.
- Документация не обновлена.

---

## 17. Открытые вопросы (перенесено из `ARCHITECT.md`)

Следующие открытые вопросы из `ARCHITECT.md` § 12 закрываются по мере прохождения фаз:

| Q-ID | Вопрос | Резолюция | Фаза закрытия |
|---|---|---|---|
| Q-1 | Ollama integration (локальные LLM) | ADR-016 (Tool Capability Adapter) + ADR-015 (LLMRouter с Ollama как cheap-tier) | Phase 3 (preview) → Phase 4 (full) |
| Q-2 | LangSmith pricing (observability cost) | ADR-014 (DualStreamLogger — собственный observability, не зависящий от LangSmith) | Phase 1 |
| Q-3 | Streamlit + async (I/O concurrency) | ADR-013 (cancel через Redis pub/sub, не Streamlit native) + ADR-018 (session в Redis, не в Streamlit) + UI-2/UI-3 (`UIClient` abstraction и `@st.fragment` — из v1.1.0, частичная резолюция C-1 в Phase 1) | Phase 1 (UI-2/UI-3 — частично) + Phase 1 (ADR-013) + Phase 5 (ADR-018 — полностью) |
| Q-4 | MCP-серверы с stdio в docker-compose | ADR-012 (MCP Transport Auto-Negotiation) | Phase 4 |
| Q-5 | Стоимость LLM при >50k токенов контекста | ADR-011 (Semantic Cache) + ADR-015 (Cost-aware Router) + ADR-017 (Reranker, снижение noise) + ADR-020 (Hybrid RAG, точность > объём) | Phase 2 (частично) → Phase 3 (полностью) |

После завершения всех 6 фаз все 5 открытых вопросов закрыты. Новые открытые вопросы, возникающие в процессе внедрения, добавляются в `ARCHITECT.md` § 12 и адресуются либо в текущей фазе, либо выносятся на следующий ТРИЗ-анализ (см. § 18.6).

---

## 18. Следующие шаги

### 18.1 Ближайшие действия (срок: 2 недели)

1. **Архитектурный комитет**: ревью всех 12 драфтов ADR (ADR-009..ADR-020) на ближайшем заседании. Решение по каждому: Approved / Rejected / Needs revision. Срок: 2 недели. На первом заседании рассматриваются только ADR Phase 1 (ADR-013, ADR-014, расш. ADR-008) — остальные отложены до своих фаз.

2. **Подготовка инфраструктуры Phase 1**: развернуть Redis (для ADR-013 pub/sub + будущий ADR-010), MinIO (для расш. ADR-008), local Vault dev-mode (для ADR-014 KMS). Срок: 1 неделя, параллельно с п.1.

3. **Пилотное внедрение quick wins** (см. § 12): ADR-013 (SSE+cancel), расш. ADR-008 (Single S3 Storage), расш. ADR-001 (Cycle Detection preview). Срок: 1 sprint (2 недели).

### 18.2 Метрики идеальности (срок: до конца Phase 1)

Добавить в observability dashboard метрику «delta функциональности / delta сложности» (через LOC + ADR count + capability count). Дашборд в Grafana, алертинг в Slack #architecture при падении trend. Срок: до конца Phase 1 (4 недели).

### 18.3 Ревизия плана (срок: на границе каждой фазы)

После завершения каждой фазы архитектурный комитет пересматривает план:

- Все ли ADR фазы Approved?
- Метрика идеальности не упала?
- Открытые вопросы фазы закрыты?

Если да — переход к следующей фазе. Если нет — продление фазы на 1 sprint, пересмотр ADR.

### 18.4 Triage оставшихся вопросов (срок: Phase 2)

Q-1 (Ollama), Q-2 (LangSmith pricing), Q-4 (Streamlit+async) из § 12 `ARCHITECT.md` требуют отдельных ТРИЗ-разборов, если их базовая резолюция (см. § 17) окажется недостаточной. Срок: Phase 2 — после накопления опыта с ADR-010, ADR-014, ADR-013.

### 18.5 Обновление `ARCHITECT.md` (срок: после каждого approval ADR)

После approval каждого ADR — обновление `ARCHITECT.md`:

- § 7 ADR: добавлен новый ADR (или помечен как Superseded).
- § 8 Trade-offs: соответствующее противоречие помечено как resolved.
- § 12 Открытые вопросы: соответствующий Q закрыт.
- § 13 (если есть) — компонентная диаграмма обновлена.

Срок: 1 день после approval. Ответственный: автор ADR.

### 18.6 Повторный ТРИЗ-анализ (срок: после Phase 3)

Через 2 фазы (после Phase 3) — повторить ТРИЗ-анализ, так как архитектура эволюционирует и появятся новые противоречия. Граница Phase 3 выбрана как контрольная точка, потому что: (а) все High-приоритетные противоречия из текущего анализа закрыты; (б) Phase 4–6 имеют граничные значения метрики идеальности — риск накопления новых противоречий максимальный.

Повторный анализ должен:

- Пересмотреть существующие ADR (что-то может стать `Superseded`).
- Выявить новые противоречия, возникшие в результате внедрения.
- Обновить ИКР-0..ИКР-7 — некоторые могут быть достигнуты, новые формулировки.
- Пересмотреть `ROADMAP.md` — фазы 4–6 могут быть пересмотрены.

Срок: 2 недели (1 неделя анализа + 1 неделя ревью). Ответственный: tech-лид + внешний ТРИЗ-консультант (если доступен).

---

## 19. Приложения

### 19.1 Глоссарий

| Термин | Определение |
|---|---|
| **ADR** (Architecture Decision Record) | Документ, фиксирующий архитектурное решение: контекст, решение, последствия. Шаблон в `ARCHITECT.md` § 7. |
| **ТРИЗ** | Теория решения изобретательских задач, Г. Альтшуллер. Применена в `TRIZ-ANALYSIS.md` для анализа архитектуры LLM Client. |
| **ИКР** | Идеальный конечный результат — предельное состояние системы, при котором она выполняет функцию, не существуя как объект. ИКР-0..ИКР-7 в `TRIZ-ANALYSIS.md` § 3. |
| **Веполь (Su-Field)** | Минимальная техническая система из двух веществ (S1, S2) и поля (F). Применяется в `TRIZ-ANALYSIS.md` § 8 для анализа ключевых триад. |
| **Capability** | Функциональная возможность системы: RAG, tools, MCP, streaming, semantic cache, cost-aware routing, etc. |
| **Абстракция** | Interface / registry / adapter / factory — структурный элемент архитектуры, скрывающий детали реализации. |
| **Идеальность** | Σ функциональности / Σ сложности. Метрика эволюции системы по закону 4.4 из `TRIZ-ANALYSIS.md`. |
| **Phase** | Этап развития продукта в `ROADMAP.md`: MVP → Alpha → Beta → Local LLM → Scale → Interoperability. |
| **Pilot** | Тестовое внедрение ADR на staging с метриками успеха и критериями отката (см. § 14). |
| **Supersedes** | Явное указание в новом ADR, какой существующий ADR он заменяет. |
| **Quick win** | ADR с Low сложностью, высоким эффектом, независимый от других — внедряется до основной фазы. |
| **G-1..G-5** | Бизнес-цели LLM Client из `ARCHITECT.md` § 2. |
| **C-1..C-15** | Технические противоречия из `TRIZ-ANALYSIS.md` § 10. |
| **Q-1..Q-5** | Открытые вопросы из `ARCHITECT.md` § 12. |

### 19.2 Связанные документы

- `ARCHITECT.md` v1.0.0 — текущее состояние архитектуры LLM Client: 7 слоёв, 8 ADR, 8 Trade-offs, 5 открытых вопросов. Базовый документ.
- `TRIZ-ANALYSIS.md` v1.0.0 — ТРИЗ-анализ архитектуры: 15 противоречий, 4 вепольные триады, ИКР-0..ИКР-7, 12 новых ADR. Источник архитектурных решений для `ROADMAP.md`.
- `ROADMAP.md` v1.0.0 (этот документ) — план внедрения ADR по фазам.
- `CONTRIBUTING.md` (если есть) — процесс внесения изменений и стандарты кодирования.
- `SECURITY.md` (если есть) — security-политики, включая PII handling, RBAC, audit.

### 19.3 Ресурсы по ТРИЗ (из `TRIZ-ANALYSIS.md` § 14.4)

- Альтшуллер Г.С. «Найти идею» — базовая методология.
- Альтшуллер Г.С. «Творчество как точная наука» — 40 принципов и матрица.
- ТРИЗ-матрица онлайновых инструментов: https://www.triz50.org/
- Standard Solutions: https://www.triz-journal.com/standard-solutions/
- Su-Field Analysis: https://www.triz-journal.com/substance-field-analysis/
- Применение ТРИЗ к ПО: https://triznext.org/ (библиотека кейсов)

### 19.4 Версионирование документа

`ROADMAP.md` пересматривается:

- На границе каждой фазы (контрольная точка метрики идеальности).
- При каждом Approved/Rejected ADR (обновление статусов).
- После повторного ТРИЗ-анализа (см. § 18.6).

Семантическое версионирование:

- **MAJOR** (v2.0.0): пересмотр фаз, добавление/удаление ADR.
- **MINOR** (v1.1.0): новый ADR в существующей фазе, изменения в составе работ.
- **PATCH** (v1.0.1): уточнения сроков, метрик, критериев готовности.

---

*Конец ROADMAP.md. Документ должен пересматриваться на границе каждой фазы и после каждого Approved/Rejected ADR; новые ADR добавлять в соответствующую фазу с обновлением § 4 сводной таблицы.*

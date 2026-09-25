# BACKLOG.md — Недостающая UI- и Agent-service работа для LLM Client

| Атрибут | Значение |
|---|---|
| Версия документа | 1.1.0 |
| Дата | 2026-09-26 |
| Источники | `ARCHITECT.md` v1.1.0 §4.1, §4 (agent-service container, строка 124), §5.1 (строка 357), §5.2.2 (Orchestration), §5.2.3 (LLM Provider), §5.2.4 (Tool Layer), §7 ADR-001/ADR-002/ADR-005/ADR-006/ADR-007; `TRIZ-ANALYSIS.md` v1.0.0 §3.2 (ИКР-1), §4.1, §4.2, §5.1 (C-1), §11 (драфт ADR-018); `ROADMAP.md` v1.0.0 §3.4, §5, §9.3, §15.2; `MVP-PROMPTS.md` v1.0.0 §3 (C-1..C-6), §4 (D-1..D-6) |
| Статус | Draft → Review → Approved |
| Аудитория | Tech-лид + Frontend-разработчик + ML/Backend-разработчик + Архитектурный комитет |
| Связанные документы | `UI-PROMPTS.md` v1.0.0 (промпты UI), `AG-PROMPTS.md` v1.0.0 (future — промпты AG), `ROADMAP.md` v1.2.0 (future патч — AG-составляющая в Phase 1) |

---

## 1. Назначение документа

`BACKLOG.md` закрывает разрыв между тремя файлами промптов (`MVP-PROMPTS.md`, `ALPHA-PROMPTS.md`, `BETA-PROMPTS.md`, покрывающими Phase 1–3) и архитектурным замыслом, в котором Presentation Layer Streamlit фиксируется ADR-002 как «уже существующий» с первого дня Phase 1. Анализ показал: единственный UI-касающий промпт во всём корпусе — `C-5` из `MVP-PROMPTS.md` (UI watcher для auto-cancel), и он является JS-инъекцией в уже существующий Streamlit, а не конструкцией UI. В результате любой, кто проходит промпты «с нуля», поднимает Redis, MinIO, Vault, cancel-endpoint, dual-stream logger — но не имеет самого чата, к которому всё это прикручивается.

Документ выполняет три функции. **Первая** — формальный реестр всех UI- и Agent-service работ, явно распределённых по фазам, с приоритетами, зависимостями и оценками в чел-дн. **Вторая** — точка входа для архитектурного комитета при ревью: какие работы вводятся в Phase 1 досрочно (нарушая исходный план `ROADMAP.md` v1.0.0), какие остаются на Phase 2/4/5/6. **Третья** — трассировка: каждая работа связана с конкретным ADR и/или противоречием из `TRIZ-ANALYSIS.md` §10, что исключает ad-hoc задачи, не имеющие архитектурного обоснования.

Документ не вводит новые ADR. Все работы ссылаются на существующие или на драфты из `TRIZ-ANALYSIS.md` §11. Документ является input-ом для `UI-PROMPTS.md` v1.0.0 (конкретные промпты для UI-0..UI-3), для будущего `AG-PROMPTS.md` v1.0.0 (конкретные промпты для AG-0..AG-4) и для патча `ROADMAP.md` v1.1.0 → v1.2.0 (продвижение `UIClient` abstraction из Phase 5 в Phase 1 + добавление AG-составляющей в Phase 1).

---

## 2. Контекст проблемы

### 2.1 Состояние UI в текущем корпусе документов

`ARCHITECT.md` v1.1.0 §4.1 (строка 172) фиксирует контейнер `ui` как Streamlit 1.40 с ответственностью «Чат UI, история сессий, кнопки скачивания». §5 (строки 190–192) описывает Presentation Layer как первый из семи слоёв архитектуры: «Chat components, session history, file download». ADR-002 (§7, строки 730–739) фиксирует выбор Streamlit для MVP/Alpha и планирует миграцию на Chainlit или FastAPI+Next.js в Phase 5.

Однако при этом ни один промпт-файл Phase 1–3 не описывает, **как именно создаётся этот UI**. `MVP-PROMPTS.md` строка 53 упоминает «существующий docker-compose уже содержит PostgreSQL и Streamlit-сервис» — то есть Streamlit подразумевается как данный, не как создаваемый. ТРИЗ-анализ в §4.5 (строка 258) прямо диагностирует дисбаланс: «в LLM Client явно отстаёт Presentation Layer (Streamlit single-instance, нет real-time collab, нет mobile)… Сильно переразвиты LLM Provider Layer и RAG Layer». §13.4 (строка 1237) рекомендует: «Заморозить RAG, направить ресурсы на UI и Security».

Несмотря на это, `ROADMAP.md` v1.0.0 §4 (строка 185–190) не включает ни одной UI-работы в Phase 1–3. Первая UI-работа — ADR-018 (External Session Store) — появляется в Phase 5 (строка 587: «Реализация SessionStore abstraction + RedisSessionStore + sync с Streamlit session_state»). Это создаёт три конкретных пробела:

- **Пробел A** — нет промпта на инициализацию Streamlit-чата. C-5 (UI watcher из `MVP-PROMPTS.md` §3) вообще бессмыслен без UI, к которому он прикручивается.
- **Пробел B** — нет промпта на chat-фронт: рендер стримящихся токенов через `st.write_stream`, история сессий, кнопки скачивания артефактов (`md`/`pdf`/`docx`).
- **Пробел C** — нет промпта на `UIClient` abstraction. TRIZ-рекомендация по C-1 (`TRIZ-ANALYSIS.md` §5.1, строка 339) описывает `UIClient` interface с методами `render_message`, `render_artifact`, `stream_token`, `handle_user_input` и реализации `StreamlitClient` (MVP), `ChainlitClient` (Alpha), `FastAPIClient` (Production). По логике `ROADMAP.md` v1.0.0 эта абстракция вводится в Phase 5 вместе с ADR-018, но это значит, что весь UI-код Phase 1–4 пишется под Streamlit-specific API, и миграция в Phase 5 становится переписыванием, а не «добавлением имплементации к существующему interface» (как требует принцип ТРИЗ #16, `ROADMAP.md` §3.4).

### 2.2 Корневая причина

Корневая причина — фазировка по принципу «сначала backend, потом UI», унаследованная из `TRIZ-ANALYSIS.md` §12 (строка 1130), где ADR-018 (External Session Store) привязан к Phase 5 как часть «перехода в multi-instance». В этой логике UI работает в single-instance весь Phase 1–4, и его абстракция нужна только когда возникает multi-instance-требование. Это разумно для **runtime**-аспектов UI (session store), но не для **interface**-аспектов (как UI-код вызывает бэкенд: через Streamlit-specific API или через общий `UIClient`).

Принцип ТРИЗ #16 («частичное/избыточное действие»), зафиксированный в `ROADMAP.md` §3.4 (строка 167), требует: «внедрять абстракцию "избыточно" (полный interface), но имплементировать "частично" (одна реализация). Когда появится вторая реализация — interface уже готов». `UIClient` — точный кейс: interface полный (4 метода), имплементация одна (`StreamlitClient`), вторая (`ChainlitClient`) появится в Phase 5. По логике принципа #16 interface должен быть введён в Phase 1, чтобы Phase 5 добавил имплементацию, а не переписывал код.

То же самое относится к UI-0 (scaffold) и UI-1 (base UI elements): они являются предпосылкой ADR-013 (cancel button UI), ADR-014 (PII score display в metadata) и ADR-008 (download buttons для file artifacts). Без них ADR-013/014/008 не имеют полного UX-цикла.

### 2.3 Состояние agent-service в текущем корпусе документов

`ARCHITECT.md` v1.1.0 §4 (строка 124, контейнерная диаграмма C4 Level 2) фиксирует контейнер `agent-service` (Python 3.11, LangGraph, LangChain) с ответственностью «Оркестрация графа агента, tool calling loop, streaming». §5.2.2 (строки 359–395) описывает Orchestration Layer: `StateGraph(AgentState)` с нодами `planner`, `tool_executor`, `rag_retriever`, `mcp_invoker`, `final_answer`, conditional edges `route_after_planner` / `route_after_tool`. §5.2.3 (строки 397–422) описывает LLM Provider Layer: `LLMProviderFactory.create()` с реализациями `ChatOpenAI` / `ChatAnthropic` / (Phase 4) `ChatOllama`. §5.2.4 (строки 424–462) описывает Tool Layer: `@tool`-декорированные функции `web_search`, `file_export`, `rag_query`, `mcp_call`. ADR-001 (§7, строки 718–728) фиксирует выбор LangGraph как оркестратора. ADR-006 (§7) фиксирует нативный tool calling через `bind_tools()`. ADR-007 (§7, строки 786–795) фиксирует SSE для streaming LLM-ответов.

Однако ни один промпт-файл Phase 1–3 не описывает, **как именно создаётся этот agent-service**. `MVP-PROMPTS.md` §1 A-1 (строка 53) упоминает «существующий docker-compose уже содержит PostgreSQL и Streamlit-сервис» — то есть agent-service подразумевается как данный, не как создаваемый. `UI-PROMPTS.md` §1 промпт UI-0 (строка 47) уточняет: «ADR-001: LangGraph-агент с существующим SSE endpoint POST `/sessions/{session_id}/chat` (запуск) и GET `/sessions/{session_id}/stream` (токены)» — то есть UI предполагает готовый agent-service, который сам по себе нигде не формализован. `BACKLOG.md` v1.0.0 закрыл UI-пробел (UI-0..UI-3), но не закрыл пробел agent-service.

В текущей кодовой базе (`src/llm_client/agent/__init__.py`) экспортируются только `IterationMonitor` и `compute_state_delta` (B-3 Quick Win — state-delta cycle detection). Самого графа LangGraph нет. В `pyproject.toml` декларированы `langgraph>=0.2.0`, `langchain>=0.3.0`, `langchain-openai>=0.2.0`, `langchain-anthropic>=0.3.0`, но ни один из этих пакетов не импортируется в `src/`. В `.env.example` нет `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `LLM_PROVIDER`. В `src/llm_client/api.py` есть только маршрут `POST /sessions/{id}/cancel` (ADR-013), но нет `POST /sessions/{id}/chat` и `GET /sessions/{id}/stream`. UI настроен на `AGENT_SERVICE_URL=http://localhost:8000`, но на этом адресе ничего нет, кроме `scripts/mock_agent_service.py` (FastAPI-мок, отдающий 1000 токенов строкой `"Hello, this is a simulated token from the mock agent-service."` с задержкой 50 мс).

Это создаёт четыре конкретных пробела:

- **Пробел D** — нет промпта на создание контейнера `agent-service` (AG-0): FastAPI-приложения с маршрутами `POST /sessions/{id}/chat` (запуск генерации) и `GET /sessions/{id}/stream` (SSE-стриминг токенов). Без этого UI-0 (scaffold) не имеет точки интеграции — стриминг в UI идёт из mock-сервиса, не из реального агента.
- **Пробел E** — нет промпта на построение графа LangGraph (AG-1). ADR-001 фиксирует выбор LangGraph, но не описывает, какие ноды и рёбра создаются в Phase 1. В результате C-4 (`MVP-PROMPTS.md` Блок C, «CancelSubscriber on agent side — между node-ами графа LangGraph») формально реализован (publisher/subscriber/registry работают, тесты green), но подписчику некому передавать сигнал — графа, который бы проверял `token.is_cancelled` между нодами, не существует.
- **Пробел F** — нет промпта на `LLMProviderFactory` (AG-2). `ARCHITECT.md` §5.2.3 описывает factory с `ChatOpenAI` / `ChatAnthropic`, но в `src/llm_client/agent/` нет `provider.py`. Без этого AG-1 не имеет LLM для вызова — граф есть, но обращаться не к чему.
- **Пробел G** — нет промпта на эмит SSE-событий из `graph.astream(...)` в формате ADR-007 (AG-3). `MVP-PROMPTS.md` C-6 (cancel → forensic logging) и D-5 (PII score в messages) реализованы на стороне записи (operational/forensic writers работают, pii_score считается), но UI ожидает SSE-события `event: metadata` (PII score, ADR-014), `event: artifact_ready` (ADR-008), `event: cancelled` (ADR-013). Без AG-3 UI-1 (PII badge, download buttons, cancelled badge) работает «вхолостую» — у него нет источника событий, кроме mock-сервиса, который их не эмитит.

### 2.4 Корневая причина пробелов D–G

Корневая причина та же, что и для пробелов A–C: фазировка по принципу «сначала инфра, потом продукт». `ROADMAP.md` v1.0.0 §5 (Phase 1 — MVP) фокусируется на инфраструктурных ADR (Redis, MinIO, Vault) и UX-cancel (ADR-013) / compliance (ADR-014). Сам agent-service с графом LangGraph и LLM-провайдером неявно предполагается как «уже работающий» — но кодовая база Phase 1 этого не содержит. В результате все 194 теста проходят, дашборд идеальности показывает ratio 2.0 ≥ 1, формальные критерии выхода Phase 1 соблюдены, но продукт не выполняет свою основную функцию — чат с LLM.

Это нарушает принцип ТРИЗ #2 (вынесение) в части «изделие отдельно, инструмент отдельно»: инфраструктура (Redis, MinIO, Vault) отделена и формализована, а само изделие (agent-service) слито с подразумеваемым контекстом и не формализовано. Принцип #16 (частичное/избыточное действие) требует обратного: формализовать interface (контракт `POST /sessions/{id}/chat` + `GET /sessions/{id}/stream` + SSE event protocol) «избыточно», а имплементацию графа и tool layer — «частично» (минимальный набор: `planner` + `final_answer`, без `tool_executor` / `rag_retriever` / `mcp_invoker` до Phase 2/4).

Принцип #19 (переход в другое измерение) применяется к AG-0: вместо единого in-process Streamlit + LangGraph (MVP-предположение `ARCHITECT.md` §5.1 строка 357: «UI общается с `agent_service` через Streamlit native callbacks (MVP, in-process) или через FastAPI + SSE (Alpha+ для multi-instance)») — сразу вынести agent-service в отдельный FastAPI-процесс. Это соответствует ADR-007 (SSE для streaming) и подготавливает multi-instance Phase 5 без переписывания (UI-4 / UI-5 в Phase 5 работают с тем же `AGENT_SERVICE_URL` контрактом).

---

## 3. Реестр работ

### 3.1 Соглашения

- **ID** — формат `UI-N` / `AG-N` для формализации. Не совпадает с ADR-ID; ADR-привязка указана отдельно.
- **Приоритет** — High / Medium / Low по влиянию на критерии выхода из Phase 1 (`ROADMAP.md` §5.6).
- **Фаза** — фаза, в которую работа попадает после патча `ROADMAP.md` v1.1.0. До патча — текущая фаза в `ROADMAP.md` v1.0.0 (отмечена в скобках).
- **Сложность** — по шкале `ROADMAP.md` §5.2: Low / Medium / High.
- **Срок** — оценка в чел-дн.
- **Зависимости** — список других UI-работ, ADR или инфра-блоков.
- **Резолвит** — противоречие из `TRIZ-ANALYSIS.md` §10 (если применимо).

### 3.2 Сводная таблица

| ID | Работа | Фаза (после патча) | Фаза (в v1.0.0) | Приоритет | Сложность | Срок (чел-дн) | Зависимости | Резолвит / Связанные G |
|---|---|---|---|---|---|---|---|---|
| **UI-0** | Scaffold Streamlit chat: `app.py` с `st.chat_input`, `st.chat_message`, session_id из URL, рендер стримящихся токенов через `st.write_stream` | Phase 1 (UI-составляющая, в v1.0.0 не формализована) | не формализована | High | Low | 1.5 | ADR-001 (LangGraph), ADR-002 (Streamlit), ADR-007 (SSE) | G-5 (UX MVP), ИКР-1 (UI адаптивен) |
| **UI-1** | Base UI elements: sidebar с историей сессий, кнопки скачивания артефактов (md/pdf/docx), индикатор streaming/cancelled/error | Phase 1 | Phase 1 (подразумевается) | High | Low | 1.5 | UI-0, ADR-008 (file artifacts), ADR-013 (cancel button), ADR-014 (PII score badge) | G-5 (UX MVP) |
| **UI-2** | `UIClient` abstraction: interface полный (4 метода), имплементация — `StreamlitClient` только. Подготовка к Phase 5 без переписывания | Phase 1 (после патча) | Phase 5 (внутри ADR-018) | High | Medium | 2.5 | UI-0, UI-1 | C-1 (частичная резолюция), принцип #16, G-1 (multi-instance prep) |
| **UI-3** | Streamlit fragments (1.40+) для разделения static shell + dynamic content — снимает узкое место из C-1 (re-runs vs streaming) | Phase 1 (после патча) | не формализована | Medium | Low | 1.0 | UI-0, ADR-007 (SSE) | C-1 (частичная резолюция), §4.3 TRIZ (согласование ритмики) |
| UI-4 | `SessionStore` abstraction + `RedisSessionStore` + sync callback с Streamlit `session_state` | Phase 5 (без изменений) | Phase 5 (ADR-018) | High | Medium | 4 | UI-2, Блок A-1 (Redis из MVP-PROMPTS) | C-1 (полная резолюция), ADR-018 |
| UI-5 | `ChainlitClient` — вторая имплементация `UIClient` interface | Phase 5 (без изменений) | Phase 5 (упоминается в ADR-002) | Medium | High | 6 | UI-2, UI-4 | C-1 (полная резолюция), ИКР-1 |
| UI-6 | `FastAPIClient` — третья имплементация `UIClient` (Production-контроль) | Phase 5+ | Phase 5+ (упоминается в ADR-002) | Low | High | 8 | UI-2, UI-4 | ИКР-1 |
| UI-7 | Embed mode: iframe API + JS SDK + session sync с host через postMessage | Phase 6 | Phase 6 | High | Medium | 6 | UI-2, ADR-004 (MCP Server full) | ИКР-0 (полная реализация) |
| **AG-0** | Scaffold agent-service: FastAPI с `POST /sessions/{id}/chat` + `GET /sessions/{id}/stream` (SSE) | Phase 1 (AG-составляющая, new в v1.1.0) | не формализована | High | Low | 1.5 | ADR-001 (LangGraph), ADR-007 (SSE) | G-5 (MVP), принцип #19 (вынесение) |
| **AG-1** | LangGraph agent graph: `StateGraph(AgentState)` с `planner` + `final_answer` нодами, conditional edges, cycle detection (B-3), cancel token wiring (C-1..C-4) | Phase 1 (AG-составляющая, new в v1.1.0) | не формализована | High | Medium | 2.5 | AG-0, ADR-001, ADR-006, B-3 (cycle detection), C-1..C-4 (cancel) | G-2 (унифицированный LLM), G-3 (tool layer — частично) |
| **AG-2** | `LLMProviderFactory`: OpenAI через `langchain-openai` (Anthropic/Ollama — stub `NotImplementedError` до Phase 3/4) | Phase 1 (AG-составляющая, new в v1.1.0) | не формализована | High | Low | 1 | AG-1, ADR-006 (native tool calling) | G-2 |
| **AG-3** | SSE event protocol emission: `event: token` / `metadata` (PII score, ADR-014) / `artifact_ready` (ADR-008) / `cancelled` (ADR-013) / `error` / `done` | Phase 1 (AG-составляющая, new в v1.1.0) | не формализована | High | Medium | 1.5 | AG-0, AG-1, ADR-007, ADR-013, ADR-014, расш. ADR-008, D-5 (PII metadata) | G-5 (связка с UI-1) |
| **AG-4** | `file_export` tool: `@tool(args_schema=FileExportArgs)` через `S3CompatibleStorage`, форматы md/txt (sync) + pdf/docx (async stub, 503 + retry) | Phase 1 (AG-составляющая, new в v1.1.0) | не формализована | High | Low | 1 | AG-1, AG-3, расш. ADR-008 | G-3 (tool layer — частично), G-5 (UI-1 downloads) |
| AG-5 | `web_search` tool via Tavily | Phase 2 (new в v1.1.0 как формализация) | не формализована | Medium | Low | 1 | AG-1, ADR-005, внешний API Tavily | G-3 |
| AG-6 | `rag_query` tool + base RAG pipeline (расширяется ADR-017/020 в ALPHA-PROMPTS) | Phase 2 (new в v1.1.0 как формализация) | не формализована | High | Medium | 4 | AG-1, ADR-003, ADR-017 (расширяет), ADR-020 (расширяет) | G-1 (RAG perf) |
| AG-7 | `mcp_call` tool (`mcp_invoker` нода) | Phase 4 (new в v1.1.0 как формализация) | не формализована | Medium | Medium | 3 | AG-1, ADR-012 (MCPTransport) | G-3 |

**Итого по фазам** (по патчу ROADMAP v1.2.0; UI-0..UI-3 включаются в Phase 1 как UI-составляющая §5.2.4, не выделяются в отдельную Phase 0; AG-0..AG-4 включаются в Phase 1 как AG-составляющая §5.2.5):
- Phase 1 (с патчем v1.2.0): UI 6.5 чел-дн (UI-0..UI-3) + AG 7.5 чел-дн (AG-0..AG-4) = +14 чел-дн — было 8 чел-дн в v1.0.0, стало 22.5 чел-дн в v1.2.0
- Phase 2: было 14 чел-дн, стало 19 чел-дн (+5 на AG-5 + AG-6)
- Phase 4: было 13 чел-дн, стало 16 чел-дн (+3 на AG-7)
- Phase 5: 4 + 6 + 8 = 18 чел-дн (UI-4, UI-5, UI-6) — без изменений против v1.1.0
- Phase 6: 6 чел-дн (UI-7) — без изменений против v1.0.0
- **Суммарная delta к ROADMAP v1.0.0**: +25.5 чел-дн (12.5 на UI из v1.1.0 + 13 на AG в v1.2.0)

### 3.3 Детализация работ

#### UI-0. Streamlit chat scaffold

**Привязка**: формализует «Phase 0» (упомянут в `TRIZ-ANALYSIS.md` §3 строка 99: «Streamlit + LangGraph как ускорители → time-to-MVP ≤ 15 чел-дн», но не имеет формального статуса в `ROADMAP.md`).

**Суть**: создать файл `app.py` — точку входа Streamlit-приложения. Использует `st.chat_input` для ввода пользователя, `st.chat_message` для рендера истории, `st.write_stream` для рендера стримящихся токенов от LangGraph-агента. Session_id извлекается из URL query param (`?session_id=...`) или генерируется при первом открытии и сохраняется в `st.session_state`. Подключение к `agent-service` через существующий SSE endpoint (ADR-007). Без этой работы все последующие UI-промпты (включая C-5 из `MVP-PROMPTS.md`) не имеют точки интеграции.

**Антипаттерны** (полный список — в `UI-PROMPTS.md` §1, промпт UI-0):
- НЕ хардкодь backend URL — через env `AGENT_SERVICE_URL`.
- НЕ пиши весь код в одном файле >300 строк — выдели `chat.py`, `session.py`, `render.py`.

**Definition of Done** — см. `UI-PROMPTS.md` §1, промпт UI-0.

---

#### UI-1. Base UI elements

**Привязка**: Phase 1. В `ARCHITECT.md` §4.1 (строка 172) прямо заявлено: «Чат UI, история сессий, кнопки скачивания» — но без промптов.

**Суть**: четыре UI-элемента, отсутствующие в минимальном scaffold UI-0:
1. Sidebar с историей сессий — список из `SessionStore.list_sessions(user_id)` (или из in-memory dict в Phase 1, до UI-4), с кнопкой «New session».
2. Кнопки скачивания артефактов — для каждого `file_export` tool call рендерится `st.download_button` с форматом `md`/`txt`/`pdf`/`docx` (соответствие с `ARCHITECT.md` §1).
3. Индикатор статуса LLM-вызова — три состояния: `streaming` (анимированный спиннер), `cancelled` (красный бейдж «Cancelled»), `error` (жёлтый бейдж с краткой причиной).
4. Бейдж PII score — для каждого user message рендерится цветной бейдж `PII: low|medium|high` на основе `pii_score` из `messages.metadata` (ADR-014).

**Антипаттерны** — см. `UI-PROMPTS.md` §2, промпт UI-1.

**Definition of Done** — см. `UI-PROMPTS.md` §2.

---

#### UI-2. `UIClient` abstraction (partial implementation)

**Привязка**: Phase 1 (после патча `ROADMAP.md` v1.1.0). В `TRIZ-ANALYSIS.md` §5.1 (строка 339) рекомендована как реакция на C-1. В `ROADMAP.md` v1.0.0 §3.4 (строка 171) упоминается как применение принципа #16, но фаза не указана — неявно относится к Phase 5 из-за ADR-018. Патч v1.1.0 §5.7 формализует её в Phase 1.

**Суть**: Python-интерфейс `UIClient` с четырьмя методами:
- `render_message(role: Literal["user", "assistant", "system"], content: str, metadata: dict | None = None) -> None`
- `render_artifact(artifact: ArtifactRef) -> None`
- `stream_token(token: str) -> None`
- `handle_user_input(prompt: str) -> str | None`

Полная имплементация interface; единственная реализация — `StreamlitClient`, делегирующий в `st.chat_message`, `st.download_button`, `st.write_stream`, `st.chat_input`. Весь последующий UI-код (UI-1, UI-3, C-5 из `MVP-PROMPTS.md`) пишет против `UIClient` interface, а не против Streamlit-specific API. Когда в Phase 5 появится `ChainlitClient` (UI-5), добавится имплементация — interface не меняется. Когда в Phase 5+ появится `FastAPIClient` (UI-6) — то же самое.

**Антипаттерны** — см. `UI-PROMPTS.md` §3, промпт UI-2:
- НЕ вводи методы под Streamlit-specific концепции (например, `rerun()` — этого нет в Chainlit).
- НЕ делай `UIClient` god-object с 20 методами — только 4 базовых + extension hooks.

**Definition of Done** — см. `UI-PROMPTS.md` §3.

---

#### UI-3. Streamlit fragments для static shell + dynamic content

**Привязка**: Phase 1 (после патча). Прямая рекомендация из `TRIZ-ANALYSIS.md` §4.3 (строка 242): «разделить UI на static-shell + dynamic-content (Streamlit fragments в 1.40+)». В `ROADMAP.md` v1.0.0 не упомянута — неявно часть ADR-018 Phase 5, но логически применима уже в Phase 1.

**Суть**: Streamlit 1.40+ поддерживает `@st.fragment`-декоратор для изоляции re-run-поведения. Применить к двум фрагментам:
1. **Chat stream fragment** — обёртка вокруг `st.write_stream`, пере-рендерится только при изменении потока токенов, не при каждом нажатии в sidebar.
2. **Sidebar fragment** — обёртка вокруг history list, пере-рендерится только при изменении списка сессий.

Это снимает основное узкое место из C-1 (`TRIZ-ANALYSIS.md` §4.3, строка 240): «Streamlit re-runs (целый rerender всего UI при каждом событии) конфликтует с низколатентным streaming LLM. UI тратит время на пересборку, когда LLM уже отдал 100 токенов».

**Антипаттерны** — см. `UI-PROMPTS.md` §4, промпт UI-3:
- НЕ оборачивай весь `app.py` в один fragment — теряется смысл.
- НЕ используй `st.experimental_fragment` (deprecated) — только `@st.fragment` из 1.40+.

**Definition of Done** — см. `UI-PROMPTS.md` §4.

---

#### UI-4. `SessionStore` + `RedisSessionStore` (без изменений)

**Привязка**: Phase 5, ADR-018. В `ROADMAP.md` v1.0.0 §9.2.1 (строка 587) — без изменений в патче v1.1.0. Зависит от UI-2 (использует `UIClient` для переключения backend без потери session state).

---

#### UI-5. `ChainlitClient` (без изменений)

**Привязка**: Phase 5. В `ARCHITECT.md` ADR-002 (строка 734) и `TRIZ-ANALYSIS.md` §5.1 (строка 339) — без изменений. Зависит от UI-2.

---

#### UI-6. `FastAPIClient` (без изменений)

**Привязка**: Phase 5+. В `ARCHITECT.md` ADR-002 — без изменений. Зависит от UI-2, UI-4.

---

#### UI-7. Embed mode (без изменений)

**Привязка**: Phase 6. В `ROADMAP.md` §10.2.2 (строка 696) — без изменений. Зависит от UI-2.

---

### 3.4 Детализация работ AG-составляющей

#### AG-0. Scaffold agent-service (FastAPI + SSE endpoints)

**Привязка**: Phase 1 (new в v1.1.0). Формализует контейнер `agent-service` из `ARCHITECT.md` §4 (строка 124) и §5.1 (строка 357: «FastAPI + SSE (Alpha+ для multi-instance)"). Контракт `POST /sessions/{id}/chat` + `GET /sessions/{id}/stream` зафиксирован в ADR-007 и подразумевается в `UI-PROMPTS.md` §1 (промпт UI-0, строка 47).

**Суть**: создать `src/llm_client/agent/service.py` — FastAPI-приложение, запускаемое отдельным процессом (uvicorn) на `AGENT_SERVICE_PORT` (default 8000). Маршруты:

- `POST /sessions/{session_id}/chat` — тело `{"message": str, "user_id"?: str}`, стартует `graph.astream(...)` асинхронно, возвращает `{"status": "ok", "session_id": ...}`.
- `GET /sessions/{session_id}/stream` — `StreamingResponse(media_type="text/event-stream")`, эмитит SSE-события из AG-3.
- `GET /health` — `{"status": "ok"}` (используется UI-0 для проверки доступности и `start.ps1` для healthcheck).
- `POST /sessions/{session_id}/cancel` — делегирует в существующий `CancelPublisher` (C-2/C-3 из MVP-PROMPTS, уже реализовано в `src/llm_client/api.py`). Опционально: смонтировать существующий `api.py` как sub-app или вынести cancel-endpoint в agent-service.

Конфиг в `.env.example`: `AGENT_SERVICE_URL=http://127.0.0.1:8000`, `AGENT_SERVICE_PORT=8000`. Запуск: либо `python -m llm_client.agent.service`, либо `uvicorn llm_client.agent.service:app`. В `docker-compose.yml` добавляется сервис `agent-service` (build from `src/`, depends_on `redis` + `minio` + `vault`).

**Антипаттерны** (полный список — в будущем `AG-PROMPTS.md` §1):
- НЕ хардкодь порт — через env `AGENT_SERVICE_PORT`.
- НЕ делай in-process интеграцию со Streamlit — отдельный процесс, SSE over HTTP (принцип #19, подготовка к Phase 5 multi-instance).
- НЕ пиши SSE-протокол вручную — используй `StreamingResponse` + форматтер из ADR-007 (RFC 8895-style, см. `src/llm_client/ui/chat.py` `iter_sse_events`).
- НЕ используй WebSocket — ADR-007 явно фиксирует SSE для MVP/Alpha.

**Definition of Done** — см. `AG-PROMPTS.md` §1 (future). Минимально:
- `python -m llm_client.agent.service` поднимает FastAPI на `:8000` за <3 сек.
- `curl http://127.0.0.1:8000/health` → `{"status": "ok"}`.
- `curl -X POST http://127.0.0.1:8000/sessions/test/chat -d '{"message":"hi"}'` → `{"status": "ok", "session_id": "test"}` (без реальной LLM, возвращает 202 — граф стартует асинхронно).
- `curl -N http://127.0.0.1:8000/sessions/test/stream` → SSE-стрим с `event: done` в конце (пустой граф, без LLM, для smoke-теста).

---

#### AG-1. LangGraph agent graph (minimal: planner + final_answer)

**Привязка**: Phase 1 (new в v1.1.0). Реализует ADR-001 (LangGraph, `ARCHITECT.md` §7 строки 718–728) и ADR-006 (нативный tool calling, `ARCHITECT.md` §7). Закрывает Пробел E — даёт C-4 (CancelSubscriber on agent side) граф, в который можно встроить проверку `token.is_cancelled`.

**Суть**: создать `src/llm_client/agent/graph.py` с `build_agent_graph(llm: BaseChatModel, token: CancellationToken | None = None) -> CompiledStateGraph`. Структура по `ARCHITECT.md` §5.2.2:

- `AgentState` TypedDict (минимальный набор полей для Phase 1): `messages`, `user_id`, `session_id`, `provider`, `model_name`, `iteration`, `max_iterations=10`, `final_answer`. Поля `tools_enabled`, `retrieved_docs`, `mcp_tools_cache`, `artifacts` — добавляются в Phase 2/4 (AG-4 / AG-6 / AG-7).
- Ноды (минимум Phase 1):
  - `planner` — анализ запроса через LLM, выбор стратегии: `direct_llm` (в Phase 1 — единственная), `tools_needed` (stub, NotImplementedError в Phase 1 — нет tools). Возвращает `route_decision` в state.
  - `final_answer` — генерация финального ответа через `llm.astream(...)`, эмит токенов в `messages` (для AG-3).
- Conditional edges:
  - `route_after_planner`: если `route_decision == "tools_needed"` → `tool_executor` (stub); иначе → `final_answer`. В Phase 1 — всегда `final_answer` (нет tools).
  - `route_after_final_answer`: `END`.
- Интеграция `IterationMonitor` (B-3 Quick Win, `src/llm_client/agent/cycle_detection.py`) — callback после каждой ноды, проверка `compute_state_delta` > threshold, при 2 подряд одинаковых итерациях — `cycle_detected=True`, выход.
- Интеграция `CancellationToken` (C-1 из MVP-PROMPTS, `src/llm_client/transport/cancel.py`) — проверка `token.is_cancelled` между нодами через conditional edge middleware. При `is_cancelled=True` — выход с partial answer (текущий `messages[-1]` как `final_answer`).

**Антипаттерны** — см. `AG-PROMPTS.md` §2 (future):
- НЕ добавляй `tool_executor` / `rag_retriever` / `mcp_invoker` ноды в Phase 1 — они приходят с AG-4 / AG-6 / AG-7.
- НЕ проверяй `token.is_cancelled` внутри ноды — только между нодами (conditional edge), как требует C-4.
- НЕ используй sync `graph.invoke(...)` — только `graph.astream(...)` для streaming.
- НЕ хардкодь `max_iterations` — через `Settings.max_iterations` (default 10, ADR-001).
- НЕ используй `AgentExecutor` из LangChain — ADR-001 явно запрещает, только `langgraph.graph.StateGraph`.

**Definition of Done** — см. `AG-PROMPTS.md` §2 (future). Минимально:
- `build_agent_graph(mock_llm, token=None)` возвращает compiled graph.
- `graph.astream({"messages": [HumanMessage("hi")]})` отдаёт хотя бы один токен + завершается `END`.
- При `token.cancel("user_cancelled")` до завершения — граф выходит на следующем conditional edge, возвращает partial state.
- При 2 одинаковых итерациях подряд — `IterationMonitor` флагает `cycle_detected`, граф выходит.

---

#### AG-2. LLMProviderFactory (OpenAI only в Phase 1)

**Привязка**: Phase 1 (new в v1.1.0). Реализует `LLMProviderFactory` из `ARCHITECT.md` §5.2.3 (строки 397–422). Закрывает Пробел F — даёт AG-1 LLM для вызова. Anthropic и Ollama остаются на Phase 3 (ADR-015 cost-aware router) и Phase 4 (ADR-016 tool capability adapter) соответственно.

**Суть**: создать `src/llm_client/agent/provider.py` с `LLMProviderFactory.create(provider: str, model: str, **kwargs) -> BaseChatModel` (по образцу `ARCHITECT.md` §5.2.3):

```python
class LLMProviderFactory:
    @staticmethod
    def create(provider: str, model: str, **kwargs) -> BaseChatModel:
        match provider:
            case "openai":    return ChatOpenAI(model=model, streaming=True, **kwargs)
            case "anthropic": raise NotImplementedError("Phase 3 (ADR-015)")
            case "ollama":    raise NotImplementedError("Phase 4 (ADR-016)")
            case _:          raise ValueError(f"Unknown provider: {provider}")
```

Конфиг в `Settings` (`src/llm_client/config.py`) и `.env.example`:

- `LLM_PROVIDER` (default `openai`, Literal[`openai`, `anthropic`, `ollama`]).
- `OPENAI_API_KEY` (обязателен при `LLM_PROVIDER=openai`).
- `OPENAI_MODEL` (default `gpt-4o-mini`).
- `ANTHROPIC_API_KEY`, `ANTHROPIC_MODEL` (для Phase 3, заготовка).
- Валидация в `Settings._validate_environment`: при `LLM_PROVIDER=openai` и пустом `OPENAI_API_KEY` — startup fail fast.

Дополнительно:

- `token_usage_tracker` — оборачивает LLM, логирует `prompt_tokens` / `completion_tokens` / `cost_estimate` в operational stream (D-2).
- `retry_decorator` — exponential backoff на 429/500/503, max 3 retry (по `ARCHITECT.md` §5.2.3 строка 421).

Без `fallback_chain` — это Phase 3 (ADR-015 cost-aware router).

**Антипаттерны** — см. `AG-PROMPTS.md` §3 (future):
- НЕ имплементируй Anthropic в Phase 1 — это Phase 3 (ADR-015). Stub `NotImplementedError` с понятным сообщением.
- НЕ хардкодь API-ключ в коде — только через `Settings` + `.env`.
- НЕ используй `langchain.llms.OpenAI` (legacy) — только `langchain_openai.ChatOpenAI` (chat models, ADR-006 native tool calling).
- НЕ делай `fallback_chain` в Phase 1 — это ADR-015 (Phase 3).
- НЕ логируй `OPENAI_API_KEY` — даже в debug.

**Definition of Done** — см. `AG-PROMPTS.md` §3 (future). Минимально:
- `LLMProviderFactory.create("openai", "gpt-4o-mini")` возвращает `ChatOpenAI` instance.
- `LLMProviderFactory.create("anthropic", ...)` → `NotImplementedError("Phase 3 (ADR-015)")`.
- `LLMProviderFactory.create("ollama", ...)` → `NotImplementedError("Phase 4 (ADR-016)")`.
- При пустом `OPENAI_API_KEY` и `LLM_PROVIDER=openai` — `Settings()` raises `ValidationError`.
- `token_usage_tracker` логирует `prompt_tokens` / `completion_tokens` в operational stream после каждого LLM-вызова.

---

#### AG-3. SSE event protocol emission (token + metadata + cancelled + artifact_ready + done + error)

**Привязка**: Phase 1 (new в v1.1.0). Реализует SSE event protocol из ADR-007 (`ARCHITECT.md` §7 строки 786–795) на стороне agent-service. Закрывает Пробел G — даёт UI-1 (PII badge, download buttons, cancelled badge) источник событий. Зависит от AG-0 (endpoint), AG-1 (graph для стриминга), D-5 (PII score), C-4 (cancel → cancelled event), расш. ADR-008 (artifact_ready).

**Суть**: в `src/llm_client/agent/service.py` (AG-0) реализовать `GET /sessions/{session_id}/stream` как SSE generator, который:

1. Подписывается на `graph.astream(...)` (AG-1) через async iterator.
2. Эмитит события в формате RFC 8895-style (см. `src/llm_client/ui/chat.py` `iter_sse_events`):
   - `event: token` / `data: {"token": "..."}` — для каждого токена из `llm.astream(...)`.
   - `event: metadata` / `data: {"message_id": "...", "pii_score": 0.85, "pii_entities": [{"type": "US_SSN", "start": 11, "end": 22}, ...]}` — после обработки пользовательского сообщения через `PIIDetector.detect()` (D-1) и `attach_pii_metadata()` (D-5). Только типы и span'ы, никогда — PII-текст.
   - `event: artifact_ready` / `data: {"artifact_id": "...", "format": "md", "filename": "...", "s3_key": "..."}` — при срабатывании `file_export` tool (AG-4) или других tool calls, генерирующих артефакты (ADR-008).
   - `event: cancelled` / `data: {"reason": "user_cancelled"}` — при `CancellationToken.is_cancelled=True` (C-4 из MVP-PROMPTS).
   - `event: error` / `data: {"message": "...", "type": "..."}` — при exception в графе.
   - `event: done` / `data: {}` — при нормальном завершении графа.
3. Между событиями — heartbeat `: keepalive\n\n` каждые 15 сек (для proxy timeout).

**Антипаттерны** — см. `AG-PROMPTS.md` §4 (future):
- НЕ эмить PII-текст в `event: metadata` — только `{type, start, end}` (D-5 явно требует).
- НЕ объединяй несколько событий в один chunk — каждое событие отдельно, разделено `\n\n`.
- НЕ делай polling `token.is_cancelled` внутри generator — граф уже выходит при cancel, generator просто эмитит `event: cancelled` и закрывается.
- НЕ забывай heartbeat — без него nginx/ProxyServer закрывает connection через 60 сек.
- НЕ эмить `event: done` после `event: cancelled` или `event: error` — terminal события последние.

**Definition of Done** — см. `AG-PROMPTS.md` §4 (future). Минимально:
- `curl -N .../sessions/test/stream` после `POST /chat` получает `event: token` × N, `event: metadata` × 1, `event: done` × 1.
- При cancel во время стриминга — `event: cancelled` < 200 мс после `POST /cancel` (C-4 latency requirement).
- При exception в `planner` ноде — `event: error` с `{"message": "...", "type": "ValueError"}`.
- `event: metadata` содержит `pii_score` и `pii_entities` для user-сообщения «My SSN is 123-45-6789» → `pii_score > 0.7`, `pii_entities` содержит `{"type": "US_SSN", ...}`.
- После `file_export` tool call — `event: artifact_ready` с `{artifact_id, format, filename, s3_key}`.

---

#### AG-4. file_export tool (минимальный Tool Layer для UI-1 download buttons)

**Привязка**: Phase 1 (new в v1.1.0). Реализует `file_export` tool из `ARCHITECT.md` §5.2.4 (строки 443–462). Закрывает связку UI-1 (download buttons) с реальным источником артефактов. Без AG-4 UI-1 download buttons работают, но никогда не активируются — `event: artifact_ready` не эмитится.

**Суть**: создать `src/llm_client/agent/tools/file_export.py` с `@tool(args_schema=FileExportArgs)` декоратором (по образцу `ARCHITECT.md` §5.2.4):

```python
class FileExportArgs(BaseModel):
    content: str = Field(..., description="Контент файла")
    format: Literal["md", "txt", "pdf", "docx", "odt", "xls", "xlsx"] = Field(...)
    filename: str | None = None

@tool(args_schema=FileExportArgs)
def file_export(content: str, format: str, filename: str | None = None) -> dict:
    '''Сохраняет контент как артефакт в S3 (MinIO). Возвращает {artifact_id, format, filename, s3_key}.'''
    storage = create_file_storage()  # расш. ADR-008, уже реализовано
    artifact_id = uuid4().hex
    s3_key = f"artifacts/{artifact_id}/{filename or f'artifact.{format}'}"
    storage.save(content.encode(), s3_key, metadata={"format": format, "filename": filename})
    return {"artifact_id": artifact_id, "format": format, "filename": filename, "s3_key": s3_key}
```

Форматы:

- `md` / `txt` — синхронно (быстро, content уже есть, `storage.save()` завершается за <100 мс).
- `pdf` / `docx` / `odt` / `xls` / `xlsx` — асинхронно через background worker (в Phase 1 — stub: `asyncio.sleep(2)` для эмуляции; реальный worker — Phase 5 ADR-018). Возвращает `{"status": "generating", "artifact_id": ...}`, AG-3 эмитит `event: artifact_ready` когда готово. По контракту UI-1: 200 OK — готово, 503 — ещё генерируется (retry-кнопка).

Интеграция в AG-1 graph: `planner` нода вызывает LLM с `bind_tools([file_export])` (ADR-006 native tool calling). LLM может вернуть `tool_call` с `file_export`, graph идёт в `tool_executor` ноду (в Phase 1 — единственная tool-нода), `tool_executor` вызывает `file_export`, возвращает `ToolMessage` с `{artifact_id, ...}`, graph возвращается в `planner` для интерпретации.

**Антипаттерны** — см. `AG-PROMPTS.md` §5 (future):
- НЕ используй `LocalFileStorage` — упразднён в расш. ADR-008 (Block E). Только `create_file_storage()` → `S3CompatibleStorage`.
- НЕ хардкодь bucket — `S3_BUCKET` из env (default `llm-client-files`).
- НЕ генерируй pdf/docx/xlsx синхронно в Phase 1 — это блокирует event loop, 2–10 сек latency. Stub `asyncio.sleep` + 503, реальный worker в Phase 5.
- НЕ пиши filename без sanitization — `pathlib.Path(filename).name`, без `/` и `..`.

**Definition of Done** — см. `AG-PROMPTS.md` §5 (future). Минимально:
- LLM prompt «save 'hello world' as markdown» → `file_export` tool call → S3 объект в bucket `llm-client-files/artifacts/{id}/artifact.md`.
- AG-3 эмитит `event: artifact_ready` с `{artifact_id, format: "md", filename: "artifact.md", s3_key: "..."}`.
- UI-1 download button активируется, клик скачивает файл.
- Для `format: "pdf"` — AG-3 эмитит `event: artifact_ready` с задержкой 2 сек (stub), UI-1 показывает "Generating..." + retry.

---

#### AG-5. web_search tool via Tavily (без изменений, Phase 2)

**Привязка**: Phase 2 (new в v1.1.0 как формализация; сама работа подразумевается ADR-005 и `ARCHITECT.md` §5.2.4 строки 433–441). Зависит от AG-1 (graph), ADR-005 (Tool Layer), внешнего API Tavily. В `ROADMAP.md` v1.0.0 не формализована — добавляется как AG-5 для трассировки. Сложность: Low, 1 чел-дн.

---

#### AG-6. rag_query tool + base RAG pipeline (без изменений, Phase 2)

**Привязка**: Phase 2 (new в v1.1.0 как формализация; сама работа подразумевается ADR-003 VectorStoreFactory и `ARCHITECT.md` §5.2.5). Зависит от AG-1 (graph), ADR-003 (VectorStoreFactory), ADR-017 (reranker, расширяет), ADR-020 (hybrid retrieval, расширяет). Базовый `rag_query` tool создаётся здесь (Phase 2 начало), ADR-017/020 в ALPHA-PROMPTS его расширяют. В `ROADMAP.md` v1.0.0 не формализована — добавляется как AG-6. Сложность: Medium, 4 чел-дн.

---

#### AG-7. mcp_call tool (без изменений, Phase 4)

**Привязка**: Phase 4 (new в v1.1.0 как формализация; сама работа подразумевается ADR-004 MCP Client и ADR-012 MCPTransport). Зависит от AG-1 (graph), ADR-012 (MCPTransport abstraction). В `ARCHITECT.md` §5.2.4 описан как `mcp_invoker` нода, но без промпта. Сложность: Medium, 3 чел-дн.

---

## 4. Зависимости

```
UI-0 (Phase 1) ──→ UI-1 (Phase 1) ──→ UI-2 (Phase 1) ──→ UI-5 (Phase 5)
                │                │              └──→ UI-6 (Phase 5+)
                └──→ UI-3 (Phase 1)
                                │
                                └──→ UI-4 (Phase 5) ──→ UI-7 (Phase 6)

AG-0 (Phase 1) ──→ AG-1 (Phase 1) ──→ AG-2 (Phase 1)
                │                  │
                │                  ├──→ AG-3 (Phase 1) ──→ AG-4 (Phase 1, file_export)
                │                  │                  ├──→ AG-5 (Phase 2, web_search)
                │                  │                  └──→ AG-6 (Phase 2, rag_query) ──→ AG-7 (Phase 4, mcp_call)
                │                  │
                │                  └──→ MVP-PROMPTS C-1..C-4 (cancel wiring в графе — без графа некуда встраивать)
                │
                └──→ UI-0 (UI depends on AG-0 через AGENT_SERVICE_URL)
                                │
                                └──→ UI-1 (UI-1 зависит от AG-3: SSE events metadata/artifact_ready/cancelled)
                                                │
                                                └──→ AG-4 (UI-1 download buttons зависят от file_export → artifact_ready)
```

Критический путь UI: `UI-0 → UI-1 → UI-2 → UI-4 → UI-7`. Длительность: 1.5 + 1.5 + 2.5 + 4 + 6 = 15.5 чел-дн чистой разработки. UI-3 (1 чел-дн) и UI-5/UI-6 (6+8 чел-дн) — параллельные ветки.

Критический путь AG: `AG-0 → AG-1 → AG-2 → AG-3 → AG-4`. Длительность: 1.5 + 2.5 + 1 + 1.5 + 1 = 7.5 чел-дн чистой разработки. AG-5/AG-6 (Phase 2) и AG-7 (Phase 4) — параллельные ветки после AG-3.

Полный критический путь Phase 1: `AG-0 → AG-1 → AG-2 → AG-3 → AG-4` (backend, 7.5 чел-дн) параллельно с `UI-0 → UI-1 → UI-2 → UI-3` (frontend, 6.5 чел-дн). При команде из 2 разработчиков (backend + frontend параллельно) — 7.5 чел-дн critical path. С учётом интеграции AG-0 ↔ UI-0 (SSE endpoint ↔ UI client) и ревью — 4–5 недель Phase 1 (vs 3 недель в v1.0.0).

## 5. Критерии выхода

### 5.1 Критерии выхода UI-бэклога из Phase 1 (с патчем `ROADMAP.md` v1.1.0)

Phase 1 считается завершённой по UI-части при одновременном выполнении:

1. **UI-0 Approved**: `docker-compose up ui` поднимает Streamlit-приложение, открывается на `http://localhost:8501`, ввод промпта вызывает LLM-агент, стриминг токенов отображается в реальном времени.
2. **UI-1 Approved**: sidebar с историей сессий работает (выбор сессии из списка переключает контент); кнопки скачивания артефактов работают для всех 4 форматов (md/txt/pdf/docx); индикатор статуса корректно показывает streaming/cancelled/error; бейдж PII score отображается для каждого user message.
3. **UI-2 Approved**: `UIClient` interface существует как Python ABC с 4 методами; `StreamlitClient` — единственная имплементация; `grep -r "st\.chat_message\|st\.chat_input\|st\.write_stream" src/ | wc -l` outside `streamlit_client.py` равен 0 (весь UI-код ходит через interface).
4. **UI-3 Approved**: `@st.fragment` применяется к chat stream и к sidebar; переключение между сессиями в sidebar не вызывает пере-рендер chat area; стриминг токенов не вызывает пере-рендер sidebar.
5. **Метрика идеальности не упала**: см. `ROADMAP.md` v1.1.0 §15.2 (после патча).

### 5.2 Критерии выхода AG-бэклога из Phase 1 (new в v1.1.0, с патчем `ROADMAP.md` v1.2.0)

Phase 1 считается завершённой по AG-части при одновременном выполнении:

6. **AG-0 Approved**: `python -m llm_client.agent.service` поднимает FastAPI на `:8000`, `/health` отдаёт 200, `POST /sessions/{id}/chat` принимает промпт, `GET /sessions/{id}/stream` отдаёт SSE-стрим (с mock-LLM — `event: done` < 1 сек).
7. **AG-1 Approved**: `build_agent_graph(llm, token)` возвращает compiled graph; `graph.astream(...)` отдаёт токены; при `token.cancel()` — выход с partial answer на следующем conditional edge; `IterationMonitor` срабатывает на 2 одинаковых итерациях подряд.
8. **AG-2 Approved**: `LLMProviderFactory.create("openai", "gpt-4o-mini")` с валидным `OPENAI_API_KEY` возвращает `ChatOpenAI`; `token_usage_tracker` логирует `prompt_tokens`/`completion_tokens` в operational stream; `LLM_PROVIDER=anthropic` → `NotImplementedError("Phase 3 (ADR-015)")`.
9. **AG-3 Approved**: после `POST /chat` + `GET /stream` UI получает `event: token` × N, `event: metadata` с `pii_score` и `pii_entities` (без PII-текста), `event: done`. При cancel — `event: cancelled` < 200 мс. При exception — `event: error` с `{message, type}`.
10. **AG-4 Approved**: LLM prompt «save 'hello' as markdown» → `file_export` tool → S3 объект в bucket `llm-client-files` → UI-1 download button активируется, клик скачивает `.md`. Для `format: "pdf"` — 503 + retry (stub 2 сек).
11. **Метрика идеальности Phase 1**: Δф=+6 capabilities (cancel, dual-logging, dev-prod parity, UI scaffold + UIClient, agent-service scaffold, LangGraph orchestration), Δсложности=+3 (KMS/Vault, UIClient, LangGraph + LLM provider) → 6/3 = 2.0 ≥ 1 (порог соблюдён, см. §15.2).

### 5.3 Критерии для последующих фаз

- **Phase 5**: UI-4 Approved (2 инстанса за LB обрабатывают сессию без sticky), UI-5 Approved (Chainlit-режим работает, тот же `UIClient` interface).
- **Phase 6**: UI-7 Approved (iframe embed работает, session sync через postMessage).

## 6. Риски

### 6.1 Риск «UI-2 преждевременен»

**Описание**: введение `UIClient` в Phase 1 — это +2.5 чел-дн к фазе без немедленной выгоды (в Phase 1 всё равно только Streamlit). Может показаться over-engineering-ом.

**Контр-мера**: принцип ТРИЗ #16 явно описывает этот кейс (`ROADMAP.md` §3.4): «внедрять абстракцию "избыточно" (полный interface), но имплементировать "частично"». UI-2 вводит interface + одну имплементацию = +1 абстракция, +0 новой функциональности. Это **нарушает** метрику идеальности (Δф/Δсложности = 0/1 < 1).

**Однако**: UI-2 не вводится изолированно — он поставляется в связке с UI-0 (scaffold, +1 capability: «чат UI») и UI-1 (base elements, +1 capability: «history + downloads + status»). Суммарно по Phase 1: Δф=+2 (scaffold + base UI), Δсложности=+1 (UIClient interface) — Δф/Δсложности = 2 ≥ 1. Удовлетворяет §15.2.

**Контроль**: метрика считается по Phase 1 целиком, не по отдельным UI-N.

### 6.2 Риск «UI-3 не даст эффекта»

**Описание**: Streamlit fragments могут не дать заявленного ускорения, если chat area и sidebar уже разделены через `st.columns` или `st.sidebar`.

**Контр-мера**: UI-3 включает явный latency-тест до/после внедрения fragments. Критерий: прирост FPS стриминга (token/sec, отображённых в UI) ≥ 30% на типовом промпте (1000 токенов). Если прироста нет — UI-3 откатывается, `@st.fragment` удаляется, работа списывается как «не дала эффекта в текущем Streamlit-окружении».

### 6.3 Риск «UI-0 расходится с ADR-002»

**Описание**: формализация Phase 0 через UI-0 может быть воспринята как нарушение ADR-002 (Streamlit как данное) или как добавление неявной фазы.

**Контр-мера**: UI-0 не вводит новое архитектурное решение — он формализует то, что ADR-002 подразумевает. В `ARCHITECT.md` v1.1.0 §7 ADR-002 добавляется строка «Phase 0 Update (2026-09-23): UI-0 формализует scaffold Streamlit-приложения, ранее подразумевавшегося как данное. См. UI-PROMPTS.md §1». Это не расширение ADR-002, а уточнение его контекста.

### 6.4 Риск «AG-0 расходится с `ARCHITECT.md` §5.1 (in-process vs separate process)»

**Описание**: `ARCHITECT.md` §5.1 строка 357 явно предлагает «Streamlit native callbacks (MVP, in-process) или FastAPI + SSE (Alpha+ для multi-instance)». AG-0 фиксирует FastAPI + SSE с первого дня Phase 1, что может быть воспринято как преждевременный переход к Alpha+-архитектуре и нарушение изначального принципа «Streamlit как ускоритель time-to-MVP» (G-5).

**Контр-мера**: принцип #19 (переход в другое измерение) применяется здесь осознанно: вынос agent-service в отдельный процесс снимает связность UI и агента, подготавливает Phase 5 multi-instance (UI-4 / UI-5 работают с тем же `AGENT_SERVICE_URL` контрактом без переписывания). Сложность AG-0 — Low (1.5 чел-дн), что сравнимо с альтернативой (in-process Streamlit + LangGraph, которая потребует переписывания в Phase 5). Метрика идеальности: AG-0 добавляет +1 capability (chat MVP) при +0 новой сложности (FastAPI уже в зависимостях) — ratio ∞, не нарушает порог.

Альтернатива — in-process в Phase 1 с миграцией в Phase 5 — нарушает принцип #16 (частичное/избыточное действие): migration становится переписыванием, а не добавлением имплементации. AG-0 + ADR-007 (SSE) фиксируют контракт `AGENT_SERVICE_URL` с первого дня — Phase 5 добавляет второй инстанс за LB, контракт не меняется.

**Контроль**: при ревью AG-0 архитектурный комитет подтверждает, что FastAPI + SSE в Phase 1 не нарушает ADR-002 (Streamlit) и ADR-007 (SSE) — оба ADR явно допускают эту опцию. В `ARCHITECT.md` v1.2.0 §5.1 строка 357 уточняется: in-process опция помечается как «не используется; AG-0 фиксирует FastAPI + SSE как единственную MVP-реализацию».

## 7. Связанные документы

| Документ | Раздел | Связь |
|---|---|---|
| `ROADMAP.md` v1.1.0 | §5.7 (новый, после патча) | Формализует `UIClient` abstraction в Phase 1 |
| `ROADMAP.md` v1.1.0 | §5.2 (после патча) | Добавляет строки 5.2.4 (UI-0..UI-3) в таблицу работ Phase 1 |
| `ROADMAP.md` v1.1.0 | §5.6 (после патча) | Расширяет критерии выхода Phase 1 UI-части |
| `ROADMAP.md` v1.1.0 | §15.2 (после патча) | Обновляет расчёт метрики идеальности Phase 1 |
| `ROADMAP.md` v1.2.0 (new) | §5.2.5 (новый, после патча) | Формализует AG-составляющую в Phase 1 |
| `ROADMAP.md` v1.2.0 (new) | §5.2 (после патча) | Добавляет строки 5.2.5 (AG-0..AG-4) в таблицу работ Phase 1 |
| `ROADMAP.md` v1.2.0 (new) | §5.6 (после патча) | Расширяет критерии выхода Phase 1 AG-части |
| `ROADMAP.md` v1.2.0 (new) | §15.2 (после патча) | Обновляет расчёт метрики идеальности Phase 1 (Δф=+6, Δсложности=+3) |
| `UI-PROMPTS.md` v1.0.0 | §1–§4 | Промпты для UI-0..UI-3 |
| `AG-PROMPTS.md` v1.0.0 (future) | §1–§5 | Промпты для AG-0..AG-4 |
| `MVP-PROMPTS.md` v1.0.0 | §3 (C-5) | Зависит от UI-0 (нет UI — некуда инжектить JS watcher) |
| `MVP-PROMPTS.md` v1.0.0 | §3 (C-1..C-4) | Зависит от AG-1 (cancel wiring в графе — без графа некуда встраивать) |
| `MVP-PROMPTS.md` v1.0.0 | §3 (C-6), §4 (D-5) | Зависит от AG-3 (SSE event emission — без endpoint некуда эмитить) |
| `ARCHITECT.md` v1.1.0 | §7 ADR-002 | Не меняется; UI-0 формализует scaffold |
| `ARCHITECT.md` v1.1.0 | §5.1 (строка 357) | Уточняется: AG-0 фиксирует FastAPI + SSE как MVP-реализацию, in-process опция не используется |
| `ARCHITECT.md` v1.1.0 | §5.2.2 (Orchestration) | AG-1 реализует |
| `ARCHITECT.md` v1.1.0 | §5.2.3 (LLM Provider) | AG-2 реализует |
| `ARCHITECT.md` v1.1.0 | §5.2.4 (Tool Layer) | AG-4..AG-7 реализуют |
| `TRIZ-ANALYSIS.md` v1.0.0 | §5.1 (C-1) | UI-2 — частичная резолюция; полная — UI-4 в Phase 5 |
| `TRIZ-ANALYSIS.md` v1.0.0 | §4.3 | UI-3 — реализация рекомендации |
| `TRIZ-ANALYSIS.md` v1.0.0 | §5.2 (C-2), §5.5 (C-5) | AG-1 + AG-3 — частичная резолюция через формализацию agent-service |

---

## 8. История изменений

| Версия | Дата | Изменение |
|---|---|---|
| 1.0.0 | 2026-09-23 | Initial draft. Сформирован на основе анализа пробелов в MVP/ALPHA/BETA-PROMPTS.md относительно ARCHITECT/TRIZ/ROADMAP. |
| 1.1.0 | 2026-09-26 | Добавлена AG-составляющая (AG-0..AG-7): формализация agent-service, LangGraph graph, LLMProviderFactory, SSE event emission, file_export tool. Пробелы D–G из §2.3–§2.4 закрыты. Патч `ROADMAP.md` v1.1.0 → v1.2.0 (AG-составляющая в Phase 1, +5 чел-дн в Phase 2, +3 чел-дн в Phase 4). Создаётся input для будущего `AG-PROMPTS.md` v1.0.0. |

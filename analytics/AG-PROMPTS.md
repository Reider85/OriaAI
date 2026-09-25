# AG-PROMPTS.md — Промпты для AG-составляющей Phase 1

| Атрибут | Значение |
|---|---|
| Версия документа | 1.0.0 |
| Дата | 2026-09-26 |
| Источники | `BACKLOG.md` v1.1.0 §3.4 (AG-0..AG-4); `ROADMAP.md` v1.2.0 §5.2.5, §5.8; `ARCHITECT.md` v1.2.0 §4 (строка 124), §5.1 (строка 357), §5.2.2 (Orchestration), §5.2.3 (LLM Provider), §5.2.4 (Tool Layer), §7 ADR-001/005/006/007/008/013/014; `TRIZ-ANALYSIS.md` v1.0.0 §5.2 (C-2), §5.5 (C-5), §11 |
| Этап | Phase 1 — AG-составляющая (AG-0..AG-4) |
| Резолвит | C-2 (частично — agent-service получает граф для cancel wiring); C-5 (частично — IterationMonitor интегрируется в граф); C-4 (полная резолюция cancel через AG-1 graph + AG-3 SSE cancelled event) |
| Целевой LLM | Cursor / Copilot / Claude Code / ChatGPT |
| Гранулярность | 1 промпт = 1 файл / 1 класс / 1 подзадача |

---

## 0. Как пользоваться

5 промптов, сквозная нумерация 1–5. Зависимости:

```
1 (AG-0 service scaffold) ──→ 2 (AG-1 LangGraph graph) ──→ 3 (AG-2 LLM provider)
                                       │
                                       └──→ 4 (AG-3 SSE event protocol) ──→ 5 (AG-4 file_export tool)
```

Параллелизация (2 backend-разработчика):
- Дев 1: 1 → 2 → 4 → 5 (graph + SSE + tools)
- Дев 2: 3 → (после 2) вспомогательные тесты AG-1, интеграция token_usage_tracker

Суммарно: 7.5 чел-дн. Критерии выхода — `BACKLOG.md` §5.2 (new в v1.1.0).

**Конвенции** (наследуются из `MVP-PROMPTS.md` §0 и `UI-PROMPTS.md` §0):

- Имена классов/методов/эндпоинтов — на английском (как в `ARCHITECT.md`).
- ADR и противоречия — `ADR-001`, `C-4`.
- Каждый промпт — в код-блоке, готов к копи-пасту.
- Раздел `Definition of Done` — конкретные измеримые критерии готовности.
- Раздел `Антипаттерны` — что LLM НЕ должен делать; если предложит — отбраковывать.
- Раздел `Связанные ADR` — какие ADR затрагивает (не ломает / упразднёт / требует).
- Env vars / class names / interface signatures — продолжают контракты Phase 1 (`AGENT_SERVICE_URL`, `SSEEvent` из `src/llm_client/ui/chat.py`, `CancellationToken` из `src/llm_client/transport/cancel.py`, `PIIDetector` из `src/llm_client/security/pii_detector.py`, `S3CompatibleStorage` из `src/llm_client/storage/s3.py`, `create_file_storage` из `src/llm_client/storage/factory.py`). Не переопределяются, не дублируются.

**Существующий код**, на который опираемся (не переписываем):

- `src/llm_client/api.py` — `create_app()` с cancel endpoint (ADR-013). AG-0 добавляет сюда же `/sessions/{id}/chat` и `/sessions/{id}/stream`, либо выносит в отдельное FastAPI-app (см. промпт 1, п.5 — выбор архитектора).
- `src/llm_client/transport/` — `CancellationToken`, `CancellationTokenRegistry`, `CancelPublisher`, `CancelSubscriber` (ADR-013, B-1/C-1..C-4). AG-1 graph интегрирует token-check между нодами, не переопределяя интерфейс.
- `src/llm_client/agent/cycle_detection.py` — `compute_state_delta`, `IterationMonitor` (B-3 Quick Win). AG-1 интегрирует monitor как callback после каждой ноды.
- `src/llm_client/security/pii_detector.py` — `PIIDetector` (D-1). AG-3 использует для `event: metadata` (pii_score, pii_entities).
- `src/llm_client/storage/s3.py` + `factory.py` — `create_file_storage()` (расш. ADR-008). AG-4 использует для сохранения артефактов.
- `src/llm_client/observability/` — `OperationalWriter`, `ForensicStreamWriter` (D-2/D-3). AG-3 логирует cancel/error через эти writers; `token_usage_tracker` в AG-2 логирует usage в operational stream.
- `src/llm_client/config.py` — `Settings` (Pydantic). AG-2 добавляет `llm_provider`, `openai_api_key`, `openai_model`, `anthropic_api_key`, `anthropic_model` через расширение, не замену.
- `src/llm_client/ui/chat.py` — `iter_sse_events`, `SSEEvent` (парсер RFC 8895-style). AG-3 использует тот же формат на стороне эмиттера.
- `scripts/mock_agent_service.py` — существующий mock для UI-бенчмарков. AG-0 заменяет его на реальный `agent-service` (см. промпт 1, антипаттерн «не оставляй mock как основной backend»).

---

## 1. AG-0. Scaffold agent-service (FastAPI + SSE endpoints)

```
Ты — ML/Backend-разработчик LLM Client. Создай scaffold agent-service: FastAPI-приложение
с маршрутами POST /sessions/{id}/chat (запуск генерации) и GET /sessions/{id}/stream
(SSE-стриминг токенов). Формализация контейнера agent-service из ARCHITECT.md §4
(строка 124) и §5.1 (строка 357 — «FastAPI + SSE для multi-instance»). Без этого промпта
UI-0 (scaffold Streamlit) не имеет точки интеграции — UI смотрит на AGENT_SERVICE_URL,
где пусто (только mock_agent_service.py).

Контекст:
- ADR-001 (ARCHITECT.md §7): LangGraph как оркестратор. Сам граф — в промпте 2 (AG-1);
  здесь только FastAPI-обёртка с маршрутами.
- ADR-007 (ARCHITECT.md §7): SSE для streaming, one-way, RFC 8895-style. Парсер уже
  существует в src/llm_client/ui/chat.py (iter_sse_events) — AG-0 эмитит события в том
  же формате.
- ADR-013 (реализовано в src/llm_client/api.py): POST /sessions/{id}/cancel через Redis
  pub/sub. AG-0 либо реэкспортирует этот маршрут, либо монтирует api.py как sub-app.
- Контракт UI (src/llm_client/ui/chat.py): AGENT_SERVICE_URL (default
  http://localhost:8000), POST /sessions/{id}/chat с телом {"message": str}, GET
  /sessions/{id}/stream возвращает SSE.
- Принцип #19 (переход в другое измерение): вынос agent-service в отдельный процесс
  снимает связность UI и агента, подготавливает Phase 5 multi-instance. In-process
  опция (ARCHITECT.md §5.1 строка 357) не используется — AG-0 фиксирует FastAPI + SSE
  как единственную MVP-реализацию (см. BACKLOG.md §6.4).
- В Phase 1 (до AG-1 graph и AG-2 LLM provider) сервис должен отвечать на /health,
  принимать /chat (202 — граф стартует асинхронно), отдавать /stream (event: done
  для пустого графа — smoke-тест).

Задача:
1. Создай src/llm_client/agent/service.py с FastAPI-приложением `app`:
   - app = FastAPI(title="LLM Client — agent-service", version="0.1.0")
   - GET /health -> {"status": "ok"} (используется UI-0 и start.ps1 healthcheck).
   - POST /sessions/{session_id}/chat — тело ChatRequest {"message": str,
     "user_id": str | None = None}, response_model ChatResponse {"status": str,
     "session_id": str}. Возвращает 202 {"status": "ok", "session_id": ...}.
     В Phase 1 (без AG-1 graph) — сохраняет {session_id, message, user_id} в
     in-memory dict _sessions (аналог mock_agent_service.py, но с реальным
     контрактом для будущей подмены на graph.astream в промпте 2).
   - GET /sessions/{session_id}/stream — StreamingResponse(media_type="text/event-stream").
     В Phase 1 (без AG-1) — эмитит event: done \n\n сразу (smoke-тест). В промпте 4
     (AG-3) этот маршрут расширится до полной SSE event protocol.
   - POST /sessions/{session_id}/cancel — делегирует в существующий CancelPublisher
     (C-2 из MVP-PROMPTS, src/llm_client/transport/publisher.py). Опция 1: смонтируй
     api.py как sub-app (app.mount("/sessions", existing_cancel_router)). Опция 2:
     реэкспортируй build_cancel_router() и include_router. Выбери по simplicity —
     включить router проще, чем mount sub-app.

2. Создай src/llm_client/agent/__main__.py для запуска через `python -m llm_client.agent`:
   - uvicorn.run(app, host="127.0.0.1", port=AGENT_SERVICE_PORT).
   - Чтение env: AGENT_SERVICE_PORT (default 8000).

3. Добавь в .env.example:
   - AGENT_SERVICE_URL=http://127.0.0.1:8000 (уже в .env, проверь).
   - AGENT_SERVICE_PORT=8000.

4. Добавь сервис `agent-service` в docker-compose.yml:
   - build from src/ (или image python:3.11-slim с volume ./src:/repo/src:ro).
   - command: python -m llm_client.agent (или uvicorn llm_client.agent.service:app
     --host 0.0.0.0 --port 8000).
   - depends_on: redis (healthy), minio (healthy), vault (healthy, опционально —
     только при FORENSIC_STREAM_ENABLED=true).
   - env_file: .env.
   - ports: "127.0.0.1:8000:8000".
   - healthcheck: GET /health каждые 10 сек.
   - networks: llm-network (существующая).

5. Расширь scripts/start.ps1 и scripts/stop.ps1:
   - start.ps1: после Wait-ForInfrastructure добавить Wait-ForAgentService (TCP
     port 8000 или HTTP /health, timeout 30 сек). Запуск agent-service происходит
     через docker-compose up -d (если сервис в compose), либо как отдельный
     subprocess (если dev-режим без docker). Выбери вариант A (docker-compose) —
     проще, consistent с существующим pattern.
   - stop.ps1: docker-compose down корректно останавливает agent-service вместе с
     остальной инфрой. Дополнительно: если запускали как subprocess — Stop-Process
     по PID (аналогично Streamlit). Вариант A не требует изменений в stop.ps1.

6. Обнови scripts/mock_agent_service.py: пометь deprecated-комментарием "Phase 1
   AG-0 заменяет на реальный agent-service. Используется только для UI latency
   benchmark (prompt 11 UI-PROMPTS) — там, где нужна детерминированная задержка
   50 мс на 1000 токенов." НЕ удаляй — бенчмарк зависит от него.

Definition of Done:
- `python -m llm_client.agent` поднимает FastAPI на :8000 за <3 сек.
- `curl http://127.0.0.1:8000/health` -> {"status": "ok"}.
- `curl -X POST http://127.0.0.1:8000/sessions/test/chat -H "Content-Type:
  application/json" -d '{"message":"hi"}'` -> {"status": "ok", "session_id": "test"}.
- `curl -N http://127.0.0.1:8000/sessions/test/stream` -> `event: done\n\n` (SSE
  smoke-тест без LLM).
- `curl -X POST http://127.0.0.1:8000/sessions/test/cancel -H "Content-Type:
  application/json" -d '{"reason":"user_cancelled"}'` -> 202 (cancel endpoint
  работает; 404 если сессия не активирована — это ожидаемо, см. ADR-013).
- docker-compose up -d поднимает agent-service вместе с redis/minio/vault.
- start.ps1 после запуска проверяет /health на :8000.
- UI-0 (Streamlit) после старта agent-service получает валидный SSE-стрим (пусть
  даже пустой — event: done) вместо "Agent service unavailable".

Антипаттерны:
- НЕ хардкодь порт 8000 — через env AGENT_SERVICE_PORT.
- НЕ делай in-process интеграцию со Streamlit (например, streamlit run с импортом
  graph напрямую) — отдельный процесс, SSE over HTTP (принцип #19, подготовка к
  Phase 5 multi-instance). ARCHITECT.md §5.1 in-process опция — НЕ используется.
- НЕ пиши SSE-протокол вручную (форматируй строки `\n\n` и экранируй `data:`).
  Создай helper format_sse_event(event: str, data: Any) -> str, который:
  - JSON-serializes data (если dict/list) или берёт как str.
  - Возвращает f"event: {event}\ndata: {payload}\n\n".
  - Этот helper переиспользуется в AG-3.
- НЕ используй WebSocket — ADR-007 явно фиксирует SSE для MVP/Alpha.
- НЕ оставляй mock_agent_service.py как основной backend после AG-0 — он только
  для UI latency benchmark. start.ps1 поднимает agent-service, не mock.
- НЕ дублируй cancel-логику. Реэкспортируй build_cancel_router() из
  src/llm_client/transport/endpoint.py (уже реализовано в C-2).
- НЕ блокируй event loop в /chat — запуск графа асинхронный (возврат 202 сразу).
- НЕ создавай новый Redis client — переиспользуй из src/llm_client/api.py (или
  создай общий factory в transport/, если нужно).

Связанные ADR: реализует ADR-001 (контейнер), ADR-007 (SSE), ADR-013 (cancel
endpoint делегируется); блокирует AG-1..AG-4; разблокирует UI-0 для реального
стриминга (вместо mock).
```

---

## 2. AG-1. LangGraph agent graph (minimal: planner + final_answer)

```
Ты — ML-инженер LLM Client. Создай LangGraph agent graph для agent-service из промпта 1.
Граф минимален для Phase 1: две ноды (planner + final_answer), один conditional edge.
Полный набор нод (tool_executor, rag_retriever, mcp_invoker) придёт с AG-4 / AG-6 /
AG-7 в Phase 2/4. Закрывает Пробел E (BACKLOG.md §2.3) — даёт C-4 (CancelSubscriber on
agent side) граф, в который можно встроить проверку token.is_cancelled.

Контекст:
- ADR-001 (ARCHITECT.md §7): LangGraph 0.2+, StateGraph(AgentState), PostgresSaver
  checkpointer. В Phase 1 checkpointer НЕ подключаем — простейший in-memory state
  (PostgresSaver требует миграций, ADR-010 в Phase 2 добавит Redis+PG). Phase 1 —
  stateless, без resume-after-restart.
- ADR-006 (ARCHITECT.md §7): нативный tool calling через bind_tools(). В Phase 1 —
  без tools (AG-4 добавит file_export в промпте 5). planner нода вызывает LLM без
  bind_tools() в Phase 1.
- ARCHITECT.md §5.2.2 (строки 359–395): AgentState TypedDict с полями messages,
  user_id, session_id, provider, model_name, iteration, max_iterations=10,
  final_answer. Поля tools_enabled, retrieved_docs, mcp_tools_cache, artifacts —
  добавляются в Phase 2/4, в Phase 1 не нужны.
- B-3 Quick Win (src/llm_client/agent/cycle_detection.py): IterationMonitor уже
  реализован. AG-1 интегрирует его как callback после каждой ноды — НЕ переопределяет.
- C-1..C-4 (MVP-PROMPTS, src/llm_client/transport/): CancellationToken уже
  реализован. AG-1 проверяет token.is_cancelled между нодами через conditional edge
  middleware — НЕ переопределяет интерфейс токена.

Задача:
1. Создай src/llm_client/agent/graph.py с:
   - AgentState TypedDict (минимум Phase 1):
     ```python
     from typing import TypedDict, Annotated, Literal
     from langgraph.graph.message import add_messages

     class AgentState(TypedDict):
         messages: Annotated[list, add_messages]
         user_id: str
         session_id: str
         provider: Literal["openai", "anthropic", "ollama"]
         model_name: str
         iteration: int
         max_iterations: int  # default 10 (ADR-001)
         final_answer: str | None
     ```
   - build_agent_graph(llm: BaseChatModel, token: CancellationToken | None = None,
     tools: list | None = None) -> CompiledStateGraph:
     - Создаёт StateGraph(AgentState).
     - Добавляет ноды: planner, final_answer.
     - planner(state) -> dict: вызывает llm.ainvoke(state["messages"]), возвращает
       {"messages": [AIMessage], "iteration": state["iteration"] + 1}. В Phase 1
       planner просто вызывает LLM с user message — без tool_choice, без
       bind_tools. route_decision не возвращается (всегда идём в final_answer).
     - final_answer(state) -> dict: берёт last AIMessage из state["messages"],
       записывает в state["final_answer"], возвращает {"final_answer": content,
       "messages": []} (без новых сообщений, либо одно финальное AIMessage, если
       нужно для SSE-стриминга — см. ниже).
     - Conditional edges:
       - route_after_planner: если token is not None and token.is_cancelled ->
         END (с partial answer из state["messages"][-1] как final_answer); иначе
         -> final_answer.
       - route_after_final_answer: END.
     - Интеграция IterationMonitor: создаётся в build_agent_graph, передаётся в
       graph как callback. После каждой ноды — IterationMonitor.on_iteration(prev,
       curr) — если cycle_detected=True, в state["final_answer"] записывается
       текущий ответ, граф выходит на следующем conditional edge (через route
       после planner, который видит cycle_detected и идёт в END).
     - streaming support: planner использует llm.astream() (не ainvoke), чтобы
       эмитить токены. Каждый токен добавляется в streaming buffer state (поле
       "streaming_tokens": list[str], добавляется в AgentState). final_answer
       конкатенирует streaming_tokens в финальный ответ. Это нужно для AG-3 SSE
       event: token emission.

2. Интегрируй graph в agent-service (промпт 1):
   - В src/llm_client/agent/service.py POST /sessions/{id}/chat:
     - Создаёт llm через LLMProviderFactory.create(provider=settings.llm_provider,
       model=settings.llm_model) (из промпта 3, AG-2). В Phase 1 без AG-2 —
       заглушка mock_llm (FakeListChatModel из langchain_core.language_models,
       отдаёт фиксированный ответ для smoke-теста). После AG-2 — реальный LLM.
     - Создаёт CancellationToken, регистрирует в CancellationTokenRegistry
       (src/llm_client/transport/cancel.py, уже реализовано).
     - graph = build_agent_graph(llm, token=token).
     - Запускает graph.astream({...}) в background task (asyncio.create_task),
       возвращает 202 сразу.
   - В GET /sessions/{id}/stream: SSE generator читает из graph.astream
     (background task writes в asyncio.Queue, generator читает). Форматирование
     через format_sse_event из промпта 1.

3. Интегрируй CancelSubscriber (C-4, src/llm_client/transport/subscriber.py):
   - При POST /chat — CancelSubscriber.subscribe(session_id) (запускает фоновую
     подписку на Redis channel session:{id}:cancel).
   - При получении cancel — subscriber вызывает token.cancel(reason) (C-1
     интерфейс, уже реализовано).
   - При завершении графа (нормальном или cancel) — subscriber.unsubscribe(session_id).

4. Создай src/llm_client/agent/test_graph.py с тестами:
   - build_agent_graph с FakeListChatModel(["Hello"]) возвращает compiled graph.
   - graph.astream({"messages": [HumanMessage("hi")], "user_id": "u1",
     "session_id": "s1", "provider": "openai", "model_name": "gpt-4o-mini",
     "iteration": 0, "max_iterations": 10, "final_answer": None}) отдаёт хотя бы
     один chunk + завершается END.
   - При token.cancel("user_cancelled") до запуска graph — graph.astream
     завершается сразу, state["final_answer"] = None или partial.
   - При двух одинаковых итерациях подряд (mock LLM отдаёт "X" дважды) —
     IterationMonitor срабатывает, cycle_detected=True, граф выходит.

Definition of Done:
- build_agent_graph(mock_llm, token=None) возвращает CompiledStateGraph.
- graph.astream(...) отдаёт хотя бы один chunk + завершается END.
- При token.cancel() до запуска — граф выходит без LLM-вызова.
- При token.cancel() во время planner — граф выходит после planner (между
  нодами, согласно C-4), state["final_answer"] = partial answer (текущий
  streaming_tokens, конкатенированные).
- При 2 одинаковых итерациях подряд — IterationMonitor срабатывает, cycle_detected
  в state = True, граф выходит.
- При cancel — CancelSubscriber.unsubscribe вызывается (no leak).
- Все тесты test_graph.py зелёные.
- pytest tests/unit/test_cancel_token.py tests/unit/test_cancel_transport.py
  (существующие) — не регрессируют.

Антипаттерны:
- НЕ добавляй tool_executor / rag_retriever / mcp_invoker ноды в Phase 1 — они
  приходят с AG-4 (file_export) / AG-6 (rag_query, Phase 2) / AG-7 (mcp_call,
  Phase 4).
- НЕ проверяй token.is_cancelled внутри ноды (planner) — только между нодами
  (route_after_planner conditional edge), как требует C-4. Внутри ноды LLM-вызов
  не прерывается.
- НЕ используй sync graph.invoke(...) — только graph.astream(...) для streaming
  (SSE требует потоковой отдачи токенов).
- НЕ хардкодь max_iterations — через Settings.max_iterations (default 10,
  ADR-001).
- НЕ используй AgentExecutor из LangChain — ADR-001 явно запрещает, только
  langgraph.graph.StateGraph.
- НЕ подключай PostgresSaver checkpointer в Phase 1 — это ADR-010 (Phase 2). В
  Phase 1 graph stateless, in-memory.
- НЕ переопределяй IterationMonitor или CancellationToken — используй
  существующие из src/llm_client/agent/cycle_detection.py и
  src/llm_client/transport/cancel.py.
- НЕ логируй user_id в operational stream (PII — маскируется через ADR-014,
  src/llm_client/observability/operational_writer.py).

Связанные ADR: реализует ADR-001 (LangGraph), ADR-006 (нативный tool calling —
подготовка для AG-4); интегрирует B-3 (cycle detection) и C-1..C-4 (cancel
wiring в графе); зависит от промпта 1 (AG-0 service); блокирует промпт 3
(AG-2 LLM provider — без графа некому вызывать LLM) и промпт 4 (AG-3 SSE —
нечего эмитить без стриминга из графа).
```

---

## 3. AG-2. LLMProviderFactory (OpenAI only в Phase 1)

```
Ты — ML/Backend-разработчик LLM Client. Создай LLMProviderFactory — factory для
инстанцирования LLM-провайдеров через langchain-openai (langchain-anthropic /
langchain-ollama — stub NotImplementedError до Phase 3/4). Закрывает Пробел F
(BACKLOG.md §2.3) — даёт AG-1 graph LLM для вызова.

Контекст:
- ARCHITECT.md §5.2.3 (строки 397–422): LLMProviderFactory.create(provider, model,
  **kwargs) с match/case по провайдеру. ChatOpenAI / ChatAnthropic / (Phase 4)
  ChatOllama. Phase 1 — только OpenAI.
- ADR-006 (ARCHITECT.md §7): нативный tool calling через bind_tools(). В Phase 1
  tools не подключаются (AG-4 добавит file_export в промпте 5). factory должна
  поддержать опциональный tools параметр для будущих фаз.
- pyproject.toml уже декларирует: langchain-openai>=0.2.0,
  langchain-anthropic>=0.3.0. Пакеты установлены в .venv.
- .env.example НЕ содержит OPENAI_API_KEY / ANTHROPIC_API_KEY — добавь.
- token_usage_tracker (ARCHITECT.md §5.2.3 строка 420): оборачивает LLM, логирует
  prompt_tokens / completion_tokens / cost_estimate в operational stream (D-2).
- retry_decorator (ARCHITECT.md §5.2.3 строка 421): exponential backoff на
  429/500/503, max 3 retry.
- fallback_chain (ARCHITECT.md §5.2.3 строка 422) — Phase 3 (ADR-015 cost-aware
  router), в Phase 1 НЕ имплементируй.

Задача:
1. Создай src/llm_client/agent/provider.py с LLMProviderFactory:
   ```python
   from langchain_core.language_models import BaseChatModel
   from langchain_openai import ChatOpenAI

   class LLMProviderFactory:
       @staticmethod
       def create(
           provider: str,
           model: str,
           *,
           api_key: str | None = None,
           streaming: bool = True,
           **kwargs,
       ) -> BaseChatModel:
           match provider:
               case "openai":
                   return ChatOpenAI(
                       model=model,
                       streaming=streaming,
                       api_key=api_key,
                       **kwargs,
                   )
               case "anthropic":
                   raise NotImplementedError(
                       "Anthropic provider is Phase 3 (ADR-015 cost-aware router)"
                   )
               case "ollama":
                   raise NotImplementedError(
                       "Ollama provider is Phase 4 (ADR-016 tool capability adapter)"
                   )
               case _:
                   raise ValueError(f"Unknown provider: {provider!r}")
   ```
   - streaming=True по умолчанию (SSE требует потоковый ответ, ADR-007).
   - api_key передаётся явно (не из os.getenv внутри factory) — caller
     (Settings) отвечает за подгрузку ключа.

2. Расширь src/llm_client/config.py Settings (НЕ заменяй существующие поля):
   ```python
   # LLM Provider (AG-2)
   llm_provider: Literal["openai", "anthropic", "ollama"] = "openai"
   openai_api_key: str = ""
   openai_model: str = "gpt-4o-mini"
   anthropic_api_key: str = ""  # Phase 3, заготовка
   anthropic_model: str = "claude-3-5-sonnet-20241022"  # Phase 3
   ```
   - В _validate_environment (model_validator) добавь проверку: если
     llm_provider == "openai" и openai_api_key пустой — raise ValueError(
     "OPENAI_API_KEY required when LLM_PROVIDER=openai").
   - НЕ валидируй anthropic_api_key в Phase 1 (provider не реализован).

3. Добавь в .env.example (новая секция "LLM Provider (AG-2)"):
   ```
   LLM_PROVIDER=openai
   OPENAI_API_KEY=
   OPENAI_MODEL=gpt-4o-mini
   ANTHROPIC_API_KEY=  # Phase 3, заготовка
   ANTHROPIC_MODEL=claude-3-5-sonnet-20241022
   ```

4. Создай token_usage_tracker в src/llm_client/agent/provider.py (или
   src/llm_client/agent/usage.py — выбери по cohesion):
   ```python
   from langchain_core.callbacks import BaseCallbackHandler

   class TokenUsageTracker(BaseCallbackHandler):
       """Логирует prompt_tokens / completion_tokens / cost_estimate в operational
       stream (D-2 из MVP-PROMPTS) после каждого LLM-вызова.

       Использует OperationalWriter из src/llm_client/observability/.
       НЕ логирует PII — только usage метрики. user_id маскируется в
       OperationalWriter (D-2).
       """
       def __init__(self, operational_writer): ...
       async def on_llm_end(self, response, **kwargs): ...
   ```
   - Стоимость считается через простую таблицу cost_per_1m_tokens для
     поддерживаемых моделей (gpt-4o-mini, gpt-4o — фиксированные цены; обновление
     через env при необходимости, но в Phase 1 хардкод в коде acceptable).
   - Логирует в operational stream: {"event": "llm_usage", "provider": "openai",
     "model": "gpt-4o-mini", "prompt_tokens": 123, "completion_tokens": 456,
     "cost_estimate_usd": 0.0023, "session_id": "..."}.

5. Создай retry_decorator (в provider.py или отдельном utils/retry.py):
   - Экспоненциальный backoff на 429/500/503: 1s → 2s → 4s, max 3 retry.
   - Используй tenacity (если уже в зависимостях) или async-retry через
     asyncio.sleep.
   - НЕ оборачивает 4xx (кроме 429) — это не transient ошибки, сразу падай.

6. Интегрируй factory в graph (промпт 2, AG-1):
   - В build_agent_graph: llm = LLMProviderFactory.create(provider, model,
     api_key=api_key).
   - token_usage_tracker добавляется в llm.callbacks = [token_usage_tracker].
   - retry_decorator оборачивает llm.ainvoke/astream.

7. Создай тесты src/llm_client/agent/test_provider.py:
   - LLMProviderFactory.create("openai", "gpt-4o-mini", api_key="sk-test")
     возвращает ChatOpenAI instance (проверка класса, не вызов API).
   - LLMProviderFactory.create("anthropic", ...) → NotImplementedError с
     сообщением "Phase 3 (ADR-015)".
   - LLMProviderFactory.create("ollama", ...) → NotImplementedError с
     сообщением "Phase 4 (ADR-016)".
   - LLMProviderFactory.create("unknown", ...) → ValueError.
   - Settings() с пустым OPENAI_API_KEY и llm_provider="openai" →
     ValidationError (Pydantic).
   - TokenUsageTracker.on_llm_end пишет в mock operational_writer (verify
     writer.write called with expected event dict).

Definition of Done:
- LLMProviderFactory.create("openai", "gpt-4o-mini", api_key="sk-...")
     возвращает ChatOpenAI (instanceof BaseChatModel).
- LLMProviderFactory.create("anthropic", ...) raises NotImplementedError("...
  Phase 3 (ADR-015) ...").
- LLMProviderFactory.create("ollama", ...) raises NotImplementedError("...
  Phase 4 (ADR-016) ...").
- Settings() с пустым OPENAI_API_KEY и llm_provider="openai" — raises
  ValidationError (fail fast на старте).
- graph.astream(...) после AG-1 + AG-2 реально вызывает OpenAI API (smoke-тест
  с валидным ключом — manual или staging-only, не в CI).
- TokenUsageTracker логирует prompt_tokens / completion_tokens / cost_estimate
  в operational stream после LLM-вызова.
- Все unit-тесты test_provider.py зелёные.
- Существующие тесты (194 из SETUP_COMPLETE.md) — не регрессируют.

Антипаттерны:
- НЕ имплементируй Anthropic в Phase 1 — это Phase 3 (ADR-015). Stub
  NotImplementedError с понятным сообщением, указывающим на фазу и ADR.
- НЕ имплементируй Ollama в Phase 1 — это Phase 4 (ADR-016).
- НЕ хардкодь OPENAI_API_KEY в коде — только через Settings + .env.
- НЕ используй langchain.llms.OpenAI (legacy completion API) — только
  langchain_openai.ChatOpenAI (chat models, ADR-006 native tool calling).
- НЕ делай fallback_chain в Phase 1 — это ADR-015 (Phase 3). Один провайдер.
- НЕ логируй OPENAI_API_KEY — даже в debug level. TokenUsageTracker логирует
  только usage метрики, не ключ.
- НЕ логируй PII (prompt content) в operational stream — только usage
  (prompt_tokens count, не сам prompt). PII маскируется в OperationalWriter,
  но prompt content НЕ передаётся в TokenUsageTracker вообще.
- НЕ создавай новый OperationalWriter instance — переиспользуй из
  src/llm_client/observability/operational_writer.py (D-2, уже реализовано).
- НЕ валидируй anthropic_api_key в Phase 1 — поле существует как заготовка, но
  валидация активируется в Phase 3 когда LLMProviderFactory поддержит "anthropic".
- НЕ используй sync httpx/requests для OpenAI API — ChatOpenAI сам асинхронный
  через aiohttp/httpx, не оборачивай в sync.

Связанные ADR: реализует ARCHITECT.md §5.2.3 (LLM Provider Layer); применяет
ADR-006 (нативный tool calling — подготовка для AG-4 bind_tools); зависит от
AG-1 (graph); интегрирует D-2 (operational logging) для token usage tracking.
```

---

## 4. AG-3. SSE event protocol emission (token + metadata + cancelled + artifact_ready + done + error)

```
Ты — ML/Backend-разработчик LLM Client. Реализуй SSE event protocol на стороне
agent-service: эмит событий token / metadata / artifact_ready / cancelled / error /
done из graph.astream(...) (промпт 2). Закрывает Пробел G (BACKLOG.md §2.3) — даёт
UI-1 (PII badge, download buttons, cancelled badge) источник событий. Без AG-3
UI-1 работает «вхолостую» — у него нет источника событий, кроме mock-сервиса.

Контекст:
- ADR-007 (ARCHITECT.md §7 строки 786–795): SSE для streaming, RFC 8895-style.
  Парсер уже существует в src/llm_client/ui/chat.py (iter_sse_events). AG-3
  эмитит события в том же формате.
- ADR-013 (MVP-PROMPTS C-1..C-6, реализовано): cancel через Redis pub/sub. AG-3
  эмитит event: cancelled при CancellationToken.is_cancelled=True.
- ADR-014 (MVP-PROMPTS D-1..D-6, реализовано): PIIDetector.detect() +
  attach_pii_metadata(). AG-3 эмитит event: metadata с pii_score и pii_entities
  (только типы и span'ы, без PII-текста).
- (расш. ADR-008, Block E, реализовано): S3CompatibleStorage. AG-3 эмитит event:
  artifact_ready при срабатывании file_export tool (AG-4, промпт 5).
- src/llm_client/ui/chat.py определяет SSE event типы, которые UI ожидает:
  TOKEN_EVENTS = ("token", "message"), TERMINAL_EVENTS = ("cancelled", "error"),
  ARTIFACT_EVENTS = ("artifact_ready",), METADATA_EVENTS = ("metadata",). AG-3
  должен эмитить ВСЕ эти типы.
- format_sse_event helper создан в промпте 1 (AG-0). AG-3 его переиспользует.

Задача:
1. Реализуй GET /sessions/{session_id}/stream в src/llm_client/agent/service.py
   (промпт 1) как SSE generator:
   - async def stream_generator(session_id: str) -> AsyncIterator[str]:
     a. Получает background task из _sessions[session_id] (создана в POST /chat).
        task имеет .queue: asyncio.Queue, в которую graph.astream writes chunks.
     b. Эмитит начальное event: metadata (один раз, для user message): запускает
        PIIDetector.detect(user_message) → получает score + entities. Формат
        event: metadata \n data: {"message_id": <user_msg_id>, "pii_score":
        <float>, "pii_entities": [{"type": ..., "start": ..., "end": ...}, ...]}.
        PII-текст НЕ включается — только типы и span'ы (D-5 явно требует).
     c. while not task.done():
        - Читает chunk из task.queue (async with timeout 15 сек).
        - Если chunk — токен: эмитит event: token \n data: {"token": "<str>"}.
        - Если chunk — ToolMessage (file_export результат): эмитит event:
          artifact_ready \n data: {"artifact_id": ..., "format": ..., "filename":
          ..., "s3_key": ...}.
        - Если timeout без chunks: эмитит heartbeat ": keepalive\n\n" (без event
          field, RFC 8895 comment line).
     d. После task.done(): проверяет task.result().
        - Если final_answer не None (normal completion): эмитит event: done \n
          data: {}.
        - Если token.is_cancelled: эмитит event: cancelled \n data: {"reason":
          token.reason}.
        - Если exception: эмитит event: error \n data: {"message": str(exc),
          "type": type(exc).__name__}.
     e. ВСЕГДА в конце: CancelSubscriber.unsubscribe(session_id) (no leak).
   - Возвращает StreamingResponse(stream_generator(session_id),
     media_type="text/event-stream").

2. Расширь format_sse_event helper (промпт 1):
   ```python
   def format_sse_event(event: str, data: Any) -> str:
       if isinstance(data, (dict, list)):
           payload = json.dumps(data, separators=(",", ":"))
       else:
           payload = str(data)
       return f"event: {event}\ndata: {payload}\n\n"
   ```
   - НЕ экранирует `\n` в payload (RFC 8895: многострочные data через несколько
     data: lines, но в Phase 1 payload всегда single-line JSON — нет многострочных).

3. Интегрируй metadata event (PII score):
   - После POST /chat (до запуска graph): запускает
     PIIDetector.detect(message) (asyncio.create_task).
   - При получении result: writes в task.queue специальный "metadata" chunk (не
     токен, не ToolMessage). stream_generator видит metadata chunk и эмитит
     event: metadata.
   - PII entities в event: metadata — только {"type": ..., "start": ..., "end":
     ...}, без текста. Это требование D-5 (MVP-PROMPTS).
   - Если PII_DETECTOR_ENABLED=false (D-1 no-op mode): event: metadata с
     pii_score=0.0, pii_entities=[].

4. Интегрируй artifact_ready event (для AG-4 file_export, промпт 5):
   - graph.astream отдаёт ToolMessage с content {"artifact_id": ...,
     "format": ..., "filename": ..., "s3_key": ...} (результат file_export tool).
   - stream_generator видит ToolMessage (через type check) и эмитит event:
     artifact_ready с этим content.
   - В Phase 1 (до AG-4) — без artifacts, event не эмитится. Заглушка: stream
     generator должен корректно обрабатывать отсутствие ToolMessage.

5. Интегрируй cancelled event (C-4):
   - route_after_planner conditional edge (промпт 2): при token.is_cancelled
     граф выходит с partial answer в state["final_answer"].
   - stream_generator после task.done() проверяет token.is_cancelled — если
     True, эмитит event: cancelled с reason из token.reason.
   - Latency requirement (C-4 DoD): event: cancelled должен быть эмитит < 200
     мс после POST /cancel (Redis pub/sub latency < 5 мс + graph exit between
     nodes < 100 мс + SSE chunk write < 50 мс = ~150 мс).

6. Интегрируй error event:
   - Любое exception в graph.astream (LLM API error, network, validation) →
     task.result() поднимает exception.
   - stream_generator ловит, эмитит event: error с {"message": str(exc), "type":
     type(exc).__name__}.
   - Traceback НЕ включается в SSE (security — не утекает в UI). Логируется в
     operational stream через OperationalWriter (D-2) с traceback в forensic
     stream (D-3, encrypted).

7. Создай тесты src/llm_client/agent/test_sse.py:
   - format_sse_event("token", {"token": "hello"}) → "event: token\ndata:
     {\"token\":\"hello\"}\n\n".
   - format_sse_event("metadata", {"pii_score": 0.9, "pii_entities": [{"type":
     "US_SSN", "start": 11, "end": 22}]}) → корректный SSE.
   - mock graph.astream: отдаёт 3 токена + ToolMessage (artifact) + done.
     stream_generator отдаёт: metadata, token×3, artifact_ready, done.
   - mock graph.astream с cancel: отдаёт 2 токена + cancel token →
     stream_generator отдаёт metadata, token×2, cancelled.
   - mock graph.astream с exception: отдаёт 1 токен + raises → stream_generator
     отдаёт metadata, token, error.
   - heartbeat: mock queue пустая 16 сек → stream_generator отдаёт ": keepalive\n\n".
   - PII-текст не появляется в event: metadata payload (only types and spans).

Definition of Done:
- curl -N http://127.0.0.1:8000/sessions/test/stream после POST /chat получает:
  event: metadata \n data: {"message_id":..., "pii_score":..., "pii_entities":...}
  event: token \n data: {"token":"..."}  (×N)
  event: done \n data: {}
- При cancel во время стриминга — event: cancelled < 200 мс после POST /cancel
  (C-4 latency requirement). Проверка: timing test в test_sse.py.
- При exception в planner ноде — event: error с {"message": "...", "type":
  "ValueError"} (или соответствующий тип).
- event: metadata для user-сообщения "My SSN is 123-45-6789" → pii_score > 0.7,
  pii_entities содержит {"type": "US_SSN", "start": ..., "end": ...}. Сам SSN
  "123-45-6789" НЕ появляется в SSE payload.
- После file_export tool call (AG-4) — event: artifact_ready с {artifact_id,
  format, filename, s3_key}.
- UI-1 (Streamlit) после AG-3:
  - PII badge отображается для user message (event: metadata →
    StreamlitClient.update_pii_badge).
  - download button активируется после event: artifact_ready.
  - "Cancelled" бейдж показывается после event: cancelled.
- heartbeat каждые 15 сек при простое — curl -N держит connection открытым > 60
  сек без timeout.
- Все unit-тесты test_sse.py зелёные.

Антипаттерны:
- НЕ эмить PII-текст в event: metadata — только {type, start, end} (D-5 явно
  требует). Проверь тестом: payload не содержит "123-45-6789" после
  PIIDetector.detect("My SSN is 123-45-6789").
- НЕ объединяй несколько событий в один chunk — каждое событие отдельно,
  разделено "\n\n". format_sse_event уже это делает, но НЕ конкатенируй до
  merged str перед yield — каждое событие как отдельный yield.
- НЕ делай polling token.is_cancelled внутри stream_generator — граф уже
  выходит при cancel (промпт 2), generator просто проверяет token после
  task.done().
- НЕ забывай heartbeat — без него nginx/ProxyServer закрывает connection через
  60 сек. Heartbeat ": keepalive\n\n" (comment line, без event field).
- НЕ эмить event: done после event: cancelled или event: error — terminal
  события последние. Проверь в test_sse.py.
- НЕ включай traceback в event: error payload — security risk. Traceback
  логируется в operational/forensic streams (D-2/D-3), в UI только message + type.
- НЕ блокируй stream_generator на PIIDetector.detect (sync) — делай через
  asyncio.to_thread или используй async version, если PIIDetector поддерживает.
  В Phase 1 — async detect (PIIDetector.detect синхронный, оборачивай в
  asyncio.to_thread, чтобы не блокировать event loop).
- НЕ эмить event: metadata для assistant messages — только для user message,
  один раз в начале стрима.

Связанные ADR: реализует ADR-007 (SSE event protocol); интегрирует ADR-013
(cancelled event), ADR-014 (metadata event с PII score), расш. ADR-008
(artifact_ready event); зависит от AG-0 (endpoint), AG-1 (graph для стриминга),
D-1/D-5 (PII detection, уже реализовано); разблокирует UI-1 (PII badge,
download buttons, cancelled badge получают источник событий).
```

---

## 5. AG-4. file_export tool (минимальный Tool Layer для UI-1 download buttons)

```
Ты — ML/Backend-разработчик LLM Client. Создай file_export tool — @tool-декорированную
функцию для сохранения контента как артефакта в S3 (MinIO в dev). Закрывает связку
UI-1 (download buttons) с реальным источником артефактов. Без AG-4 UI-1 download
buttons работают, но никогда не активируются — event: artifact_ready не эмитится
(AG-3, промпт 4, ждёт ToolMessage от file_export).

Контекст:
- ARCHITECT.md §5.2.4 (строки 443–462): file_export как @tool(args_schema=FileExportArgs)
  с форматами md/txt/pdf/docx/odt/xls/xlsx. Phase 1 — md/txt синхронно, pdf/docx/etc
  асинхронно (stub 2 сек, реальный worker — Phase 5 ADR-018).
- ADR-006 (ARCHITECT.md §7): нативный tool calling через bind_tools(). AG-4
  добавляет file_export в bind_tools() вызов planner ноды (промпт 2, AG-1).
- (расш. ADR-008, Block E, реализовано): S3CompatibleStorage через
  create_file_storage() из src/llm_client/storage/factory.py. AG-4 использует
  create_file_storage() — НЕ LocalFileStorage (упразднён в E-2).
- AG-3 (промпт 4) эмитит event: artifact_ready при получении ToolMessage от
  file_export. AG-4 возвращает ToolMessage с {artifact_id, format, filename,
  s3_key}.

Задача:
1. Создай src/llm_client/agent/tools/__init__.py (новый пакет).
2. Создай src/llm_client/agent/tools/file_export.py:
   ```python
   from typing import Literal
   from uuid import uuid4
   from pathlib import Path
   from langchain_core.tools import tool
   from pydantic import BaseModel, Field
   from llm_client.storage.factory import create_file_storage

   class FileExportArgs(BaseModel):
       content: str = Field(..., description="Контент файла")
       format: Literal["md", "txt", "pdf", "docx", "odt", "xls", "xlsx"] = Field(...)
       filename: str | None = Field(default=None, description="Имя файла (без path)")

   @tool(args_schema=FileExportArgs)
   async def file_export(content: str, format: str, filename: str | None = None) -> dict:
       '''Сохраняет контент как артефакт в S3 (MinIO). Возвращает {artifact_id,
       format, filename, s3_key}. Быстрые форматы (md/txt) — синхронно.
       Медленные (pdf/docx/odt/xls/xlsx) — асинхронно, 503 + retry (Phase 5
       ADR-018 добавит real worker).'''
       # Sanitize filename
       if filename:
           filename = Path(filename).name  # no path traversal
           if not filename or filename in (".", ".."):
               filename = None
       if not filename:
           filename = f"artifact.{format}"

       artifact_id = uuid4().hex
       s3_key = f"artifacts/{artifact_id}/{filename}"
       storage = create_file_storage()

       if format in ("md", "txt"):
           # Sync fast path
           content_bytes = content.encode("utf-8")
           await storage.save(content_bytes, s3_key, metadata={
               "format": format, "filename": filename
           })
           return {
               "artifact_id": artifact_id,
               "format": format,
               "filename": filename,
               "s3_key": s3_key,
           }
       else:
           # Slow path — stub for Phase 1, real worker in Phase 5 (ADR-018)
           # В Phase 1: эмулируем 2 сек задержку + сохраняем .txt как placeholder
           # (UI-1 показывает "Generating..." + retry; реальный рендеринг PDF/DOCX
           # — Phase 5 background worker).
           import asyncio
           await asyncio.sleep(2)  # stub latency
           # Сохраняем .txt как placeholder (UI-1 retry будет тянуть пока
           # Phase 5 worker не отрендерит реальный PDF/DOCX)
           placeholder_key = s3_key.rsplit(".", 1)[0] + ".txt"
           await storage.save(content.encode("utf-8"), placeholder_key, metadata={
               "format": "txt", "filename": filename.rsplit(".", 1)[0] + ".txt",
               "original_format": format, "artifact_id": artifact_id
           })
           return {
               "artifact_id": artifact_id,
               "format": format,
               "filename": filename,
               "s3_key": placeholder_key,  # пока .txt placeholder
               "status": "generating",  # UI-1 видит 503 → "Generating..." + retry
           }
   ```

3. Интегрируй file_export в AG-1 graph (промпт 2):
   - В build_agent_graph: добавь tools параметр (default []).
   - Если tools: planner вызывает llm.bind_tools(tools) (ADR-006). LLM может
     вернуть tool_call с name="file_export" и args.
   - Добавь tool_executor ноду (минимальная — единственная tool-нода в Phase 1):
     - tool_executor(state) -> dict: для каждого tool_call в last AIMessage:
       вызывает соответствующий tool (file_export), получает result, добавляет
       ToolMessage в state["messages"].
     - В Phase 1 — один tool (file_export), но architecture должна поддержать
       добавление AG-5/AG-6/AG-7 через registry (просто list, без pluggable
       registry в Phase 1 — это упрощение).
   - Conditional edges update:
     - route_after_planner: если last AIMessage has tool_calls → tool_executor;
       иначе → final_answer.
     - route_after_tool: всегда возвращает в planner (для интерпретации
       tool result). В Phase 1 — после одного tool_call всегда final_answer
       (planner видит tool result, решает ответить пользователю).
   - max_iterations предотвращает бесконечный loop planner ↔ tool_executor.

4. Интегрируй с AG-3 SSE (промпт 4):
   - tool_executor нода возвращает ToolMessage в state["messages"].
   - graph.astream отдаёт ToolMessage как chunk (как обычное сообщение, но UI и
     AG-3 stream_generator должны распознать его как artifact event).
   - stream_generator (AG-3) проверяет isinstance(chunk, ToolMessage) и
     парсит content как JSON dict (file_export result). Если dict содержит
     artifact_id → эмитит event: artifact_ready (промпт 4, п.4).

5. Добавь GET /artifacts/{artifact_id} endpoint в agent-service (промпт 1):
   - Новый маршрут в src/llm_client/agent/service.py:
     - GET /artifacts/{artifact_id}?filename=<filename> → file response.
     - Читает из S3 через create_file_storage().get(s3_key), где s3_key
       восстанавливается из artifact_id (pattern: artifacts/{artifact_id}/{filename}).
     - 200 OK → file bytes (StreamingResponse для больших файлов, > 5 МБ).
     - 404 → если файл не найден (FileNotFoundError from storage.get).
     - 503 → если status="generating" (для pdf/docx stub) — UI-1 retry.
   - Это endpoint, который UI-1 (render_artifact_buttons в
     src/llm_client/ui/render.py) уже вызывает через fetch_artifact_content —
     контракт совпадает.

6. Создай тесты src/llm_client/agent/tools/test_file_export.py:
   - file_export.invoke({"content": "hello", "format": "md"}) → dict с
     artifact_id, format="md", filename="artifact.md", s3_key начинается с
     "artifacts/". S3 объект создан в mock storage (InMemoryFileStorage из
     tests/conftest.py).
   - file_export.invoke({"content": "...", "format": "pdf"}) → dict с
     status="generating", filename="artifact.pdf", s3_key ends with ".txt"
     (placeholder). Latency ≥ 2 сек (stub).
   - Path traversal: file_export.invoke({"content": "...", "format": "md",
     "filename": "../../../etc/passwd"}) → filename sanitized to "passwd"
     (Path(...).name).
   - Integration: graph с file_export tool, LLM mock возвращает tool_call →
     tool_executor вызывает file_export → ToolMessage в state → graph выходит
     в final_answer.
   - GET /artifacts/{id} → 200 OK для md (быстрый путь); 503 для pdf (generating).

Definition of Done:
- LLM prompt "save 'hello world' as markdown" → file_export tool call → S3
  объект в bucket llm-client-files/artifacts/{id}/artifact.md (видно в MinIO
  Console http://localhost:9001).
- AG-3 (промпт 4) эмитит event: artifact_ready с {artifact_id, format: "md",
  filename: "artifact.md", s3_key: "artifacts/.../artifact.md"}.
- UI-1 (Streamlit) download button активируется после event: artifact_ready,
  клик скачивает .md файл (через GET /artifacts/{id}).
- Для format: "pdf" — AG-3 эмитит event: artifact_ready с задержкой 2 сек
  (stub), UI-1 показывает "Generating..." + retry. GET /artifacts/{id} отдаёт
  503 для pdf в Phase 1 (пока нет Phase 5 worker).
- Path traversal protection: filename "../../../etc/passwd" → sanitized to
  "passwd" (no parent directory).
- minio bucket llm-client-files содержит артефакты после теста (видно в
  MinIO Console).
- Все unit-тесты test_file_export.py зелёные.
- Существующие тесты tests/integration/test_minio_storage.py (Block E) — не
  регрессируют.

Антипаттерны:
- НЕ используй LocalFileStorage — упразднён в расш. ADR-008 (Block E). Только
  create_file_storage() → S3CompatibleStorage (MinIO в dev, S3 в prod).
- НЕ хардкодь bucket — S3_BUCKET из env (default llm-client-files).
- НЕ генерируй pdf/docx/xlsx синхронно в Phase 1 — это блокирует event loop,
  2–10 сек latency. Stub asyncio.sleep(2) + 503 для UI retry; реальный worker
  — Phase 5 ADR-018 (async file rendering).
- НЕ пиши filename без sanitization — pathlib.Path(filename).name, без "/" и
  "..". Path traversal attack — security risk.
- НЕ хардкодь tools list в graph — передавай через параметр build_agent_graph
  (tools=None default). В Phase 1 — [file_export] после AG-4. В Phase 2/4 —
  [file_export, web_search, rag_query, mcp_call] (AG-5/6/7).
- НЕ создавай отдельный tool_registry в Phase 1 — простой list в build_agent_graph.
  Pluggable registry — Phase 4 (через entrypoints, ADR-009 pattern).
- НЕ логируй content артефакта в operational stream (potentially PII). Только
  artifact_id, format, size в operational; full content — forensic (D-3,
  encrypted) если нужно.
- НЕ сохраняй content в БД — только в S3. БД — для metadata (Phase 5, ADR-018
  worker tracking).

Связанные ADR: реализует ARCHITECT.md §5.2.4 (Tool Layer — частично); применяет
ADR-006 (нативный tool calling через bind_tools); использует расш. ADR-008
(S3CompatibleStorage); зависит от AG-1 (graph с tool_executor нодой), AG-3
(SSE event: artifact_ready emission); разблокирует UI-1 download buttons для
реальных артефактов.
```

---

## Приложение: чек-лист выхода AG-составляющей из Phase 1

**Источник**: `BACKLOG.md` v1.1.0 §5.2, `ROADMAP.md` v1.2.0 §5.6 п.6–10.

| # | Критерий | Где проверяется | Соответствующий промпт |
|---|---|---|---|
| 1 | AG-0 Approved: `python -m llm_client.agent` поднимает FastAPI на :8000, `/health` отдаёт 200, `POST /sessions/{id}/chat` принимает промпт, `GET /sessions/{id}/stream` отдаёт SSE-стрим (с mock-LLM — `event: done` < 1 сек) | manual + curl + test_service.py (future) | 1 (AG-0) |
| 2 | AG-1 Approved: `build_agent_graph(llm, token)` возвращает compiled graph; `graph.astream(...)` отдаёт токены; при `token.cancel()` — выход с partial answer на следующем conditional edge; `IterationMonitor` срабатывает на 2 одинаковых итерациях подряд | test_graph.py | 2 (AG-1) |
| 3 | AG-2 Approved: `LLMProviderFactory.create("openai", "gpt-4o-mini")` с валидным `OPENAI_API_KEY` возвращает `ChatOpenAI`; `token_usage_tracker` логирует `prompt_tokens`/`completion_tokens` в operational stream; `LLM_PROVIDER=anthropic` → `NotImplementedError("Phase 3 (ADR-015)")` | test_provider.py | 3 (AG-2) |
| 4 | AG-3 Approved: после `POST /chat` + `GET /stream` UI получает `event: token` × N, `event: metadata` с `pii_score` и `pii_entities` (без PII-текста), `event: done`. При cancel — `event: cancelled` < 200 мс. При exception — `event: error` с `{message, type}` | test_sse.py + manual | 4 (AG-3) |
| 5 | AG-4 Approved: LLM prompt «save 'hello' as markdown» → `file_export` tool → S3 объект в bucket `llm-client-files` → UI-1 download button активируется, клик скачивает `.md`. Для `format: "pdf"` — 503 + retry (stub 2 сек) | test_file_export.py + manual (MinIO Console) | 5 (AG-4) |
| 6 | Существующие тесты (194 из SETUP_COMPLETE.md) — не регрессируют | `pytest tests -v` | все |
| 7 | UI-0..UI-3 работают с реальным agent-service (не mock): стриминг, PII badge, download buttons, cancelled badge | manual: `start.ps1` → открой http://localhost:8501, введи prompt, проверь UI | интеграция AG-0..AG-4 ↔ UI-0..UI-3 |

**При невыполнении п.1–5**: соответствующий AG-N пересматривается. Возможные причины:
- ADR-001 (LangGraph) не подходит для Phase 1 minimal graph → рассмотреть linear flow без LangGraph (но это нарушает ADR-001, требует пересмотра ADR).
- LLM provider API изменился (OpenAI deprecated gpt-4o-mini) → обновить default model в Settings.
- SSE heartbeat конфликтует с proxy → увеличить интервал или использовать `Connection: keep-alive` header.

**При невыполнении п.6**: regression в существующих тестах — баг в AG-N реализации. Откатить AG-N, исправить, перезапустить.

**При невыполнении п.7**: интеграционный bug между UI и agent-service. Проверить AGENT_SERVICE_URL env, формат SSE events (парсер в ui/chat.py должен их понимать), CORS (если UI и agent-service на разных портах — FastAPI middleware).

---

## Приложение: параллелизация с UI-составляющей

AG-составляющая (7.5 чел-дн) и UI-составляющая (6.5 чел-дн) могут вестись параллельно при команде из 2 разработчиков:

| Неделя | Backend-разработчик (AG) | Frontend-разработчик (UI) |
|---|---|---|
| 1 | AG-0 (scaffold) + AG-1 (graph) start | UI-0 (scaffold) + UI-1 (base elements) |
| 2 | AG-1 finish + AG-2 (LLM provider) | UI-2 (UIClient) + UI-3 (fragments) |
| 3 | AG-3 (SSE) + AG-4 (file_export) | UI-1..UI-3 интеграция с AG-0..AG-4 (manual testing) |
| 4 | Буфер: интеграция, тесты, ревью | Буфер: интеграция, тесты, ревью |

Критический путь: 7.5 чел-дн (AG-0..AG-4) на backend, 6.5 чел-дн (UI-0..UI-3) на frontend. Параллельно — 3 недели разработки + 1 неделя интеграции и ревью = 4 недели Phase 1 (vs 3 недель в v1.0.0).

**Зависимости между AG и UI** (точки синхронизации):
- После AG-0 (backend) + UI-0 (frontend): первая интеграция — UI получает реальный SSE (пусть даже `event: done` без токенов).
- После AG-3 (backend) + UI-1 (frontend): вторая интеграция — PII badge, download buttons, cancelled badge работают с реальными событиями.
- После AG-4 (backend) + UI-1 (frontend): третья интеграция — file_export → artifact_ready → download button active.

Если backend отстаёт — frontend может продолжать на mock_agent_service.py (с оговорками: mock не эмитит event: metadata, event: artifact_ready, event: cancelled — UI-1 элементы не активируются, но стриминг работает).

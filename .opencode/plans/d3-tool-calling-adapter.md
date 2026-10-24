# План: промпт D-3 (BETA-PROMPTS.md) — `ToolCallingAdapter` (ADR-016, Phase 3)

## Цель

Создать `src/llm_client/agent/tool_calling_adapter.py`: central adapter, выбирающий режим tool calling (`native` / `react` / `hybrid`) по `ModelCapabilityMatrix` (D-1) и `ToolCallingMode` (D-2) + юнит- и интеграционный тесты. Граф (D-5), prompt builder (D-4) и пилот (D-6) — **вне** объёма.

## Текущее состояние (предусловия выполнены)

- `capability_matrix.py` (D-1) и `tool_calling_mode.py` (D-2) закоммичены (`8f6c532`, `f90e519`); `get_capability_matrix()`, `ModelCapabilityMatrix.get_capabilities()`, `ToolCallingMode.default_for_capabilities()` готовы.
- `tool_calling_adapter.py` отсутствует; `graph.py:477` до сих пор зовёт `llm.bind_tools(tools)` напрямую (замена — D-5).
- Ядро: langchain-core **1.6.12**; `BaseChatModel` абстрактен только через `_generate`/`_llm_type`; `bind_tools` по умолчанию `raise NotImplementedError`.
- Окружение: venv отсутствует, используется системный Python 3.11.9 (`python -m pytest` / `ruff` / `mypy`), пакет установлен editable из `src/`.

## Согласованные отклонения от сниппета промпта

1. **Формат эмиссии tool call (ReAct)** — подтверждено экспериментально: `AIMessage(additional_kwargs={"tool_calls":[{"tool":…,"arguments":…}]})` → `.tool_calls == []` (парсер `default_tool_parser` принимает только OpenAI-формат `{"id","function":{"name","arguments"}}`). Поэтому `ReActBoundModel` создаёт **новый** `AIMessage` с `additional_kwargs["tool_calls"] = [{"id": "react_<hex>", "function": {"name": …, "arguments": json.dumps(…)}}]`, копируя `response_metadata` / `usage_metadata`. Валидатор AIMessage парсит это в `.tool_calls` (name/args/id) → работают `route_after_planner` (graph.py:544), `_tool_executor_node` (graph.py:222-254), SSE `tool_call` (service.py:1626-1642). Контракт «contract preserved via additional_kwargs.tool_calls» (D-3 «Не затрагивает») соблюдён: сырые записи есть в additional_kwargs, нормализованные — в `.tool_calls`.
2. **HYBRID fallback только при parse-error** — вместо «any response without tool_calls → повторный ReAct-вызов». `HybridBoundModel.ainvoke`: (а) native raise → ReAct; (б) native вернул пустые `.tool_calls`, но `parse_react_response(content)` находит tool call (модель выдала JSON текстом — native API не справился) → ReAct; (в) обычный текстовый ответ → вернуть как есть. `astream` — аналогично, с warning-логом про double-streaming (антипаттерн промпта требует признать его). Иначе HYBRID (дефолт gpt-4o-mini) удваивал бы cost/latency на каждом не-тул ответе — противоречило бы ADR-015 cost predictability и pilot E-2.
3. **Info-log выбора режима** в `choose_mode` (антипаттерн: «НЕ забудь логировать mode choice — критично для ADR-016 pilot»); сниппет логировал только warning для отсутствующей записи.
4. `REACT_SYSTEM_PROMPT` остаётся module-level константой (inline) — D-4 явно спроектирован как «выделить inline implementation в `ReactToolCallPromptBuilder`»; `prompts/*.txt` отложено в Phase 4 (антипаттерн D-3/D-4).

Всё остальное — по сниппету промпта (строки 4756–5118).

## Изменения по файлам

### 1. `src/llm_client/agent/tool_calling_adapter.py` (новый)

- `from __future__ import annotations`; импорты: `json`, `logging`, `re`, `uuid4`, `Any`; `BaseChatModel`, `AIMessage`, `BaseMessage`, `SystemMessage`, `BaseTool`; `.capability_matrix` (`ModelCapabilityMatrix`, `get_capability_matrix`), `.tool_calling_mode` (`ToolCallingMode`).
- `REACT_SYSTEM_PROMPT` — дословно из промпта (плейсхолдеры `{tool_descriptions}`, `{tool_schemas}`, экранированные `{{…}}`; `.format()` валиден).
- `_to_openai_tool_call(tool_call: dict) -> dict` — приватный helper: `{tool|name, arguments|args}` → `{"id": "react_<uuid4().hex>", "function": {"name": …, "arguments": json.dumps(…)}}`; строковый `arguments` пропускается как есть.
- `ToolCallingAdapter`:
  - `__init__(capability_matrix: ModelCapabilityMatrix | None = None)` → `self._matrix = capability_matrix or get_capability_matrix()`.
  - `choose_mode(provider, model, explicit_mode=None)`: explicit override → caps None → `logger.warning` + `HYBRID` → иначе `default_for_capabilities(caps)`; в конце `logger.info("Tool calling mode for %s/%s: %s", …)`.
  - `bind_tools(llm, tools, mode) -> Any`: NATIVE → `llm.bind_tools(tools)`; REACT → `ReActBoundModel(underlying=llm, tools=tools)`; HYBRID → `try: HybridBoundModel(native_bound=llm.bind_tools(tools), react_bound=ReActBoundModel(...)) except Exception → warning + ReActBoundModel`; иначе `ValueError`.
  - `_format_tool_descriptions`, `_format_tool_schemas`, `build_react_system_prompt`, `parse_react_response` (regex с ```` ``` ````-fences и без, затем `json.loads`; иначе None) — по сниппету.
- `ReActBoundModel` (прокси, **не** наследует `BaseChatModel` — как `CacheAwareBoundModel` из B-4):
  - `__init__`: underlying, tools, `_tools_by_name`, `_adapter = ToolCallingAdapter()`.
  - `ainvoke`: инжект `SystemMessage` с ReAct-промптом перед messages → `underlying.ainvoke` → `parse_react_response(content)`; при tool call — вернуть **новый** `AIMessage(content=…, additional_kwargs={**response.additional_kwargs, "tool_calls": [raw openai-формат]}, response_metadata=…, usage_metadata=…)`.
  - `astream`: инжект промпта, аккумуляция текста (content может быть list в LC v1 → коэрсить в str), yield чанков; после стрима при tool call — yield финального `AIMessage` (аналогично ainvoke).
  - `__getattr__` → underlying.
- `HybridBoundModel`: `ainvoke`/`astream` по схеме fallback (п.2 выше); `__getattr__` → native.
- Module singleton `get_tool_calling_adapter()` (по сниппету).

### 2. `tests/unit/test_tool_calling_adapter.py` (новый)

10 тестов из промпта + 4 дополнительных (DoD требует «11+»):

1. `test_choose_mode_native_support_returns_hybrid` — `("openai","gpt-4o-mini")` → HYBRID.
2. `test_choose_mode_no_native_returns_react` — `("ollama","llama3.1-8b")` → REACT.
3. `test_choose_mode_explicit_override` — explicit NATIVE → NATIVE.
4. `test_choose_mode_unknown_model_defaults_to_hybrid` — `("unknown","nope")` → HYBRID (caps None, warning).
5. `test_bind_tools_native_mode_returns_bound_model` — mock `llm.bind_tools`, проверить вызов с tools.
6. `test_bind_tools_react_mode_returns_react_bound_model`.
7. `test_bind_tools_hybrid_mode_returns_hybrid_bound_model`.
8. `test_bind_tools_hybrid_falls_back_to_react_on_bind_error` — `llm.bind_tools` → `NotImplementedError` → ReActBoundModel (реальный случай: `bind_tools` по умолчанию в LC 1.x).
9. `test_bind_tools_unknown_mode_raises_value_error`.
10. `test_parse_react_response_extracts_json_with_fences`.
11. `test_parse_react_response_extracts_json_without_fences`.
12. `test_parse_react_response_returns_none_for_no_tool_call`.
13. `test_build_react_system_prompt_includes_tool_descriptions` — содержит имена `web_search` / `rag_query` + schemas.
14. `test_get_tool_calling_adapter_is_singleton`.
15. `test_react_bound_model_ainvoke_emits_parsable_tool_call` — underlying = `FakeListChatModel(responses=['…{"tool":"web_search","arguments":{"query":"test"}}…'])`; `adapter.bind_tools(llm, tools, REACT).ainvoke([HumanMessage])` → `msg.tool_calls[0]["name"]=="web_search"`, `args=={"query":"test"}`, `id.startswith("react_")`, raw OpenAI-формат в `additional_kwargs["tool_calls"][0]["function"]`, в messages появился SystemMessage с ReAct-промптом.

Фикстуры: реальная `get_capability_matrix()` (дефолтный YAML из D-1 — нужные записи уже есть); `MagicMock`/`sentinel` для native-bound LLM; `FakeListChatModel` (langchain_core) как underlying в react-тестах.

### 3. `tests/integration/test_react_e2e.py` (новый, `@pytest.mark.integration`, без docker)

По промпту: mock LLM возвращает текст с JSON tool call → `ReActBoundModel` извлекает его.
- `test_react_e2e_extracts_tool_call_from_text`: fake tool `web_search` (`StructuredTool.from_function` или `@tool`); `FakeListChatModel` → текст с JSON (с fence и без — параметризация); `adapter.bind_tools(..., REACT)` → `ainvoke` → assert: raw в `additional_kwargs["tool_calls"]`, нормализованный `.tool_calls`, `ToolMessage(content=await tool.ainvoke(msg.tool_calls[0]["args"]), tool_call_id=msg.tool_calls[0]["id"])` — round-trip аргументов.
- Полный прогон через `build_agent_graph` **не** делается: graph сам зовёт `llm.bind_tools` (graph.py:477) — замена на adapter происходит в D-5.

### 4. Не изменяются

`graph.py`, `service.py`, `provider.py`, `react_prompt_builder.py` (D-4), config/.env — нет новых настроек. Существующие тесты Phase 1/2/3 не трогаются.

## Антипаттерны (контроль)

- `ReActBoundModel`/`HybridBoundModel` не наследуют `BaseChatModel` — только прокси `__getattr__` (как `CacheAwareBoundModel`).
- `parse_react_response` — только regex + `json.loads`; неудача → None (без NLP).
- Double-streaming в `HybridBoundModel.astream` — только с явным warning-логом/комментарием (Phase 4 оптимизация).
- Mode choice логируется (info) — pilot ADR-016 (ReAct success rate).
- Mode selection не выносится в graph code — adapter transparent (D-5).
- `REACT_SYSTEM_PROMPT` выносится в `prompts/` только в Phase 4 (D-4 сначала выделит builder).
- Имена/эмитинг tool call id — `react_<hex>`, без PII в логах.

## Верификация (по порядку)

```powershell
# 0. Базовое состояние (зафиксировать существующие падения, если есть)
python -m pytest tests/unit -q

# 1. Новые тесты
python -m pytest tests/unit/test_tool_calling_adapter.py -v
python -m pytest tests/integration/test_react_e2e.py -v

# 2. Регрессия + линт + типы
python -m pytest tests/unit -q
python -m ruff check src tests
python -m mypy src/llm_client
```

DoD «Phase 1/2 не регрессируют»: адаптер ничего не подключает в runtime-пути — регрессия возможна только через импорт-ошибку; покрывается прогоном `tests/unit`.

## DoD mapping (промпт D-3)

| DoD-пункт | Реализация |
|---|---|
| `tool_calling_adapter.py` c `ToolCallingAdapter` (choose_mode, bind_tools, build_react_system_prompt, parse_react_response) + `ReActBoundModel` + `HybridBoundModel` + factory | п.1 |
| 11+ unit тестов зелёные | п.2 (15 тестов) |
| 1 integration тест зелёный | п.3 |
| Работает с любым `BaseChatModel` (задел под Phase 4 Ollama) | duck-typing: используются только `ainvoke`/`astream`/`bind_tools` |
| Сохранение контракта ADR-006 (`additional_kwargs.tool_calls`) | п.1: raw OpenAI-формат в additional_kwargs + нормализованный `.tool_calls` |

## Риски / отложено

- Решения по формату и HYBRID-fallback согласованы с пользователем (см. «Согласованные отклонения»).
- D-5 (`build_agent_graph` через adapter) — следующий промпт; без него graph продолжает звать `llm.bind_tools` напрямую, поведение prod не меняется.
- Коммит — только по явной просьбе пользователя.

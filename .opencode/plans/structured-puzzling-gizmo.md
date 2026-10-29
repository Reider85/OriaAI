# План: выполнение промпта H-4 (BETA-PROMPTS.md) — Probe / health-check от external MCP client

## Цель

Создать probe script `scripts/probe_mcp_server.py` (external MCP client, httpx) + integration-тесты `tests/integration/test_mcp_server_probe.py`. Pilot-критерий ROADMAP §14.1: LLM Client в MCP Server mode отвечает на list_tools и call_tool от внешнего клиента. DoD: exit 0 при healthy server, exit 1 при failure.

## Текущее состояние (предусловия H-1..H-3 выполнены)

- `src/llm_client/mcp/server.py` — `McpServer`, 4 routes:
  - `GET /mcp/health` → `{"status":"ok","tools_count":N,"tools":[names]}`
  - `GET /mcp/tools` → `{"tools":[{"name","description","args_schema"}]}`
  - `POST /mcp/tools/{name}` (JSON args) → `{"result":...,"error":null}`; handler-error → HTTP 200 `{"result":null,"error":"..."}`; unknown tool → 404
  - `GET /mcp/tools/{name}/stream?args_json=...` → SSE (`text/event-stream`), всегда заканчивается `event: done`
- `src/llm_client/mcp/tool_registry.py` — 3 tools: `rag_query`, `file_export`, `web_search` (agent_run НЕ зарегистрирован)
- `service.py:450-458` — маршруты монтируются условно при `settings.mcp_server_enabled=True`
- `httpx>=0.27.0` уже в deps; пакет `mcp` SDK не установлен и **не нужен** — сам reference-код промпта использует httpx (H-4 = black-box HTTP probe)
- `scripts/probe_mcp_server.py` и `tests/integration/test_mcp_server_probe.py` — отсутствуют (создаются)
- Тесты MCP: `tests/unit/test_mcp_server.py`, `tests/integration/test_mcp_server_e2e.py` (паттерн: `ASGITransport`, try/finally reset registry); `respx` в репо не используется

## Изменения по файлам

### 1. `scripts/probe_mcp_server.py` (новый)

По reference-коду промпта (BETA-PROMPTS.md:6345–6453) с адаптациями:

- `async def probe_mcp_server(base_url: str) -> bool`:
  1. `GET /mcp/health` — не 200 → False; лог tools_count
  2. `GET /mcp/tools` — не 200 → False; лог name/description каждого tool
  3. Для каждого tool: `POST /mcp/tools/{name}` c args из `get_minimal_args(name)`; не 200 → False; `result["error"]` truthy → **лог + continue** (tool errors не критичны, напр. без TAVILY_API_KEY); success → лог `result` (усечённый до 100 символов)
  4. SSE probe (non-critical): `GET /mcp/tools/web_search/stream` — через `params={"args_json": json.dumps({...})}` (не raw URL-строку — корректное кодирование); наличие `event:` в ответе → OK, иначе warning; не-200 → warning; probe не фейлится
- `def get_minimal_args(tool_name) -> dict`: `rag_query → {"query":"test","top_k":1}`, `file_export → {"filename":"test.txt","content":"test"}`, `web_search → {"query":"test","max_results":1}`, иначе `{}`
- `main()`: argparse `--url` (default `http://localhost:8000`), `logging.basicConfig(level=INFO)`, `sys.exit(0 if success else 1)`
- Стиль по конвенциям scripts/: module docstring, import httpx на уровне модуля

Адаптации к реальному коду (отклонения от snippets — осознанные):
- SSE URL через `params=` вместо f-string query (JSON в query string требует encoding)
- SSE probe только если `web_search` есть в tools_list (guard)
- httpx AsyncClient timeout=30.0; SSE-запрос timeout=10.0

### 2. `tests/integration/test_mcp_server_probe.py` (новый)

5 тестов по промпту, все с `pytestmark = pytest.mark.integration` (конвенция репо; фильтруемые `-m integration` CI):

Мокинг: `httpx.MockTransport(handler)` — патчинг `httpx.AsyncClient` через `monkeypatch.setattr` на уровне `httpx` (script вызывает `httpx.AsyncClient(...)` в рантайме — патч срабатывает без импорта scripts как пакета). Роутинг в handler-е по `request.url.path`:

1. `test_probe_passes_when_server_healthy` — валидные health/tools/call/stream → True
2. `test_probe_fails_on_health_check_failure` — health 500 → False (при этом list/call не вызываются)
3. `test_probe_fails_on_list_tools_failure` — health 200, tools 500 → False
4. `test_probe_passes_with_tool_errors` — call возвращает `{"result":null,"error":"TAVILY_API_KEY missing"}` → True
5. `test_get_minimal_args_per_tool` — импорт `get_minimal_args` через `importlib.util.spec_from_file_location` (scripts не является установленным пакетом; надёжнее `from scripts...`); проверить args для 3 известных tools + `{}` для неизвестного

Мок-ответы строго по контрактам H-1/H-2 (health: `tools_count`; call: `{result,error}`; stream: `event: tool_result\ndata: ...\n\n` + `event: done\ndata: {}\n\n`).

Не делается (вне скоупа H-4, относится к E-4):
- Изменения в `ci-local-staging.sh` / CI workflows (probe step в staging — отдельный промпт E-4)
- Запуск реального agent-service в тестах (только mocked HTTP, по спецификации)

## Антипаттерны (соблюдаются)

- Tool-specific errors не фейлят probe (continue)
- Minimal args — в helper function `get_minimal_args`, не захардкожены в цикле
- Health check всегда первым (discovery protocol)
- Без добавления новых зависимостей (httpx уже есть; `mcp` SDK не требуется)

## Верификация

```powershell
.\.venv\Scripts\python.exe -m pytest tests/integration/test_mcp_server_probe.py -v
.\.venv\Scripts\python.exe -m pytest tests/integration tests/unit/test_mcp_server.py tests/unit/test_mcp_sse_transport.py tests/unit/test_exposed_tool_registry.py -v   # регрессия H-1..H-3
ruff check scripts/probe_mcp_server.py tests/integration/test_mcp_server_probe.py
```

Manual run (DoD): `MCP_SERVER_ENABLED=true` agent-service + `python scripts/probe_mcp_server.py --url http://localhost:8000` → exit 0. (Если инфра недоступна — проверяется локально mocked-тестами; manual step отмечается в PR.)

## DoD mapping

| DoD-пункт | Реализация |
|---|---|
| `scripts/probe_mcp_server.py` с `probe_mcp_server` + `main()` CLI | п.1 |
| CLI `--url`, exit 0/1 | п.1 |
| Probe: /mcp/health, /mcp/tools, /mcp/tools/{name}, stream SSE | п.1 |
| 5+ integration тестов зелёные (mocked HTTP) | п.2 |
| Manual run exit 0 при MCP_SERVER_ENABLED=true | верификация |

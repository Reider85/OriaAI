# Plan: починить кнопку Stop / отмену запроса из UI

## Диагноз

Backend-цепочка отмены (endpoint → Redis pub/sub → CancellationToken → `invoke_with_cancel` → SSE `cancelled`) работает и покрыта тестами. Рвётся вход **UI → endpoint**:

1. **Кнопки Stop нет.** Есть только JS-хелпер `window.stop_llm_session` (`auto_cancel.py:79-83`), но ни `st.button`, ни HTML-кнопки, которая его вызывала бы, в UI нет (README:302 обещает — кода нет).
2. **JS не знает session_id.** Фрагмент выполняется внутри iframe `srcdoc` → `window.location.search` пуст; fallback `localStorage["llm_session_id"]` нигде не записывается → `sessionIdFromLocation()` → `null` → `sendCancel` молча выходит (`auto_cancel.py:31-35`).
3. **Не тот origin.** `inject_auto_cancel()` в `app.py:103` без `backend_origin` → `BACKEND = window.location.origin` = Streamlit (8501), а cancel живёт на agent-service (8010 в `.env`).
4. **Нет CORS** в agent-service → кросс-доменный POST с origin Streamlit забранет браузер.

## Важный нюанс Streamlit

Во время активного стриминга python-цикл `for token in chat.stream_tokens(...)` блокирует main thread фрагмента (`streamlit_client.py:251-257`) — `st.button` НЕ сработает до завершения стрима. Поэтому Stop делаем **JS-кнопкой** (`components.html`): её onclick живёт в браузере и шлёт POST параллельно блокирующему циклу. Backend отменяет граф → SSE шлёт `cancelled` → `stream_tokens` кидает `ChatStreamError(status="cancelled")` → фрагмент рендерит `Cancelled: user_cancelled` (уже есть, `render.py:186-187`).

## Изменения

### 1. `src/llm_client/ui/auto_cancel.py`

- `AUTO_CANCEL_JS`:
  - добавить placeholder `{{SESSION_ID}}`; `sessionIdFromLocation()` возвращает зашитый id (fallback — старые URL/localStorage на случай внешних вызовов);
  - `sendBeacon`: Blob `type: "text/plain;charset=UTF-8"` вместо `application/json` — simple request без preflight (важно на `beforeunload`/`pagehide`, когда preflight не успевает); Starlette парсит JSON- body независимо от content-type. `fetch`-fallback остаётся с `application/json`.
- `inject_auto_cancel(backend_origin: str | None = None, session_id: str | None = None)` — подстановка обоих в шаблон.
- Новая функция `render_stop_button(session_id: str, backend_origin: str | None = None)` — `components.html` с видимой HTML-кнопкой «Stop», `onclick` → `POST {backend}/sessions/{sid}/cancel` (`keepalive: true`, reason `user_cancelled`). Повторно использует логику из того же JS-шаблона (вынести общую часть или инжектить кнопку поверх существующего скрипта — реализовать одним фрагментом).

### 2. `src/llm_client/ui/app.py`

- Перенести `inject_auto_cancel()` **после** `session_id = session.init_state()` (сейчас строка 103 — до 107) и вызвать:
  `inject_auto_cancel(backend_origin=chat.agent_service_url(), session_id=session_id)`.

### 3. `src/llm_client/ui/streamlit_client.py` (`_streaming`)

- Перед циклом токенов: `stop_ph = st.empty()` + `render_stop_button(session_id)` в него.
- После цикла (в `finally`-подобной ветке рядом со `st_state[_STREAMING_DONE_KEY] = True`): `stop_ph.empty()` — кнопка исчезает по завершении.

### 4. `src/llm_client/agent/service.py` (создание `app`, ~строка 405)

- `app.add_middleware(CORSMiddleware, allow_origins=..., allow_methods=["POST"], allow_headers=["Content-Type"])`.
- Origins из env `UI_CORS_ORIGINS` (CSV), дефолт `http://localhost:8501,http://127.0.0.1:8501`.

### 5. Тесты

- `tests/unit/test_auto_cancel_ui.py` — обновить: подстановка `session_id`/`backend_origin`, presence кнопки Stop, `text/plain` у sendBeacon.
- Новый/расширенный юнит-тест `render_stop_button` (рендерит HTML с кнопкой и URL cancel).
- CORS: юнит-тест, что middleware добавлен (OPTIONS-предflight или наличие middleware в `app.user_middleware`).

## Верификация

```bash
.\.venv\Scripts\python.exe -m pytest tests/unit/test_auto_cancel_ui.py tests/unit/test_cancel_token.py tests/unit/test_cancel_endpoint.py -v
ruff check src tests
mypy src/llm_client
```

Ручная проверка: `docker-compose up -d` + agent-service + Streamlit → отправить запрос → клик Stop → ожидаемый бейдж `Cancelled: user_cancelled`, генерация прекращается <1 с.

## Вне объёма (по договорённости)

- cancel всегда 404 на `api.py` (другой процесс, `state.activate` не вызывается);
- утечка `SessionState` (`complete()` не вызывается);
- `llm_invoke_timeout_s` — мёртвый параметр графа.

# llm_client/ui — Streamlit chat UI (Phase 1)

Streamlit-клиент для agent-service (UI-0..UI-3, ADR-002/ADR-007).

## Паттерн: UI code calls interface, not Streamlit API

Вся отрисовка идёт через интерфейс `UIClient` (`client.py`), а не через `st.*`
напрямую. Фабрика `get_ui_client()` выбирает реализацию по env `UI_BACKEND`
(default `streamlit`). В Phase 1 доступен только `StreamlitClient`; Phase 5
добавляет `ChainlitClient` — миграция = смена factory, без переписывания
UI-кода.

```python
# app.py — точка входа
from llm_client.ui import get_ui_client

client = get_ui_client()

# рендер истории через интерфейс, а не st.chat_message
for message in session.get_messages():
    client.render_message(message["role"], message["content"], message.get("metadata"))

# стриминг токенов через интерфейс, а не st.write_stream
for token in stream:
    answer += token
    client.stream_token(token)

# артефакты через интерфейс, а не st.download_button
client.render_artifact(artifact_ref)

# ввод через интерфейс, а не st.chat_input
prompt = client.handle_user_input()
```

Интерфейс (`client.py`) — backend-agnostic, ровно 5 методов:

| Метод | Назначение |
|---|---|
| `render_message(role, content, metadata)` | сообщение + PII-бейдж (ADR-014) |
| `render_user_message(content)` | bubble пользователя, возвращает слот для live PII-бейджа |
| `render_artifact(artifact)` | кнопка скачивания артефакта (ADR-008) |
| `stream_token(token)` | буферизует токен и флюшит в placeholder |
| `handle_user_input()` | читает ввод |

## Что остаётся Streamlit-specific (вне интерфейса)

Хуки без аналогов в Chainlit вынесены из интерфейса намеренно (ТРИЗ #16):

- **Sidebar** (`sidebar.py`) — `render_sidebar()` с `st.sidebar`;
- **Status badge** (`render.render_status_badge`) — `st.status`/`st.error`/`st.warning`;
- **Live PII-слот** (`StreamlitClient.update_pii_badge`) — `st.empty()` placeholder.

В коде такие вызовы помечены комментарием
`# Streamlit-specific, not in UIClient interface.` и остаются прямо в app.py
или в StreamlitClient.

## Проверка рефакторинга (DoD промпта 8)

Прямые widget-вызовы Streamlit должны жить только в `streamlit_client.py` или
в строках с маркером `# Streamlit-specific`:

```
grep -rE "st\.chat_message|st\.chat_input|st\.write_stream|st\.download_button" src/llm_client/ui/ \
  | grep -v streamlit_client.py | grep -v "# Streamlit-specific" | wc -l   # → 0
```

`UI_BACKEND=chainlit` → `NotImplementedError` с понятным сообщением.

## Запуск

```bash
streamlit run src/llm_client/ui/app.py   # http://localhost:8501
```

Тесты: `pytest tests/unit/test_ui_client.py tests/unit/test_ui_streamlit_client.py
tests/unit/test_ui_render.py tests/unit/test_ui_chat.py tests/unit/test_ui_session.py
tests/unit/test_ui_sidebar.py tests/unit/test_auto_cancel_ui.py`.
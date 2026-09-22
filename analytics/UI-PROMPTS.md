# UI-PROMPTS.md — Промпты для UI-составляющей Phase 1

| Атрибут | Значение |
|---|---|
| Версия документа | 1.1.0 |
| Дата | 2026-09-23 |
| Источники | `BACKLOG.md` v1.0.0 §3; `ROADMAP.md` v1.1.0 §5.2.4, §5.7; `ARCHITECT.md` v1.1.0 §4.1, §7 ADR-002/007/008/013/014; `TRIZ-ANALYSIS.md` v1.0.0 §4.3, §5.1 (C-1), §11 (ADR-018 драфт) |
| Этап | Phase 1 — UI-составляющая (UI-0..UI-3) |
| Резолвит | C-1 (частично — UI-2/UI-3); C-4 (UI-часть ADR-013) |
| Целевой LLM | Cursor / Copilot / Claude Code / ChatGPT |
| Гранулярность | 1 промпт = 1 файл / 1 класс / 1 подзадача |

---

## 0. Как пользоваться

11 промптов, сквозная нумерация 1–11. Зависимости:

```
1 ──→ 2,3,4,5 ──→ 6 ──→ 7 ──→ 8 ──→ 9 ──→ 10 ──→ 11
                                          │
                                          └──→ бенчмарк (validates 9,10)
```

Параллелизация (2 разработчика):
- Дев 1: 1 → 2 → 3 → 4 → 5 → 8 (refactor pass)
- Дев 2: 6 → 7 → 9 → 10 → 11

Суммарно: 6.5 чел-дн. Критерии выхода — `BACKLOG.md` §5.1.

**Конвенции** (из `MVP-PROMPTS.md`):
- Имена классов/методов/эндпоинтов — на английском.
- ADR и противоречия — `ADR-013`, `C-4`.
- Каждый промпт — в код-блоке, готов к копи-пасту.

---

## 1. Streamlit chat scaffold

```
Ты — Frontend-разработчик LLM Client. Создай scaffold Streamlit-приложения для чата
с agent-service через SSE. Формализация "Phase 0", подразумеваемой ADR-002.

Контекст:
- ADR-002: Streamlit 1.40+ как UI для MVP.
- ADR-007: SSE для streaming (st.write_stream в Streamlit).
- ADR-001: LangGraph-агент с существующим SSE endpoint
  POST /sessions/{session_id}/chat (запуск) и
  GET /sessions/{session_id}/stream (токены).
- Без этого промпта C-5 (UI watcher из MVP-PROMPTS.md) некуда инжектить.

Задача:
1. Создай src/llm_client/ui/app.py (точка входа) + chat.py, session.py, render.py
   (логика, не более 300 строк на файл).
2. st.set_page_config(layout="wide"), st.title("LLM Client"), st.chat_input.
3. При отправке: если session_id нет в st.session_state — генерируй UUID4; POST
   на AGENT_SERVICE_URL/sessions/{id}/chat с {"message": prompt}; открой SSE на
   /sessions/{id}/stream; рендер через st.write_stream в st.chat_message("assistant").
4. История messages в st.session_state["messages"]: list[dict] {role, content,
   timestamp}. При ререндере — из session_state, не с бэкенда.
5. session_id из URL (?session_id=...) или из session_state.
6. Конфиг через env: AGENT_SERVICE_URL (default http://localhost:8000), APP_PORT
  (default 8501).

Definition of Done:
- `streamlit run app.py` поднимается <3 сек, http://localhost:8501 открывается.
- Ввод "hello" → POST → SSE → токены в st.chat_message("assistant") <500 мс до
  первого токена.
- F5 с ?session_id=X восстанавливает историю.
- Backend недоступен → st.error, не падение.
- Нет warnings в console про session_state serialization.

Антипаттерны:
- НЕ хардкодь AGENT_SERVICE_URL — через env.
- НЕ пиши всё в app.py >300 строк — выдели chat.py, session.py, render.py.
- НЕ вызывай LLM напрямую — только через agent-service SSE.
- НЕ сохраняй историю в файл/БД из UI — только session_state.
- НЕ добавляй sidebar/downloads/status — это промпты 2-5.

Связанные ADR: реализует ADR-002, ADR-007; требует ADR-001; блокирует 2-5 и C-5.
```

---

## 2. Sidebar с историей сессий

```
Ты — Frontend-разработчик LLM Client. Добавь sidebar со списком сессий и кнопкой
"New session" в Streamlit-приложение из промпта 1.

Контекст:
- Промпт 1: session_id в st.session_state, messages-история в session_state.
- Phase 1 (до UI-4 Phase 5): нет RedisSessionStore — источник in-memory dict в
  st.session_state["sessions_registry"].
- При переключении сессии chat area перерисовывается с её историей.

Задача:
1. Создай src/llm_client/ui/sidebar.py с render_sidebar() -> str | None:
   - st.sidebar, заголовок "Sessions".
   - st.button("New session") → генерирует UUID4, возвращает None.
   - st.selectbox со списком из get_sessions_list(): {session_id, first_prompt[:30],
     created_at, last_activity}.
   - Возвращает выбранный session_id или None.
2. get_sessions_list() в session.py: из st.session_state["sessions_registry"],
   инициализируется пустым dict при первом запуске.
3. Интегрируй в app.py: перед chat_input — render_sidebar(), результат переключает
   st.session_state["current_session_id"] и загружает соответствующую messages.

Definition of Done:
- Sidebar виден слева: кнопка "New session" + список.
- Клик "New session" → chat area очищается, новая сессия в списке.
- Выбор существующей сессии → chat area показывает её историю.
- F5 с ?session_id=X → эта сессия выбрана, история отображается.
- 50 сессий — sidebar прокручивается, не тормозит.

Антипаттерны:
- НЕ загружай все messages всех сессий в session_state — только текущей.
- НЕ используй st.cache_data для sessions_registry — это stateful.
- НЕ делай sidebar отдельным приложением — функция в sidebar.py.
- НЕ используй st.multiselect — нужен выбор одной сессии (selectbox/radio).

Связанные ADR: ADR-002; зависит от промпта 1; подготовка к UI-4 (Phase 5).
```

---

## 3. Кнопки скачивания артефактов

```
Ты — Frontend-разработчик LLM Client. Добавь кнопки скачивания file_export-артефактов
(ADR-008) в Streamlit UI из промпта 1.

Контекст:
- Расш. ADR-008 (MVP-PROMPTS Блок E): S3CompatibleStorage (MinIO в dev, S3 в prod).
- При file_export tool call в SSE-стриме приходит event artifact_ready:
  {"artifact_id", "format", "filename", "s3_key"}.
- Файлы доступны через GET /artifacts/{artifact_id}.
- Форматы: md, txt, pdf, docx, odt, xls/xlsx (ARCHITECT.md §1).
- Phase 5 (расш. ADR-008 async rendering): fast/slow paths. UI должен их поддерживать.

Задача:
1. Создай render_artifact_buttons(artifacts: list[dict]) -> None в render.py.
2. Для каждого артефакта:
   - md/txt (fast path): st.download_button с MIME text/markdown или text/plain,
     контент через GET /artifacts/{id} (синхронно).
   - pdf/docx/odt/xls/xlsx (slow path, 2-10 сек): st.download_button disabled с
     спиннером "Generating...", активируется по готовности.
3. Интегрируй в цикл стрима (app.py): artifact_ready → в
   st.session_state["pending_artifacts"]; после стрима — render_artifact_buttons.
4. Обработка: 404 → st.warning("Artifact not found"); 503 → st.warning("Still
   generating") + кнопка retry; 200 → активная кнопка.

Definition of Done:
- LLM "сохрани как markdown" → кнопка "Download markdown", клик сохраняет .md.
- Запрос PDF → кнопка с disabled+спиннер, через 2-10 сек активна, клик сохраняет .pdf.
- 4 формата (md/txt/pdf/docx) покрыты manual test.
- 404 → st.warning, не падение. 503 → кнопка видна с retry.
- 3+ артефакта в одном ответе — все отрендерены.

Антипаттерны:
- НЕ хардкодь presigned URL — UI получает только artifact_id.
- НЕ делай один st.download_button с selectbox форматов — каждая своя кнопка.
- НЕ блокируй UI на slow path — placeholder + спиннер.
- НЕ сохраняй файл локально на UI-сервере — только прокси-download.
- НЕ используй st.file_uploader — это для upload.

Связанные ADR: расш. ADR-008; зависит от промпта 1; подготовка к Phase 5 async.
```

---

## 4. Индикатор статуса LLM-вызова

```
Ты — Frontend-разработчик LLM Client. Добавь индикатор статуса LLM-вызова: три
состояния (streaming, cancelled, error) с визуальным различением.

Контекст:
- ADR-013 (MVP-PROMPTS Блок C): cancel через Redis pub/sub. SSE-стрим закрывается
  event: cancelled, data: {"reason": ...}.
- ADR-007: SSE event protocol (event: ..., data: ...).
- Без явного индикатора пользователь не понимает состояние. ТРИЗ #23 (обратная связь).

Задача:
1. Создай render_status_badge(status: str, detail: str | None = None) -> None в
   render.py:
   - streaming: st.status с спиннером "Generating response...".
   - cancelled: st.error с "Cancelled" (красный) + detail как reason из ADR-013.
   - error: st.warning с "Error" (жёлтый) + detail; стектрейс в expander.
2. Интегрируй в app.py в цикл st.write_stream:
   - Перед стримом: render_status_badge("streaming").
   - event: cancelled → render_status_badge("cancelled", reason).
   - event: error → render_status_badge("error", message).
   - event: done → статус закрывается без бейджа.
3. SSE event parsing в chat.py: data: {...} — payload; event: ... — тип.
   Поддерживаемые: token (по умолчанию), done, cancelled, error,
   artifact_ready, metadata. Нераспознанные — console.debug, игнор.

Definition of Done:
- При отправке промпта — спиннер "Generating response...".
- Стриминг токенов — спиннер крутится.
- Cancel (через Stop из MVP-PROMPTS C-5) → красный бейдж "Cancelled: <reason>"
  <200 мс.
- Ошибка backend → жёлтый бейдж "Error: <message>" + expander со стектрейсом.
- Нормальное завершение → спиннер исчезает без бейджа.
- 3 состояния тестируются: streaming (нормальный), cancelled (Stop), error
  (выключить agent-service).

Антипаттерны:
- НЕ используй st.spinner() — блокирует rerun. Только st.status (1.40+) или
  placeholder.
- НЕ показывай стектрейс без expander — засоряет UI.
- НЕ смешивай cancelled и error — разные UX (cancel = норма, error = проблема).
- НЕ хардкодь reason — берётся из event payload.
- НЕ оставляй спиннер висеть forever — таймаут 60 сек → "Timeout (no response)".

Связанные ADR: ADR-013, ADR-007; зависит от промпта 1 и MVP-PROMPTS C-1..C-6.
```

---

## 5. Бейдж PII score для user messages

```
Ты — Frontend-разработчик LLM Client. Добавь бейдж PII score (low/medium/high) для
каждого user message на основе metadata из ADR-014.

Контекст:
- ADR-014 (MVP-PROMPTS Блок D): PII score сохраняется в messages.metadata как
  {"pii_score": float, "pii_entities": list[str]}.
- Бэкенд отдаёт PII через SSE event: metadata, data: {"message_id", "pii_score",
  "pii_entities"} сразу после получения user message.
- Бейдж — для user message, не для assistant. ТРИЗ #3 (местное качество).

Задача:
1. Создай render_pii_badge(message_id: str, pii_score: float,
   pii_entities: list[str]) -> None в render.py.
   - <0.3 → зелёный "PII: low".
   - 0.3–0.7 → жёлтый "PII: medium".
   - ≥0.7 → красный "PII: high".
   - Tooltip: список pii_entities.
2. Интегрируй в render_messages: для msg с role="user" — после content рендерится
   бейдж. PII metadata хранится в session_state["messages"][i]["metadata"].
3. При SSE event: metadata — обнови session_state для message_id, re-render
   только бейджа (через fragment, см. промпт 9).
4. Пороги через env: PII_LOW_THRESHOLD (default 0.3), PII_HIGH_THRESHOLD (0.7).

Definition of Done:
- Ввод "My name is John Smith, SSN 123-45-6789" → "PII: high" (красный),
  tooltip ["PERSON", "US_SSN"].
- Ввод "Hello, how are you?" → "PII: low" (зелёный).
- Бейдж появляется <1 сек после отправки (после PIIDetector на бэкенде).
- Компактный, в углу st.chat_message, не мешает чтению.
- Tooltip показывает entities при наведении.

Антипаттерны:
- НЕ маскируй оригинал в UI — пользователь видит оригинал, маскирование только
  в operational логах (ADR-014).
- НЕ делай бейдж огромным — это метаданные.
- НЕ обновляй весь chat area при metadata event — только бейдж (через fragment).
- НЕ хардкодь пороги — через env.
- НЕ рендери PII для assistant messages.

Связанные ADR: ADR-014; зависит от промпта 1 и MVP-PROMPTS D-5.
```

---

## 6. `UIClient` interface (Python ABC)

```
Ты — Python-архитектор LLM Client. Создай ABC UIClient — abstraction над UI-бекендами,
изолирующий UI-код от Streamlit-specific API. Применение ТРИЗ #16 (частичное/
избыточное действие): interface полный, имплементация одна.

Контекст:
- ADR-002: Streamlit для MVP, миграция на Chainlit в Phase 5.
- TRIZ-ANALYSIS.md §5.1 (C-1): рекомендует UIClient с 4 методами.
- ROADMAP.md v1.1.0 §3.4, §5.7: UIClient в Phase 1 (не Phase 5).
- Без UIClient: весь UI-код под Streamlit API, миграция = переписывание.
- С UIClient: Phase 5 = добавление ChainlitClient, interface не меняется.

Задача:
1. Создай src/llm_client/ui/client.py с ABC UIClient:

   ```python
   from abc import ABC, abstractmethod
   from typing import Literal
   from llm_client.types import ArtifactRef

   MessageRole = Literal["user", "assistant", "system"]

   class UIClient(ABC):
       @abstractmethod
       def render_message(self, role: MessageRole, content: str,
                         metadata: dict | None = None) -> None: ...
       @abstractmethod
       def render_artifact(self, artifact: ArtifactRef) -> None: ...
       @abstractmethod
       def stream_token(self, token: str) -> None: ...
       @abstractmethod
       def handle_user_input(self) -> str | None: ...
   ```

2. Создай src/llm_client/types.py: MessageRole (Literal), ArtifactRef (Pydantic
   model с полями artifact_id, format: Literal["md","txt","pdf","docx","odt",
   "xls","xlsx"], filename, s3_key).
3. Docstrings: контракт, НЕ реализация. Backend-agnostic — НЕ Streamlit-specific.
4. Тесты src/llm_client/ui/test_client.py:
   - UIClient() raises TypeError (ABC).
   - Subclass с 4 методами — инстанцируется.
   - Subclass без 1 метода — TypeError.
   - ArtifactRef валидирует формат.
   - MessageRole rejects invalid values.

Definition of Done:
- `python -c "from llm_client.ui.client import UIClient; UIClient()"` raises
  TypeError.
- Все 4 метода — abstractmethod (IDE показывает unimplemented в подклассе).
- mypy --strict проходит на client.py, types.py.
- 5 unit-тестов зелёные.
- README в src/llm_client/ui/ описывает паттерн "UI code calls interface, not
  Streamlit API".

Антипаттерны:
- НЕ добавляй Streamlit-specific концепты (rerun() — нет в Chainlit). Только 4
  универсальных метода.
- НЕ делай god-object — 4 метода, не 20. Extension hooks (sidebar, status) —
  отдельные абстракции.
- НЕ используй typing.Protocol — нужен явный abstractmethod, не duck typing.
- НЕ добавляй async методы в Phase 1 — Streamlit sync. AsyncUIClient — отдельная
  абстракция в Phase 5 если понадобится.
- НЕ хардкодь Streamlit в docstrings — backend-agnostic.

Связанные ADR: частично резолвит C-1; применяет принцип #16 (ROADMAP.md §3.4);
подготовка к ADR-018 (Phase 5).
```

---

## 7. `StreamlitClient` — реализация

```
Ты — Python/Frontend-разработчик LLM Client. Создай StreamlitClient — реализацию
UIClient (из промпта 6) для Streamlit 1.40+. Все UI-вызовы из промптов 1-5 должны
ходить через StreamlitClient, не напрямую через st.* API.

Контекст:
- Промпт 6: UIClient ABC с 4 методами.
- Промпты 1-5: UI-код под Streamlit API напрямую — нужно отрефакторить.
- Streamlit 1.40+: st.chat_message, st.chat_input, st.write_stream,
  st.download_button, st.sidebar, st.status.

Задача:
1. Создай src/llm_client/ui/streamlit_client.py с классом StreamlitClient(UIClient):
   - render_message: st.chat_message(role) + st.markdown(content) + PII badge
     (из промпта 5) если metadata.pii_score есть.
   - render_artifact: вызывает render_artifact_buttons (промпт 3) для single
     artifact.
   - stream_token: внутренний buffer + flush через st.write_stream. Альтернатива
     — st.empty() placeholder + st.markdown(content + token). Выбери по perf
     (см. промпт 11).
   - handle_user_input: st.chat_input с уникальным key per session.
2. Stateful: внутреннее состояние (token buffer, placeholder) в st.session_state
   с префиксом "streamlit_client_..." для избежания коллизий.
3. Создай factory get_ui_client() -> UIClient в client.py:
   - Читает env UI_BACKEND (default "streamlit").
   - Возвращает StreamlitClient().
   - UI_BACKEND != "streamlit" → NotImplementedError("Backend {name} not
     implemented in Phase 1. Available: streamlit").

Definition of Done:
- `from llm_client.ui.client import get_ui_client; get_ui_client()` returns
  StreamlitClient.
- UI_BACKEND=chainlit → NotImplementedError с понятным сообщением.
- Все 4 метода реализованы, mypy --strict проходит.
- Все тесты промптов 1-5 проходят (regression).

Антипаттерны:
- НЕ делай StreamlitClient singleton — каждый запрос новый instance, state в
  session_state.
- НЕ хардкодь session_state keys — префикс "streamlit_client_...".
- НЕ используй st.experimental_* — deprecated в 1.40+.
- НЕ делай stream_token сложным — простая буферизация + flush(), иначе UX лаг.

Связанные ADR: реализует UIClient (промпт 6); применение ADR-002; подготовка к
UI-5 (Phase 5 ChainlitClient).
```

---

## 8. Миграция UI-кода на UIClient (refactor pass)

```
Ты — Frontend-разработчик LLM Client. Отрефактори UI-код из промптов 1-5, чтобы
все UI-вызовы ходили через UIClient (промпты 6-7), а не через st.* API напрямую.
Подготовка к Phase 5 — миграция на ChainlitClient = замена factory, не
переписывание UI-кода.

Контекст:
- Промпты 6-7: UIClient ABC + StreamlitClient + get_ui_client().
- Промпты 1-5: написаны ДО промптов 6-7, используют st.* напрямую.
- Sidebar (промпт 2) и status (промпт 4) — Streamlit-specific, остаются
  напрямую (нет аналогов в Chainlit). Документируй.
- TDD: тесты 1-5 не должны ломаться.

Задача:
1. В app.py замени прямые вызовы на client = get_ui_client(); client.*:
   - st.chat_message(role); st.markdown(content) → client.render_message(role,
     content, metadata).
   - st.chat_input(...) → client.handle_user_input().
   - for token in stream: st.write_stream(...) → client.stream_token(token).
   - st.download_button → client.render_artifact(artifact).
2. Sidebar (промпт 2): оставь st.sidebar напрямую + комментарий
   # Streamlit-specific, not in UIClient interface.
3. Status badge (промпт 4): оставь st.status/st.error/st.warning напрямую +
   тот же комментарий.
4. PII badge (промпт 5): теперь вызывается из StreamlitClient.render_message,
   не из app.py. Удали прямой вызов render_pii_badge из app.py.
5. Запусти все тесты промптов 1-5 — должны пройти без изменений.
6. Обнови README: "UI code calls interface, not Streamlit API" + пример.

Definition of Done:
- `grep -rE "st\.chat_message|st\.chat_input|st\.write_stream|st\.download_button"
  src/llm_client/ui/ | grep -v streamlit_client.py | grep -v "# Streamlit-specific"
  | wc -l` = 0.
- Все тесты промптов 1-5 проходят (regression).
- app.py уменьшился на ~30%.
- README описывает паттерн с примером кода.
- UI_BACKEND=chainlit → NotImplementedError с понятным сообщением.

Антипаттерны:
- НЕ рефактори sidebar и status в UIClient — Streamlit-specific, нарушение #16.
- НЕ ломай тесты 1-5 — refactor transparent для пользователя.
- НЕ добавляй новые фичи — только refactor.
- НЕ делай streamlit_client.py god-object — делегирует в существующие функции
  (render_artifact_buttons, render_pii_badge), не дублирует.

Связанные ADR: применение UIClient на практике; подготовка к UI-5 (Phase 5).
```

---

## 9. `@st.fragment` для chat stream

```
Ты — Frontend-разработчик LLM Client. Примени Streamlit 1.40+ @st.fragment к chat
area, чтобы пере-рендер происходил только при изменении потока токенов, а не при
событиях в sidebar.

Контекст:
- Streamlit 1.40+: @st.fragment изолирует re-run поведение.
- TRIZ-ANALYSIS.md §4.3 (строка 240): "Streamlit re-runs конфликтует с
  низколатентным streaming LLM. UI тратит время на пересборку, когда LLM уже отдал
  100 токенов."
- Без fragments: клик в sidebar прерывает стриминг, токены теряются.
- С fragments: chat area изолирован, sidebar re-run не влияет.

Задача:
1. В streamlit_client.py оберни chat area в @st.fragment:

   ```python
   @st.fragment
   def render_chat_fragment(self, session_id: str) -> None:
       messages = st.session_state[session_id]["messages"]
       for msg in messages:
           self.render_message(msg["role"], msg["content"], msg.get("metadata"))
   ```

2. Оберни стриминг в отдельный фрагмент:

   ```python
   @st.fragment
   def render_streaming_fragment(self, session_id: str, sse_iterator) -> None:
       with st.chat_message("assistant"):
           for token in sse_iterator:
               st.markdown(token, unsafe_allow_html=False)
   ```

3. Интегрируй в app.py: вместо одного st.write_stream — два fragment-вызова
  (chat history + streaming).
4. Критерий: переключение сессии в sidebar НЕ прерывает активный стриминг.

Definition of Done:
- Стриминг 1000 токенов, клик на другую сессию в середине — стриминг НЕ
  прерывается, токены продолжают приходить в активную сессию.
- Latency рендера одного токена <100 мс (SSE timestamp → DOM mutation).
- Hover по sidebar — chat area НЕ пере-рендерится (React DevTools: 0 commits).
- 100 сессий в sidebar + активный стриминг — CPU <50%.
- regression: тесты промптов 1-8 проходят.

Антипаттерны:
- НЕ оборачивай весь app.py в один @st.fragment — теряется смысл.
- НЕ используй st.experimental_fragment (deprecated) — только @st.fragment (1.40+).
- НЕ делай fragment для sidebar — он сам локален (st.sidebar).
- НЕ забывай передавать session_id в fragment — у fragment свой state.
- НЕ используй @st.fragment для PII badge — part of render_message, race
  condition.

Связанные ADR: частично резолвит C-1 (latency aspect); использует ADR-002, ADR-007;
зависит от промптов 1-8.
```

---

## 10. `@st.fragment` для sidebar history

```
Ты — Frontend-разработчик LLM Client. Примени Streamlit 1.40+ @st.fragment к
sidebar history list, чтобы пере-рендер происходил только при изменении списка
сессий, а не при каждом токене LLM-стрима.

Контекст:
- Без fragments: каждый токен в chat area → Streamlit re-run → sidebar
  пере-рендерится (50 сессий = заметная задержка).
- С fragments: sidebar изолирован, chat streaming не вызывает его re-render.
- Симметрично промпту 9.

Задача:
1. В sidebar.py (промпт 2) оберни render_sidebar в @st.fragment:

   ```python
   @st.fragment
   def render_sidebar_fragment(sessions_registry: dict) -> str | None:
       with st.sidebar:
           st.subheader("Sessions")
           if st.button("New session"):
               return None
           selected = st.selectbox(
               "Select session",
               options=list(sessions_registry.keys()),
               format_func=lambda sid: f"{sessions_registry[sid]['created_at']} —
                 {sessions_registry[sid]['first_prompt'][:30]}"
           )
           return selected
   ```

2. Интегрируй в app.py: render_sidebar_fragment вызывается ОДИН раз в начале
  rerun. Возвращает session_id или None (новая сессия).
3. sessions_registry обновляется только при: создании сессии (кнопка ➕),
  получении сообщения (last_activity), явном refresh (опционально 🔄 кнопка).

Definition of Done:
- Стриминг 1000 токенов — sidebar НЕ пере-рендерится на каждый токен (React
  DevTools: 0 commits в sidebar).
- Клик "New session" → sidebar пере-рендерится ОДИН раз.
- Новое сообщение в текущей сессии → last_activity обновляется, sidebar
  пере-рендерится ОДИН раз (если видна сортировка по last_activity) или 0 (по
  created_at).
- 50 сессий, переключение <200 мс (клик → обновление chat area).
- regression: тесты промптов 1-9 проходят.

Антипаттерны:
- НЕ обновляй sessions_registry в fragment без явного trigger — у fragment
  own state.
- НЕ делай sidebar fragment зависимым от chat fragment — независимы.
- НЕ используй @st.fragment(run_every=...) для sidebar — это для polling, не
  для reactive UI.

Связанные ADR: частично резолвит C-1 (sidebar aspect); использует ADR-002;
зависит от промптов 2, 9.
```

---

## 11. Latency-бенчмарк до/после fragments

```
Ты — QA/Frontend-разработчик LLM Client. Создай latency-бенчмарк для измерения
эффекта @st.fragment (промпты 9-10). Если прироста нет — fragments откатываются,
UI-3 списывается (BACKLOG.md §6.2).

Контекст:
- TRIZ-ANALYSIS.md §4.3: узкое место "Streamlit re-runs конфликтует со стримингом".
- Промпты 9-10: вводят fragments как решение. Без измерения — не доказать.
- Критерий отката UI-3 (BACKLOG.md §6.2): прирост FPS стриминга <30% → откат.
- Метрика идеальности (ROADMAP.md §15): Δф/Δсложности ≥ 1. Если fragments
  добавили сложность без выгоды — нарушение.

Задача:
1. Создай scripts/ui_latency_benchmark.py:
   - Запускает agent-service с mock LLM (1000 токенов, 50 мс между токенами).
   - Открывает Streamlit через Playwright (Chrome headless).
   - Сценарий: ввод промпта → ожидание стрима → в середине стрима клик по
     sidebar на другую сессию.
   - Измеряет: token_fps, token_fps_with_fragments, sidebar_rerender_count,
     chat_rerender_count.
2. Запуск в 2 режимах через env UI3_ENABLED:
   - false: fragments выключены (baseline).
   - true: fragments применены (промпты 9-10).
3. Сравнение: token_fps_with_fragments / token_fps ≥ 1.3 (прирост ≥30%) →
   Approved. <1.3 → Rejected, fragments удаляются.
4. Отчёт: JSON {baseline: {...}, with_fragments: {...}, ratio: ..., decision:
   "approved"|"rejected"} → scripts/ui_latency_report.json.
5. CI: nightly job запускает бенчмарк, метрика llm_client_ui_token_fps пушится
   в Prometheus.

Definition of Done:
- `python scripts/ui_latency_benchmark.py` запускается, отчёт сохраняется.
- UI3_ENABLED=true: token_fps_with_fragments / token_fps ≥ 1.3.
- sidebar_rerender_count = 0 во время стриминга.
- При ratio <1.3 — exit code 1, CI блокирует merge.
- README в src/llm_client/ui/ содержит ссылку на отчёт.
- Порог через env UI3_FPS_THRESHOLD (default 1.3).

Антипаттерны:
- НЕ измеряй "на глаз" — Playwright + DOM mutation observer, цифры.
- НЕ запускай на dev-машине — staging окружение.
- НЕ сравнивай разные браузеры — фиксируй Chrome headless.
- НЕ делай бенчмарк >2 мин — nightly CI.
- НЕ хардкодь пороги — через env.

Связанные ADR: тестирует UI-3 (BACKLOG.md §3.3); зависит от промптов 9-10;
решение по UI-3 — если fails, откат, ROADMAP.md §5.7 обновляется.
```

---

## 12. Карта промптов

| # | Промпт | Блок | Зависимости | Срок (чел-дн) |
|---|---|---|---|---|
| 1 | Streamlit chat scaffold | U0 | ADR-001, ADR-002, ADR-007 | 1.5 |
| 2 | Sidebar с историей сессий | U1 | 1 | 0.5 |
| 3 | Кнопки скачивания артефактов | U1 | 1, расш. ADR-008 | 0.5 |
| 4 | Индикатор статуса LLM-вызова | U1 | 1, ADR-013 | 0.25 |
| 5 | Бейдж PII score | U1 | 1, ADR-014 | 0.25 |
| 6 | `UIClient` interface (ABC) | U2 | — | 0.5 |
| 7 | `StreamlitClient` реализация | U2 | 6, 1-5 | 1.5 |
| 8 | Миграция UI-кода на UIClient | U2 | 6, 7 | 0.5 |
| 9 | `@st.fragment` для chat stream | U3 | 7 | 0.5 |
| 10 | `@st.fragment` для sidebar | U3 | 2, 9 | 0.25 |
| 11 | Latency-бенчмарк fragments | U3 | 9, 10 | 0.25 |
| **Итого** | **11 промптов** | | | **6.5 чел-дн** |

Параллелизация (2 разработчика, 3.25 календарных дней):
- Дев 1: 1 → 2 → 3 → 4 → 5 → 8 = 3.5 чел-дн
- Дев 2: 6 → 7 → 9 → 10 → 11 = 3.0 чел-дн
- Sync: 8 (после 7) — обе ветки готовы, refactor pass.

---

## 13. Чек-лист выхода из UI-части Phase 1

| # | Критерий | Где проверяется | Промпт |
|---|---|---|---|
| 1 | UI-0: docker-compose up ui поднимает Streamlit, чат стримит токены | manual test | 1 |
| 2 | UI-1: sidebar + downloads (4 формата) + status (streaming/cancelled/error) + PII badge | manual test | 2-5 |
| 3 | UI-2: UIClient ABC + StreamlitClient, grep st.chat_message\|st.chat_input\|st.write_stream вне streamlit_client.py = 0 | automated (DoD промпта 8) | 6-8 |
| 4 | UI-3: @st.fragment для chat и sidebar, бенчмарк ≥30% прироста | промпт 11 | 9-11 |
| 5 | Метрика идеальности не упала: Δф/Δсложности = 4/2 = 2 ≥ 1 (см. ROADMAP §15.2) | G-2 из MVP-PROMPTS | — |
| 6 | Документация обновлена: README в src/llm_client/ui/, ARCHITECT.md §7 ADR-002 — уточнение про UI-0 | manual check | 8, 11 |

При невыполнении п.1-3 — UI-часть Phase 1 продлевается на 1 sprint.
При невыполнении п.4 — UI-3 откатывается, метрика пересчитывается без него.
При невыполнении п.5-6 — документационный долг, блокирует старт Phase 2.

---

## 14. История изменений

| Версия | Дата | Изменение |
|---|---|---|
| 1.0.0 | 2026-09-23 | Initial draft (длинные промпты с U0-1..U3-3 нумерацией). |
| 1.1.0 | 2026-09-23 | Промпты сокращены до существенного (контекст + задача + DoD + антипаттерны + связи). Сквозная нумерация 1-11 вместо U0-1/U1-1..U1-4/U2-1..U2-3/U3-1..U3-3. |

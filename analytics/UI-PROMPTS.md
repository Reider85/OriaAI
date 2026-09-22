# UI-PROMPTS.md — Промпты для UI-составляющей Phase 0/1

| Атрибут | Значение |
|---|---|
| Версия документа | 1.0.0 |
| Дата | 2026-09-23 |
| Источники | `BACKLOG.md` v1.0.0 §3; `ROADMAP.md` v1.1.0 §5.2 (после патча), §5.7; `ARCHITECT.md` v1.1.0 §4.1, §5 (Presentation Layer), §7 ADR-002/ADR-007/ADR-008/ADR-013/ADR-014; `TRIZ-ANALYSIS.md` v1.0.0 §3.2 (ИКР-1), §4.3, §5.1 (C-1), §11 (драфт ADR-018) |
| Этап | Phase 0 (формализация) + Phase 1 (UI-1, UI-2, UI-3) |
| ADR в области | ADR-002 (не меняется), ADR-007 (не меняется), ADR-008 (использует), ADR-013 (использует), ADR-014 (использует) |
| Резолвит противоречия | C-1 (частично, через UI-2 + UI-3); C-4 (полностью, через UI-0+UI-1 — UI-часть ADR-013) |
| Целевой LLM | Универсальные (Cursor / Copilot / Claude Code / ChatGPT) |
| Гранулярность | Микро-промпты (1 промпт = 1 файл / 1 класс / 1 подзадача) |
| Связанный backlog | `BACKLOG.md` v1.0.0 §3 |

---

## 0. Как пользоваться документом

Каждый промпт — самостоятельный блок, огороженный ` ``` `-код-блоком, готовый к копи-пасту в любой код-ассистент. Промпты сгруппированы в четыре блока **U0–U3**, идущих в порядке зависимостей:

```
U0. Scaffold ──→ U1. Base elements ──→ U2. UIClient abstraction ──→ U3. Streamlit fragments
                                          │
                                          └──→ (готовит почву для Phase 5 UI-4/UI-5/UI-6)
```

**Конвенции** (унаследованы от `MVP-PROMPTS.md`):

- Имена классов, методов, эндпоинтов — на английском (как в `ARCHITECT.md`).
- Имена ADR и противоречий — в формате `ADR-013`, `C-4` (как в `TRIZ-ANALYSIS.md` §10).
- Раздел `Definition of Done` — конкретные измеримые критерии готовности.
- Раздел `Антипаттерны` — что LLM НЕ должен делать; если предложит — отбраковывать.
- Раздел `Связанные ADR` — какие ADR затрагивает (не ломает / упраздняет / требует).

Полный прогон блоков U0→U3 занимает 6.5 чел-дн (см. `BACKLOG.md` §3.2). Критерии выхода UI-части Phase 1 — в `BACKLOG.md` §5.1.

**Принцип ТРИЗ #16 (частичное/избыточное действие)**: UI-2 вводит `UIClient` interface «избыточно» (полный, 4 метода), но имплементирует «частично» (только `StreamlitClient`). Это сознательное решение — когда в Phase 5 появится `ChainlitClient` (UI-5 из `BACKLOG.md`), добавится имплементация, interface не меняется. См. `ROADMAP.md` v1.1.0 §3.4.

---

## 1. Блок U0. Streamlit chat scaffold

**Источник**: `BACKLOG.md` §3.3 (UI-0). Формализует «Phase 0», упомянутый в `TRIZ-ANALYSIS.md` §3 (строка 99) как «Streamlit + LangGraph как ускорители → time-to-MVP ≤ 15 чел-дн», но не имеющий формального статуса в `ROADMAP.md` v1.0.0. Патч `ROADMAP.md` v1.1.0 §5.2 вводит UI-0 в Phase 1 как предпосылку для всех остальных ADR (cancel, PII, file artifacts — все требуют наличия UI).

### U0-1. Файл `app.py` — точка входа Streamlit-приложения

```
Ты — Frontend-разработчик LLM Client. Создай минимальный scaffold Streamlit-приложения
для LLM Client: чат с agent-service через SSE (ADR-007), без UI-украшательств (sidebar,
downloads, status — в U1). Этот промпт формализует "Phase 0" — подразумеваемое ADR-002
состояние "Streamlit-приложение уже есть".

Контекст:
- ADR-002 (ARCHITECT.md §7) фиксирует Streamlit 1.40+ как UI для MVP/Alpha, с миграцией
  на Chainlit/FastAPI в Phase 5.
- ADR-007 (ARCHITECT.md §7) фиксирует SSE для streaming LLM-ответов (one-way). В Streamlit
  streaming работает через st.write_stream.
- ADR-001 (ARCHITECT.md §7) фиксирует LangGraph как оркестратор. Agent-service уже
  существует (подразумевается существующим до этого промпта) и предоставляет SSE endpoint
  POST /sessions/{session_id}/chat для запуска графа и GET /sessions/{session_id}/stream
  для получения токенов.
- MVP-PROMPTS.md §3 C-5 (UI watcher) — инжектит JS в это приложение; НЕ МОЖЕТ быть
  выполнен без U0-1.
- MVP-PROMPTS.md §3 C-2 (cancel endpoint) — endpoint на бэкенде, UI вызывает его; без
  UI-кнопки (U1) он вызывается только auto-cancel-ом.

Задача:
1. Создай файл app.py в корне репозитория (или src/llm_client/ui/app.py — по существующей
   структуре).
2. Минимальная функциональность:
   - st.set_page_config(page_title="LLM Client", layout="wide").
   - Заголовок "LLM Client" через st.title.
   - st.chat_input для ввода промпта пользователя.
   - При отправке промпта:
     * Если session_id нет в st.session_state — генерируется UUID4, сохраняется.
     * POST на AGENT_SERVICE_URL/sessions/{session_id}/chat с body {"message": prompt}.
     * Открывает SSE-соединение на AGENT_SERVICE_URL/sessions/{session_id}/stream.
     * Через st.write_stream рендерит входящие токены в st.chat_message("assistant").
   - История сообщений хранится в st.session_state["messages"]: list[dict], каждая запись
     {"role": "user"|"assistant", "content": str, "timestamp": ISO-8601}.
   - При ререндере (Streamlit re-run) история восстанавливается из session_state, не
     перезагружается с бэкенда (упрощение для Phase 0; синхронизация с бэкендом — в UI-4
     Phase 5).
3. Конфигурация через env: AGENT_SERVICE_URL (default http://localhost:8000), APP_PORT
  (default 8501).
4. Запуск: streamlit run app.py --server.port=$APP_PORT.
5. В README.md добавь секцию "Local dev UI": как поднять (docker-compose up ui), на каком
  порту, какой backend URL по умолчанию.

Definition of Done:
- `streamlit run app.py` поднимает приложение за <3 сек, открывается http://localhost:8501.
- Ввод "hello" в chat_input → POST к agent-service → SSE-стрим → токены отображаются в
  st.chat_message("assistant") в реальном времени (визуально <500 мс от нажатия Enter до
  первого токена на типовом LLM с latency p50 ~200 мс).
- При перезагрузке страницы (F5) история сохраняется, если session_id в URL
  (?session_id=...) — восстанавливается из session_state.
- При ошибке backend (AGENT_SERVICE_URL недоступен) — st.error с понятным сообщением,
  НЕ падение приложения.
- В console Streamlit нет warnings про session_state serialization.

Антипаттерны:
- НЕ хардкодь backend URL — только через env AGENT_SERVICE_URL.
- НЕ пиши весь код в app.py >300 строк — выдели chat.py (функции чата), session.py
  (session_id управление), render.py (рендер истории). app.py — только wiring.
- НЕ используй st.experimental_* — deprecated в 1.40+, используй стабильные API.
- НЕ вызывай LLM напрямую из app.py (openai.ChatCompletion.create) — только через
  agent-service SSE endpoint. UI НЕ знает про LLM-провайдеров.
- НЕ сохраняй историю в файл или БД из UI — только в session_state. Persistence
  сессий — ответственность бэкенда (ADR-005 PostgreSQL); UI только кэширует.
- НЕ используй st.cache_data для messages — это stateful, не cached computation.
- НЕ добавляй sidebar, downloads, status indicators в этом промпте — это U1.

Связанные ADR:
- Реализует часть: ADR-002 (Streamlit как UI), ADR-007 (SSE для streaming).
- Требует: ADR-001 (LangGraph) — существующий agent-service.
- Не затрагивает: ADR-013 (cancel — в C-5/MVP-PROMPTS, требует этого UI), ADR-014 (PII —
  в D-5/MVP-PROMPTS, отображается в U1).
- Блокирует: U1 (нет scaffold — нет куда добавлять sidebar/downloads/status), C-5
  (MVP-PROMPTS — некуда инжектить JS watcher).
```

---

## 2. Блок U1. Base UI elements

**Источник**: `BACKLOG.md` §3.3 (UI-1). В `ARCHITECT.md` v1.1.0 §4.1 (строка 172) прямо заявлено: «Чат UI, история сессий, кнопки скачивания» — но без промптов. U1 закрывает этот пробел. Зависит от U0 (scaffold должен существовать).

### U1-1. Sidebar с историей сессий

```
Ты — Frontend-разработчик LLM Client. Добавь sidebar в Streamlit-приложение из U0: список
сессий пользователя, кнопка "New session", переключение между сессиями.

Контекст:
- U0 создал scaffold с session_id в st.session_state и историей messages в session_state.
- В Phase 1 (до UI-4 Phase 5) нет RedisSessionStore — список сессий берётся из
  in-memory dict (просто dict[str, list[dict]] в session_state, ключ — session_id).
- При переключении сессии — загружается её messages-история в основной chat area.
- "New session" — генерирует новый UUID4, очищает chat area, оставляет sidebar список.
- В Phase 5 (UI-4) in-memory dict заменяется на RedisSessionStore без изменения UI
  (контракт list_sessions / load_session — тот же).

Задача:
1. Создай файл src/llm_client/ui/sidebar.py с функцией render_sidebar() -> str | None:
   - Возвращает session_id выбранной сессии, либо None если пользователь нажал "New
     session".
   - Использует st.sidebar с заголовком "Sessions".
   - Кнопка st.button("➕ New session") — генерирует новый UUID4, возвращает None.
   - st.selectbox или st.radio со списком сессий из get_sessions_list(). Каждая опция —
     timestamp первой message + первые 30 символов первого user prompt (для узнавания).
   - При выборе — возвращает session_id, основная функция перерисовывает chat area с
     историей выбранной сессии.
2. get_sessions_list() — функция в session.py (если в U0 не создана, создай):
   - Возвращает list[dict] сессий: [{"session_id", "first_prompt", "created_at",
     "last_activity"}].
   - Источник: st.session_state["sessions_registry"] (dict[session_id, dict]).
   - При первом запуске (sessions_registry нет в session_state) — инициализируется
     пустым dict.
3. Интегрируй в app.py: перед chat_input — render_sidebar(), результат используется для
   переключения session_state["current_session_id"].
4. Переключение сессии: st.session_state["messages"] заменяется на историю выбранной
   сессии (из sessions_registry). Если истории нет (новая сессия) — пустой list.

Definition of Done:
- Sidebar виден слева, заголовок "Sessions", кнопка "➕ New session", список сессий.
- Создание новой сессии: кнопка нажимается → chat area очищается → новая сессия
  появляется в списке.
- Переключение: выбор существующей сессии из списка → chat area отображает её историю.
- При перезагрузке страницы (F5) с ?session_id=X — эта сессия автоматически выбрана в
  sidebar, её история отображается.
- 50 сессий в списке — sidebar остаётся прокручиваемым, не тормозит.
- При первом открытии (новый браузер, без session_id в URL) — автоматически создаётся
  новая сессия.

Антипаттерны:
- НЕ хардкодь иконки через unicode-эмодзи если в кодовой базе нет других эмодзи (используй
  текст "New session" без иконки — не нарушай консистентность).
- НЕ загружай ВСЕ сообщения ВСЕХ сессий в session_state — только текущей. Сессии в
  sessions_registry хранят только метаданные, messages загружаются по требованию.
- НЕ используй st.cache_data для sessions_registry — это stateful, не cached.
- НЕ делай sidebar отдельным Streamlit-приложением — это часть app.py, изолирована в
  sidebar.py только как функция.
- НЕ используй st.multiselect для переключения сессий — это для выбора нескольких,
  не одной. st.selectbox или st.radio.

Связанные ADR:
- Реализует часть: ADR-002 (UI responsibilities из ARCHITECT.md §4.1: "история сессий").
- Зависит от: U0 (scaffold).
- Не затрагивает: ADR-005 (PostgreSQL для messages persistence — это бэкенд, не UI).
- Подготовка к: UI-4 (Phase 5, BACKLOG.md §3.3) — in-memory dict будет заменён на
  RedisSessionStore без изменения UI.
```

### U1-2. Кнопки скачивания артефактов (md / txt / pdf / docx)

```
Ты — Frontend-разработчик LLM Client. Добавь кнопки скачивания для file_export артефактов
из ADR-008 (FileStorage) в Streamlit-приложение.

Контекст:
- ADR-008 (расш. в Phase 1, MVP-PROMPTS Блок E) сохраняет файлы в S3CompatibleStorage
  (MinIO в dev, S3 в prod). Файлы — артефакты LLM: ответы в форматах md, txt, pdf, docx,
  odt, xls/xlsx (см. ARCHITECT.md §1).
- Когда LLM через tool calling вызывает file_export, в SSE-стриме приходит специальное
  событие artifact_ready: {"artifact_id", "format", "filename", "s3_key"}.
- UI должен отрендерить st.download_button с соответствующим MIME-типом и контентом.
- В Phase 1 файлы доступны через GET /artifacts/{artifact_id} (presigned URL или proxy).
- В Phase 5 (расш. ADR-008 async rendering, ROADMAP.md §9.5) появится разделение
  fast/slow paths — preview отдаётся мгновенно, full file — по готовности. UI должен
  это поддерживать.

Задача:
1. Создай функцию render_artifact_buttons(artifacts: list[dict]) -> None в render.py.
   - Принимает список артефактов из SSE-стрима (может быть несколько в одном ответе).
   - Для каждого артефакта:
     * Если format в {"md", "txt"} — st.download_button с MIME "text/markdown" или
       "text/plain", контент тянется синхронно из GET /artifacts/{artifact_id}
       (быстро, fast path).
     * Если format в {"pdf", "docx", "odt", "xls", "xlsx"} — st.download_button с
       соответствующим MIME, контент тянется через GET /artifacts/{artifact_id}?format=full
       (медленно, slow path, 2–10 сек). Пока файл генерируется — кнопка disabled с
       спиннером "Generating...".
2. Интегрируй в цикл рендера сообщений (в app.py, где обрабатывается st.write_stream):
   - При получении artifact_ready-события — добавь запись в
     st.session_state["pending_artifacts"].
   - После завершения стрима — отрендери все pending_artifacts через
     render_artifact_buttons.
3. Обработка ошибок:
   - GET /artifacts/{id} возвращает 404 — st.warning("Artifact not found").
   - GET возвращает 503 — st.warning("Artifact still generating"), кнопка
     остаётся disabled с предложением retry через st.button("Retry").
4. В UI показывай только форматы, которые пользователь явно запросил через LLM
   (artifact_ready приходит только если LLM вызвал file_export).

Definition of Done:
- При ответе LLM "Сохраните это как markdown" → появляется кнопка "Download
  markdown", клик сохраняет файл .md локально.
- При запросе PDF → кнопка "Download PDF" появляется с disabled+спиннер, через 2–10
  сек становится активной, клик сохраняет .pdf.
- 4 формата (md, txt, pdf, docx) — покрыты end-to-end (manual test).
- При 404 — st.warning, не падение приложения.
- При 503 (генерация) — кнопка остаётся видимой, не исчезает.

Антипаттерны:
- НЕ хардкодь presigned URL — UI получает только artifact_id, URL строит бэкенд через
  GET /artifacts/{id}.
- НЕ делай все форматы одним st.download_button с selectbox — каждый формат своя
  кнопка, UX яснее.
- НЕ блокируй UI на slow path (PDF/DOCX) — используй placeholder с спиннером, не
  st.spinner() блокирующий весь rerun.
- НЕ сохраняй файл локально на диск UI-сервера — только проксируем download из
  file-storage.
- НЕ используй st.file_uploader — это для upload, не для download.

Связанные ADR:
- Использует: расш. ADR-008 (S3CompatibleStorage) — file_export tool сохраняет в S3,
  UI тянет через GET /artifacts/{id}.
- Зависит от: U0 (scaffold), ADR-001 (LangGraph — file_export это tool).
- Подготовка к: расш. ADR-008 в Phase 5 (async rendering, ROADMAP.md §9.5) — UI
  уже поддерживает fast/slow paths через disabled+spinner pattern.
```

### U1-3. Индикатор статуса LLM-вызова (streaming / cancelled / error)

```
Ты — Frontend-разработчик LLM Client. Добавь индикатор статуса LLM-вызова в Streamlit
UI: три состояния (streaming, cancelled, error) с визуальным различением.

Контекст:
- ADR-013 (MVP-PROMPTS Блок C) реализует cancel через Redis pub/sub. UI получает сигнал
  об отмене через SSE (server-side закрытие потока с event: cancelled, data:
  {"reason": "..."}).
- ADR-014 (MVP-PROMPTS Блок D) реализует dual-stream logging. PII score приходит в
  SSE metadata event для каждого user message.
- Без явного индикатора пользователь не понимает: идёт стриминг, отменилось, упала
  ошибка. Текущий Scaffold U0 только стримит токены без статуса.
- ТРИЗ-принцип 23 (обратная связь): пользователь должен видеть состояние системы в
  реальном времени.

Задача:
1. Создай функцию render_status_badge(status: str, detail: str | None = None) -> None
   в render.py.
   - status="streaming": st.status с спиннером и текстом "Generating response...".
     Оставляется открытой до получения event: done или event: cancelled.
   - status="cancelled": st.error с бейджем "Cancelled" (красный) и detail как
     reason из ADR-013 (user_cancelled, tab_closed, timeout, system_error). Под
     бейджем — partial answer (последние токены до отмены).
   - status="error": st.warning с бейджем "Error" (жёлтый) и detail как message из
     исключения. Под бейджем — стектрейс в expander для debugging (collaped по
     умолчанию).
2. Интегрируй в app.py в цикл st.write_stream:
   - Перед st.write_stream — render_status_badge("streaming").
   - При получении event: cancelled — закрыть статус, render_status_badge("cancelled",
     reason).
   - При получении event: error — render_status_badge("error", message).
   - При нормальном завершении (event: done) — статус закрывается без бейджа.
3. SSE event parsing (в chat.py, функция stream_response):
   - SSE-стрим парсится построчно: data: {...} — JSON-пayload; event: ... — тип
     события.
   - Поддерживаемые events: token (по умолчанию), done, cancelled, error,
     artifact_ready (см. U1-2), metadata (PII score, см. U1-4).
   - Если event не распознан — лог в console.debug, игнор.

Definition of Done:
- При отправке промпта — появляется спиннер "Generating response...".
- При стриминге токенов — спиннер продолжает крутиться.
- При отмене (через кнопку Stop из MVP-PROMPTS C-5) — спиннер заменяется красным
  бейджем "Cancelled: user_cancelled" в течение <200 мс.
- При ошибке backend — жёлтый бейдж "Error: <message>" + expander со стектрейсом.
- При нормальном завершении — спиннер исчезает без бейджа.
- 3 состояния тестируются manual: streaming (нормальный запрос), cancelled (Stop
  кнопка), error (выключить agent-service во время запроса).

Антипаттерны:
- НЕ используй st.spinner() — он блокирует rerun, используй st.status (1.40+) или
  собственный placeholder.
- НЕ показывай полный стектрейс без expander — засоряет UI. Collapsed expander с
  заголовком "Technical details".
- НЕ смешивай cancelled и error в один бейдж — это разные состояния с разным UX
  (cancel — нормальное действие пользователя, error — проблема системы).
- НЕ хардкодь причины cancel — берётся из event payload, поддерживает все 4 reason
  из ADR-013.
- НЕ оставляй спиннер висеть forever — таймаут 60 сек, после чего статус заменяется
  на "Timeout (no response from agent)".

Связанные ADR:
- Использует: ADR-013 (cancel event), ADR-007 (SSE event protocol).
- Зависит от: U0 (scaffold), MVP-PROMPTS C-1..C-6 (cancel machinery на бэкенде).
- Не затрагивает: ADR-014 (PII — отдельный бейдж в U1-4).
```

### U1-4. Бейдж PII score для user messages

```
Ты — Frontend-разработчик LLM Client. Добавь бейдж PII score для каждого user message
в Streamlit UI: визуальная индикация уровня PII (low / medium / high) на основе
metadata из ADR-014.

Контекст:
- ADR-014 (MVP-PROMPTS Блок D) реализует DualStreamLogger. PII score сохраняется в
  messages.metadata как {"pii_score": float, "pii_entities": list[str]}.
- Бэкенд возвращает PII metadata через SSE event: metadata, data: {"message_id",
  "pii_score", "pii_entities"} сразу после получения user message.
- UI должен показать бейдж рядом с user message, чтобы пользователь понимал, какие
  данные он ввёл (и какие могут быть маскированы в operational логах).
- ТРИЗ-принцип 3 (местное качество): PII score — местная характеристика сообщения,
  не глобальная.

Задача:
1. Создай функцию render_pii_badge(message_id: str, pii_score: float,
   pii_entities: list[str]) -> None в render.py.
   - Если pii_score < 0.3 — зелёный бейдж "PII: low".
   - Если 0.3 ≤ pii_score < 0.7 — жёлтый бейдж "PII: medium".
   - Если pii_score ≥ 0.7 — красный бейдж "PII: high".
   - Tooltip (st.tooltip или native HTML title) показывает список pii_entities.
2. Интегрируй в render_messages (функция рендера истории):
   - Для каждого message с role="user" — после рендера content рендерится бейдж.
   - PII metadata хранится в session_state["messages"][i]["metadata"]["pii_score"]
     и ["pii_entities"].
3. При получении SSE event: metadata — обновляется session_state для соответствующего
   message_id, триггерится re-render только бейджа (через @st.fragment — см. U3).
4. Если PII metadata ещё не пришло (LLM-ответ в процессе) — бейдж не рендерится
   (placeholder не нужен, PII считается для user message, не для assistant).

Definition of Done:
- Ввод "My name is John Smith, SSN 123-45-6789" → бейдж "PII: high" (красный),
  tooltip показывает ["PERSON", "US_SSN"].
- Ввод "Hello, how are you?" → бейдж "PII: low" (зелёный).
- Бейдж появляется в течение <1 сек после отправки сообщения (после обработки
  PIIDetector-ом на бэкенде).
- Бейдж не мешает чтению сообщения — компактный, в углу st.chat_message.
- При наведении мыши — tooltip с entities.

Антипаттерны:
- НЕ показывай маскированный текст вместо оригинала в UI — пользователь видит
  оригинал, маскирование только в operational логах (ADR-014).
- НЕ делай бейдж огромным — это метаданные, не главный контент.
- НЕ обновляй весь chat area при получении PII metadata — только бейдж (через
  fragment, см. U3).
- НЕ хардкодь пороги 0.3 и 0.7 — вынеси в env PII_LOW_THRESHOLD, PII_HIGH_THRESHOLD
  с дефолтами.
- НЕ отображай PII score для assistant messages — PII детектируется только в user
  input.

Связанные ADR:
- Использует: ADR-014 (PII score в messages.metadata).
- Зависит от: U0 (scaffold), MVP-PROMPTS D-5 (PII score в DB).
- Не затрагивает: ADR-013 (cancel — отдельный индикатор в U1-3).
```

---

## 3. Блок U2. `UIClient` abstraction

**Источник**: `BACKLOG.md` §3.3 (UI-2). `TRIZ-ANALYSIS.md` §5.1 (строка 339) рекомендует `UIClient` с реализациями `StreamlitClient`/`ChainlitClient`/`FastAPIClient`. `ROADMAP.md` v1.0.0 §3.4 (строка 171) упоминает применение принципа #16 к `UIClient`, но фаза не указана — неявно Phase 5 (с ADR-018). Патч `ROADMAP.md` v1.1.0 §5.7 выносит в Phase 1.

### U2-1. `UIClient` interface (Python ABC)

```
Ты — Python-архитектор LLM Client. Создай абстракцию UIClient — interface для UI-бекендов,
изолирующий UI-код от Streamlit-specific API. Применяется принцип ТРИЗ #16 (частичное/
избыточное действие): interface полный, имплементация одна (StreamlitClient), вторая
(ChainlitClient) добавится в Phase 5 без изменения interface.

Контекст:
- ADR-002 (ARCHITECT.md §7) фиксирует Streamlit для MVP/Alpha, миграцию на Chainlit в
  Phase 5.
- TRIZ-ANALYSIS.md §5.1 (C-1) рекомендует abstraction UIClient с 4 методами: render_message,
  render_artifact, stream_token, handle_user_input. Реализации: StreamlitClient (MVP),
  ChainlitClient (Phase 5), FastAPIClient (Phase 5+).
- ROADMAP.md §3.4 (принцип #16): "внедрять абстракцию избыточно (полный interface), но
  имплементировать частично (одна реализация). Когда появится вторая реализация —
  interface уже готов."
- В Phase 1 UIClient имеет 1 реализацию (StreamlitClient). В Phase 5 добавится
  ChainlitClient — interface НЕ меняется. В Phase 5+ — FastAPIClient.
- Без UIClient: весь UI-код (U0, U1, C-5 из MVP-PROMPTS) пишет под Streamlit API
  (st.chat_message, st.chat_input, st.write_stream). Миграция в Phase 5 = переписывание.
- С UIClient: весь UI-код пишет против interface. Phase 5 = добавление новой
  имплементации.

Задача:
1. Создай файл src/llm_client/ui/client.py с ABC UIClient:
   ```python
   from abc import ABC, abstractmethod
   from typing import Literal, Iterator
   from llm_client.types import ArtifactRef, MessageRole

   class UIClient(ABC):
       """Abstraction over UI backend (Streamlit / Chainlit / FastAPI).
       UI code calls these 4 methods; concrete implementations translate to
       backend-specific API."""

       @abstractmethod
       def render_message(self, role: MessageRole, content: str,
                         metadata: dict | None = None) -> None:
           """Render a complete message in chat history."""

       @abstractmethod
       def render_artifact(self, artifact: ArtifactRef) -> None:
           """Render an artifact (file download button, preview, etc.)."""

       @abstractmethod
       def stream_token(self, token: str) -> None:
           """Append a streaming token to current assistant message.
           Called multiple times during LLM streaming."""

       @abstractmethod
       def handle_user_input(self) -> str | None:
           """Block until user submits input; return prompt string or None
           if session ended."""
   ```
2. Создай type aliases в src/llm_client/types.py:
   - MessageRole = Literal["user", "assistant", "system"]
   - ArtifactRef — Pydantic model: {"artifact_id": str, "format":
     Literal["md","txt","pdf","docx","odt","xls","xlsx"], "filename": str, "s3_key": str}
3. Документация в docstrings:
   - Каждый метод — описание контракта, НЕ реализации.
   - Указать, что методы вызываются UI-кодом (app.py), реализуются конкретным
     UIClient-ом (StreamlitClient в Phase 1).
   - Подчеркнуть: НЕ Streamlit-specific, НЕ Chainlit-specific — interface.
4. Покрытие тестами: src/llm_client/ui/test_client.py — tests на:
   - Interface defined, 4 abstract methods.
   - Cannot instantiate UIClient directly (TypeError).
   - Concrete subclass with all 4 methods — instantiable.

Definition of Done:
- `python -c "from llm_client.ui.client import UIClient; UIClient()"` raises TypeError
  (ABC cannot be instantiated).
- Все 4 метода — abstractmethod, IDE (PyCharm/VSCode) показывает их как unimplemented
  в новом подклассе.
- Type hints полные, mypy --strict проходит без ошибок.
- 5 unit-тестов проходят: instantiation fails, subclass with all methods works,
  subclass missing 1 method fails, ArtifactRef validates correctly, MessageRole
  rejects invalid values.
- README.md в src/llm_client/ui/ описывает UIClient и паттерн "UI code calls
  interface, not Streamlit API".

Антипаттерны:
- НЕ добавляй Streamlit-specific концепции в interface (например, rerun() — этого
  нет в Chainlit/FastAPI). Только 4 универсальных метода.
- НЕ делай UIClient god-object с 20 методами — 4 базовых достаточно. Extension hooks
  (например, render_status_badge) — отдельная абстракция, не в этом interface.
- НЕ используй typing.Protocol вместо ABC — нужен явный abstractmethod enforcement,
  не duck typing.
- НЕ добавляй async методы в Phase 1 — Streamlit sync, Chainlit async. Если async
  понадобится в Phase 5 — добавится отдельный AsyncUIClient (не ломает существующий).
- НЕ хардкодь Streamlit в docstrings — interface должен быть backend-agnostic.

Связанные ADR:
- Частично резолвит: C-1 (Streamlit vs horizontal scale) — interface позволяет
  менять backend без переписывания UI-кода.
- Подготовка к: ADR-018 (Phase 5, ROADMAP.md §9.3) — SessionStore sync с UI
  использует UIClient, а не Streamlit session_state напрямую.
- Применяет: принцип ТРИЗ #16 (ROADMAP.md §3.4).
- Не затрагивает: ADR-002 (не меняет, добавляет abstraction над ним).
- Не ломает: ADR-007 (SSE — транспорт, не UI).
```

### U2-2. `StreamlitClient` — единственная реализация в Phase 1

```
Ты — Python/Frontend-разработчик LLM Client. Создай StreamlitClient — конкретную
реализацию UIClient interface (из U2-1) для Streamlit 1.40+. Все UI-вызовы из U0 и U1
должны ходить через StreamlitClient, а не напрямую через st.* API.

Контекст:
- U2-1 создал UIClient ABC с 4 методами.
- U0 (app.py) и U1 (sidebar, downloads, status, PII badge) используют Streamlit API
  напрямую — нужно отрефакторить на UIClient interface.
- StreamlitClient — единственная реализация в Phase 1. В Phase 5 добавится
  ChainlitClient (UI-5 из BACKLOG.md), interface не меняется.
- Streamlit 1.40+ API: st.chat_message, st.chat_input, st.write_stream,
  st.download_button, st.sidebar, st.status, st.error, st.warning.

Задача:
1. Создай файл src/llm_client/ui/streamlit_client.py с классом StreamlitClient(UIClient):
   ```python
   import streamlit as st
   from llm_client.ui.client import UIClient
   from llm_client.types import ArtifactRef, MessageRole

   class StreamlitClient(UIClient):
       def render_message(self, role: MessageRole, content: str,
                         metadata: dict | None = None) -> None:
           with st.chat_message(role):
               st.markdown(content)
               if metadata and metadata.get("pii_score") is not None:
                   # PII badge rendering (U1-4) here or delegated
                   pass

       def render_artifact(self, artifact: ArtifactRef) -> None:
           # U1-2 logic: st.download_button with format-specific MIME
           pass

       def stream_token(self, token: str) -> None:
           # Use st.write_stream; this method is called token-by-token,
           # so wrap into a generator or use streamlit's incremental API
           pass

       def handle_user_input(self) -> str | None:
           return st.chat_input("Ask LLM Client...")
   ```
2. Реализуй все 4 метода (заглушки выше — раскрой):
   - render_message: st.chat_message(role) + st.markdown(content) + PII badge если
     metadata.pii_score есть (вызывает render_pii_badge из U1-4).
   - render_artifact: вызывает render_artifact_buttons из U1-2 для одного артефакта
     (создай overload для single-artifact case).
   - stream_token: использует внутренний buffer + st.write_stream pattern. Один из
     вариантов: StreamlitClient хранит _token_buffer: list[str], stream_token
     добавляет в buffer, отдельный метод flush() рендерит через st.write_stream.
     Альтернатива: использовать st.empty() placeholder и st.markdown(content +
     token) инкрементально. Выбери по производительности (см. U3 — fragments).
   - handle_user_input: st.chat_input(placeholder, key=...) с уникальным key per
     session.
3. Реализация stateful: StreamlitClient может хранить внутреннее состояние
   (token buffer, current message placeholder) в st.session_state для корректной
   работы при Streamlit re-runs.
4. Создай factory get_ui_client() -> UIClient в client.py:
   - Читает env UI_BACKEND (default "streamlit").
   - Возвращает StreamlitClient() — единственная имплементация в Phase 1.
   - Если UI_BACKEND != "streamlit" — raises NotImplementedError("Backend {UI_BACKEND}
     not implemented in Phase 1. Available: streamlit").
   - В Phase 5 factory расширится до "chainlit" и "fastapi".

Definition of Done:
- `from llm_client.ui.client import get_ui_client; client = get_ui_client()` returns
  StreamlitClient instance.
- U0 (app.py) отрефакторен: все st.chat_message/st.chat_input/st.write_stream
  заменены на client.render_message/handle_user_input/stream_token.
- U1-1 (sidebar): всё ещё использует st.sidebar напрямую (sidebar не в UIClient
  interface — это Streamlit-specific). Документируй это исключение в README.
- U1-2 (downloads): client.render_artifact() используется, прямые st.download_button
  убраны из app.py.
- U1-3 (status): использует st.status/st.error/st.warning напрямую (status не в
  UIClient interface). Документируй исключение.
- U1-4 (PII badge): вызывается из StreamlitClient.render_message (внутри), НЕ из
  app.py напрямую.
- `grep -r "st\.chat_message\|st\.chat_input\|st\.write_stream" src/llm_client/ui/ |
  grep -v streamlit_client.py | wc -l` = 0 (весь UI-контент через StreamlitClient).
- Все тесты U0/U1 проходят после рефакторинга (regression test).
- mypy --strict проходит на streamlit_client.py.

Антипаттерны:
- НЕ перемещай sidebar и status в UIClient — они не имеют аналогов в Chainlit
  напрямую, лучше оставить как Streamlit-specific extensions. Документируй явно
  в README "Streamlit-specific UI code (not in UIClient): sidebar, status badges".
- НЕ делай StreamlitClient singleton — каждый запрос создаёт новый instance, state
  в session_state, не в самом объекте.
- НЕ хардкодь session_state keys — используй префикс "streamlit_client_..." для
  избежания коллизий.
- НЕ используй st.experimental_* — deprecated в 1.40+.
- НЕ делай stream_token слишком сложным — простая буферизация + flush(), иначе
  ломается UX (визуальная задержка стриминга).

Связанные ADR:
- Реализует: UIClient ABC из U2-1.
- Применяет: ADR-002 (Streamlit как UI для MVP) — конкретная имплементация.
- Не затрагивает: ADR-007 (SSE — транспорт ниже interface).
- Подготовка к: UI-5 (Phase 5, BACKLOG.md §3.3) — ChainlitClient будет sibling
  реализацией, interface не меняется.
```

### U2-3. Миграция U0/U1 на UIClient (refactor pass)

```
Ты — Frontend-разработчик LLM Client. Отрефактори UI-код из U0 (app.py scaffold) и U1
(sidebar, downloads, status, PII badge), чтобы все UI-вызовы ходили через UIClient
interface (U2-1/U2-2), а не напрямую через st.* API. Это подготовка к Phase 5 — когда
появится ChainlitClient, миграция на него = замена factory в get_ui_client(), а не
переписывание UI-кода.

Контекст:
- U2-1 создал UIClient ABC, U2-2 — StreamlitClient реализацию и factory get_ui_client().
- U0 и U1 написаны ДО U2 (последовательность промптов) — используют Streamlit API
  напрямую. После U2 нужно отрефакторить.
- Sidebar (U1-1) и status badge (U1-3) — Streamlit-specific, остаются напрямую (см.
  антипаттерны U2-2). Документируй это.
- TDD: тесты U0/U1 не должны ломаться, только меняется implementation.

Задача:
1. В app.py замени все прямые вызовы Streamlit на client = get_ui_client(); client.*:
   - st.chat_message(role); st.markdown(content) → client.render_message(role, content,
     metadata)
   - st.chat_input(...) → client.handle_user_input()
   - for token in stream: st.write_stream(...) → client.stream_token(token)
   - st.download_button для artifacts → client.render_artifact(artifact)
2. Sidebar (U1-1) — оставь как есть, используй st.sidebar напрямую. Добавь комментарий
   # Streamlit-specific, not in UIClient interface (sidebar concept is Streamlit-only).
3. Status badge (U1-3) — оставь как есть, st.status/st.error/st.warning напрямую.
   Комментарий тот же.
4. PII badge (U1-4) — теперь вызывается из StreamlitClient.render_message, не из
   app.py. Удали прямой вызов render_pii_badge из app.py, перенеси в streamlit_client.py.
5. Запусти все тесты U0/U1 (manual + automated) — должны пройти без изменений.
6. Обнови README.md в src/llm_client/ui/: объясни, что UI-код пишет против UIClient, и
  какие части остаются Streamlit-specific (sidebar, status).

Definition of Done:
- `grep -r "st\.chat_message\|st\.chat_input\|st\.write_stream\|st\.download_button"
  src/llm_client/ui/ | grep -v streamlit_client.py | grep -v "# Streamlit-specific" |
  wc -l` = 0 (либо в streamlit_client.py, либо с комментарием Streamlit-specific).
- Все тесты U0/U1 проходят (regression).
- app.py уменьшился на ~30% (логика переехала в StreamlitClient).
- README.md описывает паттерн "UI code calls interface, not Streamlit API", с
  примером: "client.render_message('user', 'hello')" instead of
  "st.chat_message('user'); st.markdown('hello')".
- При UI_BACKEND=chainlit (env) — get_ui_client() raises NotImplementedError с
  понятным сообщением (Phase 5 yet).

Антипаттерны:
- НЕ рефактори sidebar и status в UIClient — они Streamlit-specific, нет аналогов в
  Chainlit. Если попытаться — interface раздувается, нарушает принцип #16 (избыточное
  действие, но без пользы).
- НЕ ломай тесты U0/U1 — refactor pass должен быть transparent для пользователя.
- НЕ добавляй новые фичи в этом промпте — только refactor, никаких новых capabilities.
- НЕ делай streamlit_client.py god-object — он делегирует в существующие функции
  (render_artifact_buttons, render_pii_badge), не дублирует их.

Связанные ADR:
- Реализует: применение UIClient interface из U2-1/U2-2 на практике.
- Не затрагивает: ADR-002, ADR-007, ADR-008, ADR-013, ADR-014 (функциональность
  та же, только refactor).
- Подготовка к: UI-5 (Phase 5) — миграция на ChainlitClient = добавление новой
  имплементации, без переписывания UI-кода.
```

---

## 4. Блок U3. Streamlit fragments для static shell + dynamic content

**Источник**: `BACKLOG.md` §3.3 (UI-3). Прямая рекомендация из `TRIZ-ANALYSIS.md` §4.3 (строка 242): «разделить UI на static-shell + dynamic-content (Streamlit fragments в 1.40+)». Снимает основное узкое место из C-1 (`TRIZ-ANALYSIS.md` §4.3, строка 240): «Streamlit re-runs (целый rerender всего UI при каждом событии) конфликтует с низколатентным streaming LLM».

### U3-1. `@st.fragment` для chat stream

```
Ты — Frontend-разработчик LLM Client. Примени Streamlit 1.40+ @st.fragment к chat
stream area, чтобы пере-рендер происходил только при изменении потока токенов, а не
при каждом событии в sidebar (выбор сессии, hover, etc.).

Контекст:
- Streamlit 1.40+ ввёл @st.fragment декоратор для изоляции re-run-поведения.
- TRIZ-ANALYSIS.md §4.3 (строка 240): "Streamlit re-runs (целый rerender всего UI при
  каждом событии) конфликтует с низколатентным streaming LLM. UI тратит время на
  пересборку, когда LLM уже отдал 100 токенов."
- Без fragments: при стриминге токенов LLM-ответа пользователь кликает в sidebar —
  Streamlit re-runs ВСЁ приложение, стриминг прерывается, токены теряются.
- С fragments: chat area изолирован, sidebar re-run не влияет на chat, стриминг
  продолжается.

Задача:
1. В streamlit_client.py оберни метод stream_token (или всю chat area) в @st.fragment:
   ```python
   import streamlit as st

   class StreamlitClient(UIClient):
       @st.fragment
       def render_chat_area(self, messages: list[dict],
                          streaming_token: str | None = None) -> None:
           for msg in messages:
               self.render_message(msg["role"], msg["content"], msg.get("metadata"))
           if streaming_token:
               # render streaming token via placeholder
               pass
   ```
2. Альтернативная реализация (если stream_token нельзя изолировать): создай отдельный
   метод render_chat_fragment и оберни его:
   ```python
   @st.fragment
   def render_chat_fragment(self, session_id: str) -> None:
       messages = st.session_state[session_id]["messages"]
       for msg in messages:
           self.render_message(msg["role"], msg["content"], msg.get("metadata"))
       # Streaming handled via separate fragment
   ```
3. Оберни стриминг в отдельный fragment:
   ```python
   @st.fragment
   def render_streaming_fragment(self, session_id: str, sse_iterator) -> None:
       with st.chat_message("assistant"):
           for token in sse_iterator:
               st.markdown(token, unsafe_allow_html=False)
               # Incremental rendering, no full re-run
   ```
4. Интегрируй в app.py: вместо одного st.write_stream — два fragment-вызова
  (chat history + streaming).
5. Тестирование: переключение сессии в sidebar (U1-1) НЕ прерывает активный стриминг
  LLM-ответа. Стриминг продолжается в background, sidebar re-run не влияет.

Definition of Done:
- Запусти стриминг (1000 токенов ответа от LLM). Кликни на другую сессию в sidebar в
  середине стриминга — стриминг НЕ прерывается, токены продолжают приходить в
  активную сессию (chat area переключается на новую сессию, стриминг идёт в
  background).
- Latency рендера одного токена <100 мс (измерение: timestamp в SSE event →
  timestamp в DOM mutation observer).
- При hover по sidebar элементам chat area НЕ пере-рендерится (проверь через
  React DevTools: число commit-ов Streamlit = 0 при hover).
- 100 сессий в sidebar, активный стриминг — CPU <50% (без fragments было бы 100%
  из-за постоянных re-runs).
- regression: все тесты U0/U1/U2 проходят.

Антипаттерны:
- НЕ оборачивай весь app.py в один @st.fragment — теряется смысл, fragment должен
  изолировать конкретную area.
- НЕ используй st.experimental_fragment (deprecated) — только @st.fragment (1.40+).
- НЕ делай fragment для sidebar — он сам по себе локален (st.sidebar уже изолирует
  от main area, но не от других sidebar events). Если sidebar тоже тормозит —
  отдельный промпт.
- НЕ забывай передавать session_id в fragment — fragment имеет свой own state,
  без явной передачи будут баги.
- НЕ используй @st.fragment для PII badge (U1-4) — он уже part of render_message,
  отдельный fragment создаст race condition (metadata пришло, а message ещё
  рендерится).

Связанные ADR:
- Частично резолвит: C-1 (Streamlit vs horizontal scale, latency aspect) —
  снимает локальное узкое место, но НЕ решает multi-instance (это UI-4 Phase 5).
- Использует: ADR-002 (Streamlit 1.40+), ADR-007 (SSE для streaming).
- Зависит от: U0 (scaffold), U2 (UIClient + StreamlitClient).
- Не затрагивает: ADR-013 (cancel — control plane, не data plane).
```

### U3-2. `@st.fragment` для sidebar history list

```
Ты — Frontend-разработчик LLM Client. Примени Streamlit 1.40+ @st.fragment к sidebar
history list, чтобы пере-рендер происходил только при изменении списка сессий, а не
при каждом токене LLM-стрима.

Контекст:
- Без fragments: каждый токен в chat area вызывает Streamlit re-run, sidebar
  пере-рендерится (50 сессий — заметная задержка).
- С fragments: sidebar изолирован, chat streaming не вызывает его пере-рендер.
- Симметрично U3-1: chat fragment и sidebar fragment независимы.

Задача:
1. В sidebar.py (U1-1) оберни render_sidebar в @st.fragment:
   ```python
   import streamlit as st

   @st.fragment
   def render_sidebar_fragment(sessions_registry: dict) -> str | None:
       with st.sidebar:
           st.subheader("Sessions")
           if st.button("➕ New session"):
               return None  # signal to create new
           selected = st.selectbox(
               "Select session",
               options=list(sessions_registry.keys()),
               format_func=lambda sid: f"{sessions_registry[sid]['created_at']} — {sessions_registry[sid]['first_prompt'][:30]}"
           )
           return selected
   ```
2. Интегрируй в app.py: render_sidebar_fragment вызывается ОДИН раз в начале
  rerun, возвращает session_id. Если возвращает None — создание новой сессии.
3. Сессии в sessions_registry обновляются только при:
   - Создании новой сессии (кнопка ➕).
   - Получении сообщения в существующей сессии (last_activity обновляется).
   - Явном refresh (st.button("🔄 Refresh") в sidebar, опционально).
4. Тестирование: запусти стриминг (1000 токенов). Sidebar НЕ пере-рендерится на
  каждый токен (проверь через React DevTools: число commit-ов sidebar = 0 при
  стриминге в chat area).

Definition of Done:
- Запусти стриминг 1000 токенов LLM-ответа. Sidebar НЕ пере-рендерится на каждый
  токен (проверь через React DevTools: число commit-ов sidebar = 0 при стриминге в
  chat area).
- Создание новой сессии: клик "➕ New session" → sidebar пере-рендерится ОДИН раз
  (новая сессия в списке).
- Получение нового сообщения в текущей сессии: last_activity обновляется, sidebar
  пере-рендерится ОДИН раз (если видна сортировка по last_activity) или ни разу
  (если сортировка по created_at).
- 50 сессий в sidebar — переключение между ними <200 мс (latency измеряется от
  клика до обновления chat area).
- regression: все тесты U0/U1/U2 проходят.

Антипаттерны:
- НЕ обновляй sessions_registry в fragment без явного trigger — fragment имеет
  own state, обновление извне требует специального механизма (st.session_state или
  fragment.run_count).
- НЕ делай sidebar fragment зависимым от chat fragment — они должны быть
  независимыми, иначе теряется смысл.
- НЕ используй @st.fragment(run_every=...) для sidebar — это для polling (например,
  обновление last_activity), не для reactive UI.

Связанные ADR:
- Частично резолвит: C-1 (Streamlit vs horizontal scale, sidebar aspect) —
  снимает локальное узкое место.
- Использует: ADR-002 (Streamlit 1.40+).
- Зависит от: U1-1 (sidebar), U3-1 (симметричный fragment для chat).
- Не затрагивает: ADR-018 (SessionStore — это бэкенд, fragment — UI rendering).
```

### U3-3. Latency-бенчмарк до/после fragments (validation)

```
Ты — QA/Frontend-разработчик LLM Client. Создай latency-бенчмарк, который измеряет
эффект от внедрения @st.fragment (U3-1, U3-2) и подтверждает, что узкое место из C-1
снято. Если прироста нет — фрагменты откатываются, UI-3 списывается.

Контекст:
- TRIZ-ANALYSIS.md §4.3 (строка 240) описывает узкое место: Streamlit re-runs
  конфликтует с низколатентным streaming. U3-1/U3-2 вводят fragments как решение.
- Без измерения — невозможно доказать, что fragments помогли. Метрика идеальности
  (ROADMAP.md §15) требует: Δфункциональности / Δсложности ≥ 1. Если fragments
  добавили сложность (+2 функции в коде) без функциональной выгоды — нарушение.
- Критерий отката UI-3 (BACKLOG.md §6.2): прирост FPS стриминга <30% на типовом
  промпте.

Задача:
1. Создай скрипт scripts/ui_latency_benchmark.py:
   - Запускает agent-service с mock LLM, отдающим 1000 токенов с задержкой 50 мс
     между токенами.
   - Открывает Streamlit через Playwright (browser automation).
   - Эмулирует пользовательский сценарий: ввод промпта, ожидание стрима, в середине
     стрима — клик по sidebar на другую сессию.
   - Измеряет:
     * token_fps: число токенов, отрендеренных в DOM за секунду, БЕЗ fragments.
     * token_fps_with_fragments: то же, С fragments (UI3-1/U3-2 применены).
     * sidebar_rerender_count: число Streamlit re-runs sidebar во время стриминга.
     * chat_rerender_count: число Streamlit re-runs chat area во время кликов в
       sidebar.
2. Запуск в 2 режимах:
   - UI3_ENABLED=false (fragments выключены, baseline).
   - UI3_ENABLED=true (fragments применены).
3. Сравнение метрик:
   - token_fps_with_fragments / token_fps ≥ 1.3 (прирост ≥30%) — UI3 Approved.
   - Если <1.3 — UI3 отклоняется, fragments удаляются.
4. Отчёт в JSON: {baseline: {token_fps, rerender_counts}, with_fragments: {...},
  ratio: ..., decision: "approved"|"rejected"}.
5. CI: nightly job запускает бенчмарк, результат пушится в Prometheus (метрика
  llm_client_ui_token_fps).

Definition of Done:
- Скрипт запускается через `python scripts/ui_latency_benchmark.py`.
- Отчёт сохраняется в scripts/ui_latency_report.json.
- При UI3_ENABLED=true: token_fps_with_fragments / token_fps ≥ 1.3 (доказательство
  эффекта).
- sidebar_rerender_count = 0 во время стриминга ( fragments изолируют).
- Если прироста нет (<1.3) — скрипт возвращает exit code 1, CI блокирует merge UI3.
- README.md в src/llm_client/ui/ содержит ссылку на отчёт.

Антипаттерны:
- НЕ измеряй "на глаз" — только Playwright + DOM mutation observer, цифры.
- НЕ запускай на dev-машине с fluctuating load — staging окружение.
- НЕ сравнивай разные браузеры (Chrome vs Firefox) — фиксируй один (Chrome headless).
- НЕ делай бенчмарк долгим (>2 мин) — это nightly CI, не должен тормозить.
- НЕ хардкодь пороги в скрипте — env UI3_FPS_THRESHOLD (default 1.3).

Связанные ADR:
- Тестирует: UI-3 (BACKLOG.md §3.3) — fragments.
- Зависит от: U3-1, U3-2 (fragments должны быть реализованы).
- Решение по UI-3: если бенчмарк fails — UI-3 откатывается, ROADMAP.md §5.7 (после
  патча) обновляется, метрика идеальности пересчитывается.
```

---

## 5. Карта промптов для быстрого навигации

| ID | Промпт | Зависимости | Срок (чел-дн) |
|---|---|---|---|
| U0-1 | Streamlit chat scaffold (`app.py`) | ADR-001, ADR-002, ADR-007 | 1.5 |
| U1-1 | Sidebar с историей сессий | U0-1 | 0.5 |
| U1-2 | Кнопки скачивания артефактов | U0-1, расш. ADR-008 | 0.5 |
| U1-3 | Индикатор статуса LLM-вызова | U0-1, ADR-013 | 0.25 |
| U1-4 | Бейдж PII score | U0-1, ADR-014 | 0.25 |
| U2-1 | `UIClient` interface (ABC) | — | 0.5 |
| U2-2 | `StreamlitClient` реализация | U2-1, U0-1, U1-1..U1-4 | 1.5 |
| U2-3 | Миграция U0/U1 на UIClient (refactor) | U2-1, U2-2 | 0.5 |
| U3-1 | `@st.fragment` для chat stream | U2-2 | 0.5 |
| U3-2 | `@st.fragment` для sidebar | U1-1, U3-1 | 0.25 |
| U3-3 | Latency-бенчмарк fragments | U3-1, U3-2 | 0.25 |
| **Итого** | **11 промптов** | | **6.5 чел-дн** |

**Параллелизация** (по `ROADMAP.md` v1.1.0 §11.2): при команде 2 разработчика —
- Дев 1: U0-1 → U1-2 → U1-3 → U1-4 → U2-3 (refactor) = 3 чел-дн
- Дев 2: U2-1 → U2-2 → U3-1 → U3-2 → U3-3 = 3 чел-дн
- Sync точка: U2-3 (после U2-2) — обе ветки готовы, refactor pass.
- Суммарно: 6.5 чел-дн за 3.25 календарных дней (с overlap).

---

## 6. Приложение: чек-лист выхода из UI-части Phase 1

**Источник**: `BACKLOG.md` §5.1. Используется после прогона всех блоков U0–U3 для самопроверки перед ревью архитектурным комитетом.

| # | Критерий | Где проверяется | Соответствующий промпт |
|---|---|---|---|
| 1 | UI-0 Approved: `docker-compose up ui` поднимает Streamlit, открывается на 8501, ввод промпта стримит токены | manual test | U0-1 |
| 2 | UI-1 Approved: sidebar работает, downloads работают для 4 форматов, status корректно показывает streaming/cancelled/error, PII badge отображается | manual test | U1-1..U1-4 |
| 3 | UI-2 Approved: `UIClient` ABC существует, `StreamlitClient` единственная имплементация, `grep st\.chat_message\|st\.chat_input\|st\.write_stream src/` вне `streamlit_client.py` = 0 | automated (U2-3 DoD) | U2-1..U2-3 |
| 4 | UI-3 Approved: `@st.fragment` для chat и sidebar, latency-бенчмарк показывает прирост ≥30% | U3-3 бенчмарк | U3-1..U3-3 |
| 5 | Метрика идеальности не упала: см. `ROADMAP.md` v1.1.0 §15.2 | G-2 из MVP-PROMPTS | — |
| 6 | Документация обновлена: README в src/llm_client/ui/, `ARCHITECT.md` §7 ADR-002 — уточнение про UI-0 | manual check | U2-3, U3-3 |

**При невыполнении п.1–3**: UI-часть Phase 1 продлевается на 1 sprint.
**При невыполнении п.4**: UI-3 откатывается (fragments удаляются), `ROADMAP.md` §5.7 обновляется, метрика идеальности пересчитывается без UI-3.
**При невыполнении п.5–6**: документационный долг, блокирует старт Phase 2.

---

## 7. История изменений

| Версия | Дата | Изменение |
|---|---|---|
| 1.0.0 | 2026-09-23 | Initial draft. Сформирован на основе `BACKLOG.md` v1.0.0 §3 (UI-0..UI-3). Стиль унаследован от `MVP-PROMPTS.md` v1.0.0 (маркеры, DoD, антипаттерны, связи с ADR). |

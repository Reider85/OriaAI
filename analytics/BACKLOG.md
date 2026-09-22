# BACKLOG.md — Недостающая UI-работа для LLM Client

| Атрибут | Значение |
|---|---|
| Версия документа | 1.0.0 |
| Дата | 2026-09-23 |
| Источники | `ARCHITECT.md` v1.1.0 §4.1, §5 (Presentation Layer), §7 ADR-002/ADR-007; `TRIZ-ANALYSIS.md` v1.0.0 §3.2 (ИКР-1), §4.1, §4.2, §5.1 (C-1), §11 (драфт ADR-018); `ROADMAP.md` v1.0.0 §3.4, §5, §9.3, §15.2; `MVP-PROMPTS.md` v1.0.0 §3 (C-5) |
| Статус | Draft → Review → Approved |
| Аудитория | Tech-лид + Frontend-разработчик + Архитектурный комитет |
| Связанные документы | `UI-PROMPTS.md` v1.0.0 (промпты), `ROADMAP.md` v1.1.0 (патч, см. §5.7) |

---

## 1. Назначение документа

`BACKLOG.md` закрывает разрыв между тремя файлами промптов (`MVP-PROMPTS.md`, `ALPHA-PROMPTS.md`, `BETA-PROMPTS.md`, покрывающими Phase 1–3) и архитектурным замыслом, в котором Presentation Layer Streamlit фиксируется ADR-002 как «уже существующий» с первого дня Phase 1. Анализ показал: единственный UI-касающий промпт во всём корпусе — `C-5` из `MVP-PROMPTS.md` (UI watcher для auto-cancel), и он является JS-инъекцией в уже существующий Streamlit, а не конструкцией UI. В результате любой, кто проходит промпты «с нуля», поднимает Redis, MinIO, Vault, cancel-endpoint, dual-stream logger — но не имеет самого чата, к которому всё это прикручивается.

Документ выполняет три функции. **Первая** — формальный реестр всех UI-работ, явно распределённых по фазам, с приоритетами, зависимостями и оценками в чел-дн. **Вторая** — точка входа для архитектурного комитета при ревью: какие работы вводятся в Phase 1 досрочно (нарушая исходный план `ROADMAP.md` v1.0.0), какие остаются на Phase 5/6. **Третья** — трассировка: каждая работа связана с конкретным ADR и/или противоречием из `TRIZ-ANALYSIS.md` §10, что исключает ad-hoc UI-задачи, не имеющие архитектурного обоснования.

Документ не вводит новые ADR. Все работы ссылаются на существующие или на драфты из `TRIZ-ANALYSIS.md` §11. Документ является input-ом для `UI-PROMPTS.md` v1.0.0 (конкретные промпты для каждого пункта) и для патча `ROADMAP.md` v1.1.0 (продвижение `UIClient` abstraction из Phase 5 в Phase 1).

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

---

## 3. Реестр работ

### 3.1 Соглашения

- **ID** — формат `UI-N` для формализации. Не совпадает с ADR-ID; ADR-привязка указана отдельно.
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

**Итого по фазам** (по патчу ROADMAP v1.1.0; UI-0 включается в Phase 1 как часть UI-составляющей §5.2.4, не выделяется в отдельную Phase 0):
- Phase 1 (с патчем): +6.5 чел-дн (UI-0 + UI-1 + UI-2 + UI-3) — было 8 чел-дн, станет 14.5 чел-дн
- Phase 5: 4 + 6 + 8 = 18 чел-дн (UI-4, UI-5, UI-6) — UI-5 (+6 чел-дн) становится явным, в v1.0.0 было 25 чел-дн, в v1.1.0 — 31 чел-дн
- Phase 6: 6 чел-дн (UI-7) — без изменений против v1.0.0
- **Суммарная delta**: +12.5 чел-дн к ROADMAP (6.5 на Phase 1 UI-составляющую + 6 на Phase 5 UI-5 явный)

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

## 4. Зависимости

```
UI-0 (Phase 0) ──→ UI-1 (Phase 1) ──→ UI-2 (Phase 1) ──→ UI-5 (Phase 5)
                              │                │              └──→ UI-6 (Phase 5+)
                              └──→ UI-3 (Phase 1)
                                               │
                                               └──→ UI-4 (Phase 5) ──→ UI-7 (Phase 6)
```

Критический путь UI: `UI-0 → UI-1 → UI-2 → UI-4 → UI-7`. Длительность: 1.5 + 1.5 + 2.5 + 4 + 6 = 15.5 чел-дн чистой разработки. UI-3 (1 чел-дн) и UI-5/UI-6 (6+8 чел-дн) — параллельные ветки.

## 5. Критерии выхода

### 5.1 Критерии выхода UI-бэклога из Phase 1 (с патчем `ROADMAP.md` v1.1.0)

Phase 1 считается завершённой по UI-части при одновременном выполнении:

1. **UI-0 Approved**: `docker-compose up ui` поднимает Streamlit-приложение, открывается на `http://localhost:8501`, ввод промпта вызывает LLM-агент, стриминг токенов отображается в реальном времени.
2. **UI-1 Approved**: sidebar с историей сессий работает (выбор сессии из списка переключает контент); кнопки скачивания артефактов работают для всех 4 форматов (md/txt/pdf/docx); индикатор статуса корректно показывает streaming/cancelled/error; бейдж PII score отображается для каждого user message.
3. **UI-2 Approved**: `UIClient` interface существует как Python ABC с 4 методами; `StreamlitClient` — единственная имплементация; `grep -r "st\.chat_message\|st\.chat_input\|st\.write_stream" src/ | wc -l` outside `streamlit_client.py` равен 0 (весь UI-код ходит через interface).
4. **UI-3 Approved**: `@st.fragment` применяется к chat stream и к sidebar; переключение между сессиями в sidebar не вызывает пере-рендер chat area; стриминг токенов не вызывает пере-рендер sidebar.
5. **Метрика идеальности не упала**: см. `ROADMAP.md` v1.1.0 §15.2 (после патча).

### 5.2 Критерии для последующих фаз

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

## 7. Связанные документы

| Документ | Раздел | Связь |
|---|---|---|
| `ROADMAP.md` v1.1.0 | §5.7 (новый, после патча) | Формализует `UIClient` abstraction в Phase 1 |
| `ROADMAP.md` v1.1.0 | §5.2 (после патча) | Добавляет строки 5.2.4 (UI-0..UI-3) в таблицу работ Phase 1 |
| `ROADMAP.md` v1.1.0 | §5.6 (после патча) | Расширяет критерии выхода Phase 1 UI-части |
| `ROADMAP.md` v1.1.0 | §15.2 (после патча) | Обновляет расчёт метрики идеальности Phase 1 |
| `UI-PROMPTS.md` v1.0.0 | §1–§4 | Промпты для UI-0..UI-3 |
| `MVP-PROMPTS.md` v1.0.0 | §3 (C-5) | Зависит от UI-0 (нет UI — некуда инжектить JS watcher) |
| `ARCHITECT.md` v1.1.0 | §7 ADR-002 | Не меняется; UI-0 формализует scaffold |
| `TRIZ-ANALYSIS.md` v1.0.0 | §5.1 (C-1) | UI-2 — частичная резолюция; полная — UI-4 в Phase 5 |
| `TRIZ-ANALYSIS.md` v1.0.0 | §4.3 | UI-3 — реализация рекомендации |

---

## 8. История изменений

| Версия | Дата | Изменение |
|---|---|---|
| 1.0.0 | 2026-09-23 | Initial draft. Сформирован на основе анализа пробелов в MVP/ALPHA/BETA-PROMPTS.md относительно ARCHITECT/TRIZ/ROADMAP. |

# MVP-PROMPTS.md — Промпты для этапа MVP (Phase 1)

| Атрибут | Значение |
|---|---|
| Версия документа | 1.0.0 |
| Дата | 2026-09-20 |
| Источники | `ROADMAP.md` v1.0.0 §5, §12, §18.1; `TRIZ-ANALYSIS.md` v1.0.0 §5.4, §7.1, §7.5, §11 |
| Этап | Phase 1 — MVP (8 чел-дн + 7 чел-дн Quick Wins) |
| ADR в области | ADR-013, ADR-014, (расш. ADR-008) |
| Резолвит противоречия | C-4, C-11, C-15 |
| Целевой LLM | Универсальные (Cursor / Copilot / Claude Code / ChatGPT) |
| Гранулярность | Микро-промпты (1 промпт = 1 файл / 1 класс / 1 подзадача) |

---

## 0. Как пользоваться документом

Каждый промпт — самостоятельный блок, огороженный ` ``` `-код-блоком, готовый к копи-пасту в любой код-ассистент. Промпты сгруппированы в семь блоков **A–G**, идущих в порядке зависимостей:

```
A. Инфра ──┐
            ├─→ B. Quick Wins ──→ C. ADR-013 ──┐
            │                                  ├─→ F. Тесты/CI ──→ G. Документация
            └─→ D. ADR-014 ────────────────────┘
            └─→ E. расш. ADR-008 ───────────────┘
```

**Конвенции**:

- Имена классов, методов, эндпоинтов — на английском (как в `ARCHITECT.md`).
- Имена ADR и противоречий — в формате `ADR-013`, `C-4` (как в `TRIZ-ANALYSIS.md` §10).
- Раздел `Definition of Done` — конкретные измеримые критерии готовности.
- Раздел `Антипаттерны` — что LLM НЕ должен делать; если предложит — отбраковывать.
- Раздел `Связанные ADR` — какие ADR затрагивает (не ломает / упраздняет / требует).

Полный прогон блоков A→G занимает 8 чел-дн + 1 sprint на Quick Wins. Критерии выхода из Phase 1 — в Приложении §8.

---

## 1. Блок A. Инфра-подготовка Phase 1

**Источник**: `ROADMAP.md` §18.1 п.2. Разворачивается параллельно с архитектурным ревью, до старта кодирования ADR-013 / ADR-014 / расш. ADR-008.

### A-1. Redis в docker-compose с pub/sub и healthcheck

```
Ты — DevOps-инженер команды LLM Client. Подготовь Redis 7+ для Phase 1: он будет
использоваться как (а) message bus для control-plane ADR-013 (канал session:{id}:cancel),
(б) будущий cache layer для ADR-010 в Phase 2. Пока Phase 2 не начался — Redis нужен
только под pub/sub и общий healthcheck.

Контекст:
- Существующий docker-compose уже содержит PostgreSQL и Streamlit-сервис.
- ADR-013 (TRIZ-ANALYSIS.md §11) требует Redis pub/sub latency <5 мс.
- В Phase 2 (ROADMAP.md §6.3, ADR-010) Redis станет mandatory checkpoint-layer,
  поэтому конфиг должен сразу включать AOF-persistence.
- Связанное противоречие: C-4 (SSE one-way vs interactivity) — резолвится через
  dual-channel, где Redis — control-plane транспорт.

Задача:
1. Добавь сервис `redis` в docker-compose.yml (образ redis:7-alpine).
2. Включи AOF-persistence (appendonly yes) — для будущего ADR-010.
3. Добавь healthcheck через `redis-cli ping`.
4. Создай Network, чтобы LLM Client-сервис мог ходить к redis по DNS-имени `redis`.
5. Опиши переменные окружения в .env.example: REDIS_URL=redis://redis:6379/0.
6. Документируй в README раздел "Phase 1 infra": как проверить, что pub/sub работает
   (`redis-cli SUBSCRIBE test` + `redis-cli PUBLISH test hello`).

Definition of Done:
- `docker-compose up redis` поднимает сервис за <3 сек.
- `docker-compose exec redis redis-cli ping` возвращает PONG.
- Паблиш/сабскрайб тест из README проходит за <5 мс round-trip.
- AOF-файл создаётся в volume `redis-data` после первого PUBLISH.
- В логах Redis нет warnings о maxmemory или persistence.

Антипаттерны:
- НЕ настраивай Redis Cluster / Sentinel — для Phase 1 single-instance достаточно,
  over-engineering (ROADMAP.md §13.1).
- НЕ включай TLS — внутренний трафик docker-compose, до Phase 5.
- НЕ хардкодь пароль в docker-compose.yml — только через .env.
- НЕ используй Redis 6 — pub/sub API отличается, ADR-013 требует 7+.

Связанные ADR:
- Включает инфру для: ADR-013 (control-plane), ADR-010 (Phase 2, future).
- Не затрагивает: ADR-014 (там отдельный Vault), расш. ADR-008 (там MinIO).
```

### A-2. MinIO в docker-compose с инициализацией bucket

```
Ты — DevOps-инженер команды LLM Client. Подготовь MinIO для Phase 1: он заменит
LocalFileStorage в расш. ADR-008 (TRIZ-ANALYSIS.md §7.5, противоречие C-15) и станет
 forensic-хранилищем для ADR-014 (TRIZ-ANALYSIS.md §7.1).

Контекст:
- ADR-008 зафиксил LocalFileStorage для MVP — ломает multi-instance и dev-prod parity.
- Расширение ADR-008 упраздняет LocalFileStorage, оставляет один S3CompatibleStorage.
- В dev — MinIO, в prod — AWS S3 / external MinIO. Контракт FileStorage один.
- ADR-014 требует отдельный S3 bucket для forensic stream (server-side encryption).

Задача:
1. Добавь сервис `minio` (образ minio/minio:latest) в docker-compose.yml.
2. Команда запуска: `server /data --console-address ":9001"`.
3. Создай два bucket через init-контейнер (minio/mc): `llm-client-files` (для расш.
   ADR-008) и `llm-client-forensic` (для ADR-014).
4. Настрой переменные: MINIO_ROOT_USER, MINIO_ROOT_PASSWORD, S3_ENDPOINT=http://minio:9000,
   S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET=llm-client-files, S3_FORENSIC_BUCKET=llm-client-forensic.
5. Persistent volume `minio-data` для /data.
6. Healthcheck через `mc ready local` или curl к /minio/health/ready.
7. В README добавь ссылку на MinIO Console (http://localhost:9001).

Definition of Done:
- `docker-compose up minio` поднимает сервис за <5 сек.
- `mc ls local/llm-client-files` работает без ошибок после init-контейнера.
- `mc ls local/llm-client-forensic` работает.
- Round-trip upload/download через aws-cli работает.
- MinIO Console доступна на http://localhost:9001 с указанным логином/паролем.

Антипаттерны:
- НЕ создавай bucket-ы вручную через UI — только через init-контейнер (воспроизводимость).
- НЕ хардкодь креды — только через .env.
- НЕ включай TLS в dev — до Phase 5.
- НЕ используй один bucket для files и forensic — ADR-014 требует изоляции.
- НЕ настраивай MinIO как S3-совместимый gateway в dev — должен быть нативный MinIO.

Связанные ADR:
- Включает инфру для: расш. ADR-008 (FileStorage), ADR-014 (forensic bucket).
- Зависит от: ничего (независимый сервис).
```

### A-3. HashiCorp Vault dev-mode с transit-ключом для AES-256-GCM

```
Ты — Security-инженер команды LLM Client. Подготовь HashiCorp Vault в dev-mode для
Phase 1: он будет использоваться ADR-014 (DualStreamLogger) как KMS для шифрования
forensic stream через AES-256-GCM.

Контекст:
- ADR-014 (TRIZ-ANALYSIS.md §7.1, противоречие C-11) требует AES-256-GCM шифрование
  forensic stream с ключами в KMS/Vault — НЕ в приложении.
- В Phase 1 — local Vault dev-mode (ROADMAP.md §2.3 п.2): не для production, но
  контракт с приложением должен быть production-ready.
- В Phase 5 будет миграция на managed KMS (AWS KMS / GCP KMS); интерфейс KeyProvider
  должен абстрагировать смену.

Задача:
1. Добавь сервис `vault` (образ hashicorp/vault:latest) в docker-compose.yml с
   командой `server -dev -dev-root-token-id=root` (только для dev!).
2. Создай init-контейнер, который через vault CLI:
   - Включает transit engine: `vault secrets enable transit`.
   - Создаёт ключ: `vault write -f transit/keys/forensic-aes256-gcm type=aes256-gcm`.
   - Выдаёт policy `forensic-encryptor`: только encrypt/decrypt для ключа forensic-aes256-gcm.
3. Переменные окружения в .env.example: VAULT_ADDR=http://vault:8200, VAULT_TOKEN=root,
   VAULT_TRANSIT_KEY=forensic-aes256-gcm.
4. Healthcheck через `vault status`.
5. В README раздел "Phase 1 KMS": как проверить, что шифрование работает
   (`vault write transit/encrypt/forensic-aes256-gcm plaintext=$(base64 <<< "test")`).

Definition of Done:
- `docker-compose up vault` поднимает сервис за <3 сек.
- `vault status` возвращает initialized=true, sealed=false.
- Encrypt/decrypt round-trip через CLI работает.
- Policy forensic-encryptor НЕ содержит путей `auth/`, `sys/`, `secret/` — только transit.
- В логах Vault есть запись о создании ключа forensic-aes256-gcm.

Антипаттерны:
- НЕ используй dev-mode в staging/prod — только local dev. В staging — file storage
  backend с proper unseal, в prod — managed KMS.
- НЕ хардкоди root token в приложении — только через VAULT_TOKEN env var.
- НЕ создавай ключ вручную через UI — только через init-контейнер (IaC).
- НЕ используй тип ключа `aes128-gcm` или `chacha20-poly1305` — ADR-014 явно требует AES-256-GCM.
- НЕ храни plaintext в логах Vault — это форензический KMS, leakage = компрометация.

Связанные ADR:
- Включает инфру для: ADR-014 (KMS provider).
- Не затрагивает: ADR-013, расш. ADR-008.
```

---

## 2. Блок B. Quick Wins (§12 ROADMAP)

**Источник**: `ROADMAP.md` §12. Три быстрых победы до полного старта Phase 1, 7 чел-дн суммарно. Не требуют KMS (B-1, B-2, B-3) — ADR-014 в Quick Wins не входит.

### B-1. Quick Win 12.1: Минимальная версия ADR-013 (cancel через Redis pub/sub)

```
Ты — Backend-разработчик LLM Client. Реализуй минимальную версию ADR-013 как Quick Win
(ROADMAP.md §12.1): cancel работающего LLM-вызова через Redis pub/sub, без UI auto-cancel
(он придёт в полном ADR-013 в Блоке C).

Контекст:
- ADR-007 (SSE для streaming) — one-way, cancel требует отдельный канал.
- ТРИЗ-противоречие C-4 (TRIZ-ANALYSIS.md §5.4): SSE simpler vs one-way limitation.
- Принципы ТРИЗ 15 (динамичность) + 17 (переход в другое измерение): data-plane SSE
  остаётся, control-plane выносим в Redis pub/sub.
- В этом Quick Win НЕ реализуем: UI auto-cancel on tab close, forensic log cancel event,
  partial answer return — это в полном ADR-013 (Блок C).

Задача:
1. Создай HTTP endpoint POST /sessions/{session_id}/cancel в существующем web-сервере.
   - Тело запроса: {"reason": "user_cancelled" | "timeout" | "system_error"}.
   - Возвращает 202 Accepted (cancel поставлен в очередь).
   - Endpoint публикует сообщение в Redis-канал session:{session_id}:cancel.
2. Создай подписчика CancelSubscriber, который:
   - Subscribes на session:{session_id}:cancel.
   - При получении сообщения выставляет CancellationToken для соответствующего графа.
3. CancellationToken — простой in-memory объект с флагом is_cancelled и callback-ами.
4. В графе LangGraph добавь проверку token.is_cancelled между node-ами (не внутри node —
   между, на этапе conditional edge).
5. При is_cancelled=true граф останавливается, возвращает текущий partial state.

Definition of Done:
- POST /sessions/{id}/cancel возвращает 202 за <50 мс (без ожидания фактической отмены).
- Redis PUBLISH доставляется до подписчика за <5 мс (round-trip).
- Граф останавливается в течение 100 мс после получения cancel-сигнала (если между
  node-ами — это latency одного node execution).
- Unit-тест: публикация cancel → подписчик выставил флаг → граф остановился.

Антипаттерны:
- НЕ используй WebSocket — ТРИЗ-принцип 26 (копирование): HTTP + SSE + Redis проще.
- НЕ делай polling из UI на /cancel-status — Redis pub/sub event-driven.
- НЕ проверяй token внутри node-функции — только между node-ами (минимум изменений).
- НЕ блокируй endpoint на фактическую отмену — 202 сразу, фактическая отмена асинхронна.
- НЕ используй один глобальный token на все сессии — per-session.

Связанные ADR:
- Partial implementation of: ADR-013 (полная версия в Блоке C).
- Не затрагивает: ADR-014 (forensic log), ADR-007 (SSE не трогаем).
```

### B-2. Quick Win 12.2: Минимальная версия расш. ADR-008 (MinIO в dev, feature-flag)

```
Ты — Backend-разработчик LLM Client. Реализуй минимальную версию расширения ADR-008 как
Quick Win (ROADMAP.md §12.2): S3CompatibleStorage для dev через MinIO, LocalFileStorage
пока НЕ удаляй — переключение через feature-flag.

Контекст:
- ADR-008 зафиксил LocalFileStorage для MVP и S3FileStorage для prod — двойная
  имплементация, ломает parity (TRIZ-ANALYSIS.md §7.5, C-15).
- Принципы ТРИЗ 28 (замена механической схемы) + 5 (объединение): одна реализация
  S3CompatibleStorage, конфигурация через env vars.
- В этом Quick Win НЕ удаляем LocalFileStorage — он остаётся как fallback, переключение
  через STORAGE_BACKEND=local|s3. Удаление — в полном расш. ADR-008 (Блок E).

Задача:
1. Создай класс S3CompatibleStorage, реализующий существующий FileStorage interface:
   - Методы: save(file: bytes, key: str) -> str, get(key: str) -> bytes, delete(key: str),
     exists(key: str) -> bool.
   - Используй boto3 (sync) или aiobotocore (async, если существующий FileStorage async).
   - Конфигурация через env: S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET.
2. В фабрике FileStorage добавь переключатель по env STORAGE_BACKEND:
   - "local" → LocalFileStorage (существующий, без изменений).
   - "s3" → S3CompatibleStorage (новый).
   - default — "local" (backward compat).
3. В docker-compose dev-окружения установи STORAGE_BACKEND=s3 (с MinIO из Блока A-2).
4. Все новые тесты проходят с STORAGE_BACKEND=s3.
5. Существующие тесты с STORAGE_BACKEND=local НЕ ломаются.

Definition of Done:
- При STORAGE_BACKEND=s3 сохранение файла через FileStorage.save() появляется в MinIO
  bucket llm-client-files (видно в MinIO Console http://localhost:9001).
- Round-trip save→get→delete работает для бинарного и текстового контента.
- При STORAGE_BACKEND=local всё работает как раньше (regression test проходит).
- Все существующие caller-ы FileStorage не требуют изменения (миграция прозрачна).

Антипаттерны:
- НЕ удаляй LocalFileStorage в этом Quick Win — только добавь S3CompatibleStorage и флаг.
- НЕ создавай третий backend (например, MemoryFileStorage для prod) — только 2 сейчас.
- НЕ дублируй логику в S3CompatibleStorage и S3FileStorage (если уже есть S3FileStorage
  из ADR-008 — переиспользуй или замени на S3CompatibleStorage).
- НЕ делай sync I/O в async-контексте — используй aiobotocore если FileStorage async.
- НЕ хардкодь endpoint MinIO в коде — только env vars.

Связанные ADR:
- Partial implementation of: расш. ADR-008 (полная версия с удалением LocalFileStorage в Блоке E).
- Включает infra из: Блок A-2 (MinIO).
```

### B-3. Quick Win 12.3: State-Delta Cycle Detection (preview, без embeddings)

```
Ты — ML-инженер LLM Client. Реализуй preview-версию State-Delta Cycle Detection как
Quick Win (ROADMAP.md §12.3): детекция зацикливания LangGraph по state-delta, без
embeddings (простой текстовый diff), без интеграции с полным расш. ADR-001.

Контекст:
- ADR-001 использует LangGraph с max_iterations=10 — единственная защита от зацикливания.
- ТРИЗ-противоречие C-5 (TRIZ-ANALYSIS.md §5.5): cycles для гибкости vs infinite loops.
- Принципы ТРИЗ 23 (обратная связь) + 22 (превращение вреда в пользу): delta-state
  monitoring, при delta < threshold — переключение стратегии.
- В этом Quick Win НЕ используем embeddings (придут в полном расш. ADR-001 в Phase 4) —
  только простой текстовый diff (difflib.SequenceMatcher).

Задача:
1. Создай функцию compute_state_delta(prev_state: dict, curr_state: dict) -> float:
   - Сравнивает последние 2 messages в state через difflib.SequenceMatcher.ratio().
   - Возвращает similarity score в [0, 1].
2. Добавь iteration_monitor callback, который LangGraph вызывает после каждого node:
   - Берёт prev_state и curr_state, считает delta.
   - Если similarity > 0.95 (delta < 0.05) 2 итерации подряд — триггерит escalation.
3. escalation action: записывает в state флаг cycle_detected=true, граф должен на
   следующем conditional edge выйти (возвратить текущий ответ как final).
4. Логирование: каждое срабатывание iteration_monitor пишется в stdout с пометкой
   [cycle_detection] для последующего анализа.
5. Конфигурация через env: CYCLE_DETECTION_ENABLED=true|false, CYCLE_DETECTION_THRESHOLD=0.95.

Definition of Done:
- При двух подряд идентичных сообщениях граф останавливается на 3-й итерации (а не на 10-й).
- При нормальном потоке (каждая итерация меняет state существенно) — нет ложных триггеров.
- Логирование [cycle_detection] видно в stdout.
- Feature flag CYCLE_DETECTION_ENABLED=false отключает проверку (граф работает как раньше).

Антипаттерны:
- НЕ используй embeddings — это для полного расш. ADR-001 в Phase 4, Quick Win — простой diff.
- НЕ блокируй node-функцию — callback должен быть O(1) по сложности (diff коротких строк).
- НЕ удаляй max_iterations=10 — это safety net, cycle detection поверх него.
- НЕ делай escalation дефолтным — только через flag, чтобы не сломать существующие тесты.
- НЕ сравнивай весь state (может быть большой) — только последние 2 messages.

Связанные ADR:
- Partial implementation of: расш. ADR-001 (полная версия в Phase 4 с embeddings).
- Не затрагивает: ADR-013, ADR-014, расш. ADR-008.
```

---

## 3. Блок C. ADR-013: SSE + HTTP Cancel Endpoint — микро-декомпозиция

**Источник**: `ROADMAP.md` §5.3, `TRIZ-ANALYSIS.md` §5.4 + §11 (ADR-013). Резолвит противоречие C-4. Принципы ТРИЗ: 15, 26, 13, 17. Полная реализация: 6 подзадач, 2 чел-дн.

### C-1. CancellationToken abstraction

```
Ты — Backend-разработчик LLM Client. Создай abstraction CancellationToken для ADR-013.

Контекст:
- ADR-013 (TRIZ-ANALYSIS.md §11) требует, чтобы граф LangGraph проверял token между
  node-ами и прерывал upstream LLM-вызов при cancel.
- Token должен быть per-session, валидиться O(1), поддерживать callback-и на cancel.
- Должен корректно работать в async-контексте LangGraph (anyio/asyncio).

Задача:
1. Создай класс CancellationToken с интерфейсом:
   - is_cancelled -> bool (property, thread-safe через asyncio.Event).
   - cancel(reason: str) -> None (idempotent, ставит event, вызывает callbacks).
   - on_cancel(callback: Callable[[], Awaitable[None]]) -> None (регистрация callback).
   - reason -> str | None (property, возвращает причину cancel или None).
2. Создай CancellationTokenRegistry:
   - register(session_id: str) -> CancellationToken (создаёт новый token).
   - get(session_id: str) -> CancellationToken | None.
   - cancel(session_id: str, reason: str) -> bool (возвращает True если найден и отменён).
   - cleanup(session_id: str) -> None (удаляет из registry после завершения сессии).
3. CancellationToken должен быть сериализуемым только в смысле session_id — сам объект
   in-memory, не persistent (после restart сессии отменены через TTL Redis).

Definition of Done:
- 1000 параллельных cancel() вызовов на одном token не вызывают race condition.
- callback on_cancel вызывается ровно 1 раз даже при многократных cancel().
- is_cancelled становится True атомарно с вызовом cancel().
- Unit-тесты покрывают: cancel, double-cancel, callback registration после cancel,
  cleanup, registry get на несуществующем session_id.

Антипаттерны:
- НЕ используй threading.Event в async-коде — только asyncio.Event или anyio.Event.
- НЕ храни token в Redis (сериализация) — Redis только сигнал, сам token в памяти.
- НЕ делай token global — только per-session через Registry.
- НЕ добавляй reopen()/uncancel() — cancel окончательный.

Связанные ADR:
- Включает базис для: ADR-013 (C-2, C-3, C-4 используют этот token).
- Не затрагивает: ADR-014, расш. ADR-008.
```

### C-2. HTTP POST /sessions/{id}/cancel endpoint

```
Ты — Backend-разработчик LLM Client. Реализуй HTTP endpoint POST /sessions/{session_id}/cancel
для ADR-013 (control-plane).

Контекст:
- ADR-007 (SSE) — data-plane, остаётся без изменений.
- ADR-013 (TRIZ-ANALYSIS.md §11) — добавляет control-plane: HTTP POST + Redis pub/sub.
- ТРИЗ-принцип 15 (динамичность): data-plane и control-plane разделены, не смешиваются.

Задача:
1. Создай endpoint POST /sessions/{session_id}/cancel:
   - Path param: session_id (строка, валидируется через существующий session manager).
   - Body: {"reason": "user_cancelled" | "tab_closed" | "timeout" | "system_error",
            "user_id": str (опционально, для аудита)}.
   - Возвращает 202 Accepted с телом {"status": "cancel_queued", "session_id": ...}.
   - Возвращает 404 если session_id не найден в active sessions.
   - Возвращает 409 если сессия уже cancelled или завершена.
2. После валидации endpoint:
   - Публикует в Redis канал session:{session_id}:cancel сообщение
     {"reason": ..., "user_id": ..., "timestamp": ISO-8601}.
   - НЕ ждёт фактической отмены — 202 возвращается сразу после PUBLISH.
3. Логирует в operational stream (не forensic — forensic логирует на стороне подписчика,
   см. C-6): "Cancel request received for session {id}, reason={reason}".
4. Endpoint должен быть доступен без auth в dev, с auth (через существующий middleware)
   в staging/prod — auth не меняется.

Definition of Done:
- POST /sessions/{id}/cancel с валидным session_id возвращает 202 за <50 мс (без нагрузки).
- 404 на несуществующий session_id.
- 409 на уже отменённую сессию.
- Redis PUBLISH проходит успешно (проверка через redis-cli SUBSCRIBE).
- Лог в operational stream содержит session_id, reason, timestamp.
- Endpoint не блокируется на фактическую отмену графа.

Антипаттерны:
- НЕ возвращай 200 OK с ожиданием фактической отмены — это ломает UX (HTTP timeout).
- НЕ используй WebSocket — ТРИЗ-принцип 26, HTTP+Redis проще.
- НЕ логируй PII из body в operational stream (user_id маскируется через ADR-014).
- НЕ требуй auth-токен в body — auth через существующий middleware, не дублируй.
- НЕ используй GET /cancel — semantically incorrect, POST для state mutation.

Связанные ADR:
- Зависит от: Блок A-1 (Redis), C-1 (CancellationToken).
- Включает part of: ADR-013.
- Не ломает: ADR-007 (SSE отдельно).
```

### C-3. Redis pub/sub channel publisher (封装)

```
Ты — Backend-разработчик LLM Client. Создай CancelPublisher — обёртку над Redis pub/sub
для публикации cancel-событий, используемую endpoint-ом C-2.

Контекст:
- ADR-013 (TRIZ-ANALYSIS.md §11) использует Redis pub/sub канал session:{id}:cancel.
- ТРИЗ-принцип 17 (переход в другое измерение): control-plane вынесен в Redis, не
  смешивается с data-plane (SSE).
- Publisher должен быть переиспользуемым: endpoint C-2, UI watcher C-5, любые другие
  источники cancel-сигнала используют один Publisher.

Задача:
1. Создай класс CancelPublisher:
   - __init__(redis_client: redis.asyncio.Redis).
   - publish(session_id: str, reason: str, user_id: str | None = None) -> None:
     * Формирует message dict: {"reason", "user_id", "timestamp": ISO-8601 UTC}.
     * Сериализует в JSON.
     * Публикует в канал session:{session_id}:cancel.
     * Логирует latency в ms (для observability).
2. Connection management:
   - Использует существующий redis.asyncio.Redis-клиент из приложения (не создаёт новый).
   - При потере соединения — retry с экспоненциальной задержкой (1ms, 2ms, 4ms, max 16ms),
     затем raises PublishError (endpoint C-2 вернёт 503).
3. Channel naming convention: session:{session_id}:cancel. Документируй в docstring.

Definition of Done:
- publish() выполняется за <5 мс в 99% случаев (без Redis latency spikes).
- JSON-сериализация корректна (timestamp в UTC ISO-8601 с 'Z' suffix).
- При потере Redis-соединения retry отрабатывает 4 попытки, затем raises.
- Unit-тест с mock redis-клиентом проверяет формат message и channel name.
- Integration-тест с реальным Redis (Блок A-1) проверяет, что подписчик получает message.

Антипаттерны:
- НЕ создавай отдельный redis-клиент для publisher — переиспользуй существующий.
- НЕ публикуй в общий канал "cancels" с фильтрацией на стороне подписчика — per-session.
- НЕ используй Redis Streams (XADD) — pub/sub достаточно, persistent не нужен.
- НЕ сериализуй datetime в local timezone — только UTC.
- НЕ блокируй publish() на подтверждение получения подписчиком — fire-and-forget.

Связанные ADR:
- Зависит от: Блок A-1 (Redis).
- Используется в: C-2 (endpoint), C-5 (UI watcher).
- Включает part of: ADR-013.
```

### C-4. CancelSubscriber on agent side (между node-ами графа LangGraph)

```
Ты — ML/Backend-разработчик LLM Client. Реализуй CancelSubscriber, который слушает Redis
канал session:{id}:cancel и прерывает выполнение графа LangGraph через CancellationToken.

Контекст:
- ADR-013 (TRIZ-ANALYSIS.md §11): при получении cancel-сигнала граф прерывает upstream
  LLM-вызов и возвращает partial answer.
- ТРИЗ-принцип 13 (наоборот): вместо polling флага агент сам реагирует на событие.
- ТРИЗ-принцип 17: подписчик живёт в control-plane, не в data-plane (SSE).
- Сложность: граф LangGraph исполняется как sequential async-loop; между node-ами
  нужно вставить проверку token.

Задача:
1. Создай CancelSubscriber:
   - __init__(redis_client, token_registry: CancellationTokenRegistry).
   - subscribe(session_id: str) -> asyncio.Task: запускает фоновую таску, которая
     слушает канал session:{session_id}:cancel.
   - При получении сообщения:
     * Парсит JSON, достаёт reason.
     * Берёт token из registry: token_registry.get(session_id).
     * Если token есть — вызывает token.cancel(reason).
     * Логирует в operational: "Cancel signal received for session {id}, reason={reason}".
   - unsubscribe(session_id: str): отменяет фоновую таску, закрывает pubsub-подписку.
2. Интегрируй в LangGraph:
   - Перед запуском графа (graph.astream(...) или graph.ainvoke(...)) — вызывай
     subscriber.subscribe(session_id).
   - После завершения (включая cancel) — subscriber.unsubscribe(session_id) + registry.cleanup.
   - Между node-ами графа (через conditional edge или middleware) — проверяй
     token.is_cancelled. Если True — генерируй partial answer из текущего state и выходи.
3. Прерывание upstream LLM-вызова:
   - Если внутри node идёт await llm.ainvoke(...), оберни в asyncio.wait_for + token check,
     ИЛИ передай CancellationToken в langchain RunnableConfig и прерывай через callback.

Definition of Done:
- При POST /cancel → Redis PUBLISH → подписчик получает <5 мс → token.cancel().
- Граф останавливается на следующем conditional edge (не ждёт завершения текущего node,
  но ждёт await-точки внутри node — это OK, см. upstream LLM abort ниже).
- Partial answer возвращается пользователю через SSE (последний chunk перед cancel).
- forensic stream (Блок D-3) получает запись о cancel-событии с reason и timestamp.
- Нет race condition: если cancel приходит после завершения графа — игнорируется.

Антипаттерны:
- НЕ проверяй token.is_cancelled внутри node-функции синхронно (между await-ами) —
  только между node-ами или через asyncio.wait_for вокруг LLM-вызова.
- НЕ создавай подписчика без unsubscribe — утечка соединений Redis.
- НЕ блокируй граф на подписку — subscribe() запускает фоновую таску, не ждёт.
- НЕ прерывай жёстко текущий node через task.cancel() без cleanup — возможны
  некорректные состояния в LangGraph state.
- НЕ логируй user_id в operational stream (PII — маскируется через ADR-014).

Связанные ADR:
- Зависит от: C-1 (CancellationToken), Блок A-1 (Redis).
- Связан с: ADR-001 (LangGraph, не ломает — добавляет middleware).
- Включает part of: ADR-013.
```

### C-5. UI watcher: visibilitychange / beforeunload → auto-cancel

```
Ты — Frontend-разработчик LLM Client. Реализуй UI watcher, который детектирует закрытие
вкладки / потерю видимости и автоматически шлёт cancel-запрос.

Контекст:
- ADR-013 (TRIZ-ANALYSIS.md §5.4): "UI-клиент детектирует обрыв SSE-соединения (visibility
  change / beforeunload) и автоматически шлёт cancel."
- ТРИЗ-принцип 13 (наоборот): вместо ручного cancel пользователь не делает ничего —
  система сама реагирует на уход пользователя.
- LLM Client UI — Streamlit-приложение (ADR-002). Streamlit рендерит в браузер, JS можно
  инжектить через st.components.v1.html.

Задача:
1. Создай JS-фрагмент (inline через st.components.v1.html), который:
   - Слушает события: visibilitychange (document.hidden=true), beforeunload, pagehide.
   - На каждое событие:
     * Достаёт session_id из URL query param или из localStorage.
     * Формирует POST /sessions/{session_id}/cancel с reason="tab_closed" или "hidden".
     * Использует navigator.sendBeacon() для надёжной доставки даже при закрытии вкладки
       (fetch с keepalive=true как fallback).
2. Не отправляй cancel при visibilitychange=hidden если вкладка не была скрыта >5 сек
   (защита от ложных срабатываний при переключении вкладок на короткое время).
3. Также добавь ручную кнопку "Stop" в Streamlit UI — вызывает тот же endpoint с
   reason="user_cancelled" через fetch (не sendBeacon — пользователь ждёт ответа).
4. Логируй в console.debug для отладки: "[auto-cancel] event=visibilitychange, session_id=...".

Definition of Done:
- При закрытии вкладки во время активной LLM-сессии: cancel-запрос доходит до backend
  (видно в логах operational stream).
- При переключении вкладки на 3 сек и возврате: cancel НЕ отправляется (debounce 5 сек).
- При нажатии кнопки "Stop" вручную: cancel отправляется немедленно, UI показывает
  "Cancelled" в течение 200 мс.
- SSE-стрим корректно закрывается после cancel (не висит полузакрытым).
- Тест в Chrome DevTools: эмуляция закрытия вкладки работает (visibilitychange=hidden +
  pagehide).

Антипаттерны:
- НЕ используй window.onbeforeunload только — он ненадёжен в современных браузерах,
  особенно на мобильных. Используй sendBeacon + pagehide.
- НЕ отправляй cancel при каждом visibilitychange=hidden — debounce 5 сек, иначе
  переключение вкладок заспамит endpoint.
- НЕ используй fetch без keepalive для beforeunload — fetch может быть отменён браузером
  при закрытии вкладки. Только sendBeacon или fetch keepalive=true.
- НЕ хардкодь URL backend — бери из window.location.origin или env.
- НЕ шли cancel если session_id не найден (нет активной сессии) — silent skip.

Связанные ADR:
- Зависит от: C-2 (endpoint), C-3 (CancelPublisher).
- Не ломает: ADR-002 (Streamlit), ADR-007 (SSE отдельно).
- Включает part of: ADR-013.
```

### C-6. Cancel event logging в forensic stream (связка с ADR-014)

```
Ты — Backend-разработчик LLM Client. Свяжи ADR-013 (cancel) с ADR-014 (DualStreamLogger):
при cancel-событии forensic stream должен получить запись с reason, timestamp, partial
answer size, session context.

Контекст:
- ADR-013 (ROADMAP.md §5.3, критерий готовности): "forensic stream фиксирует
  cancel-событие с reason".
- ADR-014 (TRIZ-ANALYSIS.md §7.1): forensic stream — зашифрованный full trace, retention
  90+ дней, для аудита и расследований.
- Cancel-событие — критичный для аудита факт (почему сессия прервана), должен попасть в
  forensic, не только в operational (operational маскирует user_id, forensic хранит full).

Задача:
1. На стороне CancelSubscriber (C-4) после вызова token.cancel(reason) — передай в
   ForensicStreamWriter (D-3) запись:
   {
     "event_type": "session_cancelled",
     "session_id": str,
     "user_id": str,  # полный, не замаскированный
     "reason": str,   # из cancel-запроса
     "timestamp": ISO-8601 UTC,
     "partial_answer_size_bytes": int,  # размер partial state на момент cancel
     "last_node_executed": str,         # имя последнего node в графе
     "messages_count": int,             # количество messages в state на момент cancel
     "duration_ms": int                 # сколько мс прошло от старта сессии до cancel
   }
2. В operational stream (D-2) — параллельная запись с маскированным user_id и без
   partial_answer_size (это потенциально PII-bearing):
   {
     "event_type": "session_cancelled",
     "session_id": str,
     "user_id": "[MASKED]",
     "reason": str,
     "timestamp": ISO-8601 UTC
   }
3. ForensicStreamWriter шифрует запись через KMS (Блок D-4) и пишет в S3 forensic bucket.
4. OperationalStreamWriter пишет в stdout/Loki без шифрования.

Definition of Done:
- После POST /cancel → forensic stream получает запись за <500 мс (latency шифрования + S3 write).
- operational stream получает параллельную запись за <50 мс.
- В forensic записи есть все 8 полей из спецификации.
- В operational записи user_id = "[MASKED]" (или заменён через PIIDetector из D-1).
- forensic запись зашифрована (проверка: cat file | vault decrypt ... возвращает JSON).
- retention: forensic живёт 90+ дней, operational — 30 дней (настраивается в D-2, D-3).

Антипаттерны:
- НЕ пиши partial_answer_size в operational — это может утечь через размер (side-channel).
- НЕ пиши последний message текст в operational — только метаданные.
- НЕ делай forensic write синхронным в CancelSubscriber — async, не блокирует cancel flow.
- НЕ используй один writer для обоих потоков — D-2 и D-3 отдельные классы.
- НЕ пропускай forensic запись если cancel получен после завершения графа (no-op для
  cancel, но forensic должен зафиксировать попытку).

Связанные ADR:
- Зависит от: C-4 (CancelSubscriber), D-1 (PIIDetector), D-2 (OperationalStreamWriter),
  D-3 (ForensicStreamWriter), D-4 (KMS KeyProvider).
- Связывает: ADR-013 + ADR-014.
```

---

## 4. Блок D. ADR-014: Dual-Stream Logging — микро-декомпозиция

**Источник**: `ROADMAP.md` §5.4, `TRIZ-ANALYSIS.md` §7.1 + §11 (ADR-014). Резолвит противоречие C-11 (PII masking vs observability). Принципы ТРИЗ: 17, 3, 22, 26. Полная реализация: 6 подзадач, 4 чел-дн.

### D-1. PIIDetector (Presidio + custom regex)

```
Ты — Backend/Security-разработчик LLM Client. Создай PIIDetector — модуль детекции PII
на основе Microsoft Presidio + кастомных regex-правил.

Контекст:
- ADR-014 (TRIZ-ANALYSIS.md §7.1): operational stream маскируется через Presidio + custom
  regex. Forensic stream — без маскирования, шифруется целиком.
- ТРИЗ-принцип 22 (превращение вреда в пользу): PII detection — не только маскирование,
  но и аналитика (score сохраняется в messages.metadata, см. D-5).
- Presidio требует spaCy-модель (en_core_web_md или мультиязычная) — добавить в зависимости.

Задача:
1. Создай класс PIIDetector:
   - __init__(spacy_model: str = "en_core_web_md").
   - detect(text: str) -> PIIDetectionResult:
     * Запускает Presidio AnalyzerEngine с дефолтными recognizers (PERSON, EMAIL, PHONE,
       CREDIT_CARD, IBAN, IP_ADDRESS, US_SSN, URL).
     * Добавляет custom regex recognizers для внутренних форматов: employee_id
       (например, EMP-\d{6}), internal_project_code (PRJ-[A-Z]{3}-\d{4}).
     * Возвращает: PIIDetectionResult(score: float 0..1, entities: list[PIIEntity]).
   - mask(text: str) -> str:
     * Заменяет каждое найденное PII-вхождение на "[{entity_type}]" (например,
       "John Doe" → "[PERSON]", "john@example.com" → "[EMAIL]").
2. PIIDetectionResult:
   - score = (total_pii_chars / total_text_chars) — доля PII в тексте.
   - entities: list of {type, start, end, text (замаскированный)}.
3. Конфигурация через env: PII_DETECTOR_SPACY_MODEL, PII_DETECTOR_ENABLED=true|false.
4. Если PII_DETECTOR_ENABLED=false — detect() возвращает score=0, mask() возвращает
   text без изменений (для dev/test где Presidio не нужен).

Definition of Done:
- detect("My name is John Doe, email: john@example.com") находит PERSON и EMAIL.
- mask(...) заменяет оба на "[PERSON]" и "[EMAIL]".
- score корректно считается (длина PII / длина текста).
- Custom recognizers работают для EMP-123456 и PRJ-ABC-1234.
- При PII_DETECTOR_ENABLED=false detect/mask работают за <1 мс (no-op).
- Unit-тесты покрывают: пустую строку, только PII, без PII, мультиязычный текст (RU+EN).

Антипаттерны:
- НЕ используй spaCy-модель по умолчанию без явной установки в requirements — модель
  должна быть в зависимостях или загружаться при старте.
- НЕ логируй найденный PII-текст в logs (даже в debug) — это утечка PII в логи.
- НЕ используй пресеты Presidio "all" — избыточно, медленно; только нужные recognizers.
- НЕ маскируй forensic stream — он шифруется целиком, маскирование там избыточно.
- НЕ делай detect() синхронно в hot path запроса — кэшируй Presidio AnalyzerEngine в
  __init__, не создавай на каждый вызов.

Связанные ADR:
- Включает part of: ADR-014.
- Используется в: D-2 (OperationalStreamWriter), D-5 (PII score metadata).
```

### D-2. OperationalStreamWriter (маскированный → stdout/Loki/ELK)

```
Ты — Backend-разработчик LLM Client. Создай OperationalStreamWriter — пишет маскированные
логи в stdout/Loki/ELK, retention 30 дней.

Контекст:
- ADR-014 (TRIZ-ANALYSIS.md §7.1): operational stream — для команды, debugging, monitoring.
  Маскированный (через PIIDetector из D-1).
- ТРИЗ-принцип 17 (другое измерение): два потока, не один компромиссный.
- ТРИЗ-принцип 3 (местное качество): разные уровни маскирования для dev/staging/prod.

Задача:
1. Создай класс OperationalStreamWriter:
   - __init__(pii_detector: PIIDetector, sink: LogSink = StdoutSink()).
   - write(event: dict) -> None:
     * Сериализует event в JSON.
     * Прогоняет JSON-строку через pii_detector.mask() — маскирует PII в значениях.
     * Пишет в sink (stdout / Loki / ELK — абстракция через LogSink interface).
2. LogSink interface:
   - StdoutSink: print в stdout (default для dev).
   - LokiSink: HTTP POST в Loki /loki/api/v1/push (для staging/prod).
   - ELKSink: HTTP POST в Elasticsearch /_bulk (если уже есть ELK).
   - Конфигурация через env: OPERATIONAL_LOG_SINK=stdout|loki|elk,
     OPERATIONAL_LOG_LOKI_URL, OPERATIONAL_LOG_ES_URL.
3. Retention policy (не в коде writer-а, а в sink):
   - StdoutSink — нет retention, логи в docker logs.
   - LokiSink — retention 30 дней (настраивается в Loki config).
   - ELKSink — ILM policy 30 дней.
4. Async: write() должен быть async, не блокировать caller. Внутри — buffer + batch flush
   каждые 100 ms или 100 events.

Definition of Done:
- write(event) маскирует все PII в значениях (рекурсивно для nested dicts).
- Лог виден в stdout в dev через `docker-compose logs llm-client`.
- В staging с LOKI_URL — виден в Grafana Loki query.
- Batch flush работает: 1000 events/sec не вызывают OOM.
- retention 30 дней настроен в Loki/ELK (не в приложении).

Антипаттерны:
- НЕ пиши raw event без маскирования — даже в dev (privacy by default).
- НЕ используй Python logging module как sink — он синхронный, блокирует. Только
  structlog или custom async writer.
- НЕ храни operational логи в S3 — для этого есть forensic stream (D-3).
- НЕ дублируй логи в stdout И Loki одновременно — выбирается через env.
- НЕ пиши в operational stream события с session_id-ами, которые могут содержать PII
  (если session_id содержит email — маскируется как весь PII).

Связанные ADR:
- Зависит от: D-1 (PIIDetector).
- Используется в: C-6 (cancel event), всех caller-ах, которые логируют.
- Включает part of: ADR-014.
```

### D-3. ForensicStreamWriter (AES-256-GCM → S3, retention 90+ дней)

```
Ты — Backend/Security-разработчик LLM Client. Создай ForensicStreamWriter — шифрует
записи AES-256-GCM через KMS и пишет в отдельный S3 bucket, retention 90+ дней.

Контекст:
- ADR-014 (TRIZ-ANALYSIS.md §7.1): forensic stream — full trace для аудита, retention 90+
  дней, доступ через отдельный RBAC (security officer + аудит-комитет).
- ТРИЗ-принцип 26 (копирование): trace копируется дважды — masked operational + encrypted
  forensic.
- ТРИЗ-принцип 17: forensic в отдельном S3 bucket, не смешивается с operational.

Задача:
1. Создай класс ForensicStreamWriter:
   - __init__(kms_provider: KMSKeyProvider, s3_client: S3CompatibleStorage,
     bucket: str = S3_FORENSIC_BUCKET, enabled: bool = True).
   - write(event: dict) -> None:
     * Сериализует event в JSON (БЕЗ маскирования — full trace).
     * Шифрует через kms_provider.encrypt(data: bytes) -> EncryptedPayload.
     * Формирует объект: {ciphertext, iv, key_id, algorithm="AES-256-GCM"}.
     * Загружает в S3 с key = "forensic/{YYYY}/{MM}/{DD}/{session_id}/{timestamp}-{uuid}.json".
2. EncryptedPayload:
   - ciphertext: bytes.
   - iv: bytes (12 байт для GCM).
   - key_id: str (идентификатор ключа в KMS).
   - algorithm: "AES-256-GCM".
3. Batch: как и operational, buffer + flush каждые 500 ms или 50 events (реже, чем
   operational — forensic более тяжёлый из-за шифрования + S3).
4. enabled=False (dev mode) — write() no-op, логирует warning при старте.
5. S3 bucket должен иметь server-side encryption (SSE-S3 или SSE-KMS) — это второй слой
   шифрования, не заменяет application-level AES-256-GCM, но добавляет defence in depth.

Definition of Done:
- write(event) шифрует данные и пишет в S3 forensic bucket за <200 мс.
- Файл в S3 содержит ciphertext, iv, key_id, algorithm — НЕ plaintext.
- Через kms_provider.decrypt(EncryptedPayload) можно восстановить исходный event.
- retention 90 дней настроен в S3 lifecycle policy (проверка через aws s3api
  get-bucket-lifecycle-configuration).
- enabled=False в dev — write() no-op, в логах startup warning "Forensic stream disabled".
- При потере KMS — write() падает с ForensicWriteError, не проглатывает ошибку
  (forensic не может быть записан plain — лучше уронить запрос).

Антипаттерны:
- НЕ пиши plaintext в forensic "временно" — даже в dev, только enabled=false.
- НЕ шифруй в приложении без KMS — ключи НЕ в коде, НЕ в env, только KMS (Блок D-4).
- НЕ используй один IV для нескольких записей — генерируй новый IV на каждый encrypt.
- НЕ пиши в operational bucket — forensic изолирован, отдельный bucket, отдельный RBAC.
- НЕ делай forensic write синхронным в hot path запроса — async, не блокирует caller.
- НЕ проглатывай ошибки шифрования — forensic failure = request failure (privacy first).

Связанные ADR:
- Зависит от: D-4 (KMSKeyProvider), Блок A-2 (MinIO/S3 forensic bucket), расш. ADR-008
  (S3CompatibleStorage).
- Используется в: C-6 (cancel event), всех caller-ов с full trace.
- Включает part of: ADR-014.
```

### D-4. KMS/Vault KeyProvider

```
Ты — Security/Backend-разработчик LLM Client. Создай KMSKeyProvider — абстракцию над KMS
для шифрования/расшифрования forensic данных AES-256-GCM.

Контекст:
- ADR-014 (TRIZ-ANALYSIS.md §7.1): ключи в KMS/Vault, НЕ в приложении.
- В Phase 1 — local Vault dev-mode (Блок A-3) с transit engine.
- В Phase 5 — миграция на managed KMS (AWS KMS / GCP KMS). Интерфейс KeyProvider должен
  абстрагировать смену — это та самая "частичная имплементация" ТРИЗ-принципа 16
  (избыточная абстракция, частичная реализация), упомянутая в ROADMAP.md §13.1.

Задача:
1. Создай interface KMSKeyProvider:
   - encrypt(plaintext: bytes, context: dict | None = None) -> EncryptedPayload.
   - decrypt(payload: EncryptedPayload, context: dict | None = None) -> bytes.
   - rotate_key() -> str (возвращает новый key_id; старый остаётся валидным для decrypt).
2. Создай реализацию VaultTransitKeyProvider:
   - __init__(vault_client: hvac.Client, key_name: str = "forensic-aes256-gcm").
   - encrypt: POST transit/encrypt/{key_name} с plaintext (base64).
   - decrypt: POST transit/decrypt/{key_name} с ciphertext.
   - Возвращает EncryptedPayload с key_id из ответа Vault.
3. Создай реализацию LocalDevKeyProvider (для unit-тестов, НЕ для dev-окружения):
   - Генерирует AES-256-GCM ключ in-memory при init.
   - Шифрует/расшифровывает локально через cryptography.hazmat.
   - Только для тестов; в логах startup warning "USING LOCAL KEY — TEST ONLY".
4. Конфигурация через env: KMS_PROVIDER=vault|local, VAULT_ADDR, VAULT_TOKEN,
   VAULT_TRANSIT_KEY.
5. Key rotation: rotate_key() в Vault — обновляет версию ключа, старые ciphertext-ы
   расшифровываются через старую версию (Vault хранит все версии).

Definition of Done:
- encrypt("test") → decrypt(...) возвращает "test" round-trip.
- VaultTransitKeyProvider работает с Vault из Блока A-3 (dev-mode).
- LocalDevKeyProvider работает без Vault — для unit-тестов.
- При KMS_PROVIDER=vault и недоступном Vault — startup fails fast с понятной ошибкой.
- При rotate_key() старые ciphertext-ы всё ещё расшифровываются (проверка через тест).
- key_id в EncryptedPayload однозначно идентифицирует версию ключа.

Антипаттерны:
- НЕ храни ключи в env vars или config-файлах — только KMS.
- НЕ используй LocalDevKeyProvider вне тестов — добавь assert в __init__, что запуск
  только в pytest контексте.
- НЕ делай свой crypto — используй Vault transit engine или cryptography.hazmat (для
  LocalDevKeyProvider), никогда не пиши AES-implementation вручную.
- НЕ проглатывай ошибки расшифрования — log + raise, не возвращай None.
- НЕ кэшируйте ключи в приложении — Vault сам кэширует, лишний кэш = security risk.

Связанные ADR:
- Включает abstraction для: ADR-014 (D-3 forensic).
- Будет переиспользован в: Phase 5 (AWS KMS provider — просто новая реализация interface).
- Зависит от: Блок A-3 (Vault dev-mode).
```

### D-5. PII score в messages.metadata (DB migration)

```
Ты — Backend/разработчик LLM Client. Добавь PII score в metadata таблицы messages —
сохранять результат PIIDetector для каждого сообщения для последующей аналитики.

Контекст:
- ADR-014 (TRIZ-ANALYSIS.md §7.1): "PII detection score сохраняется в messages таблице
  как metadata для аналитики".
- ТРИЗ-принцип 22 (превращение вреда в пользу): PII detection — не только защита, но и
  аналитический сигнал (доля sensitive data в запросах).
- Существующая таблица messages (из ADR-001 LangGraph state) — добавить колонку metadata
  JSONB, не отдельную таблицу.

Задача:
1. Создай Alembic migration:
   - ALTER TABLE messages ADD COLUMN pii_score FLOAT DEFAULT NULL;
   - ALTER TABLE messages ADD COLUMN pii_entities JSONB DEFAULT NULL;
   - CREATE INDEX idx_messages_pii_score ON messages(pii_score) WHERE pii_score IS NOT NULL;
2. В существующий код, который пишет в messages (LangGraph state saver или wrapper):
   - Перед сохранением message прогоняй pii_detector.detect(message.content).
   - Сохраняй result.score в pii_score, result.entities (без текста PII, только типы и
     позиции) в pii_entities.
3. Запрети сохранять сам PII-текст в pii_entities — только {type, start, end}, без text.
4. Конфигурация: PII_METADATA_ENABLED=true|false. Если false — pii_score=NULL, pii_entities=NULL.
5. Добавь SQL-запрос для аналитики (в README или observability docs):
   ```sql
   SELECT
     DATE(created_at) AS day,
     AVG(pii_score) AS avg_pii_score,
     COUNT(*) FILTER (WHERE pii_score > 0.1) AS high_pii_messages
   FROM messages
   WHERE created_at > NOW() - INTERVAL '30 days'
   GROUP BY day ORDER BY day;
   ```

Definition of Done:
- Migration проходит на staging без ошибок и без блокировки writes >1 сек.
- После миграции новые messages содержат pii_score и pii_entities.
- Старые messages (до миграции) — pii_score=NULL (не ретроспективно).
- pii_entities НЕ содержит PII-текста — только типы и позиции.
- SQL-запрос из README работает и возвращает корректные данные.
- При PII_METADATA_ENABLED=false — колонки остаются NULL, приложение не падает.

Антипаттерны:
- НЕ сохраняй PII-текст в pii_entities — это утечка PII в БД (даже если БД зашифрована).
- НЕ делай отдельную таблицу pii_scores — JOIN замедляет аналитику, JSONB в messages OK.
- НЕ пересчитывай pii_score при каждом чтении messages — только при записи.
- НЕ используй FLOAT(53) — FLOAT достаточно, DOUBLE precision избыточна для score 0..1.
- НЕ забудь индекс по pii_score — аналитические запросы без него будут slow.

Связанные ADR:
- Зависит от: D-1 (PIIDetector).
- Связан с: ADR-001 (messages таблица LangGraph state).
- Включает part of: ADR-014.
```

### D-6. Dev-mode toggle (forensic отключён, только operational)

```
Ты — Backend-разработчик LLM Client. Реализуй dev-mode toggle для ADR-014: в dev-окружении
forensic stream отключён, работает только operational.

Контекст:
- ADR-014 (TRIZ-ANALYSIS.md §11): "В dev-окружении forensic stream отключён, только
  operational".
- ТРИЗ-принцип 3 (местное качество): разные уровни маскирования/логирования для разных
  окружений.
- Dev-mode = no Vault dependency (Vault из Блока A-3 опционален), faster startup, less
  infra для локальной разработки.

Задача:
1. Создай LogLevelConfig (или расширь существующий config):
   - ENVIRONMENT=dev|staging|prod (env var).
   - FORENSIC_STREAM_ENABLED=true|false (env var, default: dev=false, staging=prod=true).
2. В DI-контейнере приложения:
   - Если FORENSIC_STREAM_ENABLED=false:
     * ForensicStreamWriter инициализируется с enabled=False (write no-op).
     * KMSKeyProvider НЕ инициализируется (нет зависимости от Vault).
     * В логах startup: WARN "Forensic stream disabled — dev mode".
   - Если FORENSIC_STREAM_ENABLED=true:
     * ForensicStreamWriter с KMSKeyProvider (Vault).
     * При отсутствии Vault — startup fails fast.
3. OperationalStreamWriter — всегда enabled (в dev, staging, prod).
4. PIIDetector — всегда enabled (даже в dev, privacy by default).
5. В README раздел "Local dev without Vault": как поднять приложение только с Redis и
   MinIO, без Vault (для быстрых iteration).

Definition of Done:
- При ENVIRONMENT=dev + FORENSIC_STREAM_ENABLED=false: приложение стартует без Vault,
  forensic writes no-op, operational работает.
- При ENVIRONMENT=staging/prod + FORENSIC_STREAM_ENABLED=true: приложение требует Vault,
  при отсутствии fails fast с понятной ошибкой.
- При попытке выставить FORENSIC_STREAM_ENABLED=false в prod — startup fails
  (env var validation: prod → must be true).
- PIIDetector работает в обоих режимах (маскирование в operational всегда активно).
- В README есть инструкция для локального dev без Vault.

Антипаттерны:
- НЕ отключай PIIDetector в dev — privacy by default, даже разработчик не должен видеть
  raw PII в логах.
- НЕ позволяй FORENSIC_STREAM_ENABLED=false в prod — добавь валидацию.
- НЕ делай fallback на LocalDevKeyProvider в dev-mode для forensic — лучше совсем no-op,
  чтобы не было иллюзии что forensic работает.
- НЕ забывай warning в логах — silent no-op = будущий баг ("почему forensic пустой?").
- НЕ требуй Vault для unit-тестов — unit-тесты используют mock KMSKeyProvider.

Связанные ADR:
- Зависит от: D-3 (ForensicStreamWriter), D-4 (KMSKeyProvider), Блок A-3 (Vault).
- Включает part of: ADR-014.
```

---

## 5. Блок E. (расш. ADR-008): Single S3 Storage — микро-декомпозиция

**Источник**: `ROADMAP.md` §5.5, `TRIZ-ANALYSIS.md` §7.5. Резолвит противоречие C-15 (Local file storage vs multi-instance). Принципы ТРИЗ: 17, 13, 28, 5. Полная реализация: 4 подзадачи, 2 чел-дн (после B-2).

### E-1. S3CompatibleStorage полная реализация

```
Ты — Backend-разработчик LLM Client. Доведите S3CompatibleStorage (из B-2) до production
качества: все методы FileStorage interface, корректная обработка ошибок, multipart upload
для больших файлов.

Контекст:
- B-2 создал минимальную S3CompatibleStorage с базовыми save/get/delete/exists.
- Расш. ADR-008 (TRIZ-ANALYSIS.md §7.5) требует упразднения LocalFileStorage —
  S3CompatibleStorage должна покрыть все use-cases, которые покрывал LocalFileStorage.
- ТРИЗ-принцип 28 (замена механической схемы) + 5 (объединение): одна реализация, два
  deployment-режима (embedded MinIO для dev, external S3 для prod).

Задача:
1. Полная реализация S3CompatibleStorage (расширь то, что сделано в B-2):
   - save(file: bytes | BinaryIO, key: str, metadata: dict | None = None) -> str:
     * Если file > 5 МБ — multipart upload (boto3 upload_fileobj с auto-multipart).
     * metadata → S3 object metadata (Content-Type, custom x-amz-meta-*).
     * Возвращает key (или полный URL — зависит от существующего контракта).
   - get(key: str) -> bytes:
     * Streaming download для больших файлов (не загружать в память целиком если >100 МБ).
     * Возвращает bytes (контракт FileStorage); для streaming использовать get_stream().
   - get_stream(key: str) -> AsyncIterator[bytes]:
     * Дополнительный метод для streaming-чтения (если существующий FileStorage
       не имеет — добавь в interface, но с default реализацией через get()).
   - delete(key: str) -> None:
     * Idempotent — не падает если key не существует.
   - exists(key: str) -> bool:
     * Через HEAD object.
   - list(prefix: str) -> list[str]:
     * Дополнительный метод для listing (если нужен в caller-ах).
2. Обработка ошибок:
   - S3NotFoundError → raise FileNotFoundError (контракт FileStorage).
   - S3AccessDeniedError → raise PermissionError.
   - S3ConnectionError → retry 3 раза с экспоненциальной задержкой, затем raise
     StorageError.
3. Конфигурация:
   - S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET, S3_REGION (опционально для MinIO).
   - S3_PRESIGNED_URL_EXPIRY=3600 (для генерации временных ссылок если нужно).

Definition of Done:
- save/get/delete/exists покрыты unit-тестами с mock S3 (moto или LocalStack).
- Integration-тест с реальным MinIO (Блок A-2): round-trip файлов 1KB, 1MB, 50MB, 200MB.
- Multipart upload автоматически включается для файлов >5 МБ (проверка через S3 metadata).
- Streaming get_stream работает для 200 МБ файла без OOM.
- Ошибки корректно мапятся в FileNotFoundError/PermissionError/StorageError.
- Idempotent delete на несуществующем key не падает.

Антипаттерны:
- НЕ загружай большие файлы в memory целиком в get() — только streaming.
- НЕ хардкодь bucket в коде — через env.
- НЕ используй sync boto3 в async-контексте — aiobotocore.
- НЕ игнорируй metadata в save() — caller может передать Content-Type.
- НЕ делай list() recursive по умолчанию — только prefix match, иначе slow на больших
  bucket-ах.

Связанные ADR:
- Расширяет: B-2 (Quick Win 12.2).
- Включает part of: расш. ADR-008.
- Зависит от: Блок A-2 (MinIO).
```

### E-2. Удаление LocalFileStorage и миграция всех caller-ов

```
Ты — Backend-разработчик LLM Client. Удали LocalFileStorage из кодовой базы и мигрируй
все caller-ы на S3CompatibleStorage.

Контекст:
- B-2 добавил S3CompatibleStorage с feature-flag STORAGE_BACKEND=local|s3.
- Расш. ADR-008 (TRIZ-ANALYSIS.md §7.5, принципы 28+5): упразднить LocalFileStorage,
  оставить только S3CompatibleStorage.
- ROADMAP.md §5.6 критерий выхода из Phase 1: "LocalFileStorage удалён; dev/staging/prod
  используют S3-only".
- Это breaking change для dev-разработчиков: теперь у всех должен быть MinIO (Блок A-2).

Задача:
1. Найди все использования LocalFileStorage в кодовой базе (через grep).
2. Удали класс LocalFileStorage полностью.
3. Удали feature-flag STORAGE_BACKEND — теперь только S3.
4. В фабрике FileStorage оставь только создание S3CompatibleStorage.
5. Обнови все импорты LocalFileStorage → S3CompatibleStorage (если были прямые импорты).
6. В docker-compose dev-окружения: MinIO обязателен (Блок A-2), STORAGE_BACKEND удалён.
7. В .env.example обнови переменные: S3_ENDPOINT, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET
   обязательны для dev.
8. В README раздел "Local dev setup": обнови инструкцию, MinIO теперь обязательный
   сервис.
9. Удали тесты для LocalFileStorage — они больше не нужны.

Definition of Done:
- `grep -r "LocalFileStorage" src/` возвращает 0 совпадений.
- `grep -r "STORAGE_BACKEND" src/` возвращает 0 совпадений.
- Все unit-тесты проходят с MinIO (Блок A-2 запущен).
- Все integration-тесты проходят.
- В .env.example чётко указано: MinIO обязателен для dev.
- README обновлён: новая инструкция для local dev setup.

Антипаттерны:
- НЕ оставляй LocalFileStorage "на всякий случай" — это нарушает принцип 5 (объединение),
  ТРИЗ-явный anti-pattern.
- НЕ делай migration постепенно (один PR на caller) — одним PR, atomic change, иначе
  код в transition состоянии надолго.
- НЕ сохраняй feature-flag "для тестов" — для тестов есть InMemoryFileStorage (E-3).
- НЕ удаляй тесты LocalFileStorage "потом" — в этом же PR.
- НЕ забудь обновить CI конфиг — MinIO должен быть в services: в GitHub Actions /
  GitLab CI для прогона тестов.

Связанные ADR:
- Завершает: расш. ADR-008 (упразднение LocalFileStorage).
- Упраздняет: ADR-008 partial (LocalFileStorage часть).
- Зависит от: E-1 (полная S3CompatibleStorage), E-3 (InMemoryFileStorage для тестов),
  Блок A-2 (MinIO).
```

### E-3. InMemoryFileStorage test-double для unit-тестов

```
Ты — Backend/Test-разработчик LLM Client. Создай InMemoryFileStorage — test-double для
unit-тестов, заменяющий S3CompatibleStorage без внешних зависимостей.

Контекст:
- После E-2 LocalFileStorage удалён — теперь в тестах нельзя использовать "локальный"
  storage.
- ТРИЗ-принцип 9 (предварительное противодействие): test-double готов заранее, до
  удаления LocalFileStorage, чтобы не сломать тесты.
- InMemoryFileStorage — НЕ production-код, только test fixture. Должен быть в
  tests/doubles/ или src/test_utils/, не в основной src/.

Задача:
1. Создай класс InMemoryFileStorage, реализующий тот же FileStorage interface:
   - save(file, key, metadata=None) -> str: сохраняет в dict in-memory.
   - get(key) -> bytes.
   - get_stream(key) -> Iterator[bytes].
   - delete(key) -> None.
   - exists(key) -> bool.
   - list(prefix) -> list[str].
   - clear() -> None (для сброса между тестами).
2. Thread-safe (используй threading.Lock или asyncio.Lock если async interface).
3. Не поддерживает metadata持久化 — просто игнорирует (или хранит в dict для проверки).
4. Не поддерживает TTL, persistence, multipart — все операции O(1) в памяти.
5. В conftest.py добавь fixture file_storage, возвращающий InMemoryFileStorage:
   ```python
   @pytest.fixture
   def file_storage():
       return InMemoryFileStorage()
   ```
6. Все unit-тесты, использующие FileStorage, должны принимать file_storage fixture.

Definition of Done:
- InMemoryFileStorage проходит все unit-тесты, которые ранее проходил LocalFileStorage.
- 1000 saves + 1000 gets в InMemoryFileStorage выполняются за <100 мс.
- fixture file_storage доступна во всех тестовых модулях.
- Нет внешних зависимостей (только Python stdlib).
- В коде InMemoryFileStorage есть docstring: "Test double. Do not use in production."

Антипаттерны:
- НЕ используй InMemoryFileStorage в production-коде — добавь assert в __init__ или
  маркер в имени модуля (test_utils/), чтобы исключить случайный импорт.
- НЕ делай InMemoryFileStorage persistent между тестами — clear() в fixture teardown.
- НЕ реализуй сложную логику (multipart, retries) — это test-double, простой dict.
- НЕ наследуй InMemoryFileStorage от S3CompatibleStorage — независимая реализация
  interface.
- НЕ используй InMemoryFileStorage в integration-тестах — там реальный MinIO.

Связанные ADR:
- Включает test infrastructure для: расш. ADR-008 (после E-2).
- Используется в: всех unit-тестах с FileStorage dependency.
```

### E-4. S3 access logs → forensic stream (интеграция с D-3)

```
Ты — Backend/Security-разработчик LLM Client. Настрой S3 access logs так, чтобы они
попадали в forensic stream (D-3) для полного аудита файловых операций.

Контекст:
- Расш. ADR-014 (TRIZ-ANALYSIS.md §7.5, эффект): "Аудитируемость: S3 access logs
  интегрируются в forensic stream".
- S3 access logs содержат: кто, когда, какой объект, какой операцией (GET/PUT/DELETE).
- Для аудита важно знать: кто обращался к forensic bucket, не было ли несанкционированных
  доступов.
- ТРИЗ-принцип 23 (обратная связь): мониторинг обращений к forensic = защита forensic.

Задача:
1. На MinIO включи server logging для bucket llm-client-forensic:
   - В docker-compose MinIO добавь env: MINIO_SERVER_LOGGING_TARGET=https://llm-client/...
     или через `mc admin config set` (для dev).
   - Для prod AWS S3 — включи S3 Server Access Logging на bucket, target = тот же
     forensic bucket в prefix `_access_logs/`.
2. Создай AccessLogIngestor (фоновой таск в LLM Client):
   - Раз в 5 минут читает новые access log entries из S3 (или webhook от MinIO).
   - Для каждой записи формирует event:
     {
       "event_type": "s3_access",
       "bucket": str,
       "key": str,
       "operation": "GET" | "PUT" | "DELETE" | ...,
       "requester": str,  # IAM user / IP
       "timestamp": ISO-8601,
       "request_id": str,
       "bytes_transferred": int
     }
   - Передаёт в ForensicStreamWriter (D-3) — шифруется и пишется в forensic stream.
3. Alerting: если requester не в allow-list (только LLM Client service account + security
   officer) — alert в Slack #security.

Definition of Done:
- При GET/PUT/DELETE на forensic bucket — запись появляется в forensic stream за <10 мин
  (период ингестинга).
- Access log запись содержит все 7 полей из спецификации.
- Если requester не в allow-list — alert в Slack #security (можно через webhook).
- В dev (MinIO) — access logs доступны через `mc admin trace`.
- В prod (AWS S3) — access logs в S3 _access_logs/ prefix, ингестируются AccessLogIngestor.

Антипаттерны:
- НЕ пиши access logs в operational stream — они не PII-bearing, но могут содержать
  имена файлов с PII в названии (редко, но возможно). Только forensic.
- НЕ делай ингестинг каждую секунду — S3 API имеет rate limits, 5 минут достаточно.
- НЕ храни access logs в plaintext — даже в forensic bucket отдельным prefix, всегда
  шифровать через ForensicStreamWriter.
- НЕ игнорируй alerting — если allow-list violation не алертится, forensic теряет смысл.
- НЕ забудь логировать самого AccessLogIngestor (что он запущен, что ингестирует) —
  иначе сбой останется незамеченным.

Связанные ADR:
- Зависит от: D-3 (ForensicStreamWriter), расш. ADR-008 (S3 bucket), Блок A-2 (MinIO).
- Связывает: расш. ADR-008 + ADR-014.
```

---

## 6. Блок F. Тесты и CI для Phase 1

**Источник**: `ROADMAP.md` §5.6 (критерии выхода), §18.2 (метрика идеальности). Покрывает три ADR-критерия: cancel latency <100ms в 99%, PII leaks = 0, MinIO parity.

### F-1. Тест cancel latency <100ms в 99% (k6 / pytest-asyncio)

```
Ты — QA/Automation-разработчик LLM Client. Создай нагрузочный тест, проверяющий что cancel
срабатывает за <100 мс в 99% случаев на staging-нагрузке (ROADMAP.md §5.6 п.1).

Контекст:
- ADR-013 (ROADMAP.md §5.3): критерий готовности — cancel срабатывает за <100 мс в 99%
  случаев; partial answer возвращается пользователю.
- Staging-нагрузка: 50 параллельных сессий, 10 RPS новых сессий, каждая сессия 30-60 сек.
- Нужно измерить end-to-end latency: от POST /cancel до фактической остановки графа.

Задача:
1. Создай pytest-asyncio integration-тест (предпочтительно) ИЛИ k6-скрипт (если нужен
   больший RPS):
   - Запускает 50 параллельных LLM-сессий через POST /sessions (с existing test fixtures).
   - Для каждой сессии через 5 сек после старта шлёт POST /sessions/{id}/cancel.
   - Замеряет latency: timestamp POST /cancel отправки → timestamp получения последнего
     SSE-chunk (после cancel).
   - Собирает 1000 сэмплов, считает p50, p95, p99.
2. Дополнительно проверяет:
   - partial answer возвращается (SSE-stream закрыт корректно, не оборван).
   - forensic stream (если включён) содержит запись session_cancelled.
   - operational stream содержит запись без PII.
3. Запускается только на staging (не в unit-тестах, не в dev). CI-markers: @pytest.mark.
   staging_load или k6 stage: staging.
4. В CI: запускается nightly job + manually перед релизом Phase 1.

Definition of Done:
- 1000 сэмплов собираются за <10 минут.
- p99 latency <100 мс — критерий PASS.
- p50, p95 reported в CI артефактах (JSON-отчёт).
- При FAIL (p99 >100ms) — CI job exit code != 0.
- partial answer возвращается в 100% случаев (не обрыв без ответа).
- forensic запись о cancel присутствует в 100% случаев (если forensic enabled).

Антипаттерны:
- НЕ запускай тест в unit-тестах — нужны реальные Redis, MinIO, Vault (Блок A-1..A-3).
- НЕ используй sleep() для ожидания cancel — event-driven (ждать последний SSE-chunk).
- НЕ замеряй latency только на стороне клиента — это network latency, не cancel latency.
  Замеряй от POST /cancel до последнего SSE-chunk.
- НЕ запускай тест в GitHub Actions без services (Redis, MinIO, Vault) — нужен staging.
- НЕ уменьшай sample size для скорости — 1000 сэмплов нужно для p99 статистики.

Связанные ADR:
- Тестирует: ADR-013 (Блок C).
- Зависит от: Блок A-1..A-3 (infra), Блок C-1..C-6 (реализация).
```

### F-2. Автоматизированный PII leak audit (Presidio analyzer по operational logs)

```
Ты — QA/Security-разработчик LLM Client. Создай автоматизированный тест-аудит: проверяет,
что в operational stream НЕТ PII-утечек после маскирования (через PIIDetector из D-1).

Контекст:
- ADR-014 (ROADMAP.md §5.6 п.2): критерий готовности — PII leaks в operational stream = 0
  (автоматизированный audit).
- ADR-014 (TRIZ-ANALYSIS.md §7.1): operational stream маскируется, forensic шифруется.
- Тест должен поймать регрессию: если PIIDetector упустил тип PII, тест FAIL.

Задача:
1. Создай pytest-тест test_pii_leak_audit:
   - Поднимает dev-окружение с OPERATIONAL_LOG_SINK=stdout (или buffer sink для тестов).
   - Загружает набор тестовых messages с известными PII: имя, email, телефон, credit card,
     IBAN, IP, SSN, URL, employee_id (EMP-\d{6}), project_code (PRJ-[A-Z]{3}-\d{4}).
   - Каждое message прогоняет через OperationalStreamWriter.write().
   - Собирает все записи из stdout/buffer.
   - Прогоняет Presidio AnalyzerEngine по каждой записи (в audit mode, не masking mode).
   - Если найдено хоть одно PII-вхождение — тест FAIL с указанием где и какой тип.
2. Покрытие типов PII: PERSON, EMAIL, PHONE, CREDIT_CARD, IBAN, IP_ADDRESS, US_SSN, URL,
   EMPLOYEE_ID (custom), PROJECT_CODE (custom).
3. Запускается в CI на каждом PR (unit-уровень) + nightly на staging (integration).
4. При FAIL: артефакт с leak sample (masked) + stack trace до writer-а.

Definition of Done:
- 100% тестовых messages с PII — маскируются в operational stream.
- 0 leaks после прогона Presidio analyzer.
- Все 10 типов PII покрыты тест-кейсами.
- При добавлении нового типа PII (расширение custom recognizers) — тест автоматически
  проверяет что masking работает.
- CI job exit code != 0 при leak.
- В CI-артефактах: JSON-отчёт с leaks (если есть) с masked samples.

Антипаттерны:
- НЕ используй тот же PIIDetector для audit что и для masking — это self-test, нужен
  independent analyzer (можно Presidio с другим spacy-моделью или другим recognizers
  set).
- НЕ маскируй leak samples в отчёте полностью — оставь тип PII и позицию для debug.
- НЕ пропускай тест "потому что в dev нет PII" — это regression protection.
- НЕ запускай только на staging — нужен и unit (быстрый feedback) и integration.
- НЕ забудь custom recognizers — standard Presidio их не найдёт.

Связанные ADR:
- Тестирует: ADR-014 (Блок D), особенно D-1 (PIIDetector) и D-2 (OperationalStreamWriter).
- Зависит от: Блок A-1..A-3 (infra для integration), D-1, D-2.
```

### F-3. MinIO parity test (один FileStorage контракт dev/staging/prod)

```
Ты — QA/разработчик LLM Client. Создай parity-тест: один и тот же набор операций
FileStorage проходит на dev (MinIO), staging (MinIO external), prod (S3), доказывая что
контракт один (расш. ADR-008).

Контекст:
- Расш. ADR-008 (ROADMAP.md §5.6 п.3): критерий выхода — "LocalFileStorage удалён;
  dev/staging/prod используют S3-only".
- TRIZ-ANALYSIS.md §7.5 (эффект): "Dev-prod parity: одно хранилище, одно поведение".
- Тест должен гарантировать что миграция dev→staging→prod не ломает поведение.

Задача:
1. Создай parametrized pytest test_filestorage_parity:
   - Параметризация через env FILESTORAGE_BACKEND=target (minio_dev, minio_staging, s3_prod).
   - Набор операций: save→get→exists→delete→exists, save large file (50MB), save metadata,
     list prefix, get_stream, concurrency test (10 parallel saves).
   - Каждая операция сравнивается с expected behavior (одинаковым для всех backend-ов).
2. Запускается в 3 режимах:
   - dev: MinIO из docker-compose (Блок A-2).
   - staging: external MinIO (staging cluster).
   - prod: S3 (через staging account, не real prod — для parity check).
3. CI matrix: 3 parallel jobs (dev/staging/prod), все должны PASS.
4. Дополнительно: проверяет что LocalFileStorage удалён из кода (import test должен FAIL
   при попытке `from llm_client.storage import LocalFileStorage`).

Definition of Done:
- 3 jobs dev/staging/prod проходят одинаковый набор операций.
- Все операции возвращают одинаковый результат (с точностью до S3-specific metadata).
- Large file (50MB) round-trip работает на всех 3 backend-ах.
- Concurrency test: 10 parallel saves не теряют данные, не интерферируют.
- Import test LocalFileStorage FAILS с ImportError.
- CI matrix виден в PR check (3 green checks).

Антипаттерны:
- НЕ использую разные тест-кейсы для разных backend-ов — это ломает parity idea.
- НЕ игнорируй minor differences (например, S3 returns ETag, MinIO может не возвращать) —
  тест должен либо игнорировать (с явным comment), либо фиксировать как known issue.
- НЕ пропускай prod parity test "потому что дорого" — это критерий выхода из Phase 1.
- НЕ забудь cleanup после теста (delete test objects из bucket).
- НЕ используй real prod bucket для теста — staging-account-mimicking-prod достаточно.

Связанные ADR:
- Тестирует: расш. ADR-008 (Блок E), особенно E-1 (S3CompatibleStorage) и E-2 (удаление
  LocalFileStorage).
- Зависит от: Блок A-2 (MinIO), Блок E-1..E-3.
```

### F-4. CI pipeline для Phase 1 (запуск infra + tests на PR)

```
Ты — DevOps/CI-разработчик LLM Client. Настрой CI pipeline для Phase 1: на каждый PR
запускаются Блок A (infra), Блок F-1..F-3 (тесты), блокируется merge при FAIL.

Контекст:
- ROADMAP.md §5.6: 3 критерия выхода из Phase 1 — все должны проверяться в CI.
- ROADMAP.md §18.2: метрика идеальности в Grafana + Slack alerting — отдельный pipeline
  (nightly).
- CI должен быть воспроизводимым: тот же набор шагов на dev-машинах через docker-compose.

Задача:
1. Создай .github/workflows/phase1-ci.yml (или эквивалент для GitLab CI):
   - Triggers: pull_request to main, push to main.
   - Jobs:
     a) lint-and-unit: ruff/mypy + unit-тесты с InMemoryFileStorage (E-3), без внешних
        сервисов. <2 мин.
     b) integration-dev: docker-compose up Redis + MinIO + Vault (Блок A-1..A-3) →
        integration-тесты dev-режима (FORENSIC_STREAM_ENABLED=false). <5 мин.
     c) integration-staging: то же, но FORENSIC_STREAM_ENABLED=true (с Vault). <10 мин.
     d) pii-leak-audit: F-2. <3 мин.
     e) minio-parity: F-3 (только dev-часть, staging/prod — nightly). <5 мин.
   - Все jobs параллельны, кроме зависимостей.
   - При FAIL любого job — PR заблокирован для merge.
2. Создай .github/workflows/phase1-nightly.yml:
   - Triggers: nightly at 03:00 UTC.
   - Jobs:
     a) cancel-latency-staging: F-1 (на staging-окружении).
     b) minio-parity-full: F-3 (dev + staging + prod-like).
     c) idealidad-metric: collect metrics → Grafana → Slack alert if trend down.
3. Кэширование: pip cache, docker layers, spacy models — для ускорения.
4. Artefacts: junit XML, coverage HTML, leak-audit JSON, latency report JSON — хранить
   30 дней.

Definition of Done:
- PR-pipeline завершается за <15 минут (parallel jobs).
- Nightly pipeline завершается за <30 минут.
- При FAIL — понятное сообщение в PR с ссылкой на artefact.
- Coverage report показывает % покрытия ADR-013, ADR-014, расш. ADR-008.
- Slack alerting в #architecture при падении idealidad metric.
- Локальный запуск `make ci-local` поднимает тот же docker-compose + pytest — для
  отладки failing tests без push.

Антипаттерны:
- НЕ делай sequential jobs — все независимые должны идти параллельно.
- НЕ используй self-hosted runners для PR-pipeline — GitHub-hosted достаточно, security.
- НЕ хардкодй secrets в workflow — через GitHub Secrets / GitLab Variables.
- НЕ пропускай nightly job "потому что weekend" — метрика идеальности важна.
- НЕ забудь cleanup docker-compose после тестов (down -v) — иначе runner забивается.

Связанные ADR:
- Покрывает CI для: всех ADR Phase 1 (ADR-013, ADR-014, расш. ADR-008).
- Зависит от: Блок A (infra), Блок F-1..F-3 (тесты).
```

---

## 7. Блок G. Документация и метрика идеальности

**Источник**: `ROADMAP.md` §5.6 п.5 (документация обновлена), §18.2 (метрика идеальности в Grafana).

### G-1. Обновление ARCHITECT.md §7 / §8 / §12 после Phase 1

```
Ты — Tech-писатель / архитектор LLM Client. Обнови ARCHITECT.md после завершения Phase 1:
добавь новые ADR, пометь противоречия как resolved, закрой открытые вопросы.

Контекст:
- ROADMAP.md §5.6 п.5: "ARCHITECT.md § 7 ADR обновлён (ADR-013, ADR-014 добавлены; ADR-008
  расширен); § 8 Trade-offs обновлён (C-4, C-11, C-15 помечены как resolved)".
- ROADMAP.md §18.5: "После approval каждого ADR — обновление ARCHITECT.md. Срок: 1 день
  после approval."
- Документация должна отражать новое состояние архитектуры, не противоречить ROADMAP/TRIZ.

Задача:
1. В §7 ADR ARCHITECT.md:
   - Добавь ADR-013 (SSE + HTTP Cancel Endpoint) — Status: Approved.
   - Добавь ADR-014 (Dual-Stream Logging) — Status: Approved.
   - Расширь ADR-008: добавь секцию "Phase 1 Update: LocalFileStorage упразднён, остаётся
     только S3CompatibleStorage (расш. ADR-008)".
   - Для каждого нового ADR — Context, Decision, Consequences (как в TRIZ-ANALYSIS.md §11).
2. В §8 Trade-offs:
   - C-4 (SSE one-way vs interactivity) → пометить [RESOLVED by ADR-013 in Phase 1].
   - C-11 (PII masking vs observability) → пометить [RESOLVED by ADR-014 in Phase 1].
   - C-15 (Local file storage vs multi-instance) → пометить [RESOLVED by расш. ADR-008 in
     Phase 1].
   - Каждое противоречие — оставить как есть (для исторического контекста), добавить
     markdown-зачёркивание или [RESOLVED] метку.
3. В §12 Открытые вопросы:
   - Q-2 (LangSmith pricing) → [CLOSED: ADR-014 DualStreamLogger — собственный
     observability, не зависит от LangSmith].
   - Q-3 (Streamlit + async) → частично [CLOSED: ADR-013 — cancel через Redis pub/sub,
     не Streamlit native; полное закрытие в Phase 5 через ADR-018].
4. В §13 (если есть компонентная диаграмма) — обновить: добавить Redis, MinIO, Vault как
   инфра-сервисы, добавить CancelEndpoint, DualStreamLogger.
5. Согласованность с ROADMAP.md:
   - В §7 ARCHITECT.md для каждого ADR — ссылка на соответствующий § в ROADMAP.md (где
     описана фаза) и TRIZ-ANALYSIS.md (где описано противоречие).

Definition of Done:
- ARCHITECT.md версия обновлена (1.0.0 → 1.1.0) с changelog.
- §7 содержит ADR-013, ADR-014 (новые) и обновлённый ADR-008.
- §8 содержит 3 помеченных [RESOLVED] противоречия.
- §12 содержит 2 закрытых Q (Q-2 полностью, Q-3 частично с пояснением).
- Компонентная диаграмма (если есть) обновлена.
- Все ссылки на ROADMAP.md / TRIZ-ANALYSIS.md — корректны (не 404).
- PR с обновлением reviewed архитектурным комитетом, merged.

Антипаттерны:
- НЕ удаляй старые Trade-offs — оставь для исторического контекста с [RESOLVED] меткой.
- НЕ скрывай упразднённые ADR (LocalFileStorage часть ADR-008) — явно пометь "упразднено
  в Phase 1".
- НЕ переписывай существующие ADR-001..ADR-008 — только добавляй новые и расширяй.
- НЕ добавляй ADR из Phase 2+ (ADR-010, ADR-011, ...) — только Phase 1 ADR.
- НЕ забудь changelog — без него невозможно отследить что изменилось.

Связанные ADR:
- Документирует: ADR-013, ADR-014, расш. ADR-008.
- Ссылается на: ROADMAP.md §5, TRIZ-ANALYSIS.md §5.4, §7.1, §7.5, §11.
```

### G-2. Grafana dashboard с метрикой идеальности + Slack alerting

```
Ты — DevOps/Observability-разработчик LLM Client. Создай Grafana dashboard с метрикой
идеальности Δф/Δсложности (ROADMAP.md §18.2) + Slack alerting при падении trend.

Контекст:
- ROADMAP.md §15.1: метрика идеальности = Δфункциональности / Δсложности.
- ROADMAP.md §15.2: контрольная точка Phase 1 — Δф/Δсложности ≥ 2.0 (2 new capabilities /
  1 new dependency).
- ROADMAP.md §18.2: "дашборд в Grafana, алертинг в Slack #architecture при падении trend".
- Источники данных: Git (LOC + ADR count), код (capability count через grep маркеров),
  Jira/Linear (story points completed).

Задача:
1. Создай метрики (через Prometheus exporter или script-cron):
   - llm_client_loc_total: lines of code (без тестов, без vendor) — через `cloc`.
   - llm_client_adr_count_total: количество ADR в ARCHITECT.md (grep "## ADR-").
   - llm_client_capability_count: количество capabilities (через grep "@capability" в
     коде или явный реестр).
   - llm_client_dependency_count: количество external dependencies (из pyproject.toml).
   - llm_client_idealidad_ratio: derived metric = (Δcapability / Δdependency).
2. Grafana dashboard (JSON model):
   - Panel 1: idealidad_ratio trend (graph, последние 6 месяцев).
   - Panel 2: capability_count vs dependency_count (stacked bar).
   - Panel 3: LOC + ADR count (dual axis).
   - Panel 4: per-Phase breakdown (Phase 1 = 2.0, Phase 2 = 1.5, Phase 3 = 1.33, ...).
   - Annotations: границы фаз (vertical lines).
3. Slack alerting (через Grafana alerting → Slack webhook):
   - Alert: idealidad_ratio < 1.0 за последние 2 недели (trend down).
   - Alert: dependency_count вырос на >2 за неделю (potential over-engineering).
   - Channel: #architecture.
   - Message: "Architecture idealidad trend down: {ratio}. Review recent ADR approvals.
     See: {grafana_url}".
4. Сбор метрик: cron-скрипт раз в сутки, push в Prometheus pushgateway (или direct DB
   write если используете Postgres-metrics).

Definition of Done:
- Dashboard доступен по ссылке в Confluence / internal wiki.
- Метрики обновляются раз в сутки (или чаще если есть CI trigger).
- Trend visible за последние 6 месяцев (с annotations границ фаз).
- Slack alerting: при искусственном понижении метрики (например, добавили 5 зависимостей
  без новых capabilities) — alert приходит в течение 24 часов.
- В Phase 1 control point (после завершения) — visible check: ratio ≥ 2.0 (2 caps / 1 dep).

Антипаттерны:
- НЕ считай LOC включая тесты и vendor-код — только production code.
- НЕ делай alert на каждое изменение метрики — только на trend (2 недели window).
- НЕ забудь annotations границ фаз — без них trend непонятен.
- НЕ используй ручной ввод метрик — только автоматический сбор (cron / CI step).
- НЕ привязывай метрику к конкретному ADR — это aggregated metric, не per-ADR KPI.

Связанные ADR:
- Не ADR-specific, инфраструктурная задача.
- Источник требования: ROADMAP.md §15.1, §15.2, §18.2.
```

---

## 8. Приложение: чек-лист выхода из Phase 1

**Источник**: `ROADMAP.md` §5.6. Используется после прогона всех блоков A–G для самопроверки перед ревью архитектурным комитетом.

| # | Критерий | Где проверяется | Соответствующий блок промптов |
|---|---|---|---|
| 1 | ADR-013 Approved: cancel latency <100 мс в 99% случаев на staging | F-1 nightly | Блок C + F-1 |
| 2 | ADR-013: partial answer возвращается пользователю | C-4 (manual test) | Блок C |
| 3 | ADR-013: forensic stream фиксирует cancel-событие с reason | C-6 (manual query forensic bucket) | C-6 |
| 4 | ADR-014 Approved: PII leaks = 0 (automated audit) | F-2 в CI | Блок D + F-2 |
| 5 | ADR-014: forensic stream доступен security officer в течение 24 часов | manual (запрос + расшифровка) | D-3, D-4 |
| 6 | ADR-014: retention forensic 90 дней обеспечен | S3 lifecycle policy check | D-3 |
| 7 | расш. ADR-008 Approved: LocalFileStorage удалён | `grep -r LocalFileStorage src/` = 0 | E-2 |
| 8 | расш. ADR-008: dev/staging/prod используют S3-only | F-3 parity test PASS | E-1, F-3 |
| 9 | Метрика идеальности: Δф/Δсложности = 2/1 = 2 ≥ 1 | G-2 Grafana dashboard | G-2 |
| 10 | Документация обновлена: ARCHITECT.md §7, §8, §12 | PR merged | G-1 |
| 11 | Все ADR Phase 1: Status Approved в ARCHITECT.md | manual check | G-1 |

**При невыполнении любого из п.1–8**: фаза продлевается на 1 sprint (ROADMAP.md §5.6).
**При невыполнении п.9**: ADR пересматривается (вероятный over-engineering, ROADMAP.md §13.1).
**При невыполнении п.10–11**: документационный долг, блокирует старт Phase 2.

---

## 9. Карта промптов для быстрого навигации

| ID | Промпт | Зависимости | Срок (чел-дн) |
|---|---|---|---|
| A-1 | Redis в docker-compose | — | 0.25 |
| A-2 | MinIO в docker-compose | — | 0.25 |
| A-3 | Vault dev-mode | — | 0.5 |
| B-1 | Quick Win 12.1: cancel minimal | A-1 | 1 |
| B-2 | Quick Win 12.2: S3 minimal | A-2 | 1 |
| B-3 | Quick Win 12.3: cycle detection | — | 1.5 |
| C-1 | CancellationToken abstraction | — | 0.25 |
| C-2 | HTTP POST /cancel endpoint | A-1, C-1 | 0.25 |
| C-3 | CancelPublisher (Redis pub/sub) | A-1 | 0.25 |
| C-4 | CancelSubscriber (graph) | C-1, C-3 | 0.5 |
| C-5 | UI watcher (visibilitychange) | C-2 | 0.5 |
| C-6 | Cancel → forensic logging | C-4, D-3 | 0.25 |
| D-1 | PIIDetector (Presidio + regex) | — | 0.5 |
| D-2 | OperationalStreamWriter | D-1 | 0.5 |
| D-3 | ForensicStreamWriter | D-4, E-1, A-2 | 0.75 |
| D-4 | KMS/Vault KeyProvider | A-3 | 0.5 |
| D-5 | PII score в messages.metadata | D-1 | 0.5 |
| D-6 | Dev-mode toggle | D-3, D-4 | 0.25 |
| E-1 | S3CompatibleStorage full | A-2, B-2 | 0.5 |
| E-2 | Удаление LocalFileStorage | E-1, E-3 | 0.5 |
| E-3 | InMemoryFileStorage test-double | — | 0.25 |
| E-4 | S3 access logs → forensic | D-3, E-1 | 0.5 |
| F-1 | Cancel latency <100ms test | Блок C, A-1..A-3 | 0.5 |
| F-2 | PII leak audit | D-1, D-2 | 0.5 |
| F-3 | MinIO parity test | E-1, E-2 | 0.5 |
| F-4 | CI pipeline Phase 1 | Блоки A, C, D, E, F-1..F-3 | 0.5 |
| G-1 | ARCHITECT.md update | Блоки C, D, E completed | 0.25 |
| G-2 | Grafana idealidad dashboard | — | 0.5 |
| **Итого** | **27 промптов** | | **~12.5 чел-дн** (с overlap параллельных задач) |

**Параллелизация (ROADMAP.md §11.2)**: при команде 2 разработчика — 8 чел-дн на ADR-013 + ADR-014 + расш. ADR-008, плюс 7 чел-дн на Quick Wins = 15 чел-дн за 1 sprint. Блоки F и G добавляют ~2.5 чел-дн, выполняясь в конце фазы.


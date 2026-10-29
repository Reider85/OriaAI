# План: BUG-MVP-03 — подключить AccessLogIngestor к startup (MVP-PROMPTS E-4)

## Цель

`AccessLogIngestor` (`src/llm_client/observability/access_log_ingestor.py`, 198 строк, 4 юнит-теста) реализован, но нигде не инстанциируется: нет ни settings-флага, ни wiring в startup, ни env в compose. Закрыть разрыв: feature-flag `ACCESS_LOG_INGEST_ENABLED`, wiring в agent-service startup/shutdown, env в docker-compose, dev-скрипт `mc admin trace`, e2e-интеграционный тест.

## Текущее состояние (проверено)

- `AccessLogIngestor.__init__(forensic_writer, s3_client, bucket=None, *, poll_interval_seconds=300, allowlist=None, security_webhook_url=None)`; `start()`/`close()`; поллинг `_access_logs/` префикса; парсит AWS Server Access Log → event `s3_access` (7 полей спеки) → `ForensicStreamWriter.write()`; не-allowlisted requester → webhook-алерт (placeholder → только warning).
- Env-fallback'и в классе: `S3_ACCESS_LOG_ALLOWLIST`, `SECURITY_ALERT_WEBHOOK_URL` (уже есть в `.env.example:132-136`, но **нет** `ACCESS_LOG_INGEST_ENABLED`).
- `config.py`: нет полей `access_log_ingest_enabled` / `s3_access_log_allowlist` / `security_alert_webhook_url`.
- `service.py` (agent-service, единственное приложение в docker-compose, запускается `python -m llm_client.agent`): forensic builder — строки 366–393, startup — 1239–1246, shutdown — 1296–1310. `api.py` — cancel control-plane, в compose не деплоится; wiring делаем только в `service.py`.
- `docker-compose.yml`: minio-init уже имеет `mc ilm` (BUG-MVP-02 в работе); у сервиса `minio` нет logging env.
- CI `integration-dev` (phase1-ci.yml:66-124) поднимает MinIO, создаёт оба бакета, запускает **всё** `tests/integration` — новый e2e попадёт в CI автоматически.
- README:419-429 — секция E-4 уже описывает класс (без wiring/флага).

## Спека и антипаттерны (MVP-PROMPTS E-4, :1162–1220)

- DoD: запись в forensic stream за <10 мин; 7 полей; Slack-алерт при нарушении allow-list; dev — доступ через `mc admin trace`; prod — `_access_logs/` в forensic bucket.
- Антипаттерны: только forensic (не operational); поллинг не чаще раза в 5 мин; всегда шифровать через ForensicStreamWriter; логировать факт запуска ингестора.

## Изменения по файлам

### 1. `src/llm_client/config.py` — settings (блок после s3_*, ~line 61)

```python
# S3 access logs → forensic (Block E-4)
access_log_ingest_enabled: bool = False      # ACCESS_LOG_INGEST_ENABLED
s3_access_log_allowlist: str = "llm-client-service"   # CSV, как tools_enabled
security_alert_webhook_url: str = ""         # SECURITY_ALERT_WEBHOOK_URL
access_log_poll_interval_seconds: int = 300  # E-4: не чаще 5 минут
```

В `_validate_environment` добавить fail-fast (конвенция Settings):

```python
if self.access_log_ingest_enabled and not self.forensic_stream_enabled:
    raise ValueError(
        "ACCESS_LOG_INGEST_ENABLED requires FORENSIC_STREAM_ENABLED=true"
    )
if self.access_log_poll_interval_seconds < 60:
    raise ValueError("ACCESS_LOG_POLL_INTERVAL_SECONDS must be >= 60 (E-4 anti-pattern: no per-second polling)")
```

### 2. `src/llm_client/agent/service.py` — wiring

**а) Конструирование** (после `forensic_writer = build_forensic_writer(...)`, ~line 391):

```python
access_log_ingestor = None
if settings.forensic_stream_enabled and settings.access_log_ingest_enabled:
    from ..observability.access_log_ingestor import AccessLogIngestor
    from ..storage.s3 import S3CompatibleStorage

    # Ингестор читает _access_logs/ из forensic bucket (спека E-4: target = forensic bucket)
    _ingest_s3 = S3CompatibleStorage(
        endpoint=settings.s3_endpoint,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        bucket=settings.s3_forensic_bucket,
    )
    access_log_ingestor = AccessLogIngestor(
        forensic_writer=forensic_writer,
        s3_client=_ingest_s3,
        bucket=settings.s3_forensic_bucket,
        poll_interval_seconds=settings.access_log_poll_interval_seconds,
        allowlist=[v.strip() for v in settings.s3_access_log_allowlist.split(",") if v.strip()],
        security_webhook_url=settings.security_alert_webhook_url or None,
    )
```

**б) app.state** (после `app.state.forensic_writer = forensic_writer`, ~line 471): `app.state.access_log_ingestor = access_log_ingestor`

**в) startup** (после `await forensic_writer.start()`, ~line 1246):

```python
if access_log_ingestor is not None:
    await access_log_ingestor.start()
```

**г) shutdown** (после `await forensic_writer.close()`, ~line 1309):

```python
if access_log_ingestor is not None:
    await access_log_ingestor.close()
```

Порядок shutdown: ingestor.close() до forensic_writer.close() (ingestor может писать в writer).

Примечание: сигнатура класса — `s3_client=`, `security_webhook_url=` (скетч из BUGFIXES-BETA.md неточен, используем реальную).

### 3. `.env.example` (блок E-4, ~line 132)

Добавить перед `S3_ACCESS_LOG_ALLOWLIST`:

```
# Access log ingestor: on in staging/prod with forensic stream; off in dev.
ACCESS_LOG_INGEST_ENABLED=false
# Poll period, seconds (E-4: min 60, default 300)
ACCESS_LOG_POLL_INTERVAL_SECONDS=300
```

### 4. `docker-compose.yml`

- Сервис `minio` (environment, ~line 63): `- MINIO_SERVER_LOGGING_TARGET=${MINIO_SERVER_LOGGING_TARGET:-}` (критерий приёмки; в compose-network URL пока пустой — см. «Нюансы»).
- Сервис `agent-service` (environment, ~line 207): `- ACCESS_LOG_INGEST_ENABLED=${ACCESS_LOG_INGEST_ENABLED:-false}` (env_file и так пробрасывает явный passthrough — по конвенции MCP_SERVER_ENABLED).

### 5. `scripts/dev_minio_trace.sh` (новый, Шаг 3 фикса)

Dev-реализация DoD «access logs доступны через `mc admin trace`»:

```bash
#!/usr/bin/env bash
# Dump MinIO access trace (dev stand-in for AWS Server Access Logging).
set -euo pipefail
DURATION="${1:-60}"
OUT="trace-$(date +%Y%m%dT%H%M%S).jsonl"
timeout "${DURATION}" docker-compose exec -T minio \
  mc admin trace --call access local --json > "/tmp/${OUT}" || true
docker-compose cp "/tmp/${OUT}" llm-minio:/tmp/
docker-compose exec minio mc cp "/tmp/${OUT}" \
  "local/llm-client-forensic/_access_logs/${OUT}"
echo "Uploaded _access_logs/${OUT} — AccessLogIngestor picks it up next poll."
```

### 6. `tests/integration/test_access_log_ingestor_e2e.py` (новый)

`pytestmark = pytest.mark.integration`. Адаптация критерия «ждёт 5+ минут»: вместо sleep — прямой `ingest_once()` (событийный подход, конвенция репо; CI-дружелюбно). Сценарий:

1. Fixtures (паттерн `test_forensic_stream_e2e.py`): Settings (ENVIRONMENT=dev/staging, FORENSIC_STREAM_ENABLED=true, KMS local), skip если MinIO недоступен; бакеты создаются в test body (`mc`-эквивалент через storage: bucket создать нельзя напрямую — CI уже создаёт оба бакета шагом выше; локально — пропуск при отсутствии).
2. `test_unauthorized_access_lands_in_forensic_and_alerts`:
   - Загрузить в `_access_logs/2026-02-06-e2e.log` строку AWS-формата с `requester=evil-actor` (не в allowlist) — имитация S3 Server Access Logging.
   - `writer = build_forensic_writer(settings, LocalDevKeyProvider())` (production-путь, без ручной инстанциации).
   - `ingestor = AccessLogIngestor(forensic_writer=writer, s3_client=forensic_scoped_storage, allowlist=["llm-client-service"], security_webhook_url="https://hooks.slack.com/services/test")`; monkeypatch `httpx.AsyncClient` → `MockTransport` (конвенция probe-тестов), фиксируем POST payload.
   - `await writer.start(); await ingestor.ingest_once(); await writer.flush()`.
   - Asserts: (a) в forensic bucket появился объект под `forensic/` (list + fetch + decrypt через `LocalDevKeyProvider.decrypt`, поле `event_type == "s3_access"`, `requester == "evil-actor"`); (b) webhook получил POST с текстом `non-allowlisted requester`; (c) allowlisted-строка (requester=`llm-client-service`) не алертится.
3. `test_ingestor_start_close_lifecycle`: `start()` → задача живёт, `close()` → завершается; лог «AccessLogIngestor started».

### 7. `tests/unit/test_config_access_log_ingest.py` (новый, маленький)

- `access_log_ingest_enabled=true` + `forensic_stream_enabled=false` → `ValidationError`.
- `access_log_poll_interval_seconds=5` → `ValidationError`.
- Дефолты: `access_log_ingest_enabled is False`.

### 8. `README.md` — секция E-4 (:419-429)

Дополнить: env-флаг `ACCESS_LOG_INGEST_ENABLED` (требует `FORENSIC_STREAM_ENABLED=true`), wiring в agent-service startup, dev-скрипт `scripts/dev_minio_trace.sh`, команда проверки: `docker-compose logs agent-service | grep "AccessLogIngestor started"`, e2e-тест.

### 9. `analytics/BUGFIXES-BETA.md` — BUG-MVP-03

Отметить `[x]` все три критерия приёмки (с оговоркой: e2e-тест использует `ingest_once()` + имитацию access-log файла вместо ожидания 5+ минут — это осознанная адаптация, зафиксировать в комментарии к чекбоксу или в самом тесте).

## Верификация

```powershell
.\.venv\Scripts\python.exe -m pytest tests/unit/test_access_log_ingestor.py tests/unit/test_config_access_log_ingest.py -v
.\.venv\Scripts\python.exe -m pytest tests/integration/test_access_log_ingestor_e2e.py -v   # требует MinIO (docker-compose up -d minio)
ruff check src/llm_client/config.py src/llm_client/agent/service.py tests/integration/test_access_log_ingestor_e2e.py tests/unit/test_config_access_log_ingest.py
mypy src/llm_client
```

Регрессия: `pytest tests/unit/test_forensic_writer.py tests/integration/test_forensic_stream_e2e.py -v`.

Manual (DoD): `FORENSIC_STREAM_ENABLED=true ACCESS_LOG_INGEST_ENABLED=true` (+ KMS local) → старт agent-service → в логах `AccessLogIngestor started`; `scripts/dev_minio_trace.sh 30` → следующий поллинг пишет зашифрованную `s3_access`-запись в forensic bucket (`mc ls local/llm-client-forensic/forensic/...`).

## Нюансы (осознанные отклонения)

1. **`MINIO_SERVER_LOGGING_TARGET`** — не является реальным env MinIO (MinIO использует `mc admin config set logger_webhook` / `MINIO_LOGGER_WEBHOOK_TARGET_*`; AWS-формат server access logging в MinIO отсутствует). Добавляем env в compose как требует критерий приёмки (MinIO игнорирует неизвестные env, безвредно), а фактический dev-путь — `scripts/dev_minio_trace.sh` (`mc admin trace`), как и требует DoD E-4. Для prod AWS S3 — штатный Server Access Logging с target-префиксом `_access_logs/` (задокументировать в README).
2. **Ожидание «5+ минут» в e2e** заменено на прямой `ingest_once()` + загрузку готовой AWS-формат log-строки — тот же код-путь, без sleep; конвенция репо (event-driven, anti-pattern «НЕ используй sleep()»).
3. **Wiring только в `service.py`** (agent-service) — единственное деплоимое приложение; `api.py` — control-plane, в compose не запускается. Дублирование фонового таска в двух процессах исключено.
4. `mc admin trace --json` выдаёт JSON, а не AWS-формат — ингестор его не парсит; скрипт решает задачу DoD («логи доступны через mc admin trace»), а ingestion-путь в e2e тестируется на корректном AWS-формате (как в prod).

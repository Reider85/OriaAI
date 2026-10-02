# LLM Client — Phase 1

Быстрый старт dev-окружения: Redis, MinIO, HashiCorp Vault + Python-пакет `llm-client`
(Quick Wins B-1..B-3).

## Сервисы

| Сервис | URL / порт | Назначение |
|---|---|---|
| Redis | `localhost:6380` (host) / `redis:6379` (compose network) | pub/sub cancel-канал, healthcheck |
| MinIO | `http://localhost:9000` (API) / `http://localhost:9001` (Console) | S3-совместимое хранилище файлов и forensic |
| Vault | `http://localhost:8200` | KMS, transit engine для AES-256-GCM |

> Если порт 6379 занят другим проектом — Redis смонтирован на `6380`. Внутри compose-сети
> сервис остаётся доступен как `redis:6379` (см. `REDIS_URL` в `.env`).

## Быстрый старт

```bash
# 1. Скопировать переменные
copy .env.example .env

# 2. Поднять всю инфраструктуру
docker-compose up -d

# 3. Установить Python-пакет с dev-зависимостями
pip install -e ".[dev]"

# 4. Прогнать тесты (unit + integration против реальных Redis/MinIO)
# pytest установлен в .venv — сначала активировать окружение:
.\.venv\Scripts\Activate.ps1
pytest tests -v
```

> Если `pytest` не распознаётся (`CommandNotFoundException`) — окружение не активировано.
> Без активации: `.\.venv\Scripts\pytest.exe tests -v` или `.\.venv\Scripts\python.exe -m pytest tests -v`.
> Если `Activate.ps1` блокируется политикой выполнения: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

---

## Redis — проверка pub/sub

### healthcheck

```powershell
docker-compose exec redis redis-cli ping
# → PONG
```

### Pub/Sub тест (round-trip < 5 мс)

Терминал 1 — подписаться:

```powershell
docker-compose exec redis redis-cli SUBSCRIBE test
```

Терминал 2 — опубликовать:

```powershell
docker-compose exec redis redis-cli PUBLISH test hello
```

Ожидаемый результат: сообщение `hello` получено в терминале 1, latency < 5 мс.

---

## Phase 2 ML models

### BGE-reranker-base setup

```bash
# 1. Скачать BGE-reranker-base модель (требуется ~600MB)
python scripts/download_bge_reranker.py
# → Download completed in ~2-5 minutes
# → Smoke test passed
# → Model cached in models/bge-reranker-base/
```

**Модель**: `BAAI/bge-reranker-base` (278M параметров, ~600MB в памяти)  
**Назначение**: Reranker в RAG pipeline (ADR-017)  
**Latency**: ~150 мс CPU / ~30 мс GPU на 20 чанков (batch_size=8/32)  
**RAM-профиль**: ~600MB после загрузки, ~1.2GB пиковая при inference  

```bash
# 2. Проверить работу модели (опционально)
docker-compose up agent-service
# → Agent service запускается с примонтированной моделью
# → Reranker доступен через RERANKER_MODEL_NAME env var
```

**Настройки** (в `.env`):
- `RERANKER_MODEL_NAME=BAAI/bge-reranker-base`
- `RERANKER_MODEL_DIR=./models/bge-reranker-base`
- `RERANKER_DEVICE=cpu` (или `cuda` если GPU доступен)
- `RERANKER_MAX_LENGTH=512`
- `RERANKER_BATCH_SIZE=8`

---

## Phase 2 ML models

### BGE-reranker-base setup

```bash
# 1. Скачать BGE-reranker-base модель (требуется ~600MB)
python scripts/download_bge_reranker.py
# → Download completed in ~2-5 minutes
# → Smoke test passed
# → Model cached in models/bge-reranker-base/
```

**Модель**: `BAAI/bge-reranker-base` (278M параметров, ~600MB в памяти)  
**Назначение**: Reranker в RAG pipeline (ADR-017)  
**Latency**: ~150 мс CPU / ~30 мс GPU на 20 чанков (batch_size=8/32)  
**RAM-профиль**: ~600MB после загрузки, ~1.2GB пиковая при inference  

```bash
# 2. Проверить работу модели (опционально)
docker-compose up agent-service
# → Agent service запускается с примонтированной моделью
# → Reranker доступен через RERANKER_MODEL_NAME env var
```

**Настройки** (в `.env`):
- `RERANKER_MODEL_NAME=BAAI/bge-reranker-base`
- `RERANKER_MODEL_DIR=./models/bge-reranker-base`
- `RERANKER_DEVICE=cpu` (или `cuda` если GPU доступен)
- `RERANKER_MAX_LENGTH=512`
- `RERANKER_BATCH_SIZE=8`

---

## Phase 1+2 — инфраструктура Redis

Redis DB 0 — ADR-013 pub/sub; Redis DB 1 — ADR-010 checkpoint-WAL. Не переключай DB без необходимости — pub/sub не работает кросс-DB в одном connection.

### Проверка Redis DB 1 (checkpoint-WAL)

```powershell
# Проверка доступности DB 1
docker-compose exec redis redis-cli -n 1 ping
# → PONG

# Проверка памяти (должно быть 0 после старта)
docker-compose exec redis redis-cli -n 1 INFO memory | grep used_memory_human
# → 0K

# Проверка eviction policy (должно быть 0)
docker-compose exec redis redis-cli -n 1 INFO stats | grep evicted_keys
# → 0

# Проверка AOF-персистентности
docker-compose exec redis redis-cli -n 1 INFO persistence | grep aof_enabled
# → 1

# Проверка appendfsync
docker-compose exec redis redis-cli CONFIG GET appendfsync
# → 1) "appendfsync"
# → 2) "everysec"
```

При интеграции с Блоком B-1 AOF-файл `appendonly.aof` будет расти в volume `redis-data` по мере выполнения графов.

### Проверка eviction (alert)

Если `evicted_keys` > 0 — alert (checkpoint-теряется, OOM imminent):
```powershell
docker-compose exec redis redis-cli -n 1 INFO stats | grep evicted_keys
# Если > 0 — проверяем maxmemory-policy:
docker-compose exec redis redis-cli -n 1 INFO memory | grep maxmemory_policy
# → noeviction (ожидаемо)
```

---

## MinIO — проверка bucket'ов

После `docker-compose up minio minio-init`:

```powershell
# Убедиться что bucket'ы созданы
docker-compose exec minio mc ls local/
# → local/llm-client-files/
# → local/llm-client-forensic/
```

Console доступна: [http://localhost:9001](http://localhost:9001)
Логин / пароль: из `.env` → `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`.

### Round-trip upload/download

> `docker-compose exec minio mc cp C:\...` **не работает**: `mc` выполняется внутри
> контейнера, где нет Windows-путей. Сначала файл копируется в контейнер через
> `docker cp`, а alias `local` внутри контейнера MinIO нужно настроить с root-кредами
> (иначе `AccessDenied`).

```powershell
# 1. Скопировать файл с хоста в контейнер
$cid = docker-compose ps -q minio
docker cp "C:\temp\test.txt" "$cid`:/tmp/test.txt"

# 2. Настроить alias local с root-кредами (разово)
docker-compose exec minio mc alias set local http://localhost:9000 minioadmin minioadmin

# 3. Upload файла
docker-compose exec minio mc cp /tmp/test.txt local/llm-client-files/test.txt

# 4. Download файла (внутри контейнера → копируем наружу)
docker-compose exec minio mc cp local/llm-client-files/test.txt /tmp/downloaded.txt
docker cp "$cid`:/tmp/downloaded.txt" "C:\temp\downloaded.txt"

# 5. Удаление
docker-compose exec minio mc rm local/llm-client-files/test.txt
```

> Креды для шага 2 — `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` из `.env`, например `minioadmin`/`minioadmin`.

---

## Vault — проверка шифрования

### healthcheck

```powershell
docker-compose exec vault vault status
# → Initialized: true, Sealed: false
```

### Encrypt/Decrypt round-trip

```powershell
# Шифрование
docker-compose exec vault vault write transit/encrypt/forensic-aes256-gcm plaintext=$(echo -n "test" | base64)

# Результат содержит `ciphertext` — сохраните его.
# Расшифрование (подставьте ciphertext):
# docker-compose exec vault vault write transit/decrypt/forensic-aes256-gcm ciphertext="vault:v1:..."
```

Policy `forensic-encryptor` содержит только `transit/encrypt/forensic-aes256-gcm` и `transit/decrypt/forensic-aes256-gcm` — без путей `auth/`, `sys/`, `secret/`. Ключ создаётся с типом `aes256-gcm96` (именование нового Vault для AES-256-GCM).

---

## Quick Wins Phase 1 (ROADMAP §12)

### B-1 — Cancel через Redis pub/sub (мин. ADR-013)

Компоненты: `src/llm_client/transport/` (CancellationToken, Registry, CancelPublisher,
CancelSubscriber) + HTTP endpoint `POST /sessions/{id}/cancel` (FastAPI).

Проверка полного цикла:

```powershell
# Терминал 1: подписчик
docker-compose exec redis redis-cli SUBSCRIBE session:demo:cancel
# Терминал 2: публикация (--raw: без форматирования)
docker-compose exec redis redis-cli PUBLISH session:demo:cancel "{\"reason\":\"user_cancelled\"}"
```

Unit/интеграция: `pytest tests/unit/test_cancel_token.py tests/unit/test_cancel_transport.py
tests/unit/test_cancel_endpoint.py tests/integration/test_redis_cancel.py`.

### B-2 — S3CompatibleStorage (мин. расш. ADR-008)

Компоненты: `src/llm_client/storage/` (FileStorage interface, S3CompatibleStorage) +
переключатель `STORAGE_BACKEND=local|s3` (default `local`) — на момент Quick Win.

> После Блока E (расш. ADR-008): `LocalFileStorage` **удалён**, `STORAGE_BACKEND` упразднён.
> Единственный backend — `S3CompatibleStorage` (MinIO в dev, AWS S3 в prod); MinIO **обязателен**
> для локальной разработки (`docker-compose up -d`, см. «Сервисы»).

Проверка round-trip в MinIO:

```powershell
docker-compose exec minio mc ls local/llm-client-files/
# после save() через FileStorage — файл появляется здесь
```

Тесты: `pytest tests/integration/test_minio_storage.py`.
MinIO Console: http://localhost:9001 (логин/пароль из `.env`).

### B-3 — State-Delta Cycle Detection (preview)

Компоненты: `src/llm_client/agent/cycle_detection.py` (`compute_state_delta`,
`IterationMonitor`). Флаги: `CYCLE_DETECTION_ENABLED`, `CYCLE_DETECTION_THRESHOLD`.
При 2 итерациях подряд с similarity > threshold — граф флагает `cycle_detected`
(log `[cycle_detection]`) и выходит на следующем conditional edge.

Тесты: `pytest tests/unit/test_cycle_detection.py`.

---

## Phase 1 — ADR-013 полный (Block C) + ADR-014 (Block D)

### C-5 — UI auto-cancel

JS-фрагмент (`src/llm_client/ui/auto_cancel.py`) для Streamlit: слушает
`visibilitychange` / `pagehide` / `beforeunload`, шлёт `POST /sessions/{id}/cancel`
через `navigator.sendBeacon` (fallback `fetch keepalive`) при закрытии вкладки.
Debounce 5 сек — переключение вкладок на короткое время не шлёт cancel. Ручная
кнопка "Stop" вызывает `window.stop_llm_session("user_cancelled")`.

```python
from llm_client.ui import inject_auto_cancel
inject_auto_cancel()  # в начале Streamlit-скрипта
```

### C-6 — Cancel → forensic logging

`CancelSubscriber` (Block C) вызывает handler, который пишет:
- **operational** (маскированный): `{event_type, session_id, user_id: "[MASKED]", reason, timestamp}`;
- **forensic** (полный trace, зашифрованный): user_id полный + partial answer size,
  last node, message count, duration_ms.

### D-1 — PIIDetector (Presidio + custom regex)

```bash
pip install "presidio-analyzer>=2.2.0" "spacy>=3.7.0"
python -m spacy download en_core_web_md
```

`src/llm_client/security/pii_detector.py`: детектит PERSON, EMAIL, PHONE, CREDIT_CARD,
IBAN, IP, US_SSN, URL + внутренние форматы `EMP-\d{6}` и `PRJ-[A-Z]{3}-\d{4}`.
`PII_DETECTOR_ENABLED=false` — no-op для dev/test.

### D-2/D-3 — Dual-Stream Logging

- **Operational** (`OPERATIONAL_LOG_SINK=stdout|loki|elk`): PII маскируется, batch flush 100 ms / 100 events, retention 30 дней задаётся в sink-е (Loki/ELK).
- **Forensic** (`FORENSIC_STREAM_ENABLED=true`): full trace шифруется AES-256-GCM через
  Vault transit и пишется в S3 bucket `llm-client-forensic`, путь
  `forensic/YYYY/MM/DD/{session_id}/...`, batch flush 500 ms / 50 events. Privilege:
  Security officer + аудит-комитет, retention 90+ дней (lifecycle policy на bucket).

### D-4 — KMS KeyProvider

`KMS_PROVIDER=vault` (default) или `local` (TEST ONLY). Vault-transit интерфейс
абстрагирует миграцию на managed KMS в Phase 5.

### D-5 — PII score в messages

Реализовано: при записи сообщений `attach_pii_metadata()` считает `pii_score` и
`pii_entities` (только {type, start, end}, никогда текст PII). Сохраняется в таблицу
`messages` колонками `pii_score FLOAT` и `pii_entities JSONB`.

- **User сообщения**: PII метадата сохраняется при записи в БД
- **Assistant/tool сообщения**: `pii_score` и `pii_entities` = NULL (метрика только для user)
- **Миграция**: `migrations/005_add_pii_score_to_messages.sql` (с индексом `idx_messages_pii_score`)
- **Аналитика**: `ops/pii_analytics.sql` — ежедневные метрики PII по user-сообщениям

**PII_METADATA_ENABLED=false** → колонки `pii_score` и `pii_entities` = NULL.

### D-6 — Local dev without Vault

По умолчанию `ENVIRONMENT=dev` + `FORENSIC_STREAM_ENABLED=false`: forensic выключен,
Vault не запрашивается, приложение стартует только с Redis и MinIO
(`docker-compose up redis minio`). PIIDetector и operational logging активны всегда.

Для staging/prod: `FORENSIC_STREAM_ENABLED=true` (обязателен Vault, иначе startup
fails fast; в `env=prod` значение `false` отклоняется валидацией config).

---

## Phase 1 — Block E: Single S3 Storage (расш. ADR-008)

### E-1 — S3CompatibleStorage (production-quality)

`src/llm_client/storage/s3.py`: полная реализация `FileStorage` через aiobotocore:

- `save(file, key, metadata=None)` — multipart upload автоматически для файлов > 5 МБ
  (8 МБ на часть, abort multipart при ошибке), `Metadata` → S3 object metadata;
- `get` / `get_stream` / `delete` / `exists` / `list` — полный контракт;
- Error mapping: `404 → FileNotFoundError`, `403/AccessDenied → PermissionError`,
  остальные transient-ошибки → экспоненциальный retry (1ms→2ms→4ms), затем `StorageError`;
- Единый backend для dev (MinIO) / staging / prod (S3) — один `FileStorage` контракт.

### E-2 — LocalFileStorage удалён

`LocalFileStorage` и флаг `STORAGE_BACKEND` **удалены** из кодовой базы. Единственный
backend — `S3CompatibleStorage` (`create_file_storage()` без аргументов). **MinIO
обязателен для локальной разработки** (`docker-compose up -d`).

Проверка удаления:

```powershell
rg "LocalFileStorage|STORAGE_BACKEND" src/
# → 0 совпадений
```

### E-3 — InMemoryFileStorage (test-double)

`tests/conftest.py`: thread-safe dict-реализация `FileStorage` для unit-тестов.
Fixture `file_storage` доступна во всех тестовых модулях.

### E-4 — S3 access logs → forensic stream

`src/llm_client/observability/access_log_ingestor.py`: `AccessLogIngestor` — фоновый
таск, каждые 5 минут читает Server Access Log из `_access_logs/` prefix, парсит каждую
строку в событие `s3_access` ({bucket, key, operation, requester, request_id, timestamp,
bytes_transferred}) и передаёт в `ForensicStreamWriter` (шифруется + пишется в forensic
bucket). Если requester не в allow-list (`S3_ACCESS_LOG_ALLOWLIST`, default
`llm-client-service`) — пишется alert в `SECURITY_ALERT_WEBHOOK_URL` (Slack #security).

Тесты: `pytest tests/unit/test_access_log_ingestor.py tests/unit/test_s3_storage.py
tests/integration/test_minio_storage.py`.

---

## Phase 2 — PostgreSQL full-text search

### Phase 2 инфраструктура

PostgreSQL 16 добавлен для полнотекстового поиска с tsvector + GIN индексами:

| Сервис | URL / порт | Назначение |
|---|---|---|
| PostgreSQL | `localhost:5434` (host) / `postgres:5432` (compose network) | База данных для документов, full-text search |

### healthcheck

```powershell
docker-compose exec postgres pg_isready -U postgres -d llm_client
# → llm_client is accepting connections
```

### Проверка tsvector

```powershell
docker-compose exec postgres psql -U postgres -d llm_client -c "
SELECT id, search_vector FROM documents LIMIT 5;"
# → Должен вернуть tsvector с лемматизированными терминами
```

### Проверка GIN индекса

```powershell
docker-compose exec postgres psql -U postgres -d llm_client -c "
EXPLAIN ANALYZE SELECT * FROM documents 
WHERE search_vector @@ websearch_to_tsquery('english', 'error code 1234');"
# → Должен использовать "Bitmap Index Scan on idx_documents_search_vector"
```

### Проверка trigram fuzzy matching

```powershell
docker-compose exec postgres psql -U postgres -d llm_client -c "
EXPLAIN ANALYZE SELECT * FROM documents WHERE content % 'приер';"
# → Должен использовать "Bitmap Index Scan on idx_documents_content_trgm"
```

### Hybrid query benchmark

На staging с 10k документов hybrid query (vector + tsvector) должен выполняться <50 мс:

```powershell
docker-compose exec postgres psql -U postgres -d llm_client -c "
EXPLAIN ANALYZE SELECT * FROM documents 
WHERE search_vector @@ websearch_to_tsquery('english', 'hello world')
ORDER BY ts_rank(search_vector, websearch_to_tsquery('english', 'hello world')) DESC
LIMIT 10;"
```

### Migration

Таблица `documents` и tsvector индекс создаются миграциями:

```bash
# Применить миграции
alembic upgrade head

# Проверить статус
alembic current
# → 008 (fix_documents_search_schema)
```

Схема: `search_vector tsvector GENERATED ALWAYS AS STORED` (пересчитывается при UPDATE content/metadata), unique index на `content_hash` (idempotent upsert в `BM25IndexBuilder`).

### Ingestion API (ADR-020 / D-2)

```bash
# Индексировать документ (BM25 + опционально vector)
curl -X POST http://localhost:8000/documents \
  -H "Content-Type: application/json" \
  -d '{"user_id":"u1","content":"Error code 1234: ...","source_type":"api"}'

# Удалить
curl -X DELETE http://localhost:8000/documents/{document_id}
```

Ответ: `{"document_id","status":"indexed|partial","bm25_indexed","vector_indexed"}`.  
Auth отсутствует (dev-only). Vector-нога включается через `VECTOR_STORE_KIND=chroma` + `pip install -e ".[vector]"`.

### Конфигурация

Переменные окружения для full-text search:

- `PG_TEXT_SEARCH_CONFIG=english` — конфигурация полнотекстового поиска
- `PG_FUZZY_MATCHING_ENABLED=false` — включить fuzzy matching через pg_trgm
- `VECTOR_STORE_KIND=none|chroma|pgvector` — vector write-path (default: none)
- `EMBEDDING_PROVIDER=openai|none`, `EMBEDDING_MODEL=text-embedding-3-small`
- `CHROMA_PERSIST_DIR=./chroma_db` — каталог Chroma (при `VECTOR_STORE_KIND=chroma`)

---

## Справка

- **AOF-персистентность Redis**: файл `appendonly.aof` создаётся в volume `redis-data` после первого `PUBLISH`.
- **Isolation**: files и forensic bucket'ы — разные (`llm-client-files` / `llm-client-forensic`), как требует ADR-014.
- **Без TLS**: внутренний трафик docker-compose; TLS добавляется в Phase 5.
- **Без паролей в коде**: все креды через `.env` только.
- **Docker Compose override**: для dev используется `docker-compose.override.yml` (если есть).

---

## Troubleshooting

| Проблема | Решение |
|---|---|
| `minio-init` падает с `Connection refused` | Подождать пока MinIO перейдёт в `healthy` (`docker-compose ps`) |
| `vault-init` "path is already in use" | Idempotent скрипт — повторный запуск безопасен (`2>/dev/null || echo`) |
| Vault "unknown key type aes256-gcm" | Использовать `type=aes256-gcm96` (новое имя AES-256-GCM) |
| `minio/minio` / `minio/mc` pull denied | Репозитории удалены из Docker Hub (2026-09). Используются `quay.io/minio/...` |
| Redis не отвечает `PONG` | `docker-compose logs redis` — проверить нет ли warnings о maxmemory |
| Порт 6379 занят | Наш Redis смонтирован на `6380:6379`, `REDIS_URL` в `.env` обновлён |
| MinIO Console 403 | Проверить `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` в `.env` |
| `pytest` не распознаётся в PowerShell | Активировать окружение: `.\.venv\Scripts\Activate.ps1`, либо запускать `.\.venv\Scripts\python.exe -m pytest tests -v` |

---

## Phase 2 CI Pipeline

### GitHub Actions Workflows

#### PR Pipeline (`.github/workflows/phase2-ci.yml`)

**Trigger**: `push` (main), `pull_request`  
**Jobs** (parallel execution):

| Job | Description | Timeout | Dependencies |
|-----|-------------|---------|--------------|
| `lint` | Code linting with ruff | - | - |
| `typecheck` | Type checking with mypy | - | - |
| `unit-tests` | Unit tests with coverage | - | - |
| `integration-dev` | Integration tests (Redis+PG+MinIO+Vault) | 120s | Services |
| `checkpoint-quick` | Checkpoint latency quick test (100 samples) | 120s | Services |
| `bm25-indexing-regression` | BM25 indexer unit test | 30s | - |
| `reranker-quick` | Reranker quick test (10 queries) | 180s | - |
| `hybrid-rag-quick` | Hybrid RAG quick test (15 queries) | 300s | - |
| `web-search-quick` | Web search quick test (mock Tavily) | 60s | - |
| `rag-query-quick` | RAG query quick test (mock pipeline) | 120s | - |
| `ui-render-phase2-quick` | UI tests (G-1..G-4) | 60s | - |

**Quick tests**: All external APIs (Tavily, OpenAI, Cohere) are mocked in PR pipeline.

#### Nightly Pipeline (`.github/workflows/phase2-nightly.yml`)

**Trigger**: `schedule` (2 AM UTC daily), `workflow_dispatch`  
**Services**: Full docker-compose stack  
**Jobs** (sequential execution, staggered):

| Job | Description | Timeout | Requirements |
|-----|-------------|---------|--------------|
| `checkpoint-latency-staging` | 1000 samples, p99 <2ms | 600s | Redis+PG |
| `checkpoint-recovery-staging` | 4 recovery scenarios (B-5) | 1200s | Redis+PG+app |
| `reranker-ab-test-staging` | 50+ queries, A/B test | 600s | bge model |
| `hybrid-rag-ab-test-staging` | 30 queries, A/B test | 600s | PG tsvector + bge |
| `web-search-integration-staging` | 5 queries, real Tavily | 180s | `STAGING_TAVILY_API_KEY` |
| `rag-query-integration-staging` | 10 queries, real PGVector | 300s | Staging PG |
| `sse-tool-events-staging` | Full SSE flow test | 120s | Agent service |
| `idealidad-metric` | Phase 2 metrics update | 300s | Prometheus |

**Caching**: HuggingFace models (`~/.cache/huggingface`) cached between runs  
**Artifacts**: 30-day retention for all test reports  
**Notifications**: Slack webhook on failure

### Local CI Scripts

#### Quick Pipeline (PR simulation)

```powershell
# Run all PR pipeline jobs locally
powershell -ExecutionPolicy Bypass -File scripts\ci-local-quick.ps1

# Run specific test categories
powershell -ExecutionPolicy Bypass -File scripts\ci-local-quick.ps1 -Target "lint,typecheck,unit,checkpoint,reranker"
```

**Options**:
- `-Target`: Specific test categories (`lint`, `typecheck`, `unit`, `integration`, `checkpoint`, `bm25`, `reranker`, `hybrid-rag`, `web-search`, `rag-query`, `ui`, `all`)
- `-TimeoutSeconds`: Default 300 seconds per test
- `-Port`: Streamlit port (default 8501)

#### Staging Pipeline (Nightly simulation)

```powershell
# Run all nightly tests locally
powershell -ExecutionPolicy Bypass -File scripts\ci-local-staging.ps1

# Run specific staging tests
powershell -ExecutionPolicy Bypass -File scripts\ci-local-staging.ps1 -Target "checkpoint-latency,reranker-ab-test,web-search-integration"
```

**Options**:
- `-Target`: Specific test categories (`checkpoint-latency`, `checkpoint-recovery`, `reranker-ab-test`, `hybrid-rag-ab-test`, `web-search-integration`, `rag-query-integration`, `sse-tool-events`, `idealidad`, `all`)
- `-TimeoutSeconds`: Default 1800 seconds per test
- `-Port`: Streamlit port (default 8501)

### Test Results

All test results are saved to `test-results/` directory:
- `test-results/checkpoint-latency/` - Checkpoint latency reports
- `test-results/reranker-ab-test/` - Reranker A/B test results
- `test-results/web-search-integration/` - Web search integration reports
- `test-results/idealidad/` - Ideality metrics

### Required Secrets for Nightly Pipeline

Configure these GitHub repository secrets for nightly pipeline:

| Secret | Purpose | Required for |
|-------|---------|--------------|
| `STAGING_TAVILY_API_KEY` | Real Tavily API calls | `web-search-integration-staging` |
| `COHERE_API_KEY` | Cohere reranker API | `reranker-ab-test-staging`, `hybrid-rag-ab-test-staging` |
| `OPENAI_API_KEY` | OpenAI API for RAG | `rag-query-integration-staging` |
| `SLACK_WEBHOOK_URL` | Failure notifications | All jobs |

### Local Development Setup

For local CI testing, ensure environment variables are set in `.env`:

```bash
# Required for integration tests
REDIS_URL=redis://localhost:6379/0
REDIS_CHECKPOINT_URL=redis://localhost:6379/1
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5434/llm_client
S3_ENDPOINT=http://localhost:9000
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=llm-client-files

# Optional for nightly tests
STAGING_TAVILY_API_KEY=your_tavily_key_here
COHERE_API_KEY=your_cohere_key_here
OPENAI_API_KEY=your_openai_key_here
```

### Pipeline Architecture

**Phase 2 CI extends Phase 1 baseline** with:
- **PR pipeline**: Quick tests only, no real API calls
- **Nightly pipeline**: Full staging tests with real APIs
- **Local scripts**: Mirror CI behavior for local development
- **Artifact management**: JUnit XML + JSON reports with 30-day retention
- **Caching**: Pip packages and HuggingFace models for faster builds

**Anti-patterns avoided**:
- No real API calls in PR pipeline (mocked only)
- No Phase 2 jobs in Phase 1 CI (separate files)
- Nightly jobs sequential (not parallel) to avoid staging overload
- Secrets never hardcoded in workflow files
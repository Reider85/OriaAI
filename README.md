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
pytest tests -v
```

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

```powershell
# Upload файла
docker-compose exec minio mc cp C:\temp\test.txt local/llm-client-files/test.txt

# Download файла
docker-compose exec minio mc cp local/llm-client-files/test.txt C:\temp\downloaded.txt

# Удаление
docker-compose exec minio mc rm local/llm-client-files/test.txt
```

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

Компоненты: `src/llm_client/storage/` (FileStorage interface, LocalFileStorage fallback,
S3CompatibleStorage) + переключатель `STORAGE_BACKEND=local|s3` (default `local`).

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
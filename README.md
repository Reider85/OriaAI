# LLM Client — Phase 1 Infrastructure

Быстрый старт dev-окружения: Redis, MinIO, HashiCorp Vault.

## Сервисы

| Сервис | URL / порт | Назначение |
|---|---|---|
| Redis | `localhost:6379` | pub/sub cancel-канал, healthcheck |
| MinIO | `http://localhost:9000` (API) / `http://localhost:9001` (Console) | S3-совместимое хранилище файлов и forensic |
| Vault | `http://localhost:8200` | KMS, transit engine для AES-256-GCM |

## Быстрый старт

```bash
# 1. Скопировать переменные
copy .env.example .env

# 2. Поднять Redis
docker-compose up redis

# 3. Поднять MinIO + инициализация bucket'ов
docker-compose up minio minio-init

# 4. Поднять Vault + инициализация transit-ключа
docker-compose up vault vault-init
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

Policy `forensic-encryptor` содержит только `transit/encrypt/forensic-aes256-gcm` и `transit/decrypt/forensic-aes256-gcm` — без путей `auth/`, `sys/`, `secret/`.

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
| `vault-init` не находит transit engine | Vault ещё не ready — проверить `vault status` |
| Redis не отвечает `PONG` | `docker-compose logs redis` — проверить нет ли warnings о maxmemory |
| MinIO Console 403 | Проверить `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` в `.env` |
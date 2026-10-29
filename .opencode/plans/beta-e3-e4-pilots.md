# План: промпты E-3 и E-4 из BETA-PROMPTS.md (Phase 3 — Тесты и CI)

## Цель

- **E-3 (ADR-016 pilot)**: manual-процедура пилота ReAct success-rate на Ollama + Llama 3.1. Фиксируется в `docs/adr_016_pilot.md`; верификация — локальный запуск пилота (success rate ≥80% = PASS, 60–80% = PARTIAL с tuning, <60% = ROLLBACK).
- **E-4 (ADR-004 preview pilot)**: CI-интеграция MCP Server probe — `scripts/probe_mcp_server.py` запускается в staging CI против deploy-нутого agent-service с `MCP_SERVER_ENABLED=true`; exit code 0/1; PASS/ROLLBACK-verdict виден в CI output.

## Текущее состояние (предусловия выполнены)

### E-3 — контент уже на диске, нужна верификация

| Артефакт | Статус |
|---|---|
| `docs/adr_016_pilot.md` | **Существует** (untracked в git), 78 строк: критерии-таблица, prerequisites, steps, tuning (v1_strict/v2_tolerant/v3_cot), exit/report — покрывает и превышает DoD E-3 |
| `scripts/pilot_ollama_react.py` (D-6) | Существует, 279 строк; `PilotResult`, 24 test-case, CLI `--ollama-url/--model/--variant/--output` |
| `tests/unit/test_pilot_ollama_react.py` | Существует, 8 тестов собираются |
| Ollama + `llama3.1:8b` | **Установлены** на машине (`ollama list` → `llama3.1:8b`, 4.9 GB); `langchain_ollama` установлен в system Python 3.11 |
| Остаток DoD | «Local pilot run procedure works» + «success rate ≥80% achievable» — проверяется реальным запуском пилота |

### E-4 — probe и тесты есть, CI-интеграции нет

| Артефакт | Статус |
|---|---|
| `scripts/probe_mcp_server.py` (H-4) | Существует: /mcp/health → /mcp/tools → call каждого tool → SSE; exit 0/1, `--url` |
| `tests/integration/test_mcp_server_probe.py` (H-4) | Существует, 5 mocked-тестов (`pytest.mark.integration`), собираются |
| MCP-роуты | `service.py:484-491` — монтируются при `settings.mcp_server_enabled`; config `mcp_server_enabled: bool = False` |
| `scripts/ci-local-staging.sh` | Target-структура; есть `phase3-adr011-integration` (E-1/E-2), **нет E-4 probe** |
| `scripts/ci-local-staging.ps1` | Аналогично — **нет E-4 probe** |
| `docker-compose.yml` | agent-service деплоится на `127.0.0.1:8000`; `env_file: .env` подхватит MCP_SERVER_ENABLED из .env, но **нет passthrough в `environment:`** — shell-переменную нельзя форсировать через `docker compose up` без правки compose |

**Осознанное отклонение от snippet промпта (E-4)**: промпт предлагает `MCP_SERVER_ENABLED=true python -m llm_client.agent &` (локальный процесс). Реальный `ci-local-staging.sh` уже деплоит agent-service через docker compose на порту 8000 — второй локальный процесс даст конфликт порта. Вместо этого: пересоздаём **deploy-нутый контейнер** с `MCP_SERVER_ENABLED=true` и ждём health, затем probe. Это соответствует формулировке DoD «запускает probe **после deploy на staging**» и устраняет хрупкие env-overrides для локального процесса (REDIS/DATABASE/S3 URL и т.д.).

## Изменения по файлам

### E-3: без изменений кода (только верификация)

Файл `docs/adr_016_pilot.md` уже соответствует промпту (задача 1) и даже богаче (таблица критериев, sample-size warning, JSON-report описание). Изменения не нужны — пилот лишь подтверждает DoD.

### E-4, файл 1: `docker-compose.yml` (+ паритет `docker-compose.bake.yml`)

В `environment:` сервиса `agent-service` добавить passthrough (после строки `FORENSIC_STREAM_ENABLED=false` или рядом с прочими preview-флагами):

```yaml
      - MCP_SERVER_ENABLED=${MCP_SERVER_ENABLED:-false}
      - MCP_SERVER_TRANSPORT=${MCP_SERVER_TRANSPORT:-sse}
```

Зачем: `env_file: .env` уже передаёт дефолт `false`; запись в `environment:` даёт возможность CI форсировать `true` через shell-env (`MCP_SERVER_ENABLED=true docker compose up -d --force-recreate agent-service` — shell имеет приоритет над env-file при compose-interpolation). Превью остаётся OFF по умолчанию (config default `False`).

`docker-compose.bake.yml` — зеркальная копия сервиса; обновить тем же passthrough для консистентности.

### E-4, файл 2: `scripts/ci-local-staging.sh`

1. В help/парсинг целей добавить `phase3-mcp-server-probe` (строки 31, 49).
2. Новый target в `run_tests()` (по аналогии с `phase3-adr011-integration`):

```bash
        phase3-mcp-server-probe)
            log_info "Running Phase 3 E-4: ADR-004 MCP Server preview probe..."
            local agent_port="${AGENT_SERVICE_HOST_PORT:-8000}"
            MCP_SERVER_ENABLED=true MCP_SERVER_TRANSPORT=sse \
                docker compose -f "${COMPOSE_FILE}" up -d --force-recreate agent-service
            wait_for_service "Agent service (MCP preview)" "http://localhost:${agent_port}/health"
            if "${PYTHON_EXE}" scripts/probe_mcp_server.py --url "http://localhost:${agent_port}"; then
                log_info "ADR-004 preview PILOT PASS - MCP Server probe succeeded"
            else
                log_error "ADR-004 preview ROLLBACK REQUIRED - MCP Server probe failed"
                exit 1
            fi
            ;;
```

3. Добавить цель в блок `all` (после `phase3-adr011-integration`).

Замечания: `set -euo pipefail` + конструкция `if ...; then` — probe с exit 1 не обрушивает скрипт молча; verdict печатается явно (DoD: «pass/rollback visible в CI output»). `--force-recreate` обязателен: обычная `up` не применит изменённый env к уже запущенному контейнеру.

### E-4, файл 3: `scripts/ci-local-staging.ps1` (паритет Windows)

1. Добавить `phase3-mcp-server-probe` в `[ValidateSet(...)]` (строка 3).
2. Новая функция (вызывает существующие `Invoke-Compose`, `Get-AgentServicePort`, `Invoke-Python`):

```powershell
function Run-Phase3McpServerProbe {
    param([string]$DockerPath, [pscustomobject]$Python)
    Write-Host "Running Phase 3 E-4: ADR-004 MCP Server preview probe..." -ForegroundColor Cyan
    $agentPort = Get-AgentServicePort
    $env:MCP_SERVER_ENABLED = "true"
    $env:MCP_SERVER_TRANSPORT = "sse"
    try {
        Invoke-Compose -DockerPath $DockerPath -Arguments @("up", "-d", "--force-recreate", "agent-service")
        $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
        while ([DateTime]::UtcNow -lt $deadline) {
            if (Test-HttpEndpoint -Uri "http://127.0.0.1:$agentPort/health") { break }
            Start-Sleep -Seconds 2
        }
        $arguments = @($Python.Prefix) + @("scripts/probe_mcp_server.py", "--url", "http://127.0.0.1:$agentPort")
        $result = Invoke-Python -Python $Python -Arguments $arguments
        if ($result -eq 0) {
            Write-Host "ADR-004 preview PILOT PASS - MCP Server probe succeeded" -ForegroundColor Green
        }
        else {
            Write-Host "ADR-004 preview ROLLBACK REQUIRED - MCP Server probe failed" -ForegroundColor Red
        }
        return $result
    }
    finally {
        Remove-Item Env:MCP_SERVER_ENABLED -ErrorAction SilentlyContinue
        Remove-Item Env:MCP_SERVER_TRANSPORT -ErrorAction SilentlyContinue
    }
}
```

3. switch-case + включить в блок `all` (после `Run-Phase3Adr011Integration`).

### E-4, задача 2 (тесты в CI) — покрыто существующим

`tests/integration/test_mcp_server_probe.py` уже запускается в CI: `ci-local-quick.sh` target `integration` (`pytest tests/integration`) и `ci-local-integration-staging.sh` (`pytest tests/integration -m integration`). Явного добавления не требует; верификация — прогон файла отдельно.

## Антипаттерны (соблюдаются)

- Не поднимаем второй локальный agent-service параллельно с compose-контейнером (конфликт порта 8000) — пересоздаём deploy-нутый контейнер.
- Не хардкодим порт — `${AGENT_SERVICE_HOST_PORT:-8000}` (.sh) / `Get-AgentServicePort` (.ps1).
- Не делаем probe blocking из-за tool-specific errors — probe-скрипт уже логирует и continue (H-4); в CI фейлим только по exit code.
- Не трогаем существующие modified-файлы из git status (чужие незакоммиченные изменения) — правим только перечисленные файлы.
- Не выставляем `MCP_SERVER_ENABLED=true` в `.env` — только shell-env на время target; после `docker compose down` (trap) состояние не сохраняется.

## Верификация

```powershell
# E-3
python -m pytest tests/unit/test_pilot_ollama_react.py -v
# локальный пилот (Ollama serve уже работает, модель llama3.1:8b есть):
python scripts/pilot_ollama_react.py --ollama-url http://localhost:11434 --model llama3.1:8b
# при 60-80%: python scripts/pilot_ollama_react.py --variant v2_tolerant (затем v3_cot)

# E-4
python -m pytest tests/integration/test_mcp_server_probe.py -v
ruff check scripts/probe_mcp_server.py tests/integration/test_mcp_server_probe.py
# синтаксис CI-скриптов:
bash -n scripts/ci-local-staging.sh
powershell -NoProfile -Command "$null = [System.Management.Automation.PSParser]::Tokenize((Get-Content scripts/ci-local-staging.ps1 -Raw), [ref]$null)"
# полный probe (если Docker доступен):
#   MCP_SERVER_ENABLED=true docker compose up -d --force-recreate agent-service
#   python scripts/probe_mcp_server.py --url http://localhost:8000  → exit 0
```

Ожидаемый вывод пилота E-3: `PILOT PASS - ADR-016 Approved` (или PARTIAL → tuning-вариант). Ожидаемый CI-verdict E-4: `ADR-004 preview PILOT PASS/ROLLBACK REQUIRED`.

## DoD mapping

| DoD-пункт | Реализация |
|---|---|
| E-3: `docs/adr_016_pilot.md` с manual procedure | уже существует на диске (проверено) |
| E-3: local pilot run работает | запуск `pilot_ollama_react.py` против Ollama + llama3.1:8b |
| E-3: success rate ≥80% достижим | вердикт реального пилота (или tuning v2/v3) |
| E-4: staging CI запускает `probe_mcp_server.py` | target `phase3-mcp-server-probe` в .sh + .ps1 |
| E-4: exit code проверяется (0=pass, 1=fail) | `if probe; then PASS else ROLLBACK; exit 1` |
| E-4: PASS/ROLLBACK виден в CI output | явные log-сообщения с вердиктом ADR-004 |
| E-4: тесты в CI | `test_mcp_server_probe.py` уже в `pytest tests/integration` (quick + integration-staging) |

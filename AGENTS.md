# AGENTS.md — OriaAI (llm-client)

## Quick Start

```bash
# 1. Create .env (if missing)
copy .env.example .env

# 2. Start infrastructure (Redis, MinIO, Vault, PostgreSQL, Prometheus, Grafana)
docker-compose up -d

# 3. Install package with dev dependencies
pip install -e ".[dev]"

# 4. Activate venv (PowerShell)
.\.venv\Scripts\Activate.ps1

# 5. Run tests
pytest tests -v
```

**Without venv activation:** `.\.venv\Scripts\python.exe -m pytest tests -v`

## Infrastructure Ports

| Service | Port | Notes |
|---------|------|-------|
| Redis | 6380 | Host port 6380 (6379 may be in use). `redis:6379` inside compose network |
| MinIO API | 9000 | S3-compatible storage (mandatory for dev) |
| MinIO Console | 9001 | Login from `.env` MINIO_ROOT_USER/PASSWORD |
| Vault | 8200 | Dev mode, root token = `root` |
| PostgreSQL | 5434 | Host port 5434 (5432 may be in use). `postgres:5432` inside compose network. Database: `llm_client` |
| Prometheus | 9090 | |
| Grafana | 3000 | admin/admin by default |
| Agent Service | 8000 | FastAPI, health at `/health`; ingestion `POST /documents` |
| Streamlit UI | 8501 | Started via `scripts/start.ps1` |

## Commands

### Tests

```bash
# All tests (unit + integration + staging_load)
pytest tests -v

# Unit only
pytest tests/unit -v

# Integration only (needs Redis/MinIO/Vault running)
pytest tests/integration -v

# Single test file
pytest tests/unit/test_cancel_token.py -v

# Single test
pytest tests/unit/test_cancel_token.py::test_function_name -v

# With coverage
pytest tests --cov=src/llm_client --cov-report=term-missing
```

**Test markers:** `integration` (needs docker-compose services), `staging_load` (nightly), `eval` (A/B test framework)

### Lint & Typecheck

```bash
# Lint
ruff check src tests

# Format (scoped to Phase 1 files in CI)
ruff format --check src tests

# Typecheck
mypy src/llm_client
```

CI runs: `ruff check` → `ruff format --check` → `mypy` → `pytest tests/unit`

### Migrations

```bash
alembic upgrade head
alembic current   # expected: 008 (fix_documents_search_schema)
```

Head chain: `004 baseline → 005 messages PII → 006 documents → 007 tsvector → 008 corrective`.  
Fresh DBs: 007 creates `search_vector tsvector GENERATED ALWAYS AS STORED` + unique `content_hash`. 008 repairs DBs that applied the broken 007.

### RAG Evaluation (Phase 2)

```bash
# A/B test for reranker evaluation (C6)
python scripts/ab_test_reranker.py

# Run evaluation tests
pytest tests/unit -m eval -v

# Run evaluation tests with coverage
pytest tests/unit -m eval --cov=src/llm_client/rag/eval --cov-report=term-missing
```

**Evaluation framework:** A/B test framework for RAG quality metrics (recall@5). Compares baseline (no reranker) vs treatment (with reranker) configurations. PASS if recall@5 improvement ≥15% AND latency overhead <100ms.

### Start/Stop Full Stack (PowerShell)

```powershell
.\scripts\start.ps1          # Starts infra + Streamlit UI
.\scripts\stop.ps1           # Stops Streamlit + docker-compose
```

## Architecture

- **Package:** `src/llm_client/` (hatchling build, Python 3.11+)
- **Entry point:** `python -m llm_client.agent` (agent-service)
- **UI:** Streamlit app at `src/llm_client/ui/app.py`
- **API:** FastAPI at `src/llm_client/api.py`

### Key Directories

| Directory | Purpose |
|-----------|---------|
| `src/llm_client/agent/` | LangGraph agent logic, cycle detection |
| `src/llm_client/transport/` | Cancel token, Redis pub/sub transport |
| `src/llm_client/storage/` | S3-compatible file storage (MinIO/S3) |
| `src/llm_client/security/` | PII detection (Presidio + spaCy) |
| `src/llm_client/observability/` | Logging, KMS, forensic stream, ideality |
| `src/llm_client/rag/` | RAG pipeline, rerankers (BGE, Cohere) |
| `src/llm_client/ui/` | Streamlit UI, auto-cancel JS |
| `src/llm_client/orchestration/` | Orchestration layer |
| `migrations/` | Alembic SQL migrations |
| `ops/` | Prometheus, Grafana, Vault configs |
| `scripts/` | Dev helpers (start/stop, benchmarks, metrics) |
| `tests/` | unit/, integration/, staging_load/ |

## Gotchas

- **Redis DB separation:** DB 0 = pub/sub (cancel channel), DB 1 = checkpoint-WAL. Do NOT cross-use.
- **MinIO is mandatory** for local dev. `LocalFileStorage` was removed; `S3CompatibleStorage` is the only backend.
- **OPENAI_API_KEY** is required at import time when `LLM_PROVIDER=openai` (default). Tests set a placeholder via `conftest.py`.
- **Vault** is only needed when `FORENSIC_STREAM_ENABLED=true` (prod/staging). In dev mode it's off.
- **spaCy model** required for PII detection: `python -m spacy download en_core_web_md`
- **Execution policy:** If `Activate.ps1` is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
- **Redis port 6379:** May be in use by other projects. Host access is on 6380; compose network uses 6379.
- **MinIO images:** Use `quay.io/minio/...` (Docker Hub minio repos removed 2026-09).
- **Config validation:** `Settings` (pydantic-settings) validates fail-fast at startup. Missing keys cause immediate error.

## CI Workflows

- **phase1-ci.yml:** On push/PR → lint → typecheck → unit tests → integration tests → cancel latency (dev sample)
- **phase1-nightly.yml:** Full staging load (1000 samples), PII audit, S3 parity matrix, ideality metric
- **checkpoint-nightly.yml:** Checkpoint backend nightly tests

## Code Style

- Python 3.11+, ruff (line-length 100, target py311)
- Pyright basic mode
- pytest-asyncio (auto mode)
- No comments unless asked

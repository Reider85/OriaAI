# OriaAI

> Production-grade LLM client — LangGraph agent orchestration, hybrid RAG, PII-aware dual-stream logging, and S3-compatible forensic storage. Built for enterprise workloads where auditability, cancellation, and retrieval quality are first-class concerns.

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](./LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![Build: hatchling](https://img.shields.io/badge/build-hatchling-00BBA4.svg)](https://hatch.pypa.io/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://docs.astral.sh/ruff/)
[![Type check: mypy](https://img.shields.io/badge/types-mypy-2.7.0+-blue.svg)](http://mypy-lang.org/)
[![Tests: 194 passing](https://img.shields.io/badge/tests-194%20passing-brightgreen.svg)](#testing)
[![Phase: MVP | ALPHA | BETA](https://img.shields.io/badge/phase-MVP%20%7C%20ALPHA%20%7C%20BETA-orange.svg)](#roadmap--phases)
[![DB: PostgreSQL 16](https://img.shields.io/badge/PostgreSQL-16-336791.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Infra: Redis | MinIO | Vault](https://img.shields.io/badge/infra-Redis%20%7C%20MinIO%20%7C%20Vault-red.svg)](#services--ports)

---

## Table of Contents

- [Overview](#overview)
- [Highlights](#highlights)
- [Architecture](#architecture)
- [Roadmap & Phases](#roadmap--phases)
  - [MVP — Core Infrastructure & Security](#mvp--core-infrastructure--security)
  - [ALPHA — ML & Search](#alpha--ml--search)
  - [BETA — Eviction Policy & Semantic Cache Foundation](#beta--eviction-policy--semantic-cache-foundation)
- [Quick Start](#quick-start)
- [Services & Ports](#services--ports)
- [Configuration](#configuration)
- [Testing](#testing)
- [CI/CD Pipelines](#cicd-pipelines)
- [Project Structure](#project-structure)
- [Architecture Decision Records](#architecture-decision-records)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Overview

OriaAI (`llm-client`) is a Python 3.11+ package implementing a LangGraph-based agent service with retrieval-augmented generation, MCP-style orchestration, and multi-provider LLM support. It ships with a FastAPI service, a Streamlit UI, and a complete Docker Compose stack — Redis, MinIO, HashiCorp Vault, PostgreSQL 16, Prometheus, and Grafana — for local development that mirrors staging.

The project is delivered in three completed phases: **MVP** (core infrastructure and security primitives), **ALPHA** (ML reranking, full-text search, hybrid RAG, evaluation framework, multi-provider LLMs), and **BETA** (Redis eviction policy with composite checkpointer recovery and isolated semantic-cache integration tests). See the [Roadmap & Phases](#roadmap--phases) section for the full breakdown.

---

## Highlights

- **Cancellation as a first-class primitive** — Redis pub/sub transport (`CancellationToken`, `CancelPublisher`/`CancelSubscriber`) plus an HTTP endpoint `POST /sessions/{id}/cancel` and Streamlit auto-cancel on tab close.
- **Dual-stream logging** — Operational stream (PII masked, 30-day retention) and forensic stream (AES-256-GCM encrypted via Vault transit, 90+ day retention in a dedicated S3 bucket).
- **PII detection** — Microsoft Presidio + custom regex for `EMP-\d{6}`, `PRJ-[A-Z]{3}-\d{4}` and the standard PERSON / EMAIL / PHONE / CREDIT_CARD / IBAN / IP / US_SSN / URL entities.
- **Single S3 backend** — `LocalFileStorage` has been removed; the only file backend is `S3CompatibleStorage` (MinIO for dev, AWS S3 for prod), with multipart upload, exponential retry, and proper error mapping.
- **Hybrid RAG** — BM25 + vector fusion, BGE-reranker-base (278M params) and optional Cohere reranker, A/B test framework gated on `recall@5 ≥ 15%` improvement AND `< 100 ms` latency overhead.
- **PostgreSQL 16 full-text search** — `tsvector GENERATED ALWAYS AS STORED` columns, GIN indexes, `pg_trgm` fuzzy matching, hybrid query `< 50 ms` on 10k documents at staging.
- **Multi-provider LLMs** — OpenAI, Anthropic, Ollama, `CUSTOM-OPENAI` (any OpenAI-compatible endpoint), and `ZAI` (Zhipu AI `glm-4.5`).
- **Production-minded CI** — Separate PR pipelines (mocked APIs) and nightly pipelines (real Tavily / Cohere / OpenAI / pgvector), 30-day artifact retention, HuggingFace cache, Slack notifications.
- **194 tests passing** — 122 unit + 16 integration + 56 staging-load, in 65.38 s on a dev laptop.

---

## Architecture

```
                ┌─────────────────────────────────────────────────────────┐
                │                     Streamlit UI (:8501)                 │
                │   auto_cancel.py  ·  inject_auto_cancel()  ·  Stop btn   │
                └────────────────────────────────────┬────────────────────┘
                                                     │  HTTP / SSE
                                                     ▼
                ┌─────────────────────────────────────────────────────────┐
                │              FastAPI Agent Service (:8000)               │
                │   POST /sessions/{id}/cancel   ·   POST /documents       │
                │   SSE tool events              ·   DELETE /documents/{id} │
                └────────────┬───────────────────────────────────┬────────┘
                             │                                    │
              ┌──────────────▼──────────────┐     ┌───────────────▼──────────────┐
              │   LangGraph Agent + cycle    │     │       RAG Pipeline           │
              │   detection (state-delta)    │     │  retrieve → rerank → answer  │
              │   orchestration · MCP        │     │   BGE / Cohere / hybrid      │
              └──────────────┬──────────────┘     └───────────────┬──────────────┘
                             │                                     │
        ┌────────────────────┼─────────────────────┬───────────────┼──────────────┐
        ▼                    ▼                     ▼               ▼              ▼
  ┌──────────┐      ┌───────────────┐     ┌───────────────┐  ┌──────────┐  ┌───────────┐
  │  Redis   │      │     MinIO     │     │    Vault      │  │PostgreSQL│  │  LLM      │
  │ DB0 pub  │      │   S3 buckets  │     │   transit     │  │  16 +    │  │ Providers │
  │ DB1 WAL  │      │ files/forensic │     │ AES-256-GCM   │  │ pgvector │  │ OpenAI /  │
  │ allkeys- │      │  lifecycle:   │     │   KMS         │  │ tsvector │  │ Anthropic │
  │   lru    │      │  30d / 90d    │     │               │  │  + GIN   │  │ ZAI / ... │
  └──────────┘      └───────────────┘     └───────────────┘  └──────────┘  └───────────┘
        │                                                                          │
        └─────────────── composite checkpointer read-through ─────────────────────┘
                                (Redis evicts → PG recovers)
```

---

## Roadmap & Phases

The project is delivered in three completed phases. Each phase is fully implemented and covered by automated tests.

### MVP — Core Infrastructure & Security

**Scope (Phase 1, ADR-013 / ADR-014 / extended ADR-008):** Cancel transport, single S3 backend, PII detection, dual-stream logging, KMS integration, and a local-dev mode that does not require Vault.

| Block | Component | Location | Notes |
|---|---|---|---|
| **B-1** | Cancel via Redis pub/sub | `src/llm_client/transport/` | `CancellationToken`, `Registry`, `CancelPublisher`, `CancelSubscriber` + HTTP endpoint `POST /sessions/{id}/cancel` |
| **B-2** | `S3CompatibleStorage` (minimal) | `src/llm_client/storage/` | `FileStorage` interface, MinIO dev / S3 prod |
| **B-3** | State-Delta Cycle Detection (preview) | `src/llm_client/agent/cycle_detection.py` | `compute_state_delta`, `IterationMonitor`; flags `cycle_detected` on 2 similar iterations |
| **C-5** | UI auto-cancel for Streamlit | `src/llm_client/ui/auto_cancel.py` | Listens to `visibilitychange` / `pagehide` / `beforeunload`; `navigator.sendBeacon` with `fetch keepalive` fallback; 5-second debounce |
| **C-6** | Cancel → forensic logging | `src/llm_client/transport/` (handler) | Operational: masked `{event_type, session_id, user_id:"[MASKED]", reason, timestamp}`. Forensic: full trace with `user_id`, partial answer size, last node, message count, `duration_ms` |
| **D-1** | `PIIDetector` | `src/llm_client/security/pii_detector.py` | Presidio + spaCy `en_core_web_md`; detects `PERSON`, `EMAIL`, `PHONE`, `CREDIT_CARD`, `IBAN`, `IP`, `US_SSN`, `URL` + internal `EMP-\d{6}` and `PRJ-[A-Z]{3}-\d{4}`. `PII_DETECTOR_ENABLED=false` = no-op |
| **D-2/D-3** | Dual-stream logging | operational sink + `ForensicStreamWriter` | Operational: `OPERATIONAL_LOG_SINK=stdout\|loki\|elk`, PII masked, batch 100 ms / 100 events, 30-day retention. Forensic: AES-256-GCM via Vault transit, batch 500 ms / 50 events, 90+ day retention in `llm-client-forensic` bucket |
| **D-4** | KMS `KeyProvider` | `src/llm_client/security/` | `KMS_PROVIDER=vault` (default) or `local` (TEST ONLY). Vault-transit interface abstracts future managed KMS migration |
| **D-5** | PII score in messages | DB layer + `migrations/005_add_pii_score_to_messages.sql` | `attach_pii_metadata()` computes `pii_score FLOAT` and `pii_entities JSONB` (only `{type, start, end}`, never raw PII). Indexed via `idx_messages_pii_score`. Daily metrics in `ops/pii_analytics.sql` |
| **D-6** | Local dev without Vault | config layer | `ENVIRONMENT=dev` + `FORENSIC_STREAM_ENABLED=false` → app starts with only Redis + MinIO. PIIDetector and operational logging always active. `env=prod` rejects `FORENSIC_STREAM_ENABLED=false` at startup (fail-fast) |
| **E-1** | Production-quality `S3CompatibleStorage` | `src/llm_client/storage/s3.py` | Built on `aiobotocore`. Multipart upload > 5 MB (8 MB parts), abort on error. Full `save` / `get` / `get_stream` / `delete` / `exists` / `list` contract. Error mapping: `404 → FileNotFoundError`, `403 → PermissionError`, transient → exponential retry (1 ms → 2 ms → 4 ms) then `StorageError` |
| **E-2** | `LocalFileStorage` removed | — | Single backend; `STORAGE_BACKEND` flag retired. `rg "LocalFileStorage\|STORAGE_BACKEND" src/` returns 0 matches |
| **E-3** | `InMemoryFileStorage` test-double | `tests/conftest.py` | Thread-safe dict-backed `FileStorage`; `file_storage` fixture available everywhere |
| **E-4** | S3 access logs → forensic stream | `src/llm_client/observability/access_log_ingestor.py` | `AccessLogIngestor` background task polls `_access_logs/` prefix every 5 min, parses `{bucket, key, operation, requester, request_id, timestamp, bytes_transferred}`, writes to `ForensicStreamWriter`. Requester not in `S3_ACCESS_LOG_ALLOWLIST` → Slack alert to `SECURITY_ALERT_WEBHOOK_URL` |

### ALPHA — ML & Search

**Scope (Phase 2):** Reranker integration, PostgreSQL 16 full-text search, hybrid RAG with BM25 + vector fusion, multi-provider LLM support, RAG evaluation framework, and dedicated PR / nightly CI pipelines.

| Area | Component | Highlights |
|---|---|---|
| **ML reranker** | BGE-reranker-base (`BAAI/bge-reranker-base`) | 278 M parameters, ~600 MB RAM after load, ~1.2 GB peak at inference. Latency ~150 ms CPU / ~30 ms GPU on 20 chunks (`batch_size=8/32`). Cached in `models/bge-reranker-base/` via `scripts/download_bge_reranker.py` |
| **Reranker integration** | ADR-017 | Drop-in reranker in RAG pipeline; alternative Cohere reranker via `pip install -e ".[rerank]"` |
| **PostgreSQL 16 FTS** | DB layer + `migrations/` | `tsvector GENERATED ALWAYS AS STORED`, GIN index `idx_documents_search_vector`, trigram fuzzy via `pg_trgm` (`idx_documents_content_trgm`), unique `content_hash` for idempotent upsert in `BM25IndexBuilder` |
| **Hybrid query benchmark** | — | Vector + tsvector fusion `< 50 ms` on staging with 10 k documents, ordered by `ts_rank` |
| **Vector store** | `VECTOR_STORE_KIND=none\|chroma\|pgvector` | Default `none`. `chroma` via `pip install -e ".[vector]"`; `pgvector` ships with `pgvector>=0.3.4`. Embeddings: `EMBEDDING_PROVIDER=openai\|none`, `EMBEDDING_MODEL=text-embedding-3-small` |
| **Document ingestion API** | ADR-020, `POST /documents`, `DELETE /documents/{id}` | Response: `{document_id, status:"indexed\|partial", bm25_indexed, vector_indexed}`. Auth disabled in dev only |
| **Multi-provider LLMs** | `langchain-openai`, `langchain-anthropic`, `langchain-ollama` (optional) | `CUSTOM-OPENAI`: any OpenAI-compatible endpoint with custom `base_url` + `api_key`. `ZAI`: Zhipu AI (`z.ai`) endpoint `https://api.z.ai/api/paas/v4`, model `glm-4.5` |
| **RAG evaluation framework** | `datasets/rag_eval/` + A/B test runner | PASS criterion: `recall@5` improvement `≥ 15 %` AND latency overhead `< 100 ms`. Test marker: `eval` |
| **Observability** | Prometheus `:9090`, Grafana `:3000`, Idealidad metrics exporter `:9101` | `idealidad-metric` job updates Phase 2 metrics nightly |
| **Local CI scripts** | `scripts/ci-local-quick.ps1`, `scripts/ci-local-staging.ps1` | Mirror PR and nightly pipelines locally with `-Target` filters and `-TimeoutSeconds` |

### BETA — Eviction Policy & Semantic Cache Foundation

**Scope (Phase 3, currently implemented):** Global Redis eviction policy with safe checkpoint recovery via the composite checkpointer, isolated semantic-cache integration tests, and AOF persistence tuning.

| Area | Implementation | Notes |
|---|---|---|
| **Redis global eviction policy** | ADR-011 — `allkeys-lru` (maxmemory 1 GB) | Supersedes Phase 2 `noeviction` (DoD A-1 superseded, see `analytics/ARCHITECT.md` §8). Eviction is safe: checkpoints in Redis DB 1 are recovered read-through from PostgreSQL via the composite checkpointer |
| **Eviction alerting** | Monitoring on `evicted_keys` | Small LRU churn under memory pressure is acceptable. A sharp increase triggers an alert: checkpoints are being evicted faster than the PG flusher can pin them (> 5 s lag = data loss on restart) |
| **Redis DB separation** | DB 0 = pub/sub cancel channel (ADR-013), DB 1 = checkpoint-WAL (ADR-010) | Pub/sub does not cross DB boundaries in a single connection; do not switch DBs without need |
| **AOF persistence** | `appendfsync=everysec`, `aof_enabled=1` | `appendonly.aof` grows in the `redis-data` volume as graphs execute. Verified via `INFO persistence` |
| **Semantic cache integration tests** | `.github/workflows/phase3-nightly.yml` | Isolated from `phase2-nightly.yml` per E-5 anti-pattern avoidance (no Phase 3 jobs in Phase 2 nightly) |
| **Pilot ADRs** | `docs/adr_015_pilot.md`, `docs/adr_016_pilot.md`, `docs/migration_adr_005_to_015.md` | Architecture pilots and the ADR-005 → ADR-015 migration plan |

---

## Quick Start

```bash
# 1. Copy environment variables
cp .env.example .env

# 2. Bring up the full infrastructure stack
docker-compose up -d

# 3. Install the Python package with dev dependencies
pip install -e ".[dev]"

# 4. (Optional) Download the BGE reranker model (~600 MB, 2-5 minutes)
python scripts/download_bge_reranker.py

# 5. (Optional) Install spaCy model for PII detection
python -m spacy download en_core_web_md

# 6. Apply database migrations
alembic upgrade head

# 7. Run the test suite
pytest tests -v
```

PowerShell users: activate the venv first with `.\.venv\Scripts\Activate.ps1` (or run `.\.venv\Scripts\python.exe -m pytest tests -v` directly). If `Activate.ps1` is blocked by execution policy: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

> **MinIO is mandatory for local development.** There is no `LocalFileStorage` fallback since Block E. `docker-compose up -d` brings it up alongside Redis, Vault, and PostgreSQL.

### Smoke checks

```bash
# Redis pub/sub round-trip (< 5 ms)
docker-compose exec redis redis-cli ping                            # → PONG
docker-compose exec redis redis-cli -n 1 INFO persistence | grep aof_enabled   # → 1

# MinIO buckets
docker-compose exec minio mc ls local/                              # → llm-client-files/  llm-client-forensic/

# Vault transit encrypt/decrypt
docker-compose exec vault vault status                              # → Initialized: true, Sealed: false

# PostgreSQL full-text search
docker-compose exec postgres pg_isready -U postgres -d llm_client   # → accepting connections
docker-compose exec postgres psql -U postgres -d llm_client -c \
  "EXPLAIN ANALYZE SELECT * FROM documents
   WHERE search_vector @@ websearch_to_tsquery('english', 'hello world')
   ORDER BY ts_rank(search_vector, websearch_to_tsquery('english', 'hello world')) DESC
   LIMIT 10;"                                                       # → Bitmap Index Scan on idx_documents_search_vector
```

---

## Services & Ports

| Service | Host port | Compose network | Purpose |
|---|---|---|---|
| Redis | `localhost:6380` | `redis:6379` | DB 0 — pub/sub cancel channel (ADR-013); DB 1 — checkpoint-WAL (ADR-010). Mounted on `6380` to avoid conflicts with host Redis on `6379` |
| MinIO API | `http://localhost:9000` | `minio:9000` | S3-compatible storage. `llm-client-files` (30-day ILM) and `llm-client-forensic` (90-day ILM) buckets |
| MinIO Console | `http://localhost:9001` | — | Web UI. Login from `.env`: `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` |
| HashiCorp Vault | `http://localhost:8200` | `vault:8200` | Dev mode, root token = `root`. Transit engine, key `forensic-aes256-gcm` (`type=aes256-gcm96`) |
| PostgreSQL 16 | `localhost:5434` | `postgres:5432` | Database `llm_client`. tsvector + GIN + pg_trgm + pgvector |
| Prometheus | `http://localhost:9090` | `prometheus:9090` | Metrics scraper |
| Grafana | `http://localhost:3000` | `grafana:3000` | Dashboards. Default `admin` / `admin` |
| Idealidad exporter | `http://localhost:9101` | — | Phase ideality metrics |
| Agent Service (FastAPI) | `http://localhost:8000` | `agent-service:8000` | Entry point `python -m llm_client.agent` |
| Streamlit UI | `http://localhost:8501` | — | `src/llm_client/ui/app.py` |

---

## Configuration

All configuration is environment-driven via `.env` (see `.env.example`). The config layer fails fast at startup if a production value is missing or inconsistent (e.g. `ENVIRONMENT=prod` + `FORENSIC_STREAM_ENABLED=false` is rejected).

### Core

| Variable | Default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `dev` | `dev` / `staging` / `prod`. Affects fail-fast validation |
| `LLM_PROVIDER` | `openai` | `openai` / `anthropic` / `ollama` / `custom-openai` / `zai` |
| `OPENAI_API_KEY` | — | Required at import time when `LLM_PROVIDER=openai` |
| `FORENSIC_STREAM_ENABLED` | `false` | `true` requires Vault; rejected if `false` in `env=prod` |
| `KMS_PROVIDER` | `vault` | `vault` (default) or `local` (TEST ONLY) |
| `PII_DETECTOR_ENABLED` | `true` | `false` = no-op detector for dev/test |
| `PII_METADATA_ENABLED` | `true` | `false` → `pii_score` and `pii_entities` columns stay `NULL` |

### Transport & storage

| Variable | Example | Purpose |
|---|---|---|
| `REDIS_URL` | `redis://localhost:6380/0` | Pub/sub cancel channel (DB 0) |
| `REDIS_CHECKPOINT_URL` | `redis://localhost:6380/1` | Checkpoint-WAL (DB 1) |
| `S3_ENDPOINT` | `http://localhost:9000` | MinIO or AWS S3 endpoint |
| `S3_ACCESS_KEY` / `S3_SECRET_KEY` | `minioadmin` / `minioadmin` | S3 credentials |
| `S3_BUCKET` | `llm-client-files` | Operational files bucket |
| `S3_FORENSIC_BUCKET` | `llm-client-forensic` | Forensic bucket (90-day ILM) |
| `S3_ACCESS_LOG_ALLOWLIST` | `llm-client-service` | Requester allow-list for `AccessLogIngestor` |
| `SECURITY_ALERT_WEBHOOK_URL` | Slack webhook | Alert target for non-allow-listed S3 access |

### Search & ML

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://postgres:postgres@localhost:5434/llm_client` | PostgreSQL 16 |
| `PG_TEXT_SEARCH_CONFIG` | `english` | FTS configuration |
| `PG_FUZZY_MATCHING_ENABLED` | `false` | Enable `pg_trgm` fuzzy matching |
| `VECTOR_STORE_KIND` | `none` | `none` / `chroma` / `pgvector` |
| `EMBEDDING_PROVIDER` | `openai` | `openai` / `none` |
| `EMBEDDING_MODEL` | `text-embedding-3-small` | OpenAI embedding model |
| `CHROMA_PERSIST_DIR` | `./chroma_db` | Chroma persistence dir when `VECTOR_STORE_KIND=chroma` |
| `RERANKER_MODEL_NAME` | `BAAI/bge-reranker-base` | HuggingFace model id |
| `RERANKER_MODEL_DIR` | `./models/bge-reranker-base` | Local cache dir |
| `RERANKER_DEVICE` | `cpu` | `cpu` or `cuda` |
| `RERANKER_MAX_LENGTH` | `512` | Max sequence length |
| `RERANKER_BATCH_SIZE` | `8` | Inference batch size |

### Cycle detection

| Variable | Default | Purpose |
|---|---|---|
| `CYCLE_DETECTION_ENABLED` | `true` | Toggle state-delta cycle detection |
| `CYCLE_DETECTION_THRESHOLD` | `0.85` | Similarity threshold for two consecutive iterations |

---

## Testing

**194 tests passing in 65.38 s** — 122 unit + 16 integration + 56 staging-load.

```bash
# Full suite
pytest tests -v

# By marker
pytest tests -m unit -v
pytest tests -m integration -v          # requires Redis/MinIO/Vault running
pytest tests -m staging_load -v
pytest tests -m eval -v                  # RAG A/B test framework

# Specific Phase 1 components
pytest tests/unit/test_cancel_token.py \
       tests/unit/test_cancel_transport.py \
       tests/unit/test_cancel_endpoint.py \
       tests/unit/test_cycle_detection.py \
       tests/unit/test_access_log_ingestor.py \
       tests/unit/test_s3_storage.py \
       tests/integration/test_redis_cancel.py \
       tests/integration/test_minio_storage.py -v
```

Test markers: `unit`, `integration`, `staging_load`, `eval`. `pytest-asyncio` runs in auto mode. `moto[s3]` is available for S3 mocking in unit tests; `InMemoryFileStorage` is the canonical test-double for `FileStorage`.

---

## CI/CD Pipelines

### Phase 2 PR pipeline (`.github/workflows/phase2-ci.yml`)

Triggered on `push` to `main` and on every `pull_request`. External APIs (Tavily, OpenAI, Cohere) are mocked.

| Job | Description | Timeout |
|---|---|---|
| `lint` | ruff | — |
| `typecheck` | mypy | — |
| `unit-tests` | unit tests with coverage | — |
| `integration-dev` | integration tests against Redis + PG + MinIO + Vault | 120 s |
| `checkpoint-quick` | checkpoint latency, 100 samples | 120 s |
| `bm25-indexing-regression` | BM25 indexer unit test | 30 s |
| `reranker-quick` | reranker quick test, 10 queries | 180 s |
| `hybrid-rag-quick` | hybrid RAG quick test, 15 queries | 300 s |
| `web-search-quick` | web search quick test, mocked Tavily | 60 s |
| `rag-query-quick` | RAG query quick test, mocked pipeline | 120 s |
| `ui-render-phase2-quick` | UI tests (G-1..G-4) | 60 s |

### Phase 2 nightly pipeline (`.github/workflows/phase2-nightly.yml`)

Triggered at 2 AM UTC daily and via `workflow_dispatch`. Sequential, staggered to avoid staging overload. Uses real APIs.

| Job | Description | Timeout | Requirements |
|---|---|---|---|
| `checkpoint-latency-staging` | 1000 samples, p99 < 2 ms | 600 s | Redis + PG |
| `checkpoint-recovery-staging` | 4 recovery scenarios (B-5) | 1200 s | Redis + PG + app |
| `reranker-ab-test-staging` | 50+ queries, A/B test | 600 s | bge model |
| `hybrid-rag-ab-test-staging` | 30 queries, A/B test | 600 s | PG tsvector + bge |
| `web-search-integration-staging` | 5 queries, real Tavily | 180 s | `STAGING_TAVILY_API_KEY` |
| `rag-query-integration-staging` | 10 queries, real pgvector | 300 s | staging PG |
| `sse-tool-events-staging` | full SSE flow test | 120 s | agent service |
| `idealidad-metric` | Phase 2 metrics update | 300 s | Prometheus |

### Phase 3 nightly pipeline (`.github/workflows/phase3-nightly.yml`)

Isolated from Phase 2 nightly per E-5 anti-pattern. Runs ADR-011 semantic cache integration tests against the full docker-compose stack.

### Other workflows

- **`phase1-ci.yml`** — Phase 1 baseline: lint → typecheck → unit tests + coverage → integration-dev → integration-staging (forensic + Vault) → cancel latency (dev sample).
- **`phase1-nightly.yml`** — Full staging load (1000 samples), PII audit, S3 parity matrix, ideality metric.
- **`checkpoint-nightly.yml`** — Checkpoint backend nightly tests.

### Required GitHub secrets

| Secret | Purpose | Required for |
|---|---|---|
| `STAGING_TAVILY_API_KEY` | Real Tavily API calls | `web-search-integration-staging` |
| `COHERE_API_KEY` | Cohere reranker API | `reranker-ab-test-staging`, `hybrid-rag-ab-test-staging` |
| `OPENAI_API_KEY` | OpenAI API for RAG | `rag-query-integration-staging` |
| `SLACK_WEBHOOK_URL` | Failure notifications | all nightly jobs |

### Local CI mirroring

```powershell
# PR simulation
powershell -ExecutionPolicy Bypass -File scripts\ci-local-quick.ps1 -Target "lint,typecheck,unit,checkpoint,reranker"

# Nightly simulation
powershell -ExecutionPolicy Bypass -File scripts\ci-local-staging.ps1 -Target "checkpoint-latency,reranker-ab-test,web-search-integration"
```

Reports are written to `test-results/{checkpoint-latency,reranker-ab-test,web-search-integration,idealidad}/` with 30-day artifact retention.

---

## Project Structure

```
OriaAI/
├── .github/workflows/          # CI: phase1-ci, phase1-nightly, phase2-ci, phase2-nightly, phase3-nightly, checkpoint-nightly
├── .opencode/plans/            # Planning documents
├── analytics/                  # ARCHITECT.md (§8 covers eviction policy & ADR-011)
├── config/                     # Runtime configuration templates
├── datasets/rag_eval/          # RAG evaluation datasets (recall@5 A/B tests)
├── docs/                       # ADRs: adr_015_pilot.md, adr_016_pilot.md, migration_adr_005_to_015.md
├── migrations/                 # SQL migrations (005_add_pii_score_to_messages.sql, 008_fix_documents_search_schema, ...)
├── ops/                        # pii_analytics.sql and other operational SQL
├── redis/                      # Redis config and AOF volume mount
├── reports/                    # Generated test and benchmark reports
├── scripts/                    # download_bge_reranker.py, ci-local-quick.ps1, ci-local-staging.ps1
├── src/llm_client/
│   ├── agent/                  # LangGraph logic + cycle_detection.py (B-3)
│   ├── api.py                  # FastAPI: POST /sessions/{id}/cancel, POST /documents, SSE
│   ├── config.py               # Pydantic settings, fail-fast validation
│   ├── mcp/                    # MCP-style orchestration primitives
│   ├── observability/          # access_log_ingestor.py (E-4), metrics
│   ├── orchestration/          # Orchestration layer
│   ├── rag/                    # Hybrid RAG pipeline, BM25IndexBuilder, rerankers
│   ├── security/               # pii_detector.py (D-1), KMS KeyProvider (D-4)
│   ├── storage/                # s3.py (E-1), FileStorage interface
│   ├── transport/              # CancellationToken, CancelPublisher/Subscriber (B-1, C-6)
│   ├── types.py                # Shared types
│   └── ui/                     # app.py (Streamlit), auto_cancel.py (C-5)
├── tests/                      # unit/ integration/ staging_load/ conftest.py (E-3 InMemoryFileStorage)
├── .env.example                # Template for environment variables
├── AGENTS.md                   # Agent-oriented project overview
├── CONTRIBUTING.md             # Contribution guidelines
├── Dockerfile.agent            # Agent service image
├── LICENSE                     # Apache License 2.0
├── Makefile                    # Common tasks
├── ORYA_PROXY_CONFIG.md        # Proxy configuration reference
├── README.md                   # This file
├── SETUP_COMPLETE.md           # Dev environment setup notes
├── alembic.ini                 # Alembic config
├── docker-compose.yml          # Full stack: Redis, MinIO, Vault, PG, Prometheus, Grafana
├── docker-compose.bake.yml     # Bake pipeline
└── pyproject.toml              # hatchling build, Python 3.11+
```

---

## Architecture Decision Records

| ADR | Phase | Topic |
|---|---|---|
| ADR-008 | MVP | S3-compatible storage (extended in Block E) |
| ADR-010 | BETA | Redis DB 1 checkpoint-WAL |
| ADR-011 | BETA | Global Redis eviction policy `allkeys-lru`, composite checkpointer read-through |
| ADR-013 | MVP | Cancel transport via Redis pub/sub |
| ADR-014 | MVP | Forensic bucket retention (90-day ILM) and dual-stream logging |
| ADR-015 | BETA | Pilot ADR — see `docs/adr_015_pilot.md` |
| ADR-016 | BETA | Pilot ADR — see `docs/adr_016_pilot.md` |
| ADR-017 | ALPHA | BGE reranker in RAG pipeline |
| ADR-020 | ALPHA | Document ingestion API |

The `docs/migration_adr_005_to_015.md` document covers the migration plan from ADR-005 to ADR-015.

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `minio-init` fails with `Connection refused` | Wait for MinIO to become `healthy` (`docker-compose ps`) before running `minio-init` |
| `vault-init` reports "path is already in use" | Idempotent script — re-running is safe (`2>/dev/null \|\| echo`) |
| Vault "unknown key type aes256-gcm" | Use `type=aes256-gcm96` (current Vault naming for AES-256-GCM) |
| `minio/minio` or `minio/mc` pull denied | Docker Hub repos removed (2026-09). Use `quay.io/minio/...` images (already in compose) |
| Redis does not answer `PONG` | `docker-compose logs redis` — check for `maxmemory` warnings |
| Port `6379` is already in use | This repo mounts Redis on `6380:6379`. Update `REDIS_URL` in `.env` if you change it |
| MinIO Console returns 403 | Verify `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` in `.env` |
| `pytest` is not recognised in PowerShell | Activate venv: `.\.venv\Scripts\Activate.ps1`; or run `.\.venv\Scripts\python.exe -m pytest tests -v` directly |
| `mc cp C:\...` fails inside MinIO container | `mc` runs in the container where Windows paths do not exist. `docker cp` the file into the container first, then `mc cp` from `/tmp/` |

---

## Roadmap

Future phases (not yet implemented):

- **Phase 4** — Multi-tenant isolation, RBAC on ingestion API, semantic cache production rollout.
- **Phase 5** — TLS for all internal docker-compose traffic, managed KMS migration (AWS KMS / GCP KMS / Azure Key Vault) via the existing `KMS_PROVIDER` abstraction, full production hardening.

---

## Contributing

Please read [CONTRIBUTING.md](./CONTRIBUTING.md) before opening an issue or pull request. The short version: trunk-based branching, Conventional Commits, ruff + mypy must pass, all tests in the affected phase must be green, and new features must ship with tests.

---

## License

Licensed under the **Apache License, Version 2.0**. See [LICENSE](./LICENSE) for the full text.

```
Copyright 2026 Reider85

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
```

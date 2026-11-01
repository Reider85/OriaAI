# Contributing to OriaAI

Thanks for your interest in contributing to OriaAI! This document covers the basics of getting set up, opening issues, and submitting pull requests. The full project setup, services, and configuration reference live in the [README](./README.md).

By participating in this project, you agree to abide by its [Code of Conduct](#code-of-conduct).

---

## Table of Contents

- [Quick Start for Contributors](#quick-start-for-contributors)
- [Opening Issues](#opening-issues)
- [Pull Requests](#pull-requests)
- [Branching & Commits](#branching--commits)
- [Code Style](#code-style)
- [Testing](#testing)
- [CI Requirements](#ci-requirements)
- [Adding New Features](#adding-new-features)
- [Code of Conduct](#code-of-conduct)
- [License](#license)

---

## Quick Start for Contributors

```bash
# 1. Fork the repository on GitHub, then clone your fork
git clone https://github.com/<your-username>/OriaAI.git
cd OriaAI

# 2. Add the upstream remote for syncing
git remote add upstream https://github.com/reider85/OriaAI.git

# 3. Copy environment variables and bring up the infrastructure
cp .env.example .env
docker-compose up -d

# 4. Create a virtual environment and install the package with dev dependencies
python -m venv .venv
source .venv/bin/activate            # macOS / Linux
# .\.venv\Scripts\Activate.ps1       # Windows PowerShell
pip install -e ".[dev]"

# 5. (Optional) Download the BGE reranker model and spaCy model
python scripts/download_bge_reranker.py
python -m spacy download en_core_web_md

# 6. Apply database migrations
alembic upgrade head

# 7. Run the test suite to verify everything works
pytest tests -v
```

See the [Services & Ports](./README.md#services--ports) and [Configuration](./README.md#configuration) sections of the README for the full infrastructure and environment reference.

---

## Opening Issues

- **Bug reports** — Include the OriaAI version (`python -c "import llm_client; print(llm_client.__version__)"` or check `pyproject.toml`), Python version, OS, the exact command or HTTP request that failed, the expected behaviour, and the actual output (logs, stack trace, or screenshot). Redact any PII before pasting logs.
- **Feature requests** — Describe the problem you are trying to solve first, then the proposed solution. If you have an ADR in mind, sketch the alternatives you considered.
- **Security reports** — Do **not** open a public issue. Privately disclose to the maintainer so the forensic path and PII controls can be evaluated before any public fix lands.

Please search existing issues before opening a new one to avoid duplicates.

---

## Pull Requests

1. **Sync with upstream.** Keep your fork on top of `main`:
   ```bash
   git fetch upstream
   git checkout main
   git merge --ff-only upstream/main
   ```
2. **Create a short-lived branch** off `main` (see [Branching & Commits](#branching--commits)).
3. **Make your change.** Keep the diff focused: one logical change per PR. If you need to refactor something unrelated, open a separate PR.
4. **Add or update tests.** Every behavioural change must be covered by a unit or integration test. New features should also include a staging-load test if they touch latency-sensitive paths.
5. **Run local checks** (see [Code Style](#code-style) and [Testing](#testing)). The CI will run the same gates, but local runs catch problems faster.
6. **Update documentation.** If your change adds, removes, or renames a feature, env var, endpoint, or service, update `README.md`, `AGENTS.md`, and any relevant ADR under `docs/`.
7. **Open the PR** against `main`. Fill in the PR template (or include the same information): what changed, why, how to test it, and any breaking changes or migration steps.
8. **Address review feedback** with new commits, not force-pushes that erase history. Reviewers need to see what changed between revisions.

A maintainer will review your PR, request changes if needed, and squash-merge it once CI is green and the review is approved.

---

## Branching & Commits

- **Trunk-based.** There is only one long-lived branch: `main`. All work happens on short-lived feature branches and lands via squash-merge.
- **Branch naming.** `<type>/<short-description>` — for example `feat/semantic-cache-recovery`, `fix/cancel-token-leak`, `docs/adr-021-sse-retry`.
- **Conventional Commits.** Use the following prefixes so changelogs and release notes can be generated automatically:
  - `feat:` — a new feature
  - `fix:` — a bug fix
  - `perf:` — a performance improvement
  - `refactor:` — a code change that neither fixes a bug nor adds a feature
  - `docs:` — documentation only
  - `test:` — adding or correcting tests
  - `chore:` — build, CI, tooling, dependencies
  - `ci:` — CI pipeline changes
  - `BREAKING CHANGE:` — append in the commit body for backwards-incompatible changes

Example:

```
feat(rag): add pgvector write-path to ingestion API

Adds VECTOR_STORE_KIND=pgvector support alongside chroma and none.
Documents are now indexed into both the tsvector GIN index and the
pgvector HNSW index when the flag is enabled.

BREAKING CHANGE: /documents response gains a vector_indexed boolean.
```

---

## Code Style

- **Python 3.11+.** New code must be compatible with 3.11, 3.12, and 3.13.
- **ruff** — line length 100, target `py311`. Run `ruff check .` and `ruff format .` before committing.
- **mypy** — basic mode. Public functions and module-level APIs must be typed. Run `mypy src/llm_client` before committing.
- **Pyright basic** — used by some IDE setups; the CI enforces mypy, but Pyright should not error.
- **Async-first.** The agent service, RAG pipeline, and storage layer are async. Do not introduce blocking calls in async paths — use `aiofiles`, `aiobotocore`, `asyncpg`, etc.
- **No comments unless necessary.** Code should be self-explanatory; reserve comments for non-obvious decisions and reference the ADR number when applicable.
- **No credentials in code.** All secrets go through `.env` and the config layer (Pydantic settings). The forensic stream and Vault integration must never log raw PII or ciphertext.

---

## Testing

The full testing guide is in the [Testing](./README.md#testing) section of the README. Summary for contributors:

```bash
# Full suite
pytest tests -v

# By marker
pytest tests -m unit -v
pytest tests -m integration -v          # requires docker-compose stack running
pytest tests -m staging_load -v
pytest tests -m eval -v                  # RAG A/B test framework

# Coverage
pytest tests --cov=src/llm_client --cov-report=term-missing
```

- **Unit tests** (`tests/unit/`) — fast, no external services. Use the `file_storage` fixture (the `InMemoryFileStorage` test-double from `tests/conftest.py`) instead of real S3.
- **Integration tests** (`tests/integration/`) — require Redis, MinIO, Vault, and PostgreSQL running via `docker-compose up -d`. Use the `integration` marker.
- **Staging-load tests** (`tests/staging_load/`) — benchmark-style tests with latency assertions. Use the `staging_load` marker.
- **Eval tests** — RAG A/B tests gated on `recall@5 ≥ 15 %` improvement AND latency overhead `< 100 ms`. Use the `eval` marker.

When adding a new feature:

- Add a unit test that covers the happy path and at least one failure mode.
- Add an integration test if the feature touches Redis, MinIO, Vault, PostgreSQL, or any external API.
- Add a staging-load test if the feature sits on a latency-critical path (cancellation, checkpoint, retrieval, reranking).
- Update `datasets/rag_eval/` if you change the RAG pipeline.

---

## CI Requirements

CI runs on every pull request and on every push to `main`. The PR pipeline mocks all external APIs; the nightly pipeline (2 AM UTC) calls real Tavily, Cohere, and OpenAI. Before opening a PR, make sure the following jobs pass locally:

```powershell
# Mirror the PR pipeline
powershell -ExecutionPolicy Bypass -File scripts\ci-local-quick.ps1 -Target "lint,typecheck,unit,integration,checkpoint"
```

Or, on macOS / Linux:

```bash
ruff check . && ruff format --check .
mypy src/llm_client
pytest tests -m "unit or integration" -v
```

PRs that touch the RAG pipeline should also pass locally:

```bash
pytest tests -m eval -v
pytest tests/unit/test_reranker*.py tests/unit/test_bm25*.py tests/unit/test_hybrid_rag*.py -v
```

If your PR adds or changes a GitHub Actions workflow, validate the YAML locally with `actionlint` before pushing.

---

## Adding New Features

Larger features usually start with an ADR. If your change introduces a new architectural decision (a new storage backend, a new transport, a new security control, a new external dependency), open an ADR draft under `docs/adr_<number>_<topic>.md` and link it from your PR. The ADR should cover:

- **Context** — what problem are we solving?
- **Decision** — what are we doing?
- **Alternatives considered** — what else did we evaluate, and why was it rejected?
- **Consequences** — what are the trade-offs, migration steps, and rollback plan?

When adding a new env var:

1. Add it to `.env.example` with a sensible default and a comment.
2. Add it to the Pydantic settings class in `src/llm_client/config.py` with the correct type and validation.
3. Document it in the [Configuration](./README.md#configuration) section of the README.
4. If it changes runtime behaviour in `env=prod`, add a fail-fast validation.

When adding a new endpoint:

1. Register it in `src/llm_client/api.py`.
2. Add request and response Pydantic models.
3. Add unit tests for the endpoint handler and integration tests for the full HTTP flow.
4. Document it in the README.

When adding a new LLM provider:

1. Add the provider enum value in `src/llm_client/config.py`.
2. Implement the provider client under `src/llm_client/orchestration/` (or wherever the existing providers live).
3. Wire it into the factory that selects providers based on `LLM_PROVIDER`.
4. Add unit tests with mocked HTTP responses.
5. Document the new provider value and its required env vars in the README.

---

## Code of Conduct

Be respectful and constructive. Treat everyone with courtesy. Disagreements happen — focus on the problem, not the person. Harassment, personal attacks, and discriminatory language are not tolerated. If you experience or witness such behaviour, contact the maintainer privately.

This project follows the spirit of the [Contributor Covenant](https://www.contributor-covenant.org/) without adopting its full text verbatim.

---

## License

By contributing, you agree that your contributions will be licensed under the [Apache License 2.0](./LICENSE). You retain copyright for your own contributions, but they are licensed to the project under the same terms as the rest of the codebase.

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

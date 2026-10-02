# ARCHITECT.md — LLM Client с агентным веб-поиском, RAG и MCP

| Атрибут | Значение |
|---|---|
| Версия документа | 1.3.0 |
| Дата | 2026-09-30 |
| Changelog | 1.3.0 (2026-09-30): Phase 2 завершена — добавлены ADR-010, ADR-017, ADR-020; C-2 помечено [RESOLVED]; C-6 помечено [PARTIALLY RESOLVED, ADR-011 pending Phase 3]; Q-5 частично закрыт; компонентная диаграмма обновлён с Redis DB 1, RerankerRegistry, HybridRetriever, BM25IndexBuilder, RagPipeline, rag_retriever нодой, web_search и rag_query tools; §5.2.2 Checkpointer обновлён на RedisPostgresCheckpointer + rag_retriever нода; §5.2.4 Tool Layer обновлён с AG-5 web_search и AG-6 rag_query; §5.2.5 RAG pipeline обновлён на hybrid + reranker + RagPipeline class; §5.1 Presentation Layer обновлён с tool-call previews, settings_panel, RAG citations, web search results panels; AG-5 и AG-6 помечены Approved в §7. \| 1.2.0 (2026-09-26): §5.1 (строка 357) уточнена — in-process опция (Streamlit native callbacks) помечена как «не используется; AG-0 (из `BACKLOG.md` v1.1.0) фиксирует FastAPI + SSE как единственную MVP-реализацию». §5.2.2 (Orchestration), §5.2.3 (LLM Provider), §5.2.4 (Tool Layer) дополнены ссылками на AG-1..AG-4 (формализация agent-service в Phase 1, см. `AG-PROMPTS.md` v1.0.0). § 8 Trade-offs обновлён (C-2, C-5 — частично resolved через AG-1/AG-3). \| 1.1.0 (2026-09-21): Phase 1 завершена — добавлены ADR-013 и ADR-014; расширен ADR-008 (LocalFileStorage упразднён); C-4/C-11/C-15 помечены [RESOLVED]; Q-2 закрыт, Q-4 закрыт частично \|
| Статус | Draft → Review → Approved |
| Аудитория | Solution-архитектор / Tech-лид |
| Технологический стек | Python 3.11, LangGraph 0.2+, LangChain 0.3+, Streamlit 1.40+ |
| Лицензия кодовой базы | MIT |

---

## 1. Executive Summary

Документ описывает архитектуру **LLM Client** — настольно/серверного приложения, предоставляющего чат-интерфейс поверх LLM-агента, способного выполнять веб-поиск, осуществлять RAG-поиск по корпоративным документам, вызывать внешние инструменты через Model Context Protocol (MCP) и сохранять результаты в форматах `md`, `txt`, `pdf`, `doc/docx`, `odt`, `xls/xlsx`. Оркестрация агента реализована на **LangGraph**, интеграция с провайдерами — через **LangChain** abstraction layer, UI — на **Streamlit**. Целевой deployment — `docker-compose` с возможностью последующего переезда в Kubernetes.

Архитектура следует принципам **modular monolith + ports&adapters**: ядро приложения изолировано от внешних зависимостей через ports (интерфейсы), конкретные адаптеры (OpenAI, Anthropic, Chroma, Qdrant, pgvector, Tavily, MCP-серверы) подключаются через dependency injection. Это позволяет заменить любой внешний сервис без перекомпиляции ядра и упрощает тестирование.

**Ключевые архитектурные решения**:

1. **LangGraph как оркестратор** вместо классической LangChain AgentExecutor — декларативный state-machine с поддержкой cycles, conditional edges, human-in-the-loop, чекпойнтинга состояния.
2. **Абстракция LLM-провайдеров** через `langchain-openai` и `langchain-anthropic` с общим интерфейсом `BaseChatModel` — переключение моделей конфигом.
3. **Три уровня векторного хранилища**: Chroma для локальной разработки/тестов, Qdrant для production RAG с высокой нагрузкой, pgvector — для случая, когда RAG живёт в той же БД, что и бизнес-данные.
4. **MCP-клиент** через официальный `mcp` Python SDK — динамическое подключение инструментов из stdio/SSE MCP-серверов.
5. **Streamlit как UI** для MVP/Alpha, с заделом на миграцию на Chainlit или FastAPI+Next.js в Production.

---

## 2. Бизнес-контекст и цели

### 2.1 Бизнес-цели

| ID | Цель | Метрика успеха |
|---|---|---|
| G-1 | Сократить время аналитика на поиск информации по корпоративным документам | Среднее время ответа < 15 сек, recall@10 > 0.75 |
| G-2 | Унифицировать работу с LLM разных провайдеров в едином UI | Переключение провайдера < 5 сек, zero code changes |
| G-3 | Дать агенту инструментальный слой для автоматизации рутины | ≥ 5 инструментов в проде (web_search, file_export, rag_query, mcp_*, calc) |
| G-4 | Обеспечить воспроизводимость и аудитируемость ответов | 100% запросов логируются с full trace, retention 90 дней |
| G-5 | Запустить MVP за 3 недели силами 2 разработчиков | Time-to-MVP ≤ 15 человеко-дней |

### 2.2 Стейкхолдеры

| Роль | Интерес | Влияние |
|---|---|---|
| End-user (аналитик/разработчик) | Удобный UI, точные ответы, возможность экспорта | High |
| Tech-лид | Maintainability, observability, безопасность ключей | High |
| DevOps-инженер | Простота деплоя, логи в stdout JSON, готовый docker-compose | Medium |
| Security-оффицер | Нет утечек PII, доступы по ролям, audit trail | High |
| Финансовый контролёр | Предсказуемые затраты на LLM API, лимиты | Medium |

### 2.3 Ограничения и предположения

- **Латентность LLM**: ответы на сложные запросы могут занимать 30-60 сек с tool calling; UI должен поддерживать streaming + partial tool outputs.
- **Стоимость**: GPT-4o ~ $5/1M input tokens; Claude 3.5 Sonnet ~ $3/1M; бюджет на пилот — $500/мес на команду из 5 пользователей.
- **Приватность**: пользовательский контент может содержать NDA-данные; только API-провайдеры с zero-retention политикой (Anthropic API, OpenAI Enterprise) либо локальные модели через Ollama.
- **Compliance**: GDPR/SOC2 — все PII при логировании маскируются; retention настраивается per-tenant.
- **Offline-режим**: не поддерживается в MVP, в Production — частичная поддержка через Ollama.

---

## 3. High-level системный контекст (C4 Level 1)

```mermaid
C4Context
    title LLM Client — System Context (C4 L1)

    Person(user, "Аналитик / разработчик", "Использует чат для поиска, RAG и автоматизации")
    System(llmclient, "LLM Client", "Python-приложение: LangGraph агент + Streamlit UI")

    System_Ext(openai, "OpenAI API", "GPT-4o / GPT-4o-mini")
    System_Ext(anthropic, "Anthropic API", "Claude 3.5 Sonnet / Haiku")
    System_Ext(tavily, "Tavily Search API", "Веб-поиск для LLM-агентов")
    System_Ext(mcp_servers, "MCP Servers", "filesystem, github, slack, custom")

    System_Ext(chroma, "Chroma (dev)", "Локальное векторное хранилище")
    System_Ext(qdrant, "Qdrant (prod)", "Production vector DB")
    System_Ext(pgvector, "pgvector", "PostgreSQL + pgvector extension")

    System_Ext(postgres, "PostgreSQL", "Сессии, чаты, метаданные документов")
    System_Ext(redis, "Redis", "Cache, rate-limit, pub/sub")

    Rel(user, llmclient, "Чат UI (HTTPS / WSS)")
    Rel(llmclient, openai, "Chat completions")
    Rel(llmclient, anthropic, "Chat completions")
    Rel(llmclient, tavily, "Web search")
    Rel(llmclient, mcp_servers, "MCP protocol (stdio/SSE)")
    Rel(llmclient, chroma, "Vector ops (dev)")
    Rel(llmclient, qdrant, "Vector ops (prod)")
    Rel(llmclient, pgvector, "Vector ops (alt)")
    Rel(llmclient, postgres, "Sessions, metadata")
    Rel(llmclient, redis, "Cache, rate-limit")

    UpdateRelStyle(user, llmclient, $offsetX="-40", $offsetY="-30")
    UpdateRelStyle(llmclient, openai, $offsetX="-30", $offsetY="-10")
    UpdateRelStyle(llmclient, tavily, $offsetX="-20", $offsetY="30")
```

### 3.1 Основные внешние зависимости

| Зависимость | Версия | SLA | Fallback |
|---|---|---|---|
| OpenAI API | `2024-08-01` preview | 99.5% uptime | retry→Anthropic→local error message |
| Anthropic API | `2023-06-01` | 99.5% uptime | retry→OpenAI→local error |
| Tavily Search | v1 | 99.0% uptime | duckduckgo-search (lib) → user-facing warning |
| MCP-серверы | spec 2024-11-05 | n/a (per-server) | graceful degradation: tool недоступен |
| Qdrant | 1.10+ | 99.9% | retry→ Chroma in-memory |
| PostgreSQL | 16+ | 99.95% | read replica для RAG metadata |
| Redis | 7+ | 99.9% | in-process LRU cache (1k entries) |

---

## 4. Контейнерная диаграмма (C4 Level 2)

```mermaid
flowchart LR
    subgraph Browser["Пользовательский браузер"]
        UI["Streamlit Chat UI<br/>streamlit:1.40"]
    end

    subgraph App["LLM Client Container (docker-compose)"]
        API["FastAPI Backend<br/>(opional BFF, для future-migration)"]
        AGENT["Agent Service<br/>LangGraph + LangChain<br/>Python 3.11"]
        WORKER["Background Worker<br/>file rendering, long tasks"]
        TOOLS["Tool Layer<br/>web_search, rag, mcp, file_export"]
    end

    subgraph Storage["Storage Layer"]
        PG[("PostgreSQL<br/>sessions, files meta<br/>+ pgvector + tsvector")]
        REDIS[("Redis<br/>DB 0: pub/sub ADR-013<br/>DB 1: checkpoint-WAL ADR-010")]
        VEC1[("Qdrant<br/>vector store")]
        VEC2[("pgvector<br/>vector alt")]
        VEC3[("Chroma<br/>vector dev")]
        FS[("Volume<br/>/data/files")]
    end

    subgraph External["External APIs"]
        OAI[OpenAI]
        ANT[Anthropic]
        TAV[Tavily]
        MCP[("MCP Servers<br/>stdio/sse")]
    end

    UI -->|HTTP/SSE| AGENT
    UI -->|HTTP/SSE| API
    AGENT --> TOOLS
    AGENT --> OAI
    AGENT --> ANT
    TOOLS --> TAV
    TOOLS --> MCP
    TOOLS --> VEC1
    TOOLS --> VEC2
    TOOLS --> VEC3
    AGENT --> PG
    AGENT --> REDIS
    WORKER --> FS
    WORKER --> PG

    classDef container fill:#1f3a5f,stroke:#3b82f6,color:#fff,stroke-width:2px
    classDef storage fill:#3a1f5f,stroke:#a855f7,color:#fff
    classDef external fill:#5f3a1f,stroke:#f59e0b,color:#fff
    class UI,API,AGENT,WORKER,TOOLS container
    class PG,REDIS,VEC1,VEC2,VEC3,FS storage
    class OAI,ANT,TAV,MCP external
```

### 4.1 Контейнеры

| Контейнер | Технология | Ответственность | API |
|---|---|---|---|
| `ui` | Streamlit 1.40 | Чат UI, история сессий, кнопки скачивания | HTTP / WS (Streamlit runtime) |
| `agent-service` | Python 3.11, LangGraph, LangChain | Оркестрация графа агента, tool calling loop, streaming | HTTP / SSE (FastAPI или нативно через Streamlit) |
| `tool-layer` | Python модули | Реализация tools: `web_search`, `rag_query`, `mcp_call`, `file_export` | in-process |
| `worker` (optional, prod) | Celery / RQ | Асинхронная генерация тяжёлых файлов (pdf/docx/xlsx), фоновый индексинг | AMQP/Redis |
| `postgres` | PostgreSQL 16 | Sessions, messages, files metadata, pgvector (alt RAG), tsvector (BM25 ADR-020) | SQL |
| `redis` | Redis 7 | DB 0: cache, rate-limit, pub/sub (ADR-013); DB 1: checkpoint-WAL (ADR-010) | RESP |
| `qdrant` | Qdrant 1.10 | Production vector DB | HTTP/gRPC |
| `chroma` | Chroma 0.5 | Локальная dev-БД векторов | HTTP |
| `nginx` (prod) | Nginx | TLS termination, reverse proxy, static assets | HTTP |

---

## 5. Слои архитектуры

Архитектура делится на 7 слоёв. Каждый слой имеет чётко определённую ответственность и зависит только от нижележащих слоёв (однонаправленная зависимость, onion/hexagonal).

```
+-------------------------------------------------------------+
| 1. Presentation Layer (Streamlit UI)                        |
|    - Chat components, session history, file download         |
|    - Tool-call previews, RAG citations, web search panels   |
+-------------------------------------------------------------+
| 2. Orchestration Layer (LangGraph)                          |
|    - State machine: planner -> tool_executor /              |
|      rag_retriever -> final_answer                          |
|    - Conditional edges, cycles, human-in-the-loop            |
|    - Checkpointing (RedisPostgresCheckpointer, ADR-010)     |
+-------------------------------------------------------------+
| 3. LLM Provider Layer (LangChain abstraction)               |
|    - BaseChatModel -> OpenAI / Anthropic / Ollama            |
|    - Token usage tracking, retry, fallback                   |
+-------------------------------------------------------------+
| 4. Tool Layer                                                |
|    - @tool-decorated functions: web_search, rag_query,       |
|      file_export, mcp_call, calc, code_exec (sandbox)        |
|    - Pydantic schemas для tool args                          |
+-------------------------------------------------------------+
| 5. RAG Layer                                                 |
|    - Document loaders (PDF/DOCX/MD/HTML/EPUB)               |
|    - Chunkers (recursive, semantic, sentence)                |
|    - Embeddings (OpenAI text-embedding-3-small / BGE)       |
|    - Vector stores: Chroma / Qdrant / pgvector               |
|    - HybridRetriever (BM25 + vector, ADR-020)               |
|    - RerankerRegistry + BgeReranker (ADR-017)               |
|    - RagPipeline (composes retriever + reranker)            |
+-------------------------------------------------------------+
| 6. MCP Client Layer                                          |
|    - mcp Python SDK, multi-transport (stdio, SSE, WS)        |
|    - Dynamic tool discovery from MCP servers                 |
|    - Tool registry <-> LangGraph tool node                   |
+-------------------------------------------------------------+
| 7. Persistence Layer                                         |
|    - SQLAlchemy 2.0 (async) -> PostgreSQL                    |
|    - Alembic migrations                                      |
|    - Redis DB 0 (pub/sub) + Redis DB 1 (checkpoint-WAL)     |
|    - File storage: S3-compatible (MinIO/S3)                 |
+-------------------------------------------------------------+
```

### 5.1 Компонентная диаграмма (C4 Level 3 — Agent Service)

```mermaid
flowchart TB
    subgraph UI[Streamlit UI]
        CHAT[chat_component<br/>+ tool-call previews G-1]
        HIST[session_history]
        DL[download_button]
        RC[rag_citations_panel G-2]
        WS[web_search_results_panel G-3]
        SET[settings_panel G-4<br/>retrieval_strategy, reranker]
    end

    subgraph ORCH[LangGraph Orchestration]
        GRAPH[StateGraph]
        NODES[Nodes: planner, tool_executor,<br/>rag_retriever, mcp_invoker,<br/>final_answer]
        CHECK[Checkpointer<br/>RedisPostgresCheckpointer<br/>ADR-010]
        STATE[AgentState<br/>TypedDict]
    end

    subgraph LLM[LLM Provider Layer]
        PROV[provider_factory]
        OAI[ChatOpenAI]
        ANT[ChatAnthropic]
        LIT[LiteLLM Gateway<br/>optional]
    end

    subgraph TOOLS[Tool Layer]
        TS[web_search<br/>Tavily AG-5]
        TR[rag_query<br/>RagPipeline AG-6]
        TM[mcp_call<br/>proxy AG-7 Phase 4]
        TF[file_export<br/>md/txt/pdf/docx/xlsx/odt AG-4]
        TC[calc/code_exec<br/>sandboxed]
    end

    subgraph RAG[RAG Layer]
        LOAD[loaders]
        CHUNK[chunkers]
        EMB[embeddings]
        VS1[(Chroma)]
        VS2[(Qdrant)]
        VS3[(pgvector)]
        BM25[BM25Retriever<br/>tsvector ADR-020]
        HYB[HybridRetriever<br/>+ RRFFusion ADR-020]
        RERANK[RerankerRegistry<br/>+ BgeRerankerAdapter<br/>ADR-017]
        PIPE[RagPipeline<br/>H-2 singleton]
    end

    subgraph MCP[MCP Client Layer]
        CLIENT[mcp.ClientSession]
        REG[tool registry]
        TRANS1[stdio transport]
        TRANS2[SSE transport]
    end

    subgraph PERS[Persistence Layer]
        SA[SQLAlchemy async]
        PG[(PostgreSQL<br/>+ pgvector + tsvector)]
        RD0[(Redis DB 0<br/>pub/sub ADR-013)]
        RD1[(Redis DB 1<br/>checkpoint-WAL ADR-010)]
        FS[(File Storage)]
        MINIO[(MinIO / S3)]
        VLT[(Vault / KMS)]
    end

    subgraph CTRL[Control Plane & Observability (Phase 1)]
        CE[CancelEndpoint<br/>POST /sessions/{id}/cancel]
        CPS[CancelPublisher<br/>Redis pub/sub]
        CSS[CancelSubscriber<br/>CancellationToken]
        OW[OperationalStreamWriter<br/>PII-masked → stdout/Loki]
        FW[ForensicStreamWriter<br/>AES-256-GCM → forensic S3]
    end

    CHAT -->|async stream| GRAPH
    GRAPH --> NODES
    NODES --> PROV
    PROV --> OAI
    PROV --> ANT
    PROV -.-> LIT
    NODES --> TOOLS
    TS --> TAV[Tavily API]
    TR --> PIPE
    PIPE --> HYB
    PIPE --> RERANK
    HYB --> BM25
    HYB --> VS1
    HYB --> VS2
    HYB --> VS3
    BM25 --> PG
    TF --> FS
    TM --> CLIENT
    CLIENT --> TRANS1
    CLIENT --> TRANS2
    TRANS1 --> MCPS1[(filesystem<br/>MCP server)]
    TRANS2 --> MCPS2[(github<br/>MCP server)]
    GRAPH --> CHECK
    CHECK --> RD1
    CHECK --> SA
    SA --> PG
    NODES --> RD0
    HIST --> SA
    DL --> FS
    RC --> PIPE
    WS --> TS
    CE --> CPS
    CPS --> RD0
    CSS --> RD0
    CSS --> GRAPH
    CSS --> OW
    CSS --> FW
    FW --> VLT
    FW --> MINIO

    classDef ui fill:#dbeafe,stroke:#1e40af,color:#000
    classDef orch fill:#dcfce7,stroke:#166534,color:#000
    classDef llm fill:#fef9c3,stroke:#854d0e,color:#000
    classDef tools fill:#fee2e2,stroke:#991b1b,color:#000
    classDef rag fill:#f3e8ff,stroke:#6b21a8,color:#000
    classDef mcp fill:#ffedd5,stroke:#9a3412,color:#000
    classDef pers fill:#e0e7ff,stroke:#3730a3,color:#000
    classDef ctrl fill:#fef9c3,stroke:#854d0e,color:#000

    class CHAT,HIST,DL,RC,WS,SET ui
    class GRAPH,NODES,CHECK,STATE orch
    class PROV,OAI,ANT,LIT llm
    class TS,TR,TM,TF,TC tools
    class LOAD,CHUNK,EMB,VS1,VS2,VS3,BM25,HYB,RERANK,PIPE rag
    class CLIENT,REG,TRANS1,TRANS2 mcp
    class SA,PG,RD0,RD1,FS,MINIO,VLT pers
    class CE,CPS,CSS,OW,FW ctrl
```

### 5.2 Описание ключевых компонентов

#### 5.2.1 Presentation Layer (Streamlit UI)

| Компонент | Файл | Ответственность |
|---|---|---|
| `chat_component` | `ui/components/chat.py` | Рендеринг сообщений, streaming tokens, tool-call previews (G-1, Phase 2) — реализовано |
| `session_history` | `ui/components/history.py` | Список сессий слева, переключение, поиск по истории |
| `download_button` | `ui/components/download.py` | Кнопки для каждого экспортированного файла |
| `rag_citations_panel` | `ui/components/rag_citations.py` | RAG citations panel (G-2, Phase 2) — отображение retrieved_docs из event: retrieved_docs — реализовано |
| `web_search_results_panel` | `ui/components/web_search.py` | Web search results panel (G-3, Phase 2) — отображение web_search tool results — реализовано |
| `settings_panel` | `ui/components/settings.py` | Выбор провайдера/модели, температура, max_tokens, tools on/off, retrieval_strategy (ADR-020), reranker (ADR-017) — реализовано (G-4, Phase 2) |
| `auth_gate` | `ui/components/auth.py` | Basic auth (MVP) -> OAuth2/OIDC (prod) |

UI общается с `agent_service` через **Streamlit native callbacks** (MVP, in-process) или через **FastAPI + SSE** (Alpha+ для multi-instance).

> **Phase 1 Update (v1.2.0, 2026-09-26)**: in-process опция (Streamlit native callbacks) **не используется**. AG-0 из `BACKLOG.md` v1.1.0 (см. `AG-PROMPTS.md` v1.0.0 §1) фиксирует **FastAPI + SSE как единственную MVP-реализацию** `agent-service`, запускаемую как отдельный процесс (`python -m llm_client.agent` или `uvicorn llm_client.agent.service:app`) на `AGENT_SERVICE_PORT` (default 8000). UI (`src/llm_client/ui/chat.py`) общается с `agent-service` через HTTP/SSE по контракту `AGENT_SERVICE_URL` (default `http://localhost:8000`). Это применяет принцип ТРИЗ #19 (переход в другое измерение) и подготавливает Phase 5 multi-instance (UI-4/UI-5 из `BACKLOG.md` v1.1.0): добавление второго инстанса `agent-service` за load balancer не требует переписывания UI-кода — контракт `AGENT_SERVICE_URL` не меняется. Подробное обоснование — `BACKLOG.md` v1.1.0 §2.3–§2.4 (Пробелы D–G) и §6.4 (риск «AG-0 расходится с ARCHITECT.md §5.1 in-process vs separate process»).

> **Phase 2 Update (v1.3.0, 2026-09-30)**: UI-расширения Блока G (`ALPHA-PROMPTS.md`) реализованы: `chat_component` получает tool-call previews (G-1) — отображение вызовов `web_search`/`rag_query`/`file_export` из SSE `event: tool_call`; добавлены `rag_citations_panel` (G-2) — панель цитат RAG из `event: retrieved_docs`; `web_search_results_panel` (G-3) — результаты веб-поиска из `event: tool_result`; `settings_panel` расширен (G-4) — tools on/off, `retrieval_strategy` (ADR-020: vector|bm25|hybrid), выбор reranker (ADR-017: bge|cohere|identity). Все компоненты расширяют `UIClient` interface (`ui/client.py`), не Streamlit-specific API напрямую.

#### 5.2.2 Orchestration Layer (LangGraph)

Ядро — `StateGraph(AgentState)`. `AgentState` — TypedDict с полями:

```python
from typing import TypedDict, Annotated, Literal
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    user_id: str
    session_id: str
    provider: Literal["openai", "anthropic"]
    model_name: str
    tools_enabled: list[str]           # ["web_search", "rag_query", ...]
    retrieved_docs: list[dict]         # контекст из RAG
    mcp_tools_cache: dict[str, dict]   # динамические tools из MCP
    iteration: int                     # защита от зацикливания
    max_iterations: int                # default = 10
    final_answer: str | None
    artifacts: list[dict]              # [{path, format, size}]
```

Граф содержит узлы:
- `planner` — анализ запроса, выбор стратегии (RAG first / web_search / direct LLM / tool chain)
- `tool_executor` — универсальный ToolNode, обрабатывает `tool_calls` из last message
- `rag_retriever` — **Phase 2 (AG-6)**. Извлекает RAG chunks через `RagPipeline`, обновляет `state["retrieved_docs"]` для `final_answer`. Вызывается когда planner выбирает `route_decision="rag_first"` (в Phase 2 — heuristic по ключевым словам; в Phase 3+ — LLM structured output). Пропускается если `rag_query` tool call уже ответил на тот же query (H-4 оптимизация, `_rag_query_answered`).
- `mcp_invoker` — делегирует вызовы в MCP client
- `final_answer` — формирует финальный ответ с цитатами и артефактами
- `human_review` (опционально) — прерывание для подтверждения тяжёлых действий (например, удаление файла через MCP filesystem)

Conditional edges:
- `route_after_planner`: **Phase 2 — 3 выхода** (Phase 1 был 1 выход): если planner вернул `tools_needed` → `tool_executor`; если `rag_first` → `rag_retriever`; иначе → `final_answer`.
- `route_after_tool`: если в `messages` есть новый `tool` message, возвращаемся в LLM для интерпретации; если `final_answer_ready` — выходим.

Checkpointer: **`RedisPostgresCheckpointer` (ADR-010, Phase 2)** — composite sync Redis + async PG. `PostgresSaver` (ADR-001) — deprecated, оставлен только для backward-compat тестов. См. `src/llm_client/orchestration/checkpointers/composite.py`.

> **Phase 2 Update (v1.3.0, 2026-09-30)**: Checkpointer обновлён с `PostgresSaver` на `RedisPostgresCheckpointer` (ADR-010). Добавлена `rag_retriever` нода (AG-6/H-2/H-3) — `src/llm_client/agent/graph.py`. `route_after_planner` расширен с 1 выхода до 3 (`direct_llm` / `tools_needed` / `rag_first`). `build_agent_graph(llm, token, tools, rag_pipeline)` — `rag_pipeline` singleton включает `rag_retriever` ноду; `None` отключает (backward compat).

#### 5.2.3 LLM Provider Layer

```python
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic

class LLMProviderFactory:
    @staticmethod
    def create(provider: str, model: str, **kwargs) -> BaseChatModel:
        match provider:
            case "openai":
                return ChatOpenAI(model=model, streaming=True, **kwargs)
            case "anthropic":
                return ChatAnthropic(model=model, streaming=True, **kwargs)
            case "ollama":
                # future: ChatOllama from langchain-ollama
                raise NotImplementedError("Phase 4+")
            case _:
                raise ValueError(f"Unknown provider: {provider}")
```

Дополнительно:
- `token_usage_tracker` — оборачивает LLM, логирует `prompt_tokens` / `completion_tokens` / `cost_estimate` в `LLMCall` таблицу.
- `retry_decorator` — exponential backoff на 429/500/503, max 3 retry.
- `fallback_chain` — если OpenAI отдаёт 5 ошибок подряд, переключаемся на Anthropic (config-driven).

#### 5.2.4 Tool Layer

Все tools — это `@tool`-декорированные функции с Pydantic-схемами args. Пример:

```python
from langchain_core.tools import tool, BaseTool
from pydantic import BaseModel, Field
from typing import Literal

class WebSearchArgs(BaseModel):
    query: str = Field(..., description="Поисковый запрос")
    max_results: int = Field(5, ge=1, le=20)

@tool(args_schema=WebSearchArgs)
def web_search(query: str, max_results: int = 5) -> list[dict]:
    '''Ищет в вебе через Tavily API. Возвращает список {title, url, snippet}.'''
    # реализация через tavily-python
    ...

class FileExportArgs(BaseModel):
    content: str = Field(..., description="Контент файла")
    format: Literal["md","txt","pdf","doc","docx","odt","xls","xlsx"] = Field(...)
    filename: str | None = None

@tool(args_schema=FileExportArgs)
def file_export(content: str, format: str, filename: str | None = None) -> dict:
    '''Сохраняет контент в файл заданного формата, возвращает {path, size}.'''
    ...

class RagQueryArgs(BaseModel):
    query: str = Field(..., description="RAG query по корпусу документов")
    top_k: int = Field(5, ge=1, le=20)

@tool(args_schema=RagQueryArgs)
async def rag_query(query: str, top_k: int = 5) -> dict:
    '''RAG retrieval через RagPipeline. Возвращает {chunks, chunk_count, top_score}.'''
    ...
```

Tool registry собирает все `BaseTool` инстансы в единый список, который передаётся в LangGraph `ToolNode`. MCP-tools добавляются в registry динамически при подключении MCP-сервера.

**Статус реализации tools по фазам:**

| Tool | Фаза | ADR | Реализация |
|---|---|---|---|
| `file_export` | Phase 1 (AG-4) | расш. ADR-008, ADR-006 | `src/llm_client/agent/tools/file_export.py` — md/txt sync, pdf/docx async stub |
| `web_search` | Phase 2 (AG-5) | ADR-005, ADR-006 | `src/llm_client/agent/tools/web_search.py` — Tavily API, `TAVILY_API_KEY` |
| `rag_query` | Phase 2 (AG-6) | ADR-003, ADR-001, ADR-017, ADR-020 | `src/llm_client/agent/tools/rag_query.py` — через `RagPipeline` |
| `mcp_call` | Phase 4 (AG-7) | ADR-012 | planned — `mcp_invoker` нода |

> **Phase 2 Update (v1.3.0, 2026-09-30)**: Tool Layer расширен AG-5 (`web_search`) и AG-6 (`rag_query`). `DEFAULT_TOOLS_ENABLED = ("file_export", "web_search", "rag_query")` в `agent/service.py`. `rag_query` возвращает `dict` с `chunks` (не list) — SSE-эмиттер парсит по shape payload. Phase 4 добавит `mcp_call` (AG-7) через `MCPTransport` (ADR-012).

#### 5.2.5 RAG Layer

Pipeline (Phase 2, ADR-020 + ADR-017):
1. **Load** — `PyPDFLoader`, `Docx2txtLoader`, `UnstructuredMarkdownLoader`, `WebBaseLoader` (для URL).
2. **Chunk** — `RecursiveCharacterTextSplitter` (default 1000/200), опционально `SemanticChunker` (через embeddings).
3. **Embed** — `OpenAIEmbeddings(model="text-embedding-3-small")` (Phase 1), `BGEEmbeddings` для локального режима (Phase 4).
4. **Store** — выбор векторного хранилища через `VectorStoreFactory`:

```python
class VectorStoreFactory:
    @staticmethod
    def create(kind: Literal["chroma","qdrant","pgvector"], **kwargs):
        match kind:
            case "chroma":
                from langchain_chroma import Chroma
                return Chroma(persist_directory=kwargs["path"], embedding_function=emb)
            case "qdrant":
                from langchain_qdrant import QdrantVectorStore
                return QdrantVectorStore(url=kwargs["url"],
                                         collection_name=kwargs["collection"],
                                         embedding_function=emb)
            case "pgvector":
                from langchain_postgres import PGVector
                return PGVector(connection=kwargs["dsn"],
                                collection_name=kwargs["collection"],
                                embedding_function=emb)
```

5. **Retrieve** — **Phase 2 default: hybrid** (`RetrieverConfig.retrieval_strategy="hybrid"`, ADR-020):
   - `HybridRetriever` (`src/llm_client/rag/retrieval/hybrid_retriever.py`) — параллельный vector + BM25.
   - Vector top-20 + BM25 top-20 → `rrf_fusion` (reciprocal rank fusion) → top-50.
   - BM25: `BM25Retriever` через PostgreSQL `tsvector` (GIN index на `documents.search_vector`).
   - Опции: `"vector"` (только embeddings), `"bm25"` (только lexical).
6. **Rerank** — **Phase 2 (ADR-017)**: cross-encoder reranker после fusion → top-5:
   - Default: `BgeRerankerAdapter` (`BAAI/bge-reranker-base`, in-process).
   - Optional: `CohereRerankAdapter`.
   - Fallback: `IdentityReranker` (no-op) через `RerankerChain`.

**RagPipeline (H-2, Phase 2)** — композирует retriever + reranker на основе `RetrieverConfig`:

```python
# src/llm_client/rag/pipeline.py
class RagPipeline:
    """Композирует retriever (HybridRetriever / VectorRetriever / BM25Retriever)
    + reranker (BgeRerankerAdapter / CohereRerankAdapter / identity) на основе
    RetrieverConfig. Singleton при agent-service startup.
    Используется rag_query @tool и rag_retriever нодой — single source of truth."""
```

> **Phase 2 Update (v1.3.0, 2026-09-30)**: RAG pipeline обновлён на hybrid + reranker + `RagPipeline` class. PostgreSQL расширен extensions: `pgvector` (existing) + `tsvector`/`pg_trgm` (new, `documents.search_vector` GENERATED ALWAYS AS STORED + GIN index). `RagPipeline.from_settings_with_overrides(...)` — singleton в `agent/service.py`, передаётся в `build_agent_graph(rag_pipeline=...)`. Retriever metrics: `RerankerMetrics` (`src/llm_client/rag/metrics.py`) — latency, recall@5, fallback_count.

#### 5.2.6 MCP Client Layer

Используется официальный `mcp` Python SDK:

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

class MCPClientManager:
    def __init__(self, config: list[dict]):
        self.servers = config  # [{"name","transport":"stdio|sse","command"/"url",...}]
        self.sessions: dict[str, ClientSession] = {}
        self.tools_cache: list[BaseTool] = []

    async def connect_all(self):
        for srv in self.servers:
            session = await self._connect(srv)
            self.sessions[srv["name"]] = session
            tools = await session.list_tools()
            self.tools_cache.extend(self._wrap_mcp_tool(t, srv["name"]) for t in tools)

    async def call_tool(self, server: str, name: str, arguments: dict) -> str:
        result = await self.sessions[server].call_tool(name, arguments)
        return result.content[0].text
```

MCP-tools автоматически регистрируются в общем `tool_registry` с префиксом имени сервера (`filesystem.read_file`, `github.create_issue`), что исключает коллизии.

#### 5.2.7 Persistence Layer

**SQLAlchemy 2.0 async** (для production), `aiosqlite` для тестов. Схема БД (упрощённая):

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('user','admin')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title TEXT,
    provider TEXT NOT NULL,
    model_name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE messages (
    id UUID PRIMARY KEY,
    session_id UUID NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user','assistant','tool','system')),
    content JSONB NOT NULL,        -- {text, tool_calls, tool_call_id, artifacts}
    tokens_in INT,
    tokens_out INT,
    cost_usd NUMERIC(10,6),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_messages_session ON messages(session_id, created_at);

CREATE TABLE files (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES sessions(id) ON DELETE CASCADE,
    user_id UUID NOT NULL REFERENCES users(id),
    path TEXT NOT NULL,
    format TEXT NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE documents (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    source_type TEXT NOT NULL,
    source_uri TEXT,
    content_hash TEXT NOT NULL UNIQUE,   -- idempotent upsert target (D-2)
    content TEXT NOT NULL,        -- полный текст документа для полнотекстового поиска
    metadata JSONB DEFAULT '{}',  -- метаданные документа (title, author и др.)
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    search_vector tsvector GENERATED ALWAYS AS (
        setweight(to_tsvector('english', coalesce(content, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(metadata->>'title', '')), 'B')
    ) STORED,                     -- auto-recomputed on content/metadata UPDATE
    CONSTRAINT idx_documents_search_vector
      USING GIN(search_vector)   -- GIN индекс для быстрого поиска
);
-- Дополнительно: unique index idx_documents_content_hash_unique (content_hash),
-- trigram index idx_documents_content_trgm (content gin_trgm_ops) для fuzzy.
-- Vector-хранилище (chroma/pgvector) — отдельно от documents; documents — BM25-сторона ADR-020.

CREATE TABLE llm_calls (
    id UUID PRIMARY KEY,
    session_id UUID REFERENCES sessions(id),
    message_id UUID REFERENCES messages(id),
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    tokens_in INT,
    tokens_out INT,
    latency_ms INT,
    cost_usd NUMERIC(10,6),
    status TEXT NOT NULL,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE agent_checkpoints (
    thread_id UUID NOT NULL,
    checkpoint_id UUID NOT NULL,
    parent_id UUID,
    state JSONB NOT NULL,
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (thread_id, checkpoint_id)
);
```

---

## 6. Сквозные потоки данных (Sequence Diagrams)

### 6.1 Поток: обычный чат с tool calling

```mermaid
sequenceDiagram
    actor U as User
    participant UI as Streamlit UI
    participant G as LangGraph
    participant L as LLM Provider
    participant T as Tool Layer
    participant DB as PostgreSQL

    U->>UI: Вводит запрос
    UI->>G: agent.invoke({messages:[user_msg]})
    G->>G: planner(state)
    G->>L: chat.completions(tools=[...])
    L-->>G: assistant msg + tool_calls
    alt tool_calls present
        G->>T: ToolNode.invoke(tool_calls)
        T-->>G: tool messages
        G->>L: chat.completions(with tool results)
        L-->>G: assistant msg (final or new tool_calls)
    end
    G->>G: final_answer node
    G->>DB: checkpoint.save(state)
    G-->>UI: streaming tokens + artifacts
    UI-->>U: рендер ответа + кнопки скачивания
```

### 6.2 Поток: RAG query

```mermaid
sequenceDiagram
    actor U as User
    participant G as LangGraph
    participant R as RAG Layer
    participant V as Vector Store
    participant L as LLM

    U->>G: Найди в документах X...
    G->>R: retrieve(query, k=8, mmr=True)
    R->>V: similarity_search(query, k=20)
    V-->>R: top-20 chunks
    R->>R: MMR rerank -> top-8
    R-->>G: documents[]
    G->>L: prompt = build_prompt(query, documents)
    L-->>G: answer with citations [doc_id, chunk_id]
    G-->>U: ответ + sources panel
```

### 6.3 Поток: MCP tool call

```mermaid
sequenceDiagram
    actor U as User
    participant G as LangGraph
    participant M as MCPClientManager
    participant S as MCP Server (filesystem)
    participant L as LLM

    U->>G: Прочитай /etc/hosts и проанализируй
    G->>L: decide tool_calls=[filesystem.read_file]
    L-->>G: tool_call{server="filesystem", name="read_file", args={path:"/etc/hosts"}}
    G->>M: call_tool("filesystem", "read_file", {path:"/etc/hosts"})
    M->>S: mcp.call_tool over stdio
    S-->>M: content="127.0.0.1 localhost..."
    M-->>G: tool result
    G->>L: build prompt with tool result
    L-->>G: analysis answer
    G-->>U: answer
```

### 6.4 Поток: file_export (мультиформатный)

```mermaid
sequenceDiagram
    actor U as User
    participant G as LangGraph
    participant TF as file_export tool
    participant W as Worker (optional)
    participant FS as File Storage
    participant DB as PostgreSQL

    U->>G: Сохрани отчёт в PDF и XLSX
    G->>TF: file_export(content=..., format="pdf")
    TF->>TF: detect_renderer(format)
    alt format in [md, txt]
        TF->>FS: write text directly
    else format in [pdf, docx, xlsx, odt]
        TF->>W: enqueue render_job (sync в MVP)
        W->>W: reportlab / python-docx / openpyxl / odfpy
        W->>FS: write file
    end
    TF->>DB: INSERT files (path, sha256, size)
    TF-->>G: {path, size, format}
    G-->>U: artifact + download_button
```

### 6.5 Поток: web search

```mermaid
sequenceDiagram
    actor U as User
    participant G as LangGraph
    participant T as web_search tool
    participant TV as Tavily API

    U->>G: Что нового в LangChain 0.3?
    G->>T: web_search(query="LangChain 0.3", max=5)
    T->>TV: POST /search
    TV-->>T: results[{title,url,content,score}]
    T-->>G: results как tool message
    G->>G: LLM synthesizes answer with sources
    G-->>U: answer + clickable URLs
```

---

## 7. Architecture Decision Records (ADR)

### ADR-001: Использовать LangGraph вместо LangChain AgentExecutor

**Status**: Accepted (2026-09-19)
**Context**: Нужен оркестратор, поддерживающий cycles, conditional edges, human-in-the-loop, чекпойнтинг состояния для resume после рестарта. AgentExecutor в LangChain 0.1 имел только linear flow и плохо поддерживал streaming.
**Decision**: Использовать `langgraph` (0.2+) как основной оркестратор. AgentExecutor не используется.
**Consequences**:
- (+) Декларативный state-machine, читаемый граф.
- (+) Native `PostgresSaver` для персистентного состояния.
- (+) Поддержка human-in-the-loop через `interrupt_before`.
- (-) Дополнительная абстракция поверх LangChain, кривая обучения ~2-3 дня для разработчика.
- (-) Streaming API чуть сложнее, нужно правильно настраивать `astream_events`.

### ADR-002: Streamlit как UI для MVP, миграция на Chainlit в Phase 5

**Status**: Accepted
**Context**: Нужен быстрый MVP (3 недели). Streamlit даёт готовый чат-компонент `st.chat_message`, `st.chat_input`, session_state. Production-нагрузку (multi-session, WS, sticky sessions) Streamlit держит плохо.
**Decision**: MVP и Alpha — на Streamlit. Phase 5 (Scale) — миграция на Chainlit (нативная интеграция с LangChain, готовый production UI) или FastAPI + Next.js если требуется полный контроль.
**Consequences**:
- (+) MVP за 3 дня на UI-часть.
- (+) Хорошо подходит для internal tools.
- (-) Streamlit re-runs: нужно тщательно управлять session_state, иначе тормозит.
- (-) Multi-instance (horizontal scale) — нужен sticky session или external session store.

### ADR-003: Тройная стратегия векторных хранилищ (Chroma / Qdrant / pgvector)

**Status**: Accepted
**Context**: Разные окружения требуют разных решений:
- Dev/тесты — Chroma (in-process, embeddable, zero-config).
- Production RAG — Qdrant (high-throughput, filtering, hybrid search).
- Business-data RAG — pgvector (когда вектора и бизнес-данные в одной БД, JOIN упрощает).

**Decision**: Внедрить `VectorStoreFactory` с тремя адаптерами. Выбор через конфиг `VECTOR_STORE_KIND`.
**Consequences**:
- (+) Гибкость, нет vendor lock-in.
- (+) Dev/prod parity через общий `VectorStore` interface.
- (-) Три имплементации нужно тестировать.
- (-) Схема коллекций немного отличается (Qdrant использует payload, pgvector — columns).

### ADR-004: MCP только в Client mode

**Status**: Accepted
**Context**: Клиент должен уметь подключаться к внешним MCP-серверам (filesystem, GitHub, Slack, custom). Экспорт своих tools как MCP-сервер — полезно, но усложняет MVP.
**Decision**: Реализовать только MCP Client. MCP Server — отложен до Phase 6 (Scale).
**Consequences**:
- (+) Меньше surface area, проще security model.
- (+) Сфокусированный MVP.
- (-) Не сможем предоставить наши tools другим агентам — узкое место для interoperability.

### ADR-005: PostgreSQL как единая БД для сессий, метаданных и чекпойнтов

**Status**: Accepted
**Context**: Нужна транзакционная БД для сессий/сообщений/файлов. LangGraph предлагает PostgresSaver как первый класс. pgvector extension даёт опцию RAG в той же БД.
**Decision**: PostgreSQL 16 как primary datastore. Redis — кэш и rate-limit. Никаких Mongo/ElasticSearch.
**Consequences**:
- (+) Одна БД для ops, проще бэкапы.
- (+) pgvector — fallback если Qdrant недоступен.
- (-) PostgreSQL vertical scale может быть узким местом при > 1000 RPS.

### ADR-006: Tool calling через нативный API LLM, а не через ReAct prompt

**Status**: Accepted
**Context**: OpenAI и Anthropic поддерживают нативный tool calling. ReAct prompt — legacy, менее надёжный.
**Decision**: Использовать `bind_tools()` LangChain и нативный tool calling API. ReAct — fallback для локальных моделей без function calling (Phase 4+).
**Consequences**:
- (+) Надёжный парсинг tool calls (структурированный JSON от API).
- (+) Меньше токенов на системный промпт.
- (-) Локальные модели без function calling (Llama 3.1 base) — не поддерживаются в MVP.

### ADR-007: Streaming через SSE (Server-Sent Events), а не WebSocket

**Status**: Accepted
**Context**: LLM streaming токенов нужно передавать в UI. WebSocket — bi-directional, но сложнее в Streamlit. SSE — one-way, проще, нативно работает через `streamlit.write_stream`.
**Decision**: SSE для streaming responses (Streamlit native). WebSocket — только для будущего real-time collaboration (Phase 6+).
**Consequences**:
- (+) Простота, работает через любой reverse proxy.
- (+) Auto-reconnect в браузере.
- (-) One-way only: для интерактивных прерываний (cancel button) нужно доп. HTTP endpoint.

### ADR-008: Файлы сохраняются в локальный volume, в Production — S3-compatible (MinIO)

**Status**: Accepted
**Context**: На MVP проще писать в локальный `/data/files`. В production — нужно shared storage для multi-instance.
**Decision**: Абстракция `FileStorage` с двумя реализациями: `LocalFileStorage` (default) и `S3FileStorage` (production). MinIO для self-hosted S3-compatible.
**Consequences**:
- (+) Простой local dev, ready для S3 в prod.
- (-) Дополнительная абстракция, нужно тестировать обе имплементации.

**Phase 1 Update (расш. ADR-008, 2026-09-21)**: `LocalFileStorage` упразднён, остаётся только `S3CompatibleStorage`. Единый контракт `FileStorage` для dev (MinIO) / staging / prod (S3); миграция прозрачна для caller-кода. См. ROADMAP.md §5.5, TRIZ-ANALYSIS.md §7.5, MVP-PROMPTS.md Блок E.

### ADR-013: SSE + HTTP Cancel Endpoint

**Status**: Approved (2026-09-21)
**Context**: ADR-007 зафиксировал SSE для streaming LLM-ответов (one-way, без интерактивных прерываний). ROADMAP.md §5.3 требует cancel за <100 мс в 99% случаев и возврат partial answer. Противоречие C-4 (SSE one-way vs interactivity).
**Decision**: Dual-channel архитектура: data-plane остаётся SSE без изменений (ADR-007 не нарушается); control-plane — HTTP POST `/sessions/{id}/cancel` + Redis pub/sub канал `session:{id}:cancel` для уведомления агента. На стороне агента — `CancellationToken`, проверяемый между node-ами графа; при cancel-сигнале граф прерывает upstream LLM-вызов и возвращает partial answer. UI-клиент детектирует обрыв SSE-соединения (visibilitychange / beforeunload) и автоматически шлёт cancel через `navigator.sendBeacon`.
**Consequences**:
- (+) Cancel работает мгновенно (Redis pub/sub latency <5 мс).
- (+) Авто-cancel при закрытии вкладки — UX improvement.
- (+) ADR-007 (SSE для данных) остаётся без изменений.
- (-) Redis pub/sub — новая dependency для control-plane.
- (-) Граф обязан проверять `CancellationToken` между node-ами.
**References**: ROADMAP.md §5.3, TRIZ-ANALYSIS.md §5.4 + §11, MVP-PROMPTS.md Блок C.

### ADR-014: Dual-Stream Logging (Encrypted + Masked)

**Status**: Approved (2026-09-21)
**Context**: §9.4 Security требует PII masking, §9.6 Observability требует full trace retention 90+ дней. ROADMAP.md §5.4 требует PII leaks = 0 (automated audit) и forensic retention 90+ дней. Противоречие C-11 (PII masking vs observability).
**Decision**: `DualStreamLogger` с двумя потоками: (1) **operational** — маскированный (Presidio + custom regex через `PIIDetector`), stdout/Loki/ELK, retention 30 дней, доступ команды для debugging; (2) **forensic** — зашифрованный AES-256-GCM через Vault/KMS (`KMSKeyProvider`), отдельный S3 bucket, retention 90+ дней, доступ через отдельный RBAC (security officer + аудит-комитет). PII detection score сохраняется в `messages` как metadata (`pii_score`, `pii_entities`). В dev forensic отключён (`FORENSIC_STREAM_ENABLED=false`, без Vault); в staging/prod обязателен (в prod `false` отклоняется валидацией).
**Consequences**:
- (+) Compliance удовлетворён (PII отсутствует в operational логах).
- (+) Воспроизводимость сохранена (forensic stream, encrypted full trace).
- (+) Аналитика по sensitive data (через PII score).
- (-) Двойная стоимость хранения логов.
- (-) Сложность доступа к forensic (отдельный RBAC, аудит).
- (-) Ключи шифрования в KMS/Vault — ещё одна зависимость.
**References**: ROADMAP.md §5.4, TRIZ-ANALYSIS.md §7.1 + §11, MVP-PROMPTS.md Блок D.

### ADR-010: Async Checkpoint Write-Behind Log

**Status**: Approved (2026-09-30)
**Context**: ADR-001 использует `PostgresSaver` для LangGraph checkpointer с синхронной записью в `agent_checkpoints` на каждом node transition. Это добавляет 10–50 мс на каждый переход, суммарно 50–200 мс на типовой агентский цикл, что становится bottleneck при росте RPS. ROADMAP.md §6.3 требует latency checkpoint <2 мс в 99% случаев и корректное восстановление при restart. Противоречие C-2 (PG checkpoint vs latency).
**Decision**: Ввести composite checkpointer `RedisPostgresCheckpointer` (`src/llm_client/orchestration/checkpointers/composite.py`), реализующий `BaseCheckpointSaver` interface LangGraph:
1. `RedisCheckpointer` — synchronous write в Redis DB 1 (`REDIS_CHECKPOINT_URL`), latency <1 мс, TTL=24h, `maxmemory-policy=noeviction`.
2. `PostgresCheckpointer` — asynchronous batched write: background flusher каждые 5 сек или N=50 checkpoints через `INSERT ... ON CONFLICT DO UPDATE`.
3. Восстановление при restart: snapshot из PostgreSQL, затем delta-replay из Redis (потеря ≤5 сек — acceptable risk).
4. `PostgresSaver` — deprecated, оставлен только для backward-compat тестов.
**Consequences**:
- (+) Latency checkpointing снижается с 10–50 мс до <1 мс.
- (+) PostgreSQL не нагружается на каждом node transition (RPS на PG снижается ~50×).
- (+) Resume-after-restart сохраняется (Redis snapshot + PostgreSQL durable).
- (-) Redis — mandatory dependency для checkpointing (раньше опциональный).
- (-) Возможна потеря последних 5 сек checkpoint-ов при одновременном отказе Redis и PostgreSQL.
- (-) Сложнее тестировать (два хранилища вместо одного).
**References**: ROADMAP.md §6.3, TRIZ-ANALYSIS.md §5.2 (C-2) + §11, ALPHA-PROMPTS.md Блок B, BACKLOG.md §3.4.

### ADR-017: Reranker Model in RAG

**Status**: Approved (2026-09-30)
**Context**: §5.2.5 упоминает MMR reranking, но без ML-reranker. Pure vector retrieval плохо ранжирует топ-K чанков. ROADMAP.md §6.4 требует recall@5 ↑ ≥15% vs baseline (no reranker) и latency retrieval ↑ <100 мс. Противоречие C-6 (long RAG context vs cost) — качественная составляющая.
**Decision**: Ввести cross-encoder reranker в RAG pipeline (`src/llm_client/rag/rerankers/`):
1. Default reranker: `BgeRerankerAdapter` (`BAAI/bge-reranker-base`, локальная in-process модель, ~600MB RAM).
2. Опционально: `CohereRerankAdapter` (Cohere Rerank API).
3. `IdentityReranker` — no-op fallback при недоступности моделей.
4. `RerankerRegistry` + `RerankerChain` — pluggable registry с graceful fallback (при ошибке одного reranker переходим к следующему в chain).
5. Pipeline: vector top-20 + BM25 top-20 → RRF fusion top-50 → reranker top-5.
**Consequences**:
- (+) Значительное улучшение precision и recall (типично +20–30% recall@5).
- (+) Снижение контекста LLM (5 качественных чанков вместо 20 шумных).
- (-) Дополнительная latency (50–200 мс на reranking CPU).
- (-) bge-reranker-base требует ~600MB RAM для in-process.
- (-) Cohere Rerank — внешняя зависимость с отдельной стоимостью.
**References**: ROADMAP.md §6.4, TRIZ-ANALYSIS.md §6.1 (C-6) + §11, ALPHA-PROMPTS.md Блок C, BACKLOG.md §3.4 (AG-6 расширяется).

### ADR-020: Hybrid (BM25 + Vector) RAG по умолчанию

**Status**: Approved (2026-09-30)
**Context**: §5.2.5 упоминает hybrid search (BM25 + vector), но как опция. Pure vector retrieval плохо находит точные совпадения (product SKU, error codes, артикулы). ROADMAP.md §6.5 требует recall ↑ ≥30% для точных терминов и latency retrieval ↑ <50 мс. ТРИЗ-стандарт 1.1.5 (введение второго поля в веполь).
**Decision**: Сделать hybrid retrieval (BM25 + vector) default (`src/llm_client/rag/retrieval/`):
1. `RetrieverConfig.retrieval_strategy: "vector"|"bm25"|"hybrid"` — default: `hybrid`.
2. `BM25Retriever` — lexical retrieval через PostgreSQL `tsvector` (GIN index на `documents.search_vector`, GENERATED ALWAYS AS STORED).
3. `HybridRetriever` — параллельный vector + BM25, `rrf_fusion` (reciprocal rank fusion) для объединения.
4. Reranker (ADR-017) применяется после fusion.
5. PostgreSQL расширен extensions: `pgvector` (existing) + `tsvector`/`pg_trgm` (new).
**Consequences**:
- (+) Значительное улучшение recall для запросов с точными терминами (≥30%).
- (+) Best of both worlds: semantic + lexical.
- (+) Нулевая новая зависимость (tsvector в существующей PostgreSQL, принцип ТРИЗ #5 «объединение»).
- (-) Дополнительное хранилище для BM25 index (GIN).
- (-) Latency retrieval возрастает на 30–50% (двойной запрос, параллельно).
- (-) Reranker обязателен (без него noise от fusion).
**References**: ROADMAP.md §6.5, TRIZ-ANALYSIS.md §6.1 (C-6) + §8.3 + §11, ALPHA-PROMPTS.md Блок D, BACKLOG.md §3.4 (AG-6 расширяется).

### AG-5: web_search tool via Tavily

**Status**: Approved (2026-09-30)
**Context**: BACKLOG.md v1.1.0 §3.4 формализует AG-5 как Phase 2 работу. ADR-005 (Tool Layer) и ADR-006 (нативный tool calling через `bind_tools()`) уже Approved. UI-1 (Phase 1) имеет G-3 (web search results panel) как потребителя событий `event: tool_call` / `event: tool_result`.
**Decision**: Реализовать `web_search` tool (`src/llm_client/agent/tools/web_search.py`):
1. `StructuredTool.from_function` с `RagQueryArgs`-подобной Pydantic-схемой (`query`, `max_results`).
2. Внешний API: Tavily (`TAVILY_API_KEY` env var).
3. Возвращает `list[dict]` `{title, url, snippet}`.
4. Подключается в `bind_tools()` planner ноды; payload (list) парсится SSE-эмиттером как `event: tool_result`.
5. При отсутствии `TAVILY_API_KEY` — startup fail-fast when `tools_enabled` contains "web_search" (default includes it). Runtime graceful degradation if key missing after startup.
**Consequences**:
- (+) Агент получает актуальные веб-данные (G-3: ≥5 инструментов в проде).
- (+) UI-1 web search results panel (G-3) получает источник событий.
- (-) Зависимость от внешнего API Tavily (cost + availability).
**References**: ROADMAP.md §6.2.4, BACKLOG.md v1.1.0 §3.4, AG-PROMPTS.md (Phase 1 AG-1..AG-4 — предусловие), ALPHA-PROMPTS.md Блок H-1.

### AG-6: rag_query tool + base RAG pipeline + rag_retriever нода

**Status**: Approved (2026-09-30)
**Context**: BACKLOG.md v1.1.0 §3.4 формализует AG-6 как Phase 2 работу (4 чел-дн). ADR-003 (VectorStoreFactory) и ADR-001 (LangGraph) Approved. Расширяется ADR-017 (reranker) и ADR-020 (hybrid retrieval) в этом же Phase 2. Закрывает связку UI-1 (RAG citations panel, G-2) с реальным источником RAG-данных.
**Decision**: Реализовать связку:
1. `RagQueryArgs` + `rag_query` @tool (`src/llm_client/agent/tools/rag_query.py`) — вызывает `RagPipeline`, возвращает `dict` с `chunks`, `chunk_count`, `top_score`.
2. `RagPipeline` (`src/llm_client/rag/pipeline.py`) — singleton при agent-service startup; композирует retriever (`HybridRetriever` / vector-only / BM25-only) + reranker (`BgeRerankerAdapter` / `CohereRerankAdapter` / identity) на основе `RetrieverConfig`. Single source of truth для `rag_query` @tool и `rag_retriever` ноды.
3. `rag_retriever` нода (`src/llm_client/agent/graph.py`) — Phase 2; извлекает RAG chunks через `RagPipeline`, обновляет `state["retrieved_docs"]`. Вызывается когда planner выбирает `route_decision="rag_first"` (heuristic по ключевым словам; в Phase 3+ — LLM structured output).
4. Conditional edges: `route_after_planner` — 3 выхода (`direct_llm` / `tools_needed` / `rag_first`); `rag_retriever` пропускается если `rag_query` tool call уже ответил на тот же query (H-4 оптимизация).
**Consequences**:
- (+) RAG доступен агенту как tool (G-1: сокращение времени аналитика).
- (+) UI-1 RAG citations panel (G-2) получает источник `event: retrieved_docs`.
- (+) Single RagPipeline — единая точка конфигурации retrieval/reranker.
- (-) Дополнительная latency на rag_retriever ноду (reranker + hybrid).
**References**: ROADMAP.md §6.2.5, BACKLOG.md v1.1.0 §3.4, AG-PROMPTS.md, ALPHA-PROMPTS.md Блок H-2/H-3/H-4.

---

## 8. Trade-offs

| Decision | Pros | Cons | Mitigation |
|---|---|---|---|
| Streamlit MVP | Быстрый старт, готовый UI | Плохо scale horizontally | Migrate на Chainlit/Next.js в Phase 5 |
| LangGraph | Циклы, чекпойнты, HITL | Кривая обучения | Документация + примеры |
| Triple vector store | Гибкость, no lock-in | 3 адаптера | Покрыть contract tests |
| MCP client-only | Меньше complexity | Не экспонируем свои tools | Phase 6: MCP server mode |
| PostgreSQL-only | Проще ops | Vertical scale limit | Read replicas + pgvector scaling |
| ~~SSE streaming (C-4)~~ | Простота, proxy-friendly | One-way | ~~HTTP endpoint для cancel~~ **[RESOLVED by ADR-013 in Phase 1]** — control-plane: POST /cancel + Redis pub/sub; data-plane: SSE без изменений |
| ~~PII masking vs observability (C-11)~~ | Compliance, GDPR/SOC2 | Полный trace недоступен | **[RESOLVED by ADR-014 in Phase 1]** — DualStreamLogger: operational (masked) + forensic (AES-256-GCM encrypted) |
| ~~File storage abstraction (C-15)~~ | Swappable backends | Двойная имплементация | ~~Test both в CI~~ **[RESOLVED by расш. ADR-008 in Phase 1]** — LocalFileStorage удалён, единственный S3CompatibleStorage (MinIO/S3) |
| ~~PG checkpoint vs latency (C-2)~~ | Durability, resume-after-restart | Latency 10–50 мс на каждый node transition | **[RESOLVED by ADR-010 in Phase 2]** — RedisPostgresCheckpointer: sync Redis (<1 мс) + async PG batch flush; PostgresSaver deprecated |
| ~~Long RAG context vs cost (C-6)~~ | Precision/recall RAG | Cost / context size LLM | **[PARTIALLY RESOLVED by ADR-017 + ADR-020 in Phase 2 (precision/recall)]** — reranker + hybrid retrieval снижают context (top-5 вместо top-20); **ADR-011 в Phase 3 — cost component pending** (semantic cache) |

---

## 9. Нефункциональные требования (NFRs)

### 9.1 Performance

| Метрика | Target (MVP) | Target (Production) |
|---|---|---|
| Time to first token (TTFT) | < 2 сек | < 1 сек |
| Time to full answer (без tools) | < 8 сек | < 5 сек |
| Time to full answer (1 tool call) | < 15 сек | < 10 сек |
| RAG retrieval latency | < 500 мс | < 200 мс |
| File export (1 MB PDF) | < 5 сек | < 2 сек |
| UI initial load | < 3 сек | < 1.5 сек |

### 9.2 Scalability

| Параметр | MVP | Production |
|---|---|---|
| Concurrent users | 1-5 | 100-500 |
| Sessions per user | неограниченно | неограниченно |
| Documents in RAG | 1k | 1M+ |
| Tokens per day | 50k | 5M+ |
| Horizontal scale | single instance | 3-5 instances за LB |

### 9.3 Reliability

| Метрика | Target |
|---|---|
| Uptime | 99.5% (MVP), 99.9% (prod) |
| LLM API error retry | 3 retries with exponential backoff |
| Fallback provider | автоматический при 5 ошибках подряд |
| Graceful degradation | web_search недоступен -> warning + продолжение без tool |
| Backup | daily Postgres dump, retention 30 дней |

### 9.4 Security

| Контрол | MVP | Production |
|---|---|---|
| Auth | basic (env-credentials) | OAuth2/OIDC (Keycloak/Authentik) |
| Secrets | `.env` (не в git) | Vault / SOPS / AWS Secrets Manager |
| TLS | none (local) | nginx + Let's Encrypt / internal CA |
| PII masking in logs | regex-based | Microsoft Presidio + custom rules |
| Rate limiting | in-process token bucket | Redis-based distributed limiter |
| File access | по user_id | RBAC + path whitelisting |
| MCP server trust | explicit config | signed manifests, allow-list |
| Audit log | basic в messages таблице | structured audit trail с SIEM интеграцией |

### 9.5 Maintainability

| Метрика | Target |
|---|---|
| Test coverage (core) | > 80% |
| Linting | ruff + mypy strict |
| Type hints | 100% для публичных API |
| Docstrings | все публичные функции (Google style) |
| CI pipeline | < 5 минут на PR |

### 9.6 Observability

| Слой | MVP | Production |
|---|---|---|
| Logs | `structlog` JSON в stdout | + Loki / ELK |
| Metrics | basic (requests, latency) | Prometheus + Grafana dashboards |
| Tracing | OpenTelemetry spans (manual) | auto-instrumentation + Jaeger |
| LLM cost tracking | в `llm_calls` таблице | dashboard per user/session/day |
| LangSmith | optional tracing | mandatory для prod traces |
| Health checks | `/healthz` endpoint | + readiness + dependency probes |

---

## 10. Структура репозитория

```
llm-client/
+-- docker-compose.yml
+-- docker-compose.prod.yml
+-- .env.example
+-- pyproject.toml
+-- README.md
+-- ARCHITECT.md
+-- ROADMAP.md
+-- docs/
|   +-- adr/                    # ADR-001..008.md
|   +-- runbooks/
|   +-- diagrams/
+-- src/
|   +-- llm_client/
|       +-- __init__.py
|       +-- main.py             # Streamlit entrypoint
|       +-- config.py           # Pydantic Settings
|       +-- ui/
|       |   +-- chat.py
|       |   +-- history.py
|       |   +-- settings_panel.py
|       |   +-- download.py
|       +-- agent/
|       |   +-- graph.py        # StateGraph definition
|       |   +-- state.py        # AgentState TypedDict
|       |   +-- nodes/
|       |   |   +-- planner.py
|       |   |   +-- tool_executor.py
|       |   |   +-- rag_retriever.py
|       |   |   +-- mcp_invoker.py
|       |   |   +-- final_answer.py
|       |   +-- checkpointer.py
|       +-- llm/
|       |   +-- factory.py
|       |   +-- token_tracker.py
|       |   +-- retry.py
|       +-- tools/
|       |   +-- web_search.py
|       |   +-- rag_query.py
|       |   +-- file_export/
|       |   |   +-- __init__.py
|       |   |   +-- renderers/
|       |   |   |   +-- md.py
|       |   |   |   +-- txt.py
|       |   |   |   +-- pdf.py
|       |   |   |   +-- docx.py
|       |   |   |   +-- xlsx.py
|       |   |   |   +-- odt.py
|       |   |   +-- storage.py
|       |   +-- mcp_proxy.py
|       |   +-- registry.py
|       +-- rag/
|       |   +-- loaders.py
|       |   +-- chunkers.py
|       |   +-- embeddings.py
|       |   +-- vector_store_factory.py
|       |   +-- retrievers.py
|       +-- mcp/
|       |   +-- client.py
|       |   +-- config.py
|       +-- persistence/
|       |   +-- models.py        # SQLAlchemy
|       |   +-- session_repo.py
|       |   +-- message_repo.py
|       |   +-- file_repo.py
|       |   +-- migrations/     # Alembic
|       +-- observability/
|       |   +-- logging.py
|       |   +-- metrics.py
|       |   +-- tracing.py
|       +-- security/
|           +-- auth.py
|           +-- pii_mask.py
+-- tests/
|   +-- unit/
|   +-- integration/
|   +-- e2e/
+-- scripts/
|   +-- seed_dev_db.py
|   +-- load_test.py
+-- deploy/
    +-- docker/
    |   +-- ui.Dockerfile
    |   +-- agent.Dockerfile
    |   +-- worker.Dockerfile
    +-- k8s/                    # future Phase 6
        +-- helm/
        +-- manifests/
```

---

## 11. Конфигурация (`.env` пример)

```bash
# LLM Providers
OPENAI_API_KEY=sk-...
OPENAI_DEFAULT_MODEL=gpt-4o-mini
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_DEFAULT_MODEL=claude-3-5-sonnet-20241022

# Search
TAVILY_API_KEY=tvly-...

# Vector Store
VECTOR_STORE_KIND=chroma              # chroma | qdrant | pgvector
CHROMA_PERSIST_DIR=/data/chroma
QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=llm_client_docs
PGVECTOR_DSN=postgresql+asyncpg://user:pass@postgres:5432/llm_client

# PostgreSQL
DATABASE_URL=postgresql+asyncpg://user:pass@postgres:5432/llm_client
REDIS_URL=redis://redis:6379/0

# File Storage
FILE_STORAGE_KIND=local                # local | s3
FILE_STORAGE_LOCAL_PATH=/data/files
S3_ENDPOINT=http://minio:9000
S3_BUCKET=llm-client-files
S3_ACCESS_KEY=...
S3_SECRET_KEY=...

# MCP Servers (JSON)
MCP_SERVERS_CONFIG_PATH=/etc/llm-client/mcp_servers.json

# Observability
LOG_LEVEL=INFO
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317
LANGSMITH_API_KEY=ls-...
LANGSMITH_TRACING=true

# Security
JWT_SECRET=...
OAUTH_ISSUER_URL=https://keycloak.internal/auth/realms/main
RATE_LIMIT_PER_MIN=60
```

`mcp_servers.json`:

```json
{
  "servers": [
    {
      "name": "filesystem",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/data/user-files"]
    },
    {
      "name": "github",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {"GITHUB_TOKEN": "${GITHUB_TOKEN}"}
    }
  ]
}
```

---

## 12. Открытые вопросы и риски

| ID | Вопрос / Риск | Вероятность | Влияние | Митигация |
|---|---|---|---|---|
| Q-1 | Будет ли Ollama поддерживаться в Phase 4? | Medium | High | Spike в Phase 3, fallback на локальные модели через LiteLLM |
| Q-2 | LangSmith pricing для большого объема трейсов | High | Medium | **[CLOSED: ADR-014 DualStreamLogger — собственный observability, не зависит от LangSmith]** |
| Q-3 | MCP-серверы с stdio в docker-compose — complexity | High | Medium | Использовать SSE transport где возможно, отдельный sidecar контейнер |
| Q-4 | Streamlit + LangGraph async — совместимость | Medium | High | **[PARTIALLY CLOSED: ADR-013 — cancel через Redis pub/sub, не Streamlit native; полное закрытие в Phase 5 через ADR-018]** |
| Q-5 | Стоимость LLM при high RAG context (>50k tokens) | High | High | **[PARTIALLY CLOSED: ADR-017 + ADR-020 снижают context size (top-5 reranked chunks вместо raw top-20); ADR-011 в Phase 3 — full closure через semantic cache]** Implement context compression (LangChain `LLMChainExtractor`), map-reduce для длинных документов |

---

## 13. References

- LangGraph docs: https://langchain-ai.github.io/langgraph/
- LangChain docs: https://python.langchain.com/docs/
- MCP specification: https://modelcontextprotocol.io/specification
- Qdrant docs: https://qdrant.tech/documentation/
- pgvector: https://github.com/pgvector/pgvector
- Streamlit chat concepts: https://docs.streamlit.io/develop/tutorials/llms
- C4 model: https://c4model.com/

---
*Конец ARCHITECT.md. Документ должен пересматриваться на каждой фазе ROADMAP.md; обновления отражать в `docs/adr/`.*

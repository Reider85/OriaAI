# ARCHITECT.md — LLM Client с агентным веб-поиском, RAG и MCP

| Атрибут | Значение |
|---|---|
| Версия документа | 1.0.0 |
| Дата | 2026-09-19 |
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
        PG[("PostgreSQL<br/>sessions, files meta")]
        REDIS[("Redis<br/>cache, rate-limit")]
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
| `postgres` | PostgreSQL 16 | Sessions, messages, files metadata, pgvector (alt RAG) | SQL |
| `redis` | Redis 7 | Cache (LLM responses, embeddings), rate-limit, pub/sub для WS | RESP |
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
+-------------------------------------------------------------+
| 2. Orchestration Layer (LangGraph)                          |
|    - State machine: planner -> tool_selector -> executor     |
|    - Conditional edges, cycles, human-in-the-loop            |
|    - Checkpointing (PostgreSQL backend)                     |
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
|    - Retrievers: similarity, MMR, hybrid (BM25 + vector)     |
+-------------------------------------------------------------+
| 6. MCP Client Layer                                          |
|    - mcp Python SDK, multi-transport (stdio, SSE, WS)        |
|    - Dynamic tool discovery from MCP servers                 |
|    - Tool registry <-> LangGraph tool node                   |
+-------------------------------------------------------------+
| 7. Persistence Layer                                         |
|    - SQLAlchemy 2.0 (async) -> PostgreSQL                    |
|    - Alembic migrations                                      |
|    - Redis client (aioredis)                                 |
|    - File storage: local FS / S3-compatible (MinIO)         |
+-------------------------------------------------------------+
```

### 5.1 Компонентная диаграмма (C4 Level 3 — Agent Service)

```mermaid
flowchart TB
    subgraph UI[Streamlit UI]
        CHAT[chat_component]
        HIST[session_history]
        DL[download_button]
    end

    subgraph ORCH[LangGraph Orchestration]
        GRAPH[StateGraph]
        NODES[Nodes: planner, tool_call,<br/>rag_retriever, mcp_call, final_answer]
        CHECK[Checkpointer<br/>PostgresSaver]
        STATE[AgentState<br/>TypedDict]
    end

    subgraph LLM[LLM Provider Layer]
        PROV[provider_factory]
        OAI[ChatOpenAI]
        ANT[ChatAnthropic]
        LIT[LiteLLM Gateway<br/>optional]
    end

    subgraph TOOLS[Tool Layer]
        TS[web_search<br/>Tavily]
        TR[rag_query<br/>retriever.invoke]
        TM[mcp_call<br/>proxy]
        TF[file_export<br/>md/txt/pdf/docx/xlsx/odt]
        TC[calc/code_exec<br/>sandboxed]
    end

    subgraph RAG[RAG Layer]
        LOAD[loaders]
        CHUNK[chunkers]
        EMB[embeddings]
        VS1[(Chroma)]
        VS2[(Qdrant)]
        VS3[(pgvector)]
        RET[retrievers]
    end

    subgraph MCP[MCP Client Layer]
        CLIENT[mcp.ClientSession]
        REG[tool registry]
        TRANS1[stdio transport]
        TRANS2[SSE transport]
    end

    subgraph PERS[Persistence Layer]
        SA[SQLAlchemy async]
        PG[(PostgreSQL)]
        RD[(Redis)]
        FS[(File Storage)]
    end

    CHAT -->|async stream| GRAPH
    GRAPH --> NODES
    NODES --> PROV
    PROV --> OAI
    PROV --> ANT
    PROV -.-> LIT
    NODES --> TOOLS
    TS --> TAV[Tavily API]
    TR --> RET
    RET --> VS1
    RET --> VS2
    RET --> VS3
    TF --> FS
    TM --> CLIENT
    CLIENT --> TRANS1
    CLIENT --> TRANS2
    TRANS1 --> MCPS1[(filesystem<br/>MCP server)]
    TRANS2 --> MCPS2[(github<br/>MCP server)]
    GRAPH --> CHECK
    CHECK --> SA
    SA --> PG
    NODES --> RD
    HIST --> SA
    DL --> FS

    classDef ui fill:#dbeafe,stroke:#1e40af,color:#000
    classDef orch fill:#dcfce7,stroke:#166534,color:#000
    classDef llm fill:#fef9c3,stroke:#854d0e,color:#000
    classDef tools fill:#fee2e2,stroke:#991b1b,color:#000
    classDef rag fill:#f3e8ff,stroke:#6b21a8,color:#000
    classDef mcp fill:#ffedd5,stroke:#9a3412,color:#000
    classDef pers fill:#e0e7ff,stroke:#3730a3,color:#000

    class CHAT,HIST,DL ui
    class GRAPH,NODES,CHECK,STATE orch
    class PROV,OAI,ANT,LIT llm
    class TS,TR,TM,TF,TC tools
    class LOAD,CHUNK,EMB,VS1,VS2,VS3,RET rag
    class CLIENT,REG,TRANS1,TRANS2 mcp
    class SA,PG,RD,FS pers
```

### 5.2 Описание ключевых компонентов

#### 5.2.1 Presentation Layer (Streamlit UI)

| Компонент | Файл | Ответственность |
|---|---|---|
| `chat_component` | `ui/components/chat.py` | Рендеринг сообщений, streaming tokens, tool-call previews |
| `session_history` | `ui/components/history.py` | Список сессий слева, переключение, поиск по истории |
| `download_button` | `ui/components/download.py` | Кнопки для каждого экспортированного файла |
| `settings_panel` | `ui/components/settings.py` | Выбор провайдера/модели, температура, max_tokens, tools on/off |
| `auth_gate` | `ui/components/auth.py` | Basic auth (MVP) -> OAuth2/OIDC (prod) |

UI общается с `agent_service` через **Streamlit native callbacks** (MVP, in-process) или через **FastAPI + SSE** (Alpha+ для multi-instance).

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
- `rag_retriever` — инкапсулирует retriever.invoke, обновляет `retrieved_docs`
- `mcp_invoker` — делегирует вызовы в MCP client
- `final_answer` — формирует финальный ответ с цитатами и артефактами
- `human_review` (опционально) — прерывание для подтверждения тяжёлых действий (например, удаление файла через MCP filesystem)

Conditional edges:
- `route_after_planner`: если planner вернул `tools_needed`, идём в `tool_executor`; иначе — в `final_answer`.
- `route_after_tool`: если в `messages` есть новый `tool` message, возвращаемся в LLM для интерпретации; если `final_answer_ready` — выходим.

Checkpointer: `PostgresSaver` (LangGraph 0.2+) — персистентное состояние графа, поддержка resume-after-restart.

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
```

Tool registry собирает все `BaseTool` инстансы в единый список, который передаётся в LangGraph `ToolNode`. MCP-tools добавляются в registry динамически при подключении MCP-сервера.

#### 5.2.5 RAG Layer

Pipeline:
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

5. **Retrieve** — `vector_store.as_retriever(search_type="mmr", k=8, fetch_k=20)`. Для гибридного поиска — комбинируем BM25 (через `rank_bm25`) с vector reranking.

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
    content_hash TEXT NOT NULL,
    meta JSONB NOT NULL DEFAULT '{}',
    indexed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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

---

## 8. Trade-offs

| Decision | Pros | Cons | Mitigation |
|---|---|---|---|
| Streamlit MVP | Быстрый старт, готовый UI | Плохо scale horizontally | Migrate на Chainlit/Next.js в Phase 5 |
| LangGraph | Циклы, чекпойнты, HITL | Кривая обучения | Документация + примеры |
| Triple vector store | Гибкость, no lock-in | 3 адаптера | Покрыть contract tests |
| MCP client-only | Меньше complexity | Не экспонируем свои tools | Phase 6: MCP server mode |
| PostgreSQL-only | Проще ops | Vertical scale limit | Read replicas + pgvector scaling |
| SSE streaming | Простота, proxy-friendly | One-way | HTTP endpoint для cancel |
| File storage abstraction | Swappable backends | Двойная имплементация | Test both в CI |

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
| Q-2 | LangSmith pricing для большого объема трейсов | High | Medium | Sampling (только 10% трейсов) + self-hosted Langfuse |
| Q-3 | MCP-серверы с stdio в docker-compose — complexity | High | Medium | Использовать SSE transport где возможно, отдельный sidecar контейнер |
| Q-4 | Streamlit + LangGraph async — совместимость | Medium | High | Spike в Phase 1, fallback на FastAPI backend + Streamlit как pure frontend |
| Q-5 | Стоимость LLM при high RAG context (>50k tokens) | High | High | Implement context compression (LangChain `LLMChainExtractor`), map-reduce для длинных документов |

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

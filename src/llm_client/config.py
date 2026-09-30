from pydantic import model_validator
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    environment: str = "dev"
    forensic_stream_enabled: bool = False
    pii_detector_enabled: bool = True
    pii_detector_spacy_model: str = "en_core_web_md"
    pii_metadata_enabled: bool = True
    cycle_detection_enabled: bool = True
    cycle_detection_threshold: float = 0.95

    # Observability (ADR-014)
    operational_log_sink: str = "stdout"
    operational_log_loki_url: str = "http://loki:3100"
    operational_log_es_url: str = "http://elasticsearch:9200"
    kms_provider: str = "vault"

    # Redis
    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_checkpoint_url: str = "redis://127.0.0.1:6379/1"
    redis_checkpoint_ttl_seconds: int = 86400
    redis_checkpoint_maxmemory_policy: str = "noeviction"
    checkpoint_backend: str = "redis_postgres"

    # MinIO / S3
    s3_endpoint: str = "http://127.0.0.1:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "llm-client-files"
    s3_forensic_bucket: str = "llm-client-forensic"

    # PostgreSQL (for ADR-010)
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5434/llm_client"
    checkpoint_flush_interval_seconds: int = 5
    checkpoint_flush_batch_size: int = 50
    # PostgreSQL full-text search (ADR-020 / A-3)
    pg_text_search_config: str = "english"
    pg_fuzzy_matching_enabled: bool = False

    # Vault
    vault_addr: str = "http://127.0.0.1:8200"
    vault_token: str = "root"
    vault_transit_key: str = "forensic-aes256-gcm"

    # LLM Provider (AG-2)
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    anthropic_api_key: str = ""  # Phase 3, placeholder
    anthropic_model: str = "claude-3-5-sonnet-20241022"  # Phase 3

    # RAG Pipeline (ADR-017/020, Phase 2)
    reranker_enabled: bool = True  # Enable/disable reranking in RAG pipeline
    # Vector write-path (ADR-003 / ADR-020)
    vector_store_kind: str = "none"  # none | chroma | pgvector
    embedding_model: str = "text-embedding-3-small"
    embedding_provider: str = "openai"  # openai | none
    chroma_persist_dir: str = "./chroma_db"

    # Web Search (AG-5, Phase 2)
    tavily_api_key: str = ""
    tavily_search_depth: str = "basic"
    tavily_timeout_seconds: float = 10.0
    tavily_snippet_max_chars: int = 500

    model_config = {"env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def _validate_environment(self) -> "Settings":
        if self.environment not in {"dev", "staging", "prod"}:
            raise ValueError(
                f"ENVIRONMENT must be dev|staging|prod, got {self.environment!r}"
            )
        if self.environment == "prod" and not self.forensic_stream_enabled:
            raise ValueError(
                "FORENSIC_STREAM_ENABLED must be true in prod (privacy-first auditing)"
            )
        if self.operational_log_sink not in {"stdout", "loki", "elk"}:
            raise ValueError(
                f"OPERATIONAL_LOG_SINK must be stdout|loki|elk, got {self.operational_log_sink!r}"
            )
        if self.kms_provider not in {"vault", "local"}:
            raise ValueError(
                f"KMS_PROVIDER must be vault|local, got {self.kms_provider!r}"
            )
        if self.llm_provider not in {"openai", "anthropic", "ollama"}:
            raise ValueError(
                f"LLM_PROVIDER must be openai|anthropic|ollama, got {self.llm_provider!r}"
            )
        if self.llm_provider == "openai" and not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY required when LLM_PROVIDER=openai"
            )
        if self.tavily_search_depth not in {"basic", "advanced"}:
            raise ValueError(
                f"TAVILY_SEARCH_DEPTH must be basic|advanced, got {self.tavily_search_depth!r}"
            )
        if self.tavily_timeout_seconds <= 0:
            raise ValueError(
                f"TAVILY_TIMEOUT_SECONDS must be > 0, got {self.tavily_timeout_seconds!r}"
            )
        if self.tavily_snippet_max_chars <= 0:
            raise ValueError(
                f"TAVILY_SNIPPET_MAX_CHARS must be > 0, got {self.tavily_snippet_max_chars!r}"
            )
        if self.checkpoint_backend not in {"redis_postgres", "redis_only", "postgres_only"}:
            raise ValueError(
                f"CHECKPOINT_BACKEND must be redis_postgres|redis_only|postgres_only, got {self.checkpoint_backend!r}"
            )
        return self


settings: Settings


def __getattr__(name: str) -> object:
    """Build the ``settings`` singleton lazily (PEP 562).

    ``Settings`` validates fail-fast (e.g. a missing ``OPENAI_API_KEY``), so the
    singleton must not be constructed at import time — that would make every
    ``import llm_client.config`` fail, breaking unrelated components and the
    test suite. Instantiating on first attribute access keeps the fail-fast
    behaviour where it belongs: at application startup.
    """
    if name == "settings":
        global settings
        settings = Settings()
        return settings
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

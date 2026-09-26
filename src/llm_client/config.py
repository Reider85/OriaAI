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

    # MinIO / S3
    s3_endpoint: str = "http://127.0.0.1:9000"
    s3_access_key: str = "minioadmin"
    s3_secret_key: str = "minioadmin"
    s3_bucket: str = "llm-client-files"
    s3_forensic_bucket: str = "llm-client-forensic"

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

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    environment: str = "dev"
    storage_backend: str = "local"
    forensic_stream_enabled: bool = False
    pii_detector_enabled: bool = True
    cycle_detection_enabled: bool = True
    cycle_detection_threshold: float = 0.95

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

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
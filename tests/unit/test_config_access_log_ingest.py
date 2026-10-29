"""Configuration tests — S3 access log ingestor (Block E-4, BUG-MVP-03)."""

import pytest

from llm_client.config import Settings


def test_access_log_ingest_default_disabled():
    """Ingestor is opt-in: default flag is False (dev off)."""
    settings = Settings(access_log_ingest_enabled=False)
    assert settings.access_log_ingest_enabled is False


def test_access_log_defaults():
    """E-4 class defaults: off, allowlist service account, 5-minute poll, no webhook.

    Asserted via model_fields — .env in dev workspaces overrides instance values.
    """
    fields = Settings.model_fields
    assert fields["access_log_ingest_enabled"].default is False
    assert fields["s3_access_log_allowlist"].default == "llm-client-service"
    assert fields["access_log_poll_interval_seconds"].default == 300
    assert fields["security_alert_webhook_url"].default == ""


def test_access_log_ingest_requires_forensic_stream():
    """ACCESS_LOG_INGEST_ENABLED=true without forensic stream fails fast."""
    with pytest.raises(
        ValueError,
        match="ACCESS_LOG_INGEST_ENABLED requires FORENSIC_STREAM_ENABLED=true",
    ):
        Settings(access_log_ingest_enabled=True, forensic_stream_enabled=False)


def test_access_log_ingest_ok_with_forensic_stream():
    """Flag combination accepted when forensic stream is enabled."""
    settings = Settings(access_log_ingest_enabled=True, forensic_stream_enabled=True)
    assert settings.access_log_ingest_enabled is True
    assert settings.forensic_stream_enabled is True


def test_access_log_poll_interval_min_60():
    """E-4 anti-pattern: polling more often than every 60s is rejected."""
    with pytest.raises(
        ValueError,
        match="ACCESS_LOG_POLL_INTERVAL_SECONDS must be >= 60",
    ):
        Settings(
            forensic_stream_enabled=True,
            access_log_ingest_enabled=True,
            access_log_poll_interval_seconds=5,
        )


def test_access_log_poll_interval_from_env(monkeypatch):
    """ACCESS_LOG_POLL_INTERVAL_SECONDS env var is picked up."""
    monkeypatch.setenv("ACCESS_LOG_POLL_INTERVAL_SECONDS", "600")
    settings = Settings(access_log_ingest_enabled=False)
    assert settings.access_log_poll_interval_seconds == 600

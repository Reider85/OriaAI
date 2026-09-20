"""D-6 dev-mode toggle: forensic off in dev (no Vault), on in staging/prod (fails fast)."""


import pytest

from llm_client.config import Settings


def test_dev_defaults_off_forensic():
    s = Settings(environment="dev")
    assert s.forensic_stream_enabled is False


def test_dev_explicit_off():
    s = Settings(environment="dev", forensic_stream_enabled=False)
    assert not s.forensic_stream_enabled


def test_staging_forensic_on():
    s = Settings(environment="staging", forensic_stream_enabled=True)
    assert s.forensic_stream_enabled


def test_prod_requires_forensic_on():
    with pytest.raises(ValueError):
        Settings(environment="prod", forensic_stream_enabled=False)


@pytest.mark.asyncio
async def test_create_app_dev_mode_no_vault_dependency():
    """Dev-mode create_app must not attempt Vault/KMS init when forensic is off."""
    from llm_client.api import create_app

    settings = Settings(
        environment="dev",
        forensic_stream_enabled=False,
        kms_provider="vault",
    )
    app = create_app(redis_url="redis://127.0.0.1:6399/0", _settings=settings)
    assert app.state.forensic_writer is None
    assert app.state.operational_writer is not None
    assert app.state.pii_detector is not None


def test_settings_validates_environment():
    with pytest.raises(ValueError):
        Settings(environment="production")


# ---------------------------------------------------------------------------
# D-6 DoD: startup warning log test
# ---------------------------------------------------------------------------

def test_create_app_dev_logs_forensic_disabled_warning(caplog):
    """D-6: create_app in dev mode with forensic off must log a warning."""
    import logging

    from llm_client.api import create_app

    settings = Settings(environment="dev", forensic_stream_enabled=False, kms_provider="vault")
    with caplog.at_level(logging.WARNING):
        create_app(redis_url="redis://127.0.0.1:6399/0", _settings=settings)
    assert any("Forensic stream disabled" in r.message or "forensic" in r.message.lower() for r in caplog.records)


# ---------------------------------------------------------------------------
# D-6 DoD: PIIDetector actively masking in dev mode
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dev_mode_piidetector_actively_masks():
    """D-6: PIIDetector must be always enabled, even in dev mode, and must mask PII."""
    from llm_client.api import create_app

    settings = Settings(environment="dev", forensic_stream_enabled=False, kms_provider="vault")
    app = create_app(redis_url="redis://127.0.0.1:6399/0", _settings=settings)
    detector = app.state.pii_detector
    assert detector is not None
    assert detector.enabled is True
    # Masking must work
    masked = detector.mask("Email john@example.com sent by John Doe")
    assert "john@example.com" not in masked
    assert "John Doe" not in masked
    assert "[EMAIL]" in masked
    assert "[PERSON]" in masked


# ---------------------------------------------------------------------------
# D-6 DoD: staging/prod with forensic on requires Vault (fail-fast at init)
# ---------------------------------------------------------------------------

def test_staging_forensic_on_requires_vault():
    """D-6: staging + forensic_stream_enabled=True with unreachable Vault must fail fast."""
    from llm_client.observability.kms_provider import VaultTransitKeyProvider

    with pytest.raises(ConnectionError):
        VaultTransitKeyProvider("http://127.0.0.1:1", "nope")


# ---------------------------------------------------------------------------
# D-6 DoD: prod validation — cannot set forensic=False
# ---------------------------------------------------------------------------

def test_prod_forensic_false_rejected():
    """D-6: setting FORENSIC_STREAM_ENABLED=false in prod must be rejected."""
    with pytest.raises(ValueError, match="FORENSIC_STREAM_ENABLED"):
        Settings(environment="prod", forensic_stream_enabled=False)


# ---------------------------------------------------------------------------
# D-6 DoD: dev-mode app has all expected state
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dev_mode_app_state_has_operational_writer():
    """D-6: dev mode must have operational writer (always on) but no forensic writer."""
    from llm_client.api import create_app

    settings = Settings(environment="dev", forensic_stream_enabled=False, kms_provider="vault")
    app = create_app(redis_url="redis://127.0.0.1:6399/0", _settings=settings)
    assert app.state.operational_writer is not None
    assert app.state.forensic_writer is None
    assert app.state.pii_detector is not None
    assert app.state.pii_detector.enabled is True
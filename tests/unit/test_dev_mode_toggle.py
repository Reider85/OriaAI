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
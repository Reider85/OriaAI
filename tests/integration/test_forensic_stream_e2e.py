"""Integration test: Forensic stream end-to-end (Vault + MinIO + ForensicStreamWriter).

Tests the full forensic path: Settings with forensic enabled → Vault transit encryption → 
S3 forensic bucket upload → ForensicStreamWriter → decrypt roundtrip.

This exercises the real forensic path in staging/prod environments.
"""
import json
import os

import pytest

from llm_client.config import Settings
from llm_client.observability.forensic_writer import ForensicStreamWriter
from llm_client.observability.kms_provider import VaultTransitKeyProvider
from llm_client.storage.s3 import S3CompatibleStorage

pytestmark = [pytest.mark.integration]


@pytest.fixture
def settings_staging_forensic():
    """Settings with staging environment and forensic enabled."""
    # Use environment variables, fallback to defaults for CI
    original_env = os.environ.copy()
    os.environ.update({
        "ENVIRONMENT": "staging",
        "FORENSIC_STREAM_ENABLED": "true",
        "KMS_PROVIDER": "vault",
        "VAULT_ADDR": os.getenv("VAULT_ADDR", "http://127.0.0.1:8200"),
        "VAULT_TOKEN": os.getenv("VAULT_TOKEN", "root"),
        "VAULT_TRANSIT_KEY": os.getenv("VAULT_TRANSIT_KEY", "forensic-aes256-gcm"),
        "S3_ENDPOINT": os.getenv("S3_ENDPOINT", "http://127.0.0.1:9000"),
        "S3_ACCESS_KEY": os.getenv("S3_ACCESS_KEY", "minioadmin"),
        "S3_SECRET_KEY": os.getenv("S3_SECRET_KEY", "minioadmin"),
        "S3_FORENSIC_BUCKET": os.getenv("S3_FORENSIC_BUCKET", "llm-client-forensic"),
        "REDIS_URL": os.getenv("REDIS_URL", "redis://127.0.0.1:6380/0"),
        "OPENAI_API_KEY": "sk-test-placeholder",  # Required by Settings validation
    })
    
    try:
        settings = Settings()
        assert settings.environment == "staging"
        assert settings.forensic_stream_enabled == True
        assert settings.kms_provider == "vault"
        return settings
    finally:
        os.environ.clear()
        os.environ.update(original_env)


@pytest.fixture
async def vault_provider(settings_staging_forensic):
    """Vault KMS provider (may skip if Vault unavailable)."""
    try:
        provider = VaultTransitKeyProvider(
            settings_staging_forensic.vault_addr,
            settings_staging_forensic.vault_token,
            settings_staging_forensic.vault_transit_key,
        )
        # Test connectivity by encrypting a small payload
        await provider.encrypt(b"test")
        return provider
    except (ConnectionError, OSError) as exc:
        pytest.skip(f"Vault not available or not configured: {exc}")


@pytest.fixture
async def s3_storage(settings_staging_forensic):
    """S3 storage for forensic bucket (may skip if bucket not found)."""
    try:
        storage = S3CompatibleStorage(
            endpoint=settings_staging_forensic.s3_endpoint,
            access_key=settings_staging_forensic.s3_access_key,
            secret_key=settings_staging_forensic.s3_secret_key,
            bucket=settings_staging_forensic.s3_forensic_bucket,
        )
        # Test connectivity by listing bucket (may be empty)
        await storage.list_objects(prefix="forensic/")
        return storage
    except (ConnectionError, OSError) as exc:
        pytest.skip(f"S3 forensic bucket not available: {exc}")


@pytest.mark.asyncio
async def test_forensic_write_encrypt_upload_decrypt(vault_provider, s3_storage, settings_staging_forensic):
    """Full forensic path: write → encrypt → upload → fetch → decrypt → validate."""
    # Create forensic writer with real Vault and S3
    writer = ForensicStreamWriter(
        kms_provider=vault_provider,
        s3_client=s3_storage,
        bucket=settings_staging_forensic.s3_forensic_bucket,
        enabled=True,
    )
    
    # Test event data (typical cancel event)
    test_event = {
        "event_type": "session_cancelled",
        "session_id": "test-session-123",
        "user_id": "user-full",
        "reason": "user_cancelled",
        "timestamp": "2026-10-02T00:00:00Z",
        "partial_answer_size_bytes": 1234,
        "last_node_executed": "final_answer",
        "messages_count": 5,
        "duration_ms": 4500,
        "trace_id": "trace-abc-123",
    }
    
    # Write event (should encrypt and upload)
    await writer.start()
    try:
        await writer.write(test_event)
        await writer.flush()  # Ensure write completes
        
        # Verify object exists in forensic bucket
        objects = await s3_storage.list_objects(prefix="forensic/")
        assert len(objects) >= 1
        
        # Get the forensic object (should be encrypted envelope)
        object_key = objects[0]  # Take first forensic object
        stored_data = await s3_storage.get(object_key)
        
        # Parse envelope
        envelope = json.loads(stored_data)
        assert "ciphertext" in envelope
        assert "iv" in envelope
        assert "key_id" in envelope
        assert envelope["algorithm"] == "AES-256-GCM"
        assert envelope["key_id"].startswith("forensic-aes256-gcm:v")
        
        # Decrypt and verify original event
        payload = type(
            "Payload",
            (),
            {
                "ciphertext": bytes.fromhex(envelope["ciphertext"]),
                "iv": bytes.fromhex(envelope["iv"]),
                "key_id": envelope["key_id"],
                "algorithm": envelope["algorithm"],
            },
        )()
        
        decrypted_data = await vault_provider.decrypt(payload)
        decrypted_event = json.loads(decrypted_data)
        
        # Verify roundtrip
        assert decrypted_event == test_event
        assert decrypted_event["event_type"] == "session_cancelled"
        assert decrypted_event["session_id"] == "test-session-123"
        
    finally:
        await writer.close()


@pytest.mark.asyncio
async def test_forensic_writer_enabled_flag_from_settings(settings_staging_forensic):
    """Verify Settings properly configures forensic writer enabled state."""
    # Test that settings correctly enable forensic path
    assert settings_staging_forensic.forensic_stream_enabled == True
    assert settings_staging_forensic.kms_provider == "vault"
    assert settings_staging_forensic.environment == "staging"
    
    # Verify forensic bucket name is set
    assert settings_staging_forensic.s3_forensic_bucket == "llm-client-forensic"
    assert settings_staging_forensic.vault_transit_key == "forensic-aes256-gcm"


def test_staging_settings_validation():
    """Test that staging environment + forensic enabled loads without error."""
    original_env = os.environ.copy()
    os.environ.update({
        "ENVIRONMENT": "staging",
        "FORENSIC_STREAM_ENABLED": "true",
        "KMS_PROVIDER": "vault",
        "VAULT_ADDR": "http://127.0.0.1:8200",
        "VAULT_TOKEN": "root",
        "VAULT_TRANSIT_KEY": "forensic-aes256-gcm",
        "S3_FORENSIC_BUCKET": "llm-client-forensic",
        "REDIS_URL": "redis://127.0.0.1:6380/0",
        "OPENAI_API_KEY": "sk-test-placeholder",
    })
    
    try:
        settings = Settings()
        # Should not raise exception
        assert settings.environment == "staging"
        assert settings.forensic_stream_enabled == True
        assert settings.kms_provider == "vault"
    finally:
        os.environ.clear()
        os.environ.update(original_env)
import pytest

from llm_client.observability.kms_provider import (
    EncryptedPayload,
    LocalDevKeyProvider,
    VaultTransitKeyProvider,
)


@pytest.mark.asyncio
async def test_local_key_provider_roundtrip():
    provider = LocalDevKeyProvider()
    payload = await provider.encrypt(b"secret payload", context={"session_id": "s1"})
    assert isinstance(payload, EncryptedPayload)
    assert payload.algorithm == "AES-256-GCM"
    assert len(payload.iv) == 12
    plain = await provider.decrypt(payload)
    assert plain == b"secret payload"


@pytest.mark.asyncio
async def test_local_key_provider_unique_iv():
    provider = LocalDevKeyProvider()
    p1 = await provider.encrypt(b"data")
    p2 = await provider.encrypt(b"data")
    assert p1.iv != p2.iv
    assert p1.ciphertext != p2.ciphertext


@pytest.mark.asyncio
async def test_local_key_provider_decrypt_garbage_raises():
    from cryptography.exceptions import InvalidTag

    provider = LocalDevKeyProvider()
    payload = await provider.encrypt(b"data")
    bad = EncryptedPayload(
        ciphertext=b"\x00" * len(payload.ciphertext),
        iv=payload.iv,
        key_id=payload.key_id,
    )
    with pytest.raises(InvalidTag):
        await provider.decrypt(bad)


def test_local_key_provider_rejects_rotate():
    provider = LocalDevKeyProvider()
    with pytest.raises(NotImplementedError):
        import asyncio

        asyncio.run(provider.rotate_key())


def test_vault_provider_init_requires_running_vault():
    # Without a reachable Vault the constructor must fail fast (ADR-014 D-4 DoD).
    with pytest.raises(ConnectionError):
        VaultTransitKeyProvider("http://127.0.0.1:1", "nope")


# ---------------------------------------------------------------------------
# D-4 DoD: EncryptedPayload schema assertion
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_encrypted_payload_schema():
    """EncryptedPayload must have ciphertext (bytes), iv (12 bytes), key_id (str), algorithm='AES-256-GCM'."""
    provider = LocalDevKeyProvider()
    payload = await provider.encrypt(b"test data")
    assert isinstance(payload, EncryptedPayload)
    assert isinstance(payload.ciphertext, bytes)
    assert len(payload.ciphertext) > 0
    assert isinstance(payload.iv, bytes)
    assert len(payload.iv) == 12, f"IV must be 12 bytes for GCM, got {len(payload.iv)}"
    assert isinstance(payload.key_id, str)
    assert len(payload.key_id) > 0
    assert payload.algorithm == "AES-256-GCM"


@pytest.mark.asyncio
async def test_encrypt_deterministic_different_results():
    """Encrypting the same data twice must yield different ciphertexts (unique IV)."""
    provider = LocalDevKeyProvider()
    p1 = await provider.encrypt(b"identical input")
    p2 = await provider.encrypt(b"identical input")
    assert p1.ciphertext != p2.ciphertext
    assert p1.iv != p2.iv
    # But both must decrypt to the same value.
    assert await provider.decrypt(p1) == b"identical input"
    assert await provider.decrypt(p2) == b"identical input"


@pytest.mark.asyncio
async def test_decrypt_with_wrong_key_fails():
    """Decrypting with a different key must fail (InvalidTag)."""
    from cryptography.exceptions import InvalidTag

    p1 = LocalDevKeyProvider()
    p2 = LocalDevKeyProvider()
    payload = await p1.encrypt(b"secret")
    with pytest.raises(InvalidTag):
        await p2.decrypt(payload)
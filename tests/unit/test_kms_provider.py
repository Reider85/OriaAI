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
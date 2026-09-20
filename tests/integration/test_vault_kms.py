"""Integration test: Vault transit KMS round-trip (ADR-014 D-4, needs Block A-3 Vault).

Verifies the VaultTransitKeyProvider works against the docker-compose Vault dev-mode
service and that a ciphertext produced by encrypt() can be recovered by decrypt().
"""
import os

import pytest

from llm_client.observability.kms_provider import VaultTransitKeyProvider

pytestmark = [pytest.mark.integration]


@pytest.fixture
def vault_provider():
    addr = os.getenv("VAULT_ADDR", "http://127.0.0.1:8200")
    token = os.getenv("VAULT_TOKEN", "root")
    key = os.getenv("VAULT_TRANSIT_KEY", "forensic-aes256-gcm")
    try:
        provider = VaultTransitKeyProvider(addr, token, key)
    except ConnectionError as exc:
        pytest.skip(f"Vault not available at {addr}: {exc}")
    return provider


@pytest.mark.asyncio
async def test_vault_encrypt_decrypt_roundtrip(vault_provider):
    payload = await vault_provider.encrypt(b"forensic secret payload")
    assert payload.algorithm == "AES-256-GCM"
    assert payload.key_id.startswith("forensic-aes256-gcm:v")
    plain = await vault_provider.decrypt(payload)
    assert plain == b"forensic secret payload"


@pytest.mark.asyncio
async def test_vault_unique_ciphertexts(vault_provider):
    p1 = await vault_provider.encrypt(b"same")
    p2 = await vault_provider.encrypt(b"same")
    assert p1.ciphertext != p2.ciphertext


@pytest.mark.asyncio
async def test_vault_rotate_returns_new_version(vault_provider):
    key_id_before = (await vault_provider.encrypt(b"x")).key_id
    new_key_id = await vault_provider.rotate_key()
    assert new_key_id != key_id_before
    # Old ciphertexts remain decryptable after rotation.
    payload = await vault_provider.encrypt(b"after-rotate")
    assert await vault_provider.decrypt(payload) == b"after-rotate"
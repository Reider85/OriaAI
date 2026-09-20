"""KMS KeyProvider abstraction for AES-256-GCM forensic encryption (ADR-014, D-4).

- ``KMSKeyProvider`` is the interface (encrypt/decrypt/rotate_key) that Phase 5 can
  re-implement for AWS KMS / GCP KMS.
- ``VaultTransitKeyProvider`` talks to the local Vault dev-mode transit engine
  (Block A-3). Keys never live in the application or env vars.
- ``LocalDevKeyProvider`` is a test-only in-memory AES-256-GCM implementation that
  raises if used outside a pytest context.

Vault transit engine returns a base64 ``plaintext``/``ciphertext`` body; we map it
to ``EncryptedPayload`` so callers only ever touch bytes and a ``key_id``.
"""
import asyncio
import base64
import logging
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EncryptedPayload:
    """Encrypted forensic record envelope written to the forensic S3 bucket."""

    ciphertext: bytes
    iv: bytes
    key_id: str
    algorithm: str = "AES-256-GCM"


class KMSKeyProvider(ABC):
    """Port for symmetric-key encryption of forensic records."""

    @abstractmethod
    async def encrypt(self, plaintext: bytes, context: dict | None = None) -> EncryptedPayload:
        """Encrypt ``plaintext`` and return an EncryptedPayload envelope."""

    @abstractmethod
    async def decrypt(self, payload: EncryptedPayload, context: dict | None = None) -> bytes:
        """Decrypt ``payload`` back to plaintext bytes."""

    @abstractmethod
    async def rotate_key(self) -> str:
        """Rotate the key; returns the new key_id. Old ciphertexts stay decryptable."""


class VaultTransitKeyProvider(KMSKeyProvider):
    """Transit-engine key provider backed by HashiCorp Vault (Block A-3 / ADR-014)."""

    def __init__(self, addr: str, token: str, key_name: str = "forensic-aes256-gcm") -> None:
        import hvac  # type: ignore[import-untyped]

        self._client = hvac.Client(url=addr, token=token)
        try:
            ready = self._client.is_authenticated() and self._client.sys.is_initialized()
        except Exception as exc:
            raise ConnectionError(f"Vault not reachable at {addr}") from exc
        if not ready:
            raise ConnectionError(f"Vault not ready at {addr} — cannot initialize KMSKeyProvider")
        self._key_name = key_name

    async def encrypt(
        self, plaintext: bytes, context: dict | None = None
    ) -> EncryptedPayload:
        b64 = base64.b64encode(plaintext).decode("ascii")
        resp = await asyncio.to_thread(
            self._client.secrets.transit.encrypt_data, name=self._key_name, plaintext=b64
        )
        data = resp["data"]
        ciphertext = data["ciphertext"]
        key_version = data.get("key_version", 1)
        return EncryptedPayload(
            ciphertext=ciphertext.encode("ascii"),
            iv=b"",
            key_id=f"{self._key_name}:v{key_version}",
            algorithm="AES-256-GCM",
        )

    async def decrypt(
        self, payload: EncryptedPayload, context: dict | None = None
    ) -> bytes:
        resp = await asyncio.to_thread(
            self._client.secrets.transit.decrypt_data,
            name=self._key_name,
            ciphertext=payload.ciphertext.decode("ascii"),
        )
        b64_plain = resp["data"]["plaintext"]
        return base64.b64decode(b64_plain)

    async def rotate_key(self) -> str:
        await asyncio.to_thread(self._client.secrets.transit.rotate_key, name=self._key_name)
        key = await asyncio.to_thread(self._client.secrets.transit.read_key, name=self._key_name)
        versions = key["data"]["keys"]
        latest = max(int(v) for v in versions)
        return f"{self._key_name}:v{latest}"


class LocalDevKeyProvider(KMSKeyProvider):
    """TEST-ONLY in-memory AES-256-GCM provider. For unit tests only; never for runtime.

    Raises RuntimeError unless instantiated inside a pytest run so it can never leak
    into the dev/staging/prod runtime as a silent fallback.
    """

    def __init__(self) -> None:
        if not _in_pytest():
            raise RuntimeError(
                "LocalDevKeyProvider is TEST ONLY. Use KMS_PROVIDER=vault in runtime."
            )
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        self._key = AESGCM.generate_key(bit_length=256)
        self._aesgcm = AESGCM(self._key)
        self._key_id = f"local-test:{uuid.uuid4().hex[:8]}"
        logger.warning("USING LOCAL KEY — TEST ONLY")

    async def encrypt(
        self, plaintext: bytes, context: dict | None = None
    ) -> EncryptedPayload:
        iv = os.urandom(12)
        ciphertext = await asyncio.to_thread(self._aesgcm.encrypt, iv, plaintext, None)
        return EncryptedPayload(
            ciphertext=ciphertext,
            iv=iv,
            key_id=self._key_id,
            algorithm="AES-256-GCM",
        )

    async def decrypt(
        self, payload: EncryptedPayload, context: dict | None = None
    ) -> bytes:
        return await asyncio.to_thread(
            self._aesgcm.decrypt, payload.iv, payload.ciphertext, None
        )

    async def rotate_key(self) -> str:
        raise NotImplementedError("LocalDevKeyProvider has no key rotation semantics")


def _in_pytest() -> bool:
    import sys

    return "pytest" in sys.modules or os.environ.get("PYTEST_CURRENT_TEST") is not None
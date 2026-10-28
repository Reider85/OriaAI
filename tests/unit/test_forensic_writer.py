import json

import pytest

from llm_client.observability.forensic_writer import (
    ForensicStreamWriter,
    ForensicWriteError,
    build_forensic_writer,
)
from llm_client.observability.kms_provider import LocalDevKeyProvider
from llm_client.storage.base import FileStorage


class InMemoryS3(FileStorage):
    """Minimal async fake S3 storing objects in a dict."""

    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.writes: list[str] = []

    async def save(self, file: bytes | object, key: str) -> str:
        body = file if isinstance(file, bytes) else b"".join(file)  # type: ignore[arg-type]
        self.objects[key] = body
        self.writes.append(key)
        return key

    async def get(self, key: str) -> bytes:
        return self.objects[key]

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self.objects


@pytest.fixture
def kms():
    return LocalDevKeyProvider()


@pytest.fixture
def s3():
    return InMemoryS3()


@pytest.mark.asyncio
async def test_write_encrypts_and_stores(kms, s3):
    w = ForensicStreamWriter(kms, s3, bucket="llm-client-forensic", enabled=True)
    await w.start()
    try:
        await w.write(
            {
                "event_type": "session_cancelled",
                "session_id": "sess-1",
                "user_id": "u-full",
                "reason": "user_cancelled",
                "timestamp": "2026-09-20T00:00:00Z",
                "partial_answer_size_bytes": 123,
                "last_node_executed": "final_answer",
                "messages_count": 4,
                "duration_ms": 3500,
            }
        )
        await w.flush()
        assert len(s3.objects) == 1
        key = next(iter(s3.objects))
        assert key.startswith("forensic/")
        assert "sess-1" in key
        stored = json.loads(s3.objects[key])
        # Stored record is the encrypted envelope, NOT plaintext.
        assert "ciphertext" in stored
        assert "iv" in stored
        assert "key_id" in stored
        assert stored["algorithm"] == "AES-256-GCM"
        assert "event_type" not in stored
    finally:
        await w.close()


@pytest.mark.asyncio
async def test_write_roundtrip_via_kms_decrypt(kms, s3):
    w = ForensicStreamWriter(kms, s3, enabled=True)
    event = {"event_type": "session_cancelled", "session_id": "s1", "reason": "timeout"}
    await w.start()
    try:
        await w.write(event)
        await w.flush()
        key = next(iter(s3.objects))
        stored = json.loads(s3.objects[key])
        payload = type(
            "P",
            (),
            {
                "ciphertext": bytes.fromhex(stored["ciphertext"]),
                "iv": bytes.fromhex(stored["iv"]),
                "key_id": stored["key_id"],
                "algorithm": stored["algorithm"],
            },
        )()
        plain = json.loads(await kms.decrypt(payload))
        assert plain == event
    finally:
        await w.close()


@pytest.mark.asyncio
async def test_disabled_writer_is_noop(s3):
    w = ForensicStreamWriter(LocalDevKeyProvider(), s3, enabled=False)
    await w.start()
    try:
        await w.write({"event_type": "x", "session_id": "s1"})
        await w.flush()
        assert s3.objects == {}
    finally:
        await w.close()


@pytest.mark.asyncio
async def test_batch_flush_on_size(kms, s3):
    w = ForensicStreamWriter(kms, s3, enabled=True, max_batch_size=2)
    await w.start()
    try:
        for i in range(2):
            await w.write({"event_type": "e", "session_id": f"s{i}"})
        assert len(s3.objects) == 2
    finally:
        await w.close()


@pytest.mark.asyncio
async def test_encryption_failure_raises_forensic_error(s3):
    class BrokenKMS:
        async def encrypt(self, plaintext, context=None):
            raise RuntimeError("kms down")

        async def decrypt(self, payload, context=None):
            raise NotImplementedError

        async def rotate_key(self):
            raise NotImplementedError

    w = ForensicStreamWriter(BrokenKMS(), s3, enabled=True, max_batch_size=1)
    with pytest.raises(ForensicWriteError):
        await w.write({"event_type": "e", "session_id": "s1"})
    await w.close()


@pytest.mark.asyncio
async def test_key_path_in_record(kms, s3):
    w = ForensicStreamWriter(kms, s3, enabled=True)
    await w.start()
    try:
        await w.write({"event_type": "e", "session_id": "s9"})
        await w.flush()
        key = next(iter(s3.objects))
        stored = json.loads(s3.objects[key])
        assert stored["key_path"] == key
    finally:
        await w.close()


# ---------------------------------------------------------------------------
# D-3 DoD: flush-interval test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_flush_interval_flushes(kms, s3):
    """Timer-based flush fires within flush_interval_ms."""
    import asyncio

    w = ForensicStreamWriter(kms, s3, enabled=True, flush_interval_ms=50, max_batch_size=100)
    await w.start()
    try:
        await w.write({"event_type": "timer", "session_id": "t1"})
        # Wait for the flush loop to fire at least once.
        deadline = asyncio.get_event_loop().time() + 1.0
        while asyncio.get_event_loop().time() < deadline and not s3.objects:
            await asyncio.sleep(0.02)
        assert len(s3.objects) == 1
    finally:
        await w.close()


# ---------------------------------------------------------------------------
# D-3 DoD: S3 key format full validation
# ---------------------------------------------------------------------------

import re

_KEY_PATTERN = re.compile(r"^forensic/\d{4}/\d{2}/\d{2}/[^/]+/\d{8}T\d{6}Z-[0-9a-f]{8}\.json$")


@pytest.mark.asyncio
async def test_s3_key_format_matches_spec(kms, s3):
    """Object key must match forensic/YYYY/MM/DD/{session_id}/{timestamp}-{uuid}.json."""
    w = ForensicStreamWriter(kms, s3, enabled=True)
    await w.start()
    try:
        await w.write({"event_type": "format_check", "session_id": "sess-42"})
        await w.flush()
        key = next(iter(s3.objects))
        assert _KEY_PATTERN.match(key), f"Key does not match spec: {key}"
        assert "sess-42" in key
    finally:
        await w.close()


# ---------------------------------------------------------------------------
# D-3 DoD: EncryptedEnvelope structure assertion
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_encrypted_envelope_fields(kms, s3):
    """Stored record must contain ciphertext, iv, key_id, algorithm, key_path."""
    w = ForensicStreamWriter(kms, s3, enabled=True)
    await w.start()
    try:
        await w.write({"event_type": "schema", "session_id": "s-schema"})
        await w.flush()
        stored = json.loads(s3.objects[next(iter(s3.objects))])
        required_fields = {"ciphertext", "iv", "key_id", "algorithm", "key_path"}
        assert required_fields.issubset(set(stored.keys())), (
            f"Missing fields: {required_fields - set(stored.keys())}"
        )
        assert stored["algorithm"] == "AES-256-GCM"
        # iv must be hex-encoded 12 bytes = 24 hex chars
        assert len(stored["iv"]) == 24
        assert stored["key_id"]  # non-empty
    finally:
        await w.close()


# ---------------------------------------------------------------------------
# D-3 DoD: startup warning when disabled
# ---------------------------------------------------------------------------


def test_disabled_writer_logs_warning(caplog):
    import logging

    with caplog.at_level(logging.WARNING, logger="llm_client.observability.forensic_writer"):
        ForensicStreamWriter(LocalDevKeyProvider(), InMemoryS3(), enabled=False)
    assert any("Forensic stream disabled" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# D-3 DoD: multiple events batch correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_multiple_events_produce_separate_objects(kms, s3):
    w = ForensicStreamWriter(kms, s3, enabled=True, max_batch_size=10)
    await w.start()
    try:
        for i in range(5):
            await w.write({"event_type": f"e{i}", "session_id": f"s{i}"})
        await w.flush()
        assert len(s3.objects) == 5
        # Each key is unique (different uuid)
        keys = list(s3.objects.keys())
        assert len(set(keys)) == 5
    finally:
        await w.close()


# ---------------------------------------------------------------------------
# BUG-MVP-01: forensic writes must target S3_FORENSIC_BUCKET (ADR-014)
# ---------------------------------------------------------------------------

from types import SimpleNamespace

from llm_client.storage.s3 import S3CompatibleStorage


def _forensic_settings(**overrides) -> SimpleNamespace:
    base = {
        "s3_endpoint": "http://127.0.0.1:9000",
        "s3_access_key": "minioadmin",
        "s3_secret_key": "minioadmin",
        "s3_bucket": "llm-client-files",
        "s3_forensic_bucket": "llm-client-forensic",
        "forensic_stream_enabled": True,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_builder_targets_forensic_bucket_not_env_default(monkeypatch):
    """Production build path scopes storage to S3_FORENSIC_BUCKET, not S3_BUCKET."""
    monkeypatch.setenv("S3_BUCKET", "llm-client-files")
    w = build_forensic_writer(_forensic_settings(), LocalDevKeyProvider())
    assert isinstance(w._s3, S3CompatibleStorage)
    assert w._s3._bucket == "llm-client-forensic"
    assert w._bucket == "llm-client-forensic"
    assert w._s3._bucket != "llm-client-files"


def test_builder_accepts_injected_storage(kms, s3):
    """s3_client override (tests / special wiring) still works."""
    w = build_forensic_writer(_forensic_settings(), kms, s3)
    assert w._s3 is s3


@pytest.mark.asyncio
async def test_forensic_writer_writes_to_correct_bucket(kms, monkeypatch):
    """After put(), the object targets llm-client-forensic, NOT llm-client-files."""
    captured: dict[str, str] = {}
    monkeypatch.setenv("S3_BUCKET", "llm-client-files")

    async def fake_save(self, file, key, metadata=None):
        captured["bucket"] = self._bucket
        captured["key"] = key
        return key

    monkeypatch.setattr(S3CompatibleStorage, "save", fake_save)

    w = build_forensic_writer(_forensic_settings(), kms)
    await w.start()
    try:
        await w.write({"event_type": "session_cancelled", "session_id": "sess-b1"})
        await w.flush()
    finally:
        await w.close()

    assert captured, "no S3 save happened"
    assert captured["bucket"] == "llm-client-forensic"
    assert captured["bucket"] != "llm-client-files"
    assert captured["key"].startswith("forensic/")
    assert "sess-b1" in captured["key"]


@pytest.mark.asyncio
async def test_flush_error_reports_target_bucket(kms, monkeypatch):
    """S3 failures name the forensic bucket (self._bucket is actually used)."""

    async def failing_save(self, file, key, metadata=None):
        raise RuntimeError("s3 down")

    monkeypatch.setattr(S3CompatibleStorage, "save", failing_save)

    w = build_forensic_writer(_forensic_settings(), kms)
    await w.start()
    try:
        await w.write({"event_type": "e", "session_id": "s-err"})
        with pytest.raises(ForensicWriteError, match=r"bucket=llm-client-forensic"):
            await w.flush()
    finally:
        await w.close()

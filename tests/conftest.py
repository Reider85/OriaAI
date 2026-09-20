"""Shared test fixtures for all test levels (unit + integration)."""

import pytest

from llm_client.observability.kms_provider import LocalDevKeyProvider
from llm_client.security.pii_detector import PIIDetector
from llm_client.storage.base import FileStorage


class InMemoryFileStorage(FileStorage):
    """Test double. Do not use in production."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}

    async def save(self, file: bytes | object, key: str) -> str:  # type: ignore[override]
        body = file if isinstance(file, bytes) else b"".join(file)  # type: ignore[arg-type]
        self._store[key] = body
        return key

    async def get(self, key: str) -> bytes:
        return self._store[key]

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)

    async def exists(self, key: str) -> bool:
        return key in self._store

    async def get_stream(self, key: str):  # type: ignore[override]
        data = self._store[key]
        yield data

    async def list(self, prefix: str = "") -> list[str]:  # type: ignore[override]
        return [k for k in self._store if k.startswith(prefix)]

    def clear(self) -> None:
        self._store.clear()


class CapturingSink:
    """LogSink that records events so tests can inspect them."""

    def __init__(self) -> None:
        self.records: list[str] = []

    async def write_batch(self, events: list[str]) -> None:
        self.records.extend(events)


@pytest.fixture(scope="session")
def pii_detector():
    """Module-level PIIDetector with spaCy model loaded once per session."""
    return PIIDetector(spacy_model="en_core_web_md", enabled=True)


@pytest.fixture(scope="session")
def disabled_pii_detector():
    return PIIDetector(spacy_model="en_core_web_md", enabled=False)


@pytest.fixture
def kms_provider():
    return LocalDevKeyProvider()


@pytest.fixture
def file_storage():
    return InMemoryFileStorage()


@pytest.fixture
def capturing_sink():
    return CapturingSink()

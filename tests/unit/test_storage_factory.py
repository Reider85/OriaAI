
from llm_client.storage.factory import create_file_storage
from llm_client.storage.local import LocalFileStorage
from llm_client.storage.s3 import S3CompatibleStorage


def test_factory_defaults_to_local(monkeypatch):
    monkeypatch.delenv("STORAGE_BACKEND", raising=False)
    assert isinstance(create_file_storage(), LocalFileStorage)


def test_factory_s3_backend(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    assert isinstance(create_file_storage(), S3CompatibleStorage)


def test_factory_explicit_local(monkeypatch):
    monkeypatch.setenv("STORAGE_BACKEND", "s3")
    assert isinstance(create_file_storage("local"), LocalFileStorage)


def test_factory_explicit_s3():
    assert isinstance(create_file_storage("s3"), S3CompatibleStorage)
from llm_client.storage.factory import create_file_storage
from llm_client.storage.s3 import S3CompatibleStorage


def test_factory_returns_s3():
    assert isinstance(create_file_storage(), S3CompatibleStorage)
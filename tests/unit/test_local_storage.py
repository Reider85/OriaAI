import pytest

from llm_client.storage.local import LocalFileStorage


@pytest.fixture
def storage(tmp_path):
    return LocalFileStorage(base_dir=str(tmp_path))


@pytest.mark.asyncio
async def test_save_get_delete_roundtrip(storage):
    saved = await storage.save(b"hello world", "test/hello.txt")
    assert saved == "test/hello.txt"
    assert await storage.exists("test/hello.txt")
    assert await storage.get("test/hello.txt") == b"hello world"
    await storage.delete("test/hello.txt")
    assert not await storage.exists("test/hello.txt")


@pytest.mark.asyncio
async def test_delete_missing_is_idempotent(storage):
    await storage.delete("nonexistent.txt")


@pytest.mark.asyncio
async def test_get_stream(storage):
    data = b"x" * 131072
    await storage.save(data, "big.bin")
    collected = b"".join([chunk async for chunk in storage.get_stream("big.bin")])
    assert collected == data


@pytest.mark.asyncio
async def test_list_prefix(storage):
    await storage.save(b"1", "a/one.txt")
    await storage.save(b"2", "a/two.txt")
    await storage.save(b"3", "b/three.txt")
    keys = await storage.list("a/")
    assert sorted(keys) == ["a/one.txt", "a/two.txt"]


@pytest.mark.asyncio
async def test_get_missing_raises(storage):
    with pytest.raises(FileNotFoundError):
        await storage.get("missing.bin")
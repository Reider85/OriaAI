"""Unit tests for vector store factory write-path helpers."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError, SecretStr

from llm_client.config import Settings
from llm_client.rag.retrieval.vector_store_factory import (
    _config_get,
    create_embedding_function,
    create_vector_retriever,
    create_vector_store,
    get_vector_writer,
)


def _settings(**overrides) -> Settings:
    base = {
        "environment": "dev",
        "openai_api_key": "sk-test",
        "llm_provider": "openai",
        "vector_store_kind": "none",
        "embedding_provider": "openai",
        "embedding_model": "text-embedding-3-small",
        "chroma_persist_dir": "./chroma_db",
        "database_url": "postgresql+asyncpg://postgres:postgres@localhost:5432/llm_client",
    }
    base.update(overrides)
    return Settings(**base)


def test_config_get_dict_and_object():
    assert _config_get({"a": 1}, "a") == 1
    assert _config_get({"a": 1}, "b", 2) == 2
    obj = SimpleNamespace(a=3)
    assert _config_get(obj, "a") == 3
    assert _config_get(None, "a", 9) == 9


def test_embedding_function_none_provider():
    settings = _settings(embedding_provider="none")
    assert create_embedding_function(settings) is None


def test_embedding_function_missing_key():
    settings = _settings(
        openai_api_key="",
        embedding_provider="openai",
        llm_provider="ollama",
    )
    # Should fallback to local embeddings when cloud API key is missing
    result = create_embedding_function(settings)
    assert result is not None
    # Should be a local embeddings instance
    from llm_client.rag.retrieval.local_embeddings import LocalSentenceTransformerEmbeddings
    assert isinstance(result, LocalSentenceTransformerEmbeddings)


def test_create_vector_store_none():
    settings = _settings(vector_store_kind="none")
    assert create_vector_store(settings=settings) is None


def test_create_vector_store_unknown_kind():
    settings = _settings(vector_store_kind="qdrant-not-wired")
    with patch.dict("os.environ", {"VECTOR_STORE_KIND": "qdrant-not-wired"}):
        assert create_vector_store(settings=settings) is None


def test_create_vector_store_chroma_import_error():
    settings = _settings(vector_store_kind="chroma")
    with (
        patch.dict("os.environ", {"VECTOR_STORE_KIND": "chroma"}),
        patch("builtins.__import__", side_effect=ImportError("no chromadb")),
    ):
        assert create_vector_store(settings=settings) is None


def test_create_vector_retriever_respects_config_search_type():
    store = MagicMock()
    store.as_retriever.return_value = "retriever"
    config = {"vector_search_type": "similarity", "vector_top_k": 7}

    with patch(
        "llm_client.rag.retrieval.vector_store_factory.create_vector_store",
        return_value=store,
    ):
        result = create_vector_retriever(config, settings=_settings())

    assert result == "retriever"
    store.as_retriever.assert_called_once_with(search_type="similarity", k=7)


def test_get_vector_writer_returns_none_when_store_disabled():
    settings = _settings(vector_store_kind="none")
    assert get_vector_writer(settings) is None


def test_get_vector_writer_builds_callable():
    import asyncio

    store = MagicMock()

    async def fake_aadd_texts(texts, metadatas=None, ids=None):
        store._written = (texts, metadatas, ids)

    store.aadd_texts = fake_aadd_texts

    try:
        import langchain_text_splitters  # noqa: F401
    except ImportError:
        pytest.skip("langchain text splitter not installed")

    settings = _settings(vector_store_kind="chroma")
    with patch(
        "llm_client.rag.retrieval.vector_store_factory.create_vector_store",
        return_value=store,
    ):
        writer = get_vector_writer(settings)

    assert writer is not None

    from llm_client.rag.indexing.models import Document

    doc = Document(
        id="d1",
        user_id="u1",
        source_type="file",
        content="word " * 500,
    )

    # Create a new event loop for the test
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(writer(doc))
        texts, metadatas, ids = store._written
        assert len(texts) >= 1
        assert metadatas[0]["document_id"] == "d1"
        assert ids[0] == "d1:0"
    finally:
        loop.close()


def test_create_embedding_function_custom_openai():
        settings = _settings(
            embedding_provider="custom-openai",
            custom_openai_api_key="sk-custom",
            custom_openai_base_url="https://api.custom.com/v1",
            custom_openai_model="custom-embedding-model",
        )
        
        with patch("langchain_openai.OpenAIEmbeddings") as mock_embeddings:
            result = create_embedding_function(settings)
            assert result is not None
            mock_embeddings.assert_called_once_with(
                model="custom-embedding-model",
                api_key=SecretStr("sk-custom"),
                base_url="https://api.custom.com/v1",
            )


def test_create_embedding_function_custom_openai_missing_key():
        settings = _settings(
            embedding_provider="custom-openai",
            custom_openai_api_key="",
            custom_openai_base_url="https://api.custom.com/v1",
        )
        # Should fallback to local embeddings when custom-openai API key is missing
        result = create_embedding_function(settings)
        assert result is not None
        from llm_client.rag.retrieval.local_embeddings import LocalSentenceTransformerEmbeddings
        assert isinstance(result, LocalSentenceTransformerEmbeddings)


def test_create_embedding_function_custom_openai_missing_base_url():
        settings = _settings(
            embedding_provider="custom-openai",
            custom_openai_api_key="sk-custom",
            custom_openai_base_url="",
        )
        # Should fallback to local embeddings when custom-openai base URL is missing
        result = create_embedding_function(settings)
        assert result is not None
        from llm_client.rag.retrieval.local_embeddings import LocalSentenceTransformerEmbeddings
        assert isinstance(result, LocalSentenceTransformerEmbeddings)


def test_create_embedding_function_zai():
    settings = _settings(
        embedding_provider="zai",
        zai_api_key="sk-zai",
        zai_base_url="https://api.z.ai/api/paas/v4",
    )

    with patch("langchain_openai.OpenAIEmbeddings") as mock_embeddings:
        result = create_embedding_function(settings)
        assert result is not None
        mock_embeddings.assert_called_once_with(
                model="text-embedding-3-small",
                api_key=SecretStr("sk-zai"),
                base_url="https://api.z.ai/api/paas/v4",
            )


def test_create_embedding_function_zai_missing_key():
        settings = _settings(
            embedding_provider="zai",
            zai_api_key="",
            zai_base_url="https://api.z.ai/api/paas/v4",
        )
        # Should fallback to local embeddings when ZAI API key is missing
        result = create_embedding_function(settings)
        assert result is not None
        from llm_client.rag.retrieval.local_embeddings import LocalSentenceTransformerEmbeddings
        assert isinstance(result, LocalSentenceTransformerEmbeddings)

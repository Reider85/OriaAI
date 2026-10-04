"""VectorStoreFactory — pluggable vector store creation (ADR-003).

Phase 2: write-capable stores (chroma default, pgvector optional) plus a
read-only retriever path. Embeddings are constructed from Settings.
"""

import logging
import os
from typing import Any

from llm_client.config import Settings

logger = logging.getLogger(__name__)


def _config_get(config: Any, key: str, default: Any = None) -> Any:
    """Read *key* from a dict config or an object attribute."""
    if config is None:
        return default
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


def create_embedding_function(settings: Settings | None = None) -> Any | None:
    """Build an embeddings instance for vector indexing/retrieval.

    Returns None when the provider is "none" or no API key is available —
    callers must handle a missing embedding function gracefully.
    """
    if settings is None:
        from llm_client.config import settings as default_settings

        settings = default_settings

    provider = (settings.embedding_provider or "none").lower()
    if provider == "none":
        logger.info("EMBEDDING_PROVIDER=none — embeddings disabled")
        return None
    elif provider == "openai":
        if not settings.openai_api_key:
            logger.warning("OPENAI_API_KEY empty — embeddings disabled")
            return None
        api_key = settings.openai_api_key
        base_url = None
    elif provider == "custom-openai":
        if not settings.custom_openai_api_key:
            logger.warning("CUSTOM_OPENAI_API_KEY empty — embeddings disabled")
            return None
        if not settings.custom_openai_base_url:
            logger.warning("CUSTOM_OPENAI_BASE_URL empty — embeddings disabled")
            return None
        api_key = settings.custom_openai_api_key
        base_url = settings.custom_openai_base_url
    elif provider == "zai":
        if not settings.zai_api_key:
            logger.warning("ZAI_API_KEY empty — embeddings disabled")
            return None
        api_key = settings.zai_api_key
        base_url = settings.zai_base_url
    else:
        logger.info("EMBEDDING_PROVIDER=%s — embeddings disabled", provider)
        return None

    try:
        from langchain_openai import OpenAIEmbeddings

        # Use provider-specific model if available, otherwise fallback to embedding_model
        if provider == "custom-openai":
            model = settings.custom_openai_model
        elif provider == "zai":
            model = settings.embedding_model  # ZAI uses embedding_model for embeddings
        else:
            model = settings.embedding_model

        return OpenAIEmbeddings(
            model=model,
            api_key=api_key,
            base_url=base_url,
        )
    except ImportError:
        logger.warning("langchain-openai not installed — embeddings disabled")
        return None


def create_vector_store(
    config: Any = None,
    *,
    embedding_function: Any = None,
    settings: Settings | None = None,
) -> Any | None:
    """Create a write-capable vector store (raw LangChain store object).

    Returns None when VECTOR_STORE_KIND=none, the backend is unknown, or the
    backend package is not installed.
    """
    if settings is None:
        from llm_client.config import settings as default_settings

        settings = default_settings

    vector_store_kind = (
        _config_get(config, "vector_store_kind", None) or settings.vector_store_kind or "none"
    ).lower()
    env_kind = os.getenv("VECTOR_STORE_KIND")
    if env_kind:
        vector_store_kind = env_kind.lower()

    if vector_store_kind == "none":
        logger.info("VECTOR_STORE_KIND=none — vector store disabled")
        return None

    if embedding_function is None:
        embedding_function = create_embedding_function(settings)

    if vector_store_kind == "chroma":
        return _create_chroma_store(config, embedding_function, settings)
    if vector_store_kind == "pgvector":
        return _create_pgvector_store(config, embedding_function, settings)

    logger.warning("Unknown VECTOR_STORE_KIND=%r — falling back to none", vector_store_kind)
    return None


def create_vector_retriever(
    config: Any = None,
    *,
    embedding_function: Any = None,
    settings: Settings | None = None,
) -> Any | None:
    """Create a LangChain-compatible vector retriever (read path)."""
    store = create_vector_store(
        config,
        embedding_function=embedding_function,
        settings=settings,
    )
    if store is None:
        return None

    search_type = _config_get(config, "vector_search_type", "mmr")
    top_k = _config_get(config, "vector_top_k", 20)
    fetch_k = _config_get(config, "vector_fetch_k", 40)
    lambda_mult = _config_get(config, "vector_lambda_mult", 0.5)

    try:
        if search_type == "mmr":
            return store.as_retriever(
                search_type="mmr",
                k=top_k,
                fetch_k=fetch_k,
                lambda_mult=lambda_mult,
            )
        return store.as_retriever(search_type="similarity", k=top_k)
    except Exception as exc:  # noqa: BLE001 — factory must not crash the pipeline
        logger.warning("Failed to build vector retriever from store: %s", exc)
        return None


def _create_chroma_store(
    config: Any,
    embedding_function: Any,
    settings: Settings,
) -> Any | None:
    try:
        import chromadb
        from langchain_chroma import Chroma
    except ImportError:
        logger.warning("chromadb/langchain-chroma not installed — pip install 'llm-client[vector]'")
        return None

    chroma_dir = _config_get(config, "chroma_dir", None) or settings.chroma_persist_dir
    client = chromadb.PersistentClient(path=chroma_dir)
    client.get_or_create_collection("documents")
    return Chroma(
        client=client,
        collection_name="documents",
        embedding_function=embedding_function,
    )


def _create_pgvector_store(
    config: Any,
    embedding_function: Any,
    settings: Settings,
) -> Any | None:
    try:
        from langchain_postgres import PGVector
    except ImportError:
        try:
            from langchain_community.vectorstores import PGVector
        except ImportError:
            logger.warning(
                "langchain-postgres/langchain-community not installed — "
                "pip install 'llm-client[vector]'"
            )
            return None

    database_url = _config_get(config, "database_url", None) or settings.database_url
    return PGVector(
        connection=database_url,
        embedding_function=embedding_function,
        collection_name="documents",
    )


def get_vector_writer(settings: Settings | None = None) -> Any | None:
    """Build an async callable that indexes a Document into the vector store.

    Returns None when no vector store/embeddings are configured — callers
    treat that as "vector leg disabled".
    """
    if settings is None:
        from llm_client.config import settings as default_settings

        settings = default_settings

    store = create_vector_store(settings=settings)
    if store is None:
        return None

    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError:
        try:
            from langchain.text_splitter import RecursiveCharacterTextSplitter
        except ImportError:
            logger.warning("langchain text splitter not available — vector writer disabled")
            return None

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)

    async def _index_document(document: Any) -> None:
        chunks = splitter.split_text(document.content)
        if not chunks:
            return
        metadatas = [
            {
                "document_id": document.id,
                "user_id": document.user_id,
                "chunk_index": i,
                "source_uri": document.source_uri,
                "source_type": document.source_type,
            }
            for i in range(len(chunks))
        ]
        ids = [f"{document.id}:{i}" for i in range(len(chunks))]
        if hasattr(store, "aadd_texts"):
            await store.aadd_texts(chunks, metadatas=metadatas, ids=ids)
        else:
            store.add_texts(chunks, metadatas=metadatas, ids=ids)

    return _index_document

"""VectorStoreFactory — pluggable vector store creation (ADR-003).

Phase 2: minimal implementation supporting in-memory fallback.
Phase 4: extends with Chroma, PGVector, Qdrant via entry_points.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def create_vector_retriever(
    config: Any = None,
    *,
    embedding_function: Any = None,
) -> Any | None:
    """Create a LangChain-compatible vector retriever.

    Args:
        config: RetrieverConfig (optional, for future use).
        embedding_function: Embeddings instance (optional).

    Returns:
        A LangChain retriever object, or None if no vector store
        is configured / available.
    """
    import os

    vector_store_kind = os.getenv("VECTOR_STORE_KIND", "none")

    if vector_store_kind == "none":
        logger.info("VECTOR_STORE_KIND=none — vector retrieval disabled")
        return None

    if vector_store_kind == "chroma":
        return _create_chroma_retriever(config, embedding_function)

    if vector_store_kind == "pgvector":
        return _create_pgvector_retriever(config, embedding_function)

    logger.warning("Unknown VECTOR_STORE_KIND=%r — falling back to none", vector_store_kind)
    return None


def _create_chroma_retriever(config: Any, embedding_function: Any) -> Any:
    """Create a Chroma retriever (requires chromadb + langchain-chroma)."""
    try:
        import chromadb
        from langchain_chroma import Chroma

        chroma_dir = (
            (config or {}).get("chroma_dir", "./chroma_db")
            if isinstance(config, dict)
            else "./chroma_db"
        )
        client = chromadb.PersistentClient(path=chroma_dir)
        client.get_or_create_collection("documents")
        vectordb = Chroma(
            client=client,
            collection_name="documents",
            embedding_function=embedding_function,
        )
        return vectordb.as_retriever()
    except ImportError:
        logger.warning(
            "chromadb/langchain-chroma not installed — pip install chromadb langchain-chroma"
        )
        return None


def _create_pgvector_retriever(config: Any, embedding_function: Any) -> Any:
    """Create a PGVector retriever (requires pgvector + langchain-community)."""
    try:
        from langchain_community.vectorstores import PGVector

        database_url = (config or {}).get("database_url", "") if isinstance(config, dict) else ""
        if not database_url:
            import os

            database_url = os.getenv("DATABASE_URL", "")

        vectordb = PGVector(
            connection_string=database_url,
            embedding_function=embedding_function,
            collection_name="documents",
        )
        return vectordb.as_retriever()
    except ImportError:
        logger.warning(
            "pgvector/langchain-community not installed — pip install pgvector langchain-community"
        )
        return None

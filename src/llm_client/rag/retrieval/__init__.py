"""Retrieval module for RAG pipeline."""

from .bm25_retriever import BM25Retriever, RetrievalError
from .fusion import rrf_fusion
from .hybrid_retriever import HybridRetriever
from .vector_store_factory import (
    create_embedding_function,
    create_vector_retriever,
    create_vector_store,
    get_vector_writer,
)

__all__ = [
    "BM25Retriever",
    "HybridRetriever",
    "RetrievalError",
    "create_embedding_function",
    "create_vector_retriever",
    "create_vector_store",
    "get_vector_writer",
    "rrf_fusion",
]

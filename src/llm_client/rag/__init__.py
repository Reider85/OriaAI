"""RAG (Retrieval-Augmented Generation) configuration and pipeline modules."""

from .config import RetrievalStrategy, RetrieverConfig
from .indexing import BM25IndexBuilder, Chunk, Document, index_document_with_hybrid
from .pipeline import RagPipeline, rerank_after_fusion
from .pool import close_shared_pool, get_shared_pool, resolve_pool
from .retrieval import BM25Retriever, HybridRetriever, RetrievalError, rrf_fusion

__all__ = [
    "BM25IndexBuilder",
    "BM25Retriever",
    "Chunk",
    "Document",
    "HybridRetriever",
    "RagPipeline",
    "RetrievalError",
    "RetrievalStrategy",
    "RetrieverConfig",
    "close_shared_pool",
    "get_shared_pool",
    "index_document_with_hybrid",
    "rerank_after_fusion",
    "resolve_pool",
    "rrf_fusion",
]
